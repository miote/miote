#!/usr/bin/env python3
"""Análisis rítmico/timbrico del panwewe (todo local).

NOTA: NO usa Demucs (pesos inaccesibles en el entorno). Aísla con HPSS de librosa
+ banda grave, que es una separación mucho más débil: el bajo sigue contaminando.
Uso: analiza.py audio.wav nombre
"""
import sys, json
import numpy as np, librosa, scipy.signal as ss

path, name = sys.argv[1], sys.argv[2]
BPM0 = float(sys.argv[3]) if len(sys.argv) > 3 else None  # fuerza el nivel de pulso (evita doble tempo)
SR = 22050
y, _ = librosa.load(path, sr=SR, mono=True)
dur = len(y) / SR
out = {"archivo": name, "duracion_s": round(dur, 1)}

# --- Aislamiento débil: componente percusiva + banda grave ---------------------
_, yp = librosa.effects.hpss(y, margin=3.0)
sos = ss.butter(4, [60, 400], btype="band", fs=SR, output="sos")
yl = ss.sosfiltfilt(sos, yp)            # percusivo, 60-400 Hz

HOP = 256  # 11.6 ms
S = np.abs(librosa.stft(yl, n_fft=2048, hop_length=HOP))
env = librosa.onset.onset_strength(S=librosa.amplitude_to_db(S, ref=np.max), sr=SR, hop_length=HOP)

# --- Tempo global y local ---------------------------------------------------------
tempo_g = float(np.atleast_1d(librosa.beat.tempo(onset_envelope=env, sr=SR, hop_length=HOP))[0])
out["tempo_global_bpm_(autocorr)"] = round(tempo_g, 1)

# --- Onsets ---------------------------------------------------------------------------
on_f = librosa.onset.onset_detect(onset_envelope=env, sr=SR, hop_length=HOP,
                                  backtrack=False, delta=0.05, wait=int(0.12 * SR / HOP))
t = librosa.frames_to_time(on_f, sr=SR, hop_length=HOP)
out["n_onsets"] = int(len(t))
ioi = np.diff(t)
out["ioi_mediana_ms"] = round(float(np.median(ioi)) * 1000, 1)

# --- Fuerza y timbre de cada golpe ---------------------------------------------------
def win(sig, tt, a=0.0, b=0.06):
    i0, i1 = int((tt + a) * SR), int((tt + b) * SR)
    return sig[i0:i1]

strength = np.array([np.max(np.abs(win(yl, x, 0.0, 0.05))) for x in t])      # pico banda grave
rms_l = np.array([np.sqrt(np.mean(win(yl, x, 0, 0.05) ** 2)) for x in t])

def centroide(sig, tt):
    w = win(sig, tt, 0.0, 0.05)
    if len(w) < 512:
        return np.nan
    return float(np.mean(librosa.feature.spectral_centroid(y=w, sr=SR, n_fft=1024,
                                                           hop_length=256, center=False)))
cent_p = np.array([centroide(yp, x) for x in t])   # percusivo, banda ancha
cent_l = np.array([centroide(yl, x) for x in t])   # percusivo, banda grave

# --- Rejilla de corcheas: beat tracking, cada pulso se divide en 2 ------------------
bt_tempo, beats = librosa.beat.beat_track(onset_envelope=env, sr=SR, hop_length=HOP,
                                          start_bpm=BPM0 or tempo_g, tightness=200, units="time")
beats = np.asarray(beats)
bpm_local = 60.0 / np.diff(beats)
out["pulso_bpm_local"] = {
    "mediana": round(float(np.median(bpm_local)), 1),
    "p10": round(float(np.percentile(bpm_local, 10)), 1),
    "p90": round(float(np.percentile(bpm_local, 90)), 1),
    "primer_cuarto": round(float(np.median(bpm_local[: len(bpm_local) // 4])), 1),
    "ultimo_cuarto": round(float(np.median(bpm_local[-len(bpm_local) // 4:])), 1),
}

# Posiciones en la rejilla (en unidades de corchea, 0 = pulso, 1 = "y")
half = (beats[:-1] + beats[1:]) / 2
grid_t = np.empty(2 * len(half)); grid_t[0::2] = beats[:-1]; grid_t[1::2] = half
pos = np.interp(t, grid_t, np.arange(len(grid_t)), left=np.nan, right=np.nan)  # posición fraccional
# posición fraccionaria dentro de la corchea
idx = np.round(pos)
desv = pos - idx                       # en corcheas; ±0.5 = mitad de corchea
ioi_grid = np.median(np.diff(grid_t))
out["desviacion_a_rejilla_ms_mediana_abs"] = round(float(np.nanmedian(np.abs(desv))) * ioi_grid * 1000, 1)

# ¿Golpes fuera de rejilla? (más de 0.25 corchea de la posición de corchea más cercana)
fuera = np.abs(desv) > 0.25
out["golpes_fuera_de_rejilla_(>1/4 corchea)"] = {"n": int(np.nansum(fuera)),
                                                 "pct": round(100 * float(np.nansum(fuera)) / np.sum(~np.isnan(desv)), 1)}

# Asignar a cada casilla de la rejilla el golpe más fuerte cercano (<0.25 corchea)
ncas = len(grid_t)
cas_str = np.full(ncas, np.nan); cas_cent = np.full(ncas, np.nan)
for k, (i, d, s, c) in enumerate(zip(idx, desv, strength, cent_p)):
    if np.isnan(i) or abs(d) > 0.25:
        continue
    i = int(i)
    if np.isnan(cas_str[i]) or s > cas_str[i]:
        cas_str[i], cas_cent[i] = s, c

hit = ~np.isnan(cas_str)
out["casillas_total"] = int(ncas)
out["cobertura_corcheas_con_golpe_pct"] = round(100 * float(hit.mean()), 1)
out["cobertura_en_pulso_pct"] = round(100 * float(hit[0::2].mean()), 1)
out["cobertura_en_y_pct"] = round(100 * float(hit[1::2].mean()), 1)

# Fuerte-suave: por cada pulso, comparar golpe del pulso vs su "y" siguiente
P, Y = cas_str[0::2][: len(cas_str[1::2])], cas_str[1::2][: len(cas_str[0::2])]
ok = ~np.isnan(P[: len(Y)]) & ~np.isnan(Y)
n = min(len(P), len(Y))
P, Y = P[:n], Y[:n]; ok = ~np.isnan(P) & ~np.isnan(Y)
ratio = P[ok] / Y[ok]
out["pulso_mas_fuerte_que_y_pct"] = round(100 * float(np.mean(ratio > 1)), 1)
out["razon_pulso_sobre_y_mediana"] = round(float(np.median(ratio)), 2)
out["razon_pulso_sobre_y_p25_p75"] = [round(float(np.percentile(ratio, 25)), 2), round(float(np.percentile(ratio, 75)), 2)]
# Prueba de signo (binomial, sin scipy.stats extra): p-valor bilateral aprox.
from scipy.stats import binomtest
k = int(np.sum(ratio > 1)); nn = int(ok.sum())
out["prueba_signo_p"] = float(binomtest(k, nn, 0.5).pvalue)

# Comparación con el "y" ANTERIOR (control: ¿la alternancia es f-s o solo ruido?)
Yprev = cas_str[1::2][: n - 1]; Pnext = cas_str[0::2][1: n]
ok2 = ~np.isnan(Yprev) & ~np.isnan(Pnext)
out["control_y_vs_pulso_siguiente_pct_pulso_mayor"] = round(100 * float(np.mean(Pnext[ok2] > Yprev[ok2])), 1)

# --- Periodicidad: autocorrelación de la fuerza por casilla (en corcheas) -----------
x = np.nan_to_num(cas_str, nan=0.0)
x = x - x.mean()
ac = np.correlate(x, x, "full")[len(x) - 1:]
ac = ac / ac[0]
lags = np.arange(1, 49)
top = sorted(((int(l), round(float(ac[l]), 3)) for l in lags), key=lambda z: -z[1])[:8]
out["autocorr_fuerza_top_lags_corcheas"] = top
out["autocorr_lags_1_a_16"] = [round(float(ac[l]), 2) for l in range(1, 17)]

# Patrón de ausencias: ¿dónde faltan golpes? histograma módulo m para m=2..16
falt = (~hit).astype(float)
mods = {}
for m in (2, 3, 4, 6, 8, 12, 16):
    cols = [falt[i::m].mean() for i in range(m)]
    mods[m] = round(float(max(cols) - min(cols)), 3)   # rango de tasa de ausencia entre columnas
out["ausencia_rango_por_modulo"] = mods
out["tasa_ausencia_global"] = round(float(falt.mean()), 3)

# Fuerza media por posición módulo 4/8 corcheas (¿acento de compás?)
for m in (4, 6, 8):
    out[f"fuerza_media_relativa_mod{m}"] = [round(float(np.nanmean(cas_str[i::m]) / np.nanmean(cas_str)), 2) for i in range(m)]

# --- Timbre: centroide ---------------------------------------------------------------------
c = cent_p[~np.isnan(cent_p)]; cl = cent_l[~np.isnan(cent_l)]
out["centroide_perc_hz"] = {"mediana": round(float(np.median(c))), "p10": round(float(np.percentile(c, 10))),
                            "p90": round(float(np.percentile(c, 90)))}
out["centroide_banda_grave_hz"] = {"mediana": round(float(np.median(cl))), "p10": round(float(np.percentile(cl, 10))),
                                   "p90": round(float(np.percentile(cl, 90)))}
# bimodalidad: coeficiente de bimodalidad de Sarle (>0.555 sugiere bimodal) y gap de 2-means
from scipy.stats import skew, kurtosis
def sarle(v):
    n = len(v); g = skew(v); k = kurtosis(v)  # exceso
    return float((g ** 2 + 1) / (k + 3 * (n - 1) ** 2 / ((n - 2) * (n - 3))))
out["bimodalidad_sarle_(>0.555)_centroide_perc"] = round(sarle(c), 3)
# 2-means 1D + separación (d') y comparación con el confundente "fuerza"
def dos_means(v):
    a, b = np.percentile(v, 25), np.percentile(v, 75)
    for _ in range(50):
        lab = np.abs(v - a) < np.abs(v - b)
        a, b = v[lab].mean(), v[~lab].mean()
    lab = np.abs(v - a) < np.abs(v - b)
    dprime = abs(a - b) / np.sqrt((v[lab].var() + v[~lab].var()) / 2)
    return a, b, float(lab.mean()), float(dprime)
a, b, frac, dp = dos_means(c)
out["2means_centroide_perc"] = {"c1_hz": round(a), "c2_hz": round(b), "frac_c1": round(frac, 2), "dprime": round(dp, 2)}
# Correlación centroide-fuerza y centroide pulso vs y
m = ~np.isnan(cas_cent) & hit
out["corr_centroide_vs_fuerza_(spearman)"] = round(float(__import__("scipy.stats").stats.spearmanr(cas_cent[m], cas_str[m])[0]), 3)
cp, cy = cas_cent[0::2], cas_cent[1::2]
out["centroide_mediano_en_pulso_hz"] = round(float(np.nanmedian(cp)))
out["centroide_mediano_en_y_hz"] = round(float(np.nanmedian(cy)))

# --- Golpes extra: casillas de 1/4 de corchea (semicorcheas) con energía ------------------------
# fracción de onsets cuya posición cae a ~0.5 corchea (±0.15) de una casilla
semi = np.abs(np.abs(desv) - 0.5) < 0.15
out["onsets_en_posicion_semicorchea_(+-0.15)"] = {"n": int(np.nansum(semi)),
    "pct": round(100 * float(np.nansum(semi)) / np.sum(~np.isnan(desv)), 1)}
# Perfil: dónde ocurren los golpes fuera de rejilla (casilla mod 8)
if np.nansum(fuera) > 0:
    out["fuera_de_rejilla_por_casilla_mod8"] = np.bincount((idx[fuera & ~np.isnan(idx)].astype(int)) % 8, minlength=8).tolist()

# guardar detalle
np.savez(f"{name}_detalle.npz", t=t, strength=strength, cent_p=cent_p, cas_str=cas_str, cas_cent=cas_cent,
         beats=beats, bpm_local=bpm_local)
print(json.dumps(out, indent=2, ensure_ascii=False))
json.dump(out, open(f"{name}_resultado.json", "w"), indent=2, ensure_ascii=False)
