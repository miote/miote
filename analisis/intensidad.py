#!/usr/bin/env python3
"""Intensidad (suave/duro) y espaciado de los golpes. Lee *_detalle.npz de analiza.py."""
import sys, numpy as np
from scipy.stats import skew, kurtosis

def sarle(v):
    n = len(v); return (skew(v)**2 + 1) / (kurtosis(v) + 3*(n-1)**2/((n-2)*(n-3)))

def dos_medias(v):
    a, b = np.percentile(v, 20), np.percentile(v, 80)
    for _ in range(100):
        l = np.abs(v-a) < np.abs(v-b); a, b = v[l].mean(), v[~l].mean()
    l = np.abs(v-a) < np.abs(v-b)
    return a, b, (a+b)/2, abs(a-b)/np.sqrt((v[l].var()+v[~l].var())/2)

def hist(v, lo, hi, n, ancho=40):
    h, e = np.histogram(v, bins=n, range=(lo, hi)); m = h.max()
    for c, x in zip(h, e): print(f"  {x:6.1f} | {'#'*int(ancho*c/m):<{ancho}} {c}")

for nombre in sys.argv[1:]:
    d = np.load(f"{nombre}_detalle.npz")
    t, s, cas, beats = d["t"], d["strength"], d["cas_str"], d["beats"]
    print(f"\n===== {nombre} =====")
    db = 20*np.log10(s/np.max(s))
    print(f"Intensidad de {len(db)} golpes (dB re máximo). Sarle={sarle(db):.3f} (>0.555 = bimodal)")
    hist(db, np.percentile(db, 0.5), 0, 16)
    a, b, umbral, dp = dos_medias(db)
    print(f"2-medias: suave={a:.1f} dB, duro={b:.1f} dB, umbral={umbral:.1f} dB, d'={dp:.2f}, separación={b-a:.1f} dB")
    print(f"  fracción duros: {np.mean(db>umbral):.2f}")
    # Secuencia por casilla: 0 ausente, 1 suave, 2 duro (mismo umbral)
    c = np.full(len(cas), 0)
    ok = ~np.isnan(cas)
    c[ok] = np.where(20*np.log10(cas[ok]/np.max(s)) > umbral, 2, 1)
    for nm, sl in (("pulso", c[0::2]), ("y", c[1::2])):
        print(f"  casillas en {nm:5s}: ausente {np.mean(sl==0):.2f}  suave {np.mean(sl==1):.2f}  duro {np.mean(sl==2):.2f}")
    # Transiciones y rachas de duros en pulso
    T = np.zeros((3, 3), int)
    for x, y in zip(c[:-1], c[1:]): T[x, y] += 1
    print("  transiciones casilla->siguiente (filas: aus/suave/duro):\n", T)
    Tn = T / T.sum(1, keepdims=True)
    print("  P(siguiente|actual):\n", np.round(Tn, 2))
    # ¿Los 'y' duros (acentos fuera de pulso) se agrupan?
    yd = (c[1::2] == 2).astype(int)
    print(f"  'y' duros: {yd.sum()} de {len(yd)}; P(y duro | pulso previo suave)="
          f"{np.mean(yd[c[0::2][:len(yd)]==1]) if np.any(c[0::2][:len(yd)]==1) else float('nan'):.2f}")
    pd_ = (c[0::2] == 1).astype(int)
    print(f"  pulsos suaves: {pd_.sum()} de {len(pd_)}")
    # Espaciado: IOI en unidades de corchea local
    ioi = np.diff(t); mid = (t[:-1]+t[1:])/2
    corch = np.interp(mid, beats[:-1], np.diff(beats)/2, left=np.nan, right=np.nan)
    r = ioi/corch; r = r[~np.isnan(r)]
    print(f"Espaciado entre golpes consecutivos (en corcheas locales), n={len(r)}:")
    hist(np.clip(r, 0, 4), 0, 4, 16)
    print(f"  ≈1 corchea (0.75–1.25): {np.mean((r>.75)&(r<1.25)):.2f} | <0.75: {np.mean(r<=.75):.2f} | 1.75–2.25: {np.mean((r>1.75)&(r<2.25)):.2f} | >2.25: {np.mean(r>=2.25):.2f}")
