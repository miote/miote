//! panwewe-letra: alinea una letra al patrón base del panwewe.
//!
//! Base (medida en dos grabaciones, hipótesis confirmada a oído por el usuario):
//! un golpe por corchea; fuerte (X) en el pulso, suave (x) en el "y".
//! La herramienta NO inventa el toque del tambor: solo coloca las sílabas de la
//! letra sobre esa base, cuidando que las sílabas tónicas caigan en los golpes fuertes.
//!
//! Lo medido (ver analisis/): la intensidad del golpe es continua, no de dos niveles;
//! el pulso es fuerte en ~80-87% de los casos y el "y" es fuerte en ~40%, así que
//! X/x es la tendencia y no cada golpe. Hay golpes débiles extra a mitad de corchea
//! (24-34% de las corcheas) cuyo origen (tambor o voz) no se pudo determinar, por
//! eso no se modelan. El tempo de "La Pequeña Red" sube de ~83 a ~91 BPM: de ahí `--bpm-fin`.
//!
//! Uso:
//!   panwewe-letra [--bpm 81] [--bpm-fin 90] [--tiempo] [--pulsos 4] [--nah] [--mono] [archivo]
//!   --bpm-fin  el tempo cambia linealmente de --bpm a --bpm-fin a lo largo de toda la letra
//!   --tiempo   muestra en segundos dónde empieza cada fila (se activa solo con --bpm-fin)
//!   (sin archivo, lee de la entrada estándar; una línea de letra por línea)

use std::env;
use std::fs;
use std::io::{self, Read};

#[derive(Clone)]
struct Tok {
    s: String,
    vocal: bool,
}

fn es_fuerte(c: char) -> bool {
    matches!(c, 'a' | 'e' | 'o' | 'á' | 'é' | 'í' | 'ó' | 'ú')
}
fn es_debil(c: char) -> bool {
    matches!(c, 'i' | 'u' | 'ü')
}
fn tiene_tilde(c: char) -> bool {
    matches!(c, 'á' | 'é' | 'í' | 'ó' | 'ú')
}
fn primero(t: &Tok) -> char {
    t.s.chars().next().unwrap()
}

fn tokenizar(pal: &[char]) -> Vec<Tok> {
    let n = pal.len();
    let mut toks = Vec::new();
    let mut i = 0;
    while i < n {
        let c = pal[i];
        let sig = if i + 1 < n { Some(pal[i + 1]) } else { None };
        let prev = if i > 0 { Some(pal[i - 1]) } else { None };
        if let Some(s2) = sig {
            let par: String = [c, s2].iter().collect();
            if matches!(par.as_str(), "ch" | "ll" | "rr" | "tz" | "tl") {
                toks.push(Tok { s: par, vocal: false });
                i += 2;
                continue;
            }
        }
        if c == 'u' {
            let muda = prev == Some('q')
                || (prev == Some('g') && matches!(sig, Some('e') | Some('i') | Some('é') | Some('í')));
            if muda {
                toks.push(Tok { s: "u".into(), vocal: false });
                i += 1;
                continue;
            }
        }
        if c == 'y' {
            toks.push(Tok { s: "y".into(), vocal: i == n - 1 });
            i += 1;
            continue;
        }
        toks.push(Tok { s: c.to_string(), vocal: es_fuerte(c) || es_debil(c) });
        i += 1;
    }
    toks
}

fn inseparable(a: &Tok, b: &Tok) -> bool {
    let par = format!("{}{}", a.s, b.s);
    matches!(
        par.as_str(),
        "bl" | "br" | "cl" | "cr" | "dr" | "fl" | "fr" | "gl" | "gr" | "pl" | "pr" | "tr" | "kl" | "kr"
    )
}

/// Devuelve sílabas como rangos de tokens.
fn silabear(toks: &[Tok]) -> Vec<(usize, usize)> {
    let mut nuc: Vec<(usize, usize)> = Vec::new();
    let mut i = 0;
    while i < toks.len() {
        if toks[i].vocal {
            let ini = i;
            let mut j = i + 1;
            while j < toks.len() && toks[j].vocal {
                let hiato = es_fuerte(primero(&toks[j - 1])) && es_fuerte(primero(&toks[j]));
                if hiato {
                    break;
                }
                j += 1;
            }
            nuc.push((ini, j));
            i = j;
        } else {
            i += 1;
        }
    }
    if nuc.is_empty() {
        return vec![(0, toks.len())];
    }
    let mut cortes = Vec::new();
    for k in 0..nuc.len() - 1 {
        let ini = nuc[k].1;
        let fin = nuc[k + 1].0;
        let n = fin - ini;
        let pos = match n {
            0 | 1 => ini,
            _ => {
                if inseparable(&toks[fin - 2], &toks[fin - 1]) {
                    fin - 2
                } else {
                    fin - 1
                }
            }
        };
        cortes.push(pos);
    }
    let mut rangos = Vec::new();
    let mut desde = 0;
    for c in cortes {
        rangos.push((desde, c));
        desde = c;
    }
    rangos.push((desde, toks.len()));
    rangos
}

/// Sílabas de una palabra con su marca de tónica.
fn analizar(palabra: &str, nah: bool, mono_fuerte: bool) -> Vec<(String, bool)> {
    let chars: Vec<char> = palabra.chars().collect();
    let toks = tokenizar(&chars);
    let rangos = silabear(&toks);
    let n = rangos.len();
    let sils: Vec<String> = rangos
        .iter()
        .map(|&(a, b)| toks[a..b].iter().map(|t| t.s.as_str()).collect::<String>())
        .collect();
    let con_tilde = rangos
        .iter()
        .position(|&(a, b)| toks[a..b].iter().any(|t| t.s.chars().any(tiene_tilde)));
    let idx = if let Some(i) = con_tilde {
        Some(i)
    } else if n == 1 {
        if mono_fuerte { Some(0) } else { None }
    } else {
        let ult = *chars.last().unwrap();
        if nah || es_fuerte(ult) || es_debil(ult) || ult == 'n' || ult == 's' {
            Some(n - 2)
        } else {
            Some(n - 1)
        }
    };
    sils.into_iter()
        .enumerate()
        .map(|(i, s)| (s, Some(i) == idx))
        .collect()
}

type Casilla = Option<(String, bool)>;

/// Una línea ya colocada sobre la rejilla de corcheas.
struct Linea {
    vista: String,
    slots: Vec<Casilla>,
    pausas: usize,
}

/// Tempo: fijo, o lineal de `ini` a `fin` sobre `total` corcheas de toda la letra.
struct Reloj {
    ini: f32,
    fin: Option<f32>,
    total: usize,
}

impl Reloj {
    /// Duración en segundos de la corchea global `k`.
    fn corchea(&self, k: usize) -> f32 {
        let bpm = match self.fin {
            Some(f) if self.total > 1 => self.ini + (f - self.ini) * k as f32 / (self.total - 1) as f32,
            _ => self.ini,
        };
        30.0 / bpm
    }
    /// Segundos entre las corcheas globales `desde` (incluida) y `hasta` (excluida).
    fn tiempo(&self, desde: usize, hasta: usize) -> f32 {
        (desde..hasta).fold(0.0, |t, k| t + self.corchea(k))
    }
}

fn colocar(linea: &str, nah: bool, mono: bool) -> Option<Linea> {
    let mut sils: Vec<(String, bool)> = Vec::new();
    let mut vista: Vec<String> = Vec::new();
    for w in linea.to_lowercase().split_whitespace() {
        let limpio: String = w.chars().filter(|c| c.is_alphabetic()).collect();
        if limpio.is_empty() {
            continue;
        }
        let a = analizar(&limpio, nah, mono);
        vista.push(
            a.iter()
                .map(|(s, t)| if *t { s.to_uppercase() } else { s.clone() })
                .collect::<Vec<_>>()
                .join("-"),
        );
        sils.extend(a);
    }
    if sils.is_empty() {
        return None;
    }
    // Anacrusa: que la primera tónica caiga en un pulso (casilla par).
    let p = sils.iter().position(|(_, t)| *t).unwrap_or(0);
    let mut slots: Vec<Casilla> = Vec::new();
    if p % 2 == 1 {
        slots.push(None);
    }
    let mut pausas = slots.len();
    for (s, t) in sils {
        if t && slots.len() % 2 == 1 {
            slots.push(None);
            pausas += 1;
        }
        slots.push(Some((s, t)));
    }
    Some(Linea { vista: vista.join(" "), slots, pausas })
}

/// `k0`: índice global de la primera corchea de la línea.
fn imprimir(num: usize, l: &Linea, k0: usize, pg: usize, reloj: &Reloj, mostrar_tiempo: bool) {
    let slots = &l.slots;
    let w = slots
        .iter()
        .flatten()
        .map(|(s, _)| s.chars().count())
        .max()
        .unwrap_or(2)
        .max(3)
        + 1;
    let grupo = pg * 2;
    println!("Línea {num}: {}", l.vista);
    let mut i = 0;
    while i < slots.len() {
        let fin = (i + grupo).min(slots.len());
        let (mut r1, mut r2, mut r3) = (String::from("Pulso  "), String::from("Tambor "), String::from("Voz    "));
        for j in i..fin {
            let etiqueta = if j % 2 == 0 { ((j / 2) % pg + 1).to_string() } else { "y".to_string() };
            let golpe = if j % 2 == 0 { "X" } else { "x" };
            let voz = match &slots[j] {
                Some((s, _)) => s.clone(),
                None => "·".to_string(),
            };
            r1.push_str(&format!("{etiqueta:<w$}"));
            r2.push_str(&format!("{golpe:<w$}"));
            r3.push_str(&format!("{voz:<w$}"));
        }
        if mostrar_tiempo {
            r1.push_str(&format!(" [{:.1} s]", reloj.tiempo(0, k0 + i)));
        }
        println!("{r1}\n{r2}\n{r3}");
        i = fin;
    }
    if reloj.fin.is_some() {
        let seg = reloj.tiempo(k0, k0 + slots.len());
        println!("({} corcheas, {} pausas añadidas, ~{:.1} s)\n", slots.len(), l.pausas, seg);
    } else {
        let seg = slots.len() as f32 * 60.0 / reloj.ini / 2.0;
        println!("({} corcheas, {} pausas añadidas, ~{:.1} s a {} BPM)\n", slots.len(), l.pausas, seg, reloj.ini);
    }
}

fn main() {
    let args: Vec<String> = env::args().skip(1).collect();
    let (mut bpm, mut pg, mut nah, mut mono) = (81.0f32, 4usize, false, false);
    let (mut bpm_fin, mut tiempo): (Option<f32>, bool) = (None, false);
    let mut archivo: Option<String> = None;
    let mut i = 0;
    while i < args.len() {
        match args[i].as_str() {
            "--bpm" => {
                i += 1;
                bpm = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(bpm);
            }
            "--bpm-fin" => {
                i += 1;
                bpm_fin = args.get(i).and_then(|s| s.parse().ok());
            }
            "--pulsos" => {
                i += 1;
                pg = args.get(i).and_then(|s| s.parse().ok()).unwrap_or(pg).max(1);
            }
            "--tiempo" => tiempo = true,
            "--nah" => nah = true,
            "--mono" => mono = true,
            otro => archivo = Some(otro.to_string()),
        }
        i += 1;
    }
    bpm = bpm.max(1.0);
    bpm_fin = bpm_fin.map(|f| f.max(1.0));
    let texto = match archivo {
        Some(p) => fs::read_to_string(&p).expect("no se pudo leer el archivo"),
        None => {
            let mut s = String::new();
            io::stdin().read_to_string(&mut s).unwrap();
            s
        }
    };
    // Primero se colocan todas las líneas: el tempo creciente necesita el total de corcheas.
    let lineas: Vec<(usize, Linea)> = texto
        .lines()
        .enumerate()
        .filter_map(|(n, l)| colocar(l, nah, mono).map(|x| (n + 1, x)))
        .collect();
    let total: usize = lineas.iter().map(|(_, l)| l.slots.len()).sum();
    let reloj = Reloj { ini: bpm, fin: bpm_fin, total };
    match bpm_fin {
        Some(f) => println!(
            "Base: un golpe por corchea, X en el pulso y x en el \"y\". Tempo {bpm} → {f} BPM (lineal sobre {total} corcheas).\n"
        ),
        None => println!("Base: un golpe por corchea, X en el pulso y x en el \"y\". Tempo {bpm} BPM.\n"),
    }
    let mut k0 = 0;
    for (num, l) in &lineas {
        imprimir(*num, l, k0, pg, &reloj, tiempo || bpm_fin.is_some());
        k0 += l.slots.len();
    }
}
