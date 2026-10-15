#!/usr/bin/env python3
"""Generador de lecciones de inglés (Windows) · v3 · EL AUDIO MANDA

Flujo nuevo (sin cortar ni editar nada):
  1. Se crea `texto-para-elevenlabs.txt` (pausas incluidas como <break>).
  2. Pegas ese texto en ElevenLabs y guardas el audio como audio\\<leccion>\\narracion.mp3
  3. El programa MIDE el audio real (silencios y frases) y construye el vídeo
     alrededor de la voz: cada frase, cada pausa y cada cuenta atrás caen donde
     la voz real los pone.
Si todavía no hay audio, hace un vídeo de prueba con tiempos estimados.
"""
import argparse, json, math, re, shutil, subprocess, sys
from pathlib import Path
from PIL import Image, ImageDraw, ImageFont, ImageOps

ROOT = Path(__file__).resolve().parent
AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac")
COL = {"amarillo": "fbbf24", "blanco": "f8fafc", "gris": "94a3b8", "verde": "4ade80",
       "rojo": "f87171", "azul": "38bdf8", "fondo": "0f172a", "oscuro": "111827",
       "claro": "cbd5e1", "rosa": "f472b6", "morado": "a78bfa"}
BG = "#" + COL["fondo"]
SPK_COLORS = [COL["azul"], COL["rosa"], COL["verde"], COL["morado"]]
W, H = 1920, 1080

# ---------------------------------------------------------------- utilidades
def bgr(hexcolor):
    h = hexcolor.lstrip("#")
    return f"&H00{h[4:6]}{h[2:4]}{h[0:2]}&"

def ass_time(sec):
    cs = max(0, int(round(sec * 100)))
    h, cs = divmod(cs, 360000); m, cs = divmod(cs, 6000); s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"

def clock(sec):
    sec = max(0, sec); return f"{int(sec // 60)}:{sec % 60:04.1f}"

def esc(text):
    return str(text).replace("{", "(").replace("}", ")").replace("\\", "/").replace("\n", r"\N").strip()

def run(cmd, cwd=None):
    p = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace", cwd=str(cwd or ROOT))
    if p.returncode: raise RuntimeError((p.stderr or "")[-2500:] or "Error ejecutando: " + cmd[0])
    return p.stdout.strip()

def font(size):
    for p in ("C:/Windows/Fonts/arialbd.ttf", "C:/Windows/Fonts/arial.ttf",
              "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf"):
        if Path(p).exists(): return ImageFont.truetype(p, size)
    return ImageFont.load_default()

_FC = {}
def tw(text, size):
    """Ancho aproximado del texto en píxeles (para dibujar cajas a su medida)."""
    if size not in _FC: _FC[size] = font(size)
    try: return _FC[size].getlength(text)
    except Exception: return len(text) * size * 0.6

def rr(x, y, w, h, r):
    """Rectángulo redondeado como dibujo ASS."""
    r = max(0, min(r, w / 2, h / 2)); k = 0.5523 * r
    f = lambda v: f"{v:.0f}"
    return (f"m {f(x+r)} {f(y)} l {f(x+w-r)} {f(y)} b {f(x+w-r+k)} {f(y)} {f(x+w)} {f(y+r-k)} {f(x+w)} {f(y+r)} "
            f"l {f(x+w)} {f(y+h-r)} b {f(x+w)} {f(y+h-r+k)} {f(x+w-r+k)} {f(y+h)} {f(x+w-r)} {f(y+h)} "
            f"l {f(x+r)} {f(y+h)} b {f(x+r-k)} {f(y+h)} {f(x)} {f(y+h-r+k)} {f(x)} {f(y+h-r)} "
            f"l {f(x)} {f(y+r)} b {f(x)} {f(y+r-k)} {f(x+r-k)} {f(y)} {f(x+r)} {f(y)}")

def sentences(text):
    s = [x.strip() for x in re.split(r"(?<=[.!?…])\s+|(?<=[.!?…][»”\"])\s+", " ".join(str(text).split())) if x.strip()]
    return s or [" ".join(str(text).split())]

def weights(words):
    return [max(2, len(re.sub(r"\W", "", w))) for w in words]

def karaoke_tags(text, total_sec, lead=0.25):
    """Relleno palabra por palabra repartido en total_sec (modo estimado)."""
    words = str(text).split()
    if not words: return ""
    wt = weights(words); avail = max(0.3, total_sec - lead); tot = sum(wt)
    out = [r"{\k%d}" % int(lead * 100)] if lead > 0 else []
    for i, (w, x) in enumerate(zip(words, wt)):
        out.append(r"{\kf%d}%s%s" % (max(1, int(round(avail * x / tot * 100))), esc(w), " " if i < len(words) - 1 else ""))
    return "".join(out)

def karaoke_parts(parts, t0):
    """Relleno palabra por palabra siguiendo el tiempo REAL de cada frase del audio."""
    out, cur = [], 0
    for pi, (ps, pe, txt) in enumerate(parts):
        words = txt.split()
        if not words: continue
        gap = int(round((ps - t0) * 100)) - cur
        if gap > 0: out.append(r"{\k%d}" % gap); cur += gap
        wt = weights(words); tot = sum(wt); acc = 0
        for i, (w, x) in enumerate(zip(words, wt)):
            acc += x
            tgt = int(round((ps - t0 + (pe - ps) * acc / tot) * 100))
            k = max(1, tgt - cur); cur += k
            last = pi == len(parts) - 1 and i == len(words) - 1
            out.append(r"{\kf%d}%s%s" % (k, esc(w), "" if last else " "))
    return "".join(out)

def karaoke(text, a, lead):
    if a.get("parts"): return karaoke_parts(a["parts"], a["s"])
    return karaoke_tags(text, a["e"] - a["s"], lead)

def chunk_text(text, max_words=16):
    sents = sentences(text)
    parts = []
    for s in sents:
        if len(s.split()) > 24: parts.extend(re.split(r"(?<=,)\s+", s))
        else: parts.append(s)
    chunks, cur = [], ""
    for p in parts:
        if cur and len((cur + " " + p).split()) > max_words: chunks.append(cur); cur = p
        else: cur = (cur + " " + p).strip()
    if cur: chunks.append(cur)
    return chunks

# ---------------------------------------------------------------- línea de tiempo + imagen
class Builder:
    def __init__(self, lesson, times=None, audio_dur=0.0):
        self.l = lesson
        self.ritmo = float(lesson.get("ritmo_voz", 2.4))
        self.ritmo_en = float(lesson.get("ritmo_ingles", 1.5))
        self.times = times; self.audio_dur = audio_dur
        self.t = 0.0
        self.ev = []; self.board = []
        self.atoms = []; self.used = []; self.lines = []
        self.voz = []; self.chapters = []; self.scene_marks = []
        self.spk = {}

    # ---- eventos
    def add(self, s, e, style, text, layer=1, board=False, sub=False):
        ev = {"s": s, "e": e, "style": style, "text": text, "layer": layer, "sub": sub}
        self.ev.append(ev)
        if board: self.board.append(ev)
        return ev

    def close_board(self, t):
        for e in self.board:
            if e["e"] is None: e["e"] = t
        self.board = []

    def shape(self, s, e, d, col, alpha=0, bord=0, bcol=None, balpha=0, layer=0, fad=None, board=False, pos=(0, 0), extra=""):
        t = r"{\an7\pos(%d,%d)\bord%s\shad0\1c%s\1a&H%02X&" % (pos[0], pos[1], bord, bgr(col), alpha)
        if bord: t += r"\3c%s\3a&H%02X&" % (bgr(bcol or col), balpha)
        if fad: t += r"\fad(%d,%d)" % fad
        return self.add(s, e, "Forma", t + extra + r"\p1}" + d, layer=layer, board=board)

    def pill(self, s, e, cx, cy, text, size, bg, fg, align="c", pad=28, bgalpha=0, layer=1, board=False, fad=(200, 0), strike=False):
        w = tw(text, size) + 2 * pad; h = int(size * 1.6)
        x = cx - w / 2 if align == "c" else cx if align == "l" else cx - w
        a = self.shape(s, e, rr(x, cy - h / 2, w, h, h / 2), bg, bgalpha, layer=layer, fad=fad, board=board)
        b = self.add(s, e, "Fijo", r"{\an5\pos(%d,%d)\fs%d\1c%s\bord0\shad0\fad(%d,%d)}%s" % (x + w / 2, cy + size * 0.04, size, bgr(fg), fad[0], fad[1], esc(text)), layer=layer + 1, board=board)
        return [a, b]

    def badge(self, s, e, label, color):
        self.pill(s, e, 1800, 75, label, 36, color, COL["oscuro"], align="r", fad=(150, 100), layer=4)

    def spk_color(self, name):
        if name not in self.spk: self.spk[name] = SPK_COLORS[len(self.spk) % len(SPK_COLORS)]
        return self.spk[name]

    # ---- tiempos
    def slot(self, kind, text, exp, en=False):
        i = len(self.atoms); self.atoms.append({"kind": kind, "text": text, "exp": exp, "en": en})
        if self.times is not None and i < len(self.times): a = dict(self.times[i])
        else: a = {"s": self.t, "e": self.t + exp, "parts": None}
        self.t = a["e"]; self.used.append(a)
        return a

    def dur_voz(self, text): return max(1.0, len(str(text).split()) / self.ritmo)
    def dur_en(self, text, lento=False):
        n = len(str(text).split()); d = max(1.4, n / self.ritmo_en + 0.5)
        return d * (1.35 if lento else 1.0)

    def size_for(self, text, base):
        n = len(text)
        return base if n <= 22 else int(base * 0.82) if n <= 34 else int(base * 0.66) if n <= 48 else int(base * 0.52)

    # ---- elementos visuales
    def tablero(self, items, t):
        self.close_board(t)
        sizes = {"grande": 104, "medio": 70, "nota": 56, "bueno": 70, "malo": 70}
        colors = {"grande": COL["blanco"], "medio": COL["claro"], "nota": COL["amarillo"], "bueno": COL["verde"], "malo": COL["rojo"]}
        heights = [int(sizes.get(i.get("e", "medio"), 70) * 1.45) for i in items]
        y = max(200, 470 - sum(heights) // 2)
        for it, h in zip(items, heights):
            st = it.get("e", "medio"); sz = self.size_for(it["t"], sizes.get(st, 70)); cy = y + h // 2
            if st in ("bueno", "malo"):
                self.pill(t, None, 330, cy, "BIEN" if st == "bueno" else "MAL", 34, colors[st], COL["oscuro"], board=True, fad=(250, 0))
                extra = r"\s1" if st == "malo" else ""
                self.add(t, None, "Fijo", r"{\an5\pos(1010,%d)\fs%d\1c%s%s\fad(250,0)}%s" % (cy, sz, bgr(colors[st]), extra, esc(it["t"])), layer=3, board=True)
            elif st == "nota":
                self.pill(t, None, 960, cy, it["t"], sz, COL["amarillo"], COL["amarillo"], bgalpha=0xD8, board=True, fad=(250, 0), layer=1)
                # el texto de la nota sale en amarillo sobre la cápsula casi transparente
            else:
                self.add(t, None, "Fijo", r"{\an5\pos(960,%d)\fs%d\1c%s\fad(250,0)}%s" % (cy, sz, bgr(colors.get(st, COL["blanco"])), esc(it["t"])), layer=3, board=True)
            y += h

    def frase(self, p, a, tarde=False):
        """Frase en inglés: karaoke al ritmo de la voz + traducción + pronunciación."""
        s, e = a["s"], a["e"]
        self.close_board(s)
        en = p["en"]; sz = self.size_for(en, 118)
        quien = p.get("quien")
        if quien:
            self.pill(s, None, 960, 215, quien.upper(), 44, self.spk_color(quien), COL["oscuro"], board=True, fad=(200, 0))
        self.add(s, None, "Karaoke", r"{\an5\pos(960,%d)\fs%d\fad(200,0)}%s" % (355 if quien else 335, sz, karaoke(en, a, 0.0)), layer=3, board=True)
        if p.get("es"):
            t = e + 0.1 if tarde else s + 0.4
            self.add(t, None, "Fijo", r"{\an5\pos(960,505)\fs60\1c%s\fad(300,0)}%s" % (bgr(COL["claro"]), esc(p["es"])), layer=3, board=True)
        if p.get("pron"):
            t = e + 0.4 if tarde else s + 0.7
            self.add(t, None, "Fijo", r"{\an5\pos(960,588)\fs30\1c%s\fad(300,0)}CÓMO SUENA" % bgr(COL["gris"]), layer=3, board=True)
            self.pill(t, None, 960, 668, p["pron"], 62, COL["amarillo"], COL["oscuro"], board=True, fad=(300, 0))
        self.badge(s, e, "ESCUCHA", COL["azul"])
        self.voz.append((s, "EN", en, e))

    def pausa(self, s, e, label, modo, color):
        """Pausa de práctica: cuenta atrás + barra que se vacía, con la duración REAL del silencio."""
        d = max(0.5, e - s)
        self.pill(s, e, 960, 935, label, 44, COL["amarillo"], COL["oscuro"], fad=(200, 200), layer=4)
        self.badge(s, e, modo, color)
        # círculo con número
        self.shape(s, e, rr(0, 0, 150, 150, 75), COL["oscuro"], 0x20, bord=8, bcol=COL["amarillo"], layer=1, fad=(150, 150), pos=(1565, 160))
        n = max(1, int(round(d)))
        for k in range(n):
            self.add(s + k * d / n, s + (k + 1) * d / n, "Fijo", r"{\an5\pos(1640,238)\fs100\1c%s\bord0\shad0}%d" % (bgr(COL["amarillo"]), n - k), layer=3)
        # barra que se vacía
        self.shape(s, e, rr(0, 0, 1360, 14, 7), COL["blanco"], 0xC8, layer=1, fad=(150, 150), pos=(280, 770))
        self.shape(s, e, rr(0, 0, 1360, 14, 7), COL["amarillo"], 0, layer=2, fad=(150, 0), pos=(280, 770),
                   extra=r"\t(0,%d,\fscx0)" % int(d * 1000))
        self.voz.append((s, "PAUSA", f"{d:.0f} s", e))

    def cta(self, s, e):
        """Aviso de suscripción (solo imagen, no añade tiempo)."""
        self.pill(s, e, 1800, 75, "SUSCRÍBETE GRATIS", 36, "dc2626", "ffffff", align="r", fad=(250, 250), layer=5)
        self.pill(s, e, 1770, 172, "LIKE  ·  COMENTA  ·  CAMPANITA", 28, COL["oscuro"], COL["claro"], align="r", bgalpha=0x30, fad=(250, 250), layer=5)

    def tarjeta(self, s, e, cap, kicker):
        d = e - s
        if kicker: self.add(s, e, "Fijo", r"{\an5\pos(960,350)\fs44\1c%s\fad(300,250)}%s" % (bgr(COL["gris"]), esc(kicker.upper())), layer=2)
        self.add(s, e, "Fijo", r"{\an5\pos(960,470)\fs%d\1c%s\fad(300,250)}%s" % (self.size_for(cap, 100), bgr(COL["amarillo"]), esc(cap)), layer=2)
        self.shape(s, e, rr(0, 0, 260, 10, 5), COL["amarillo"], layer=2, pos=(830, 560), fad=(300, 250),
                   extra=r"\fscx0\t(200,%d,\fscx100)" % int(max(0.4, d * 0.6) * 1000))

    # ---- recorre la lección
    def build(self):
        title = self.l.get("titulo", "Lección"); num = self.l.get("numero")
        scenes = self.l["escenas"]
        for si, sc in enumerate(scenes, 1):
            s0 = self.t
            cap = sc.get("capitulo", f"Parte {si}")
            self.scene_marks.append((s0, cap))
            if sc.get("capitulo"): self.chapters.append((s0, cap))
            if sc.get("tarjeta", True) and si > 1:
                self.lines.append(("gap", 2.0))
                a = self.slot("gap", "", 2.0); self.tarjeta(a["s"], a["e"], cap, sc.get("kicker"))
            ss = self.t
            chrome = [self.shape(ss, None, rr(140, 140, 1640, 680, 40), "ffffff", 0xE8, bord=2, bcol="ffffff", balpha=0xB0, layer=0, fad=(300, 0))]
            chrome += self.pill(ss, None, 120, 75, sc.get("kicker", cap).upper(), 34, COL["amarillo"], COL["oscuro"], align="l", layer=1, fad=(300, 0))
            if sc.get("tablero"): self.tablero(sc["tablero"], ss)
            tarde_sc = sc.get("traduccion") == "despues"
            for p in sc["pasos"]:
                if "tablero" in p and "d" not in p and "en" not in p: self.tablero(p["tablero"], self.t); continue
                if "d" in p:
                    text = " ".join(str(p["d"]).split()); self.lines.append(("t", text))
                    chunks = chunk_text(text)
                    slots = [self.slot("speech", ch, self.dur_voz(ch)) for ch in chunks]
                    if p.get("tablero"): self.tablero(p["tablero"], slots[0]["s"])
                    for ch, a in zip(chunks, slots):
                        self.add(a["s"], a["e"] + 0.35, "Sub", r"{\an5\pos(960,905)\fad(120,160)}%s" % karaoke(ch, a, 0.0), layer=3, sub=True)
                    self.voz.append((slots[0]["s"], "ES", text, slots[-1]["e"]))
                    if p.get("cta"): self.cta(slots[0]["s"], slots[-1]["e"] + 0.3)
                elif "en" in p:
                    self.lines.append(("t", p["en"]))
                    a = self.slot("speech", p["en"], self.dur_en(p["en"], p.get("lento", False)), en=True)
                    self.frase(p, a, tarde=tarde_sc)
                    rep = p.get("repite")
                    if rep:
                        base = self.dur_en(p["en"], p.get("lento", False))
                        seg = float(rep) if not isinstance(rep, bool) else float(round(base * 1.6 + 2.0))
                        self.lines.append(("gap", seg)); g = self.slot("gap", "", seg)
                        self.pausa(g["s"], g["e"], "AHORA TÚ · REPITE EN VOZ ALTA", "REPITE", COL["amarillo"])
                elif "pausa" in p:
                    seg = max(1.0, float(p["pausa"])); self.lines.append(("gap", seg)); g = self.slot("gap", "", seg)
                    self.pausa(g["s"], g["e"], p.get("texto") or "AHORA TÚ · REPITE EN VOZ ALTA", "TU TURNO", COL["amarillo"])
                elif "reto" in p:
                    r = p["reto"]; self.lines.append(("t", r["p"]))
                    q = self.slot("speech", r["p"], self.dur_voz(r["p"]))
                    self.close_board(q["s"])
                    self.pill(q["s"], None, 960, 250, r.get("titulo", "RETO · ¿CÓMO SE DICE?"), 46, COL["azul"], COL["oscuro"], board=True, fad=(200, 0))
                    self.add(q["s"], None, "Fijo", r"{\an5\pos(960,440)\fs%d\1c%s\fad(250,0)}%s" % (self.size_for(r["p"], 90), bgr(COL["blanco"]), esc(r["p"])), layer=3, board=True)
                    self.badge(q["s"], q["e"], "TRADUCE", COL["azul"])
                    self.voz.append((q["s"], "RETO", r["p"], q["e"]))
                    seg = max(1.0, float(r.get("seg", 5))); self.lines.append(("gap", seg)); g = self.slot("gap", "", seg)
                    self.pausa(g["s"], g["e"], "PIENSA TU RESPUESTA…", "PIENSA", COL["morado"])
                    self.lines.append(("t", r["r"]))
                    a = self.slot("speech", r["r"], self.dur_en(r["r"]), en=True)
                    self.frase({"en": r["r"], "es": r.get("es"), "pron": r.get("pron")}, a, tarde=True)
                else:
                    raise ValueError(f"Paso desconocido en la escena {si}: {list(p.keys())}")
            for c in chrome: c["e"] = self.t
            self.close_board(self.t)
        self.t_end = self.t
        self.total = max(self.t, self.audio_dur) + 0.8
        self.pie(title, num)
        return self

    def pie(self, title, num):
        """Pie con título y barra de progreso segmentada por capítulos."""
        canal = self.l.get("canal")
        x = 120
        if canal:
            self.add(0, self.total, "Fijo", r"{\an1\pos(120,1030)\fs28\1c%s\bord0}%s" % (bgr(COL["amarillo"]), esc(canal)), layer=1)
            x = 120 + int(tw(canal, 28)) + 28
        self.add(0, self.total, "Fijo", r"{\an1\pos(%d,1030)\fs26\1c%s\bord0}%s" % (x, bgr(COL["gris"]), esc(title)), layer=1)
        if num: self.add(0, self.total, "Fijo", r"{\an3\pos(1800,1030)\fs26\1c%s\bord0}LECCIÓN %s" % (bgr(COL["gris"]), esc(num)), layer=1)
        marks = [m[0] for m in self.scene_marks] + [self.total]
        for i in range(len(marks) - 1):
            a, b = marks[i], marks[i + 1]
            x0 = 120 + a / self.total * 1680; x1 = 120 + b / self.total * 1680 - 5
            if x1 - x0 < 6: continue
            self.shape(0, self.total, rr(0, 0, x1 - x0, 10, 5), "ffffff", 0xD0, layer=1, pos=(x0, 1052))
            self.shape(a, self.total, rr(0, 0, x1 - x0, 10, 5), COL["amarillo"], layer=2, pos=(x0, 1052),
                       extra=r"\fscx0\t(0,%d,\fscx100)" % int(max(0.1, b - a) * 1000))

    # ---- salidas
    def ass(self):
        subs = sorted([e for e in self.ev if e["sub"]], key=lambda e: e["s"])
        for a, b in zip(subs, subs[1:]):
            if a["e"] > b["s"]: a["e"] = max(a["s"] + 0.1, b["s"])
        Y = lambda h, al=0: "&H%02X%s&" % (al, h[4:6] + h[2:4] + h[0:2])
        head = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {W}
PlayResY: {H}
WrapStyle: 0
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Fijo,Arial,64,{bgr(COL['blanco'])},{bgr(COL['blanco'])},&H00281710&,&H80000000&,-1,0,0,0,100,100,0,0,1,3,1,5,160,160,40,1
Style: Karaoke,Arial,64,{bgr(COL['amarillo'])},{bgr(COL['blanco'])},&H00281710&,&H80000000&,-1,0,0,0,100,100,0,0,1,5,2,5,160,160,40,1
Style: Sub,Arial,54,{bgr(COL['amarillo'])},{bgr(COL['blanco'])},{Y(COL['fondo'], 0x66)},&H00000000&,-1,0,0,0,100,100,0,0,3,16,0,5,200,200,40,1
Style: Forma,Arial,20,&H00FFFFFF&,&H00FFFFFF&,&H00000000&,&H00000000&,0,0,0,0,100,100,0,0,1,0,0,7,0,0,0,1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
        rows = []
        for e in self.ev:
            end = e["e"] if e["e"] is not None else self.total
            if end - e["s"] < 0.03: continue
            rows.append(f"Dialogue: {e['layer']},{ass_time(e['s'])},{ass_time(end)},{e['style']},,0,0,0,,{e['text']}")
        return head + "\n".join(rows) + "\n"

    def elevenlabs(self):
        out, pend = [], 0.0
        for k, v in self.lines:
            if k == "gap": pend += v
            else:
                if pend > 0: out.append(self.breaks(pend)); pend = 0.0
                out.append(v)
        return "\n".join(out) + "\n"

    @staticmethod
    def breaks(seg):
        parts, left = [], seg
        while left > 0.05:
            b = min(3.0, left); parts.append(f'<break time="{b:.1f}s" />'); left -= b
        return " ".join(parts)

    def guion(self, real):
        rows = [f"{clock(t)} → {clock(e)}  ({e - t:4.1f} s)  [{k}]  {txt}" for t, k, txt, e in self.voz]
        cab = "GUION CON TIEMPOS " + ("REALES (medidos en tu audio)" if real else "DEL VÍDEO (inicio → fin y segundos disponibles para cada voz o pausa)")
        return cab + "\n\n" + "\n".join(rows) + "\n"

# ---------------------------------------------------------------- sincronización con el audio real
def probe_dur(path):
    return float(run(["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "default=nw=1:nk=1", str(path)]))

def silencios(path, dur, noise=-38, d=0.10):
    p = subprocess.run(["ffmpeg", "-hide_banner", "-nostats", "-i", str(path), "-af", f"silencedetect=noise={noise}dB:d={d}", "-f", "null", "-"],
                       capture_output=True, text=True, encoding="utf-8", errors="replace")
    out, st = [], None
    for line in p.stderr.splitlines():
        m = re.search(r"silence_start:\s*(-?[\d.]+)", line)
        if m: st = max(0.0, float(m.group(1))); continue
        m = re.search(r"silence_end:\s*(-?[\d.]+)\s*\|\s*silence_duration:\s*([\d.]+)", line)
        if m and st is not None: out.append((st, float(m.group(1)))); st = None
    if st is not None: out.append((st, dur))
    return out

def elegir_pausas(cands, exp_lens, est_pos, dur):
    """Elige, entre los silencios largos, los que mejor encajan con las pausas del guion (programación dinámica)."""
    n, S = len(cands), len(exp_lens); INF = 1e18
    if n < S or S == 0: return None
    def c(j, i):
        s, e = cands[i]
        return abs(math.log((e - s + 0.3) / (exp_lens[j] + 0.3))) + 2.0 * abs(s - est_pos[j]) / max(dur, 1.0)
    cost = [[INF] * n for _ in range(S)]; back = [[-1] * n for _ in range(S)]
    for i in range(n): cost[0][i] = c(0, i)
    for j in range(1, S):
        best, bi = INF, -1
        for i in range(n):
            if i > 0 and cost[j - 1][i - 1] < best: best, bi = cost[j - 1][i - 1], i - 1
            if best < INF: cost[j][i] = best + c(j, i); back[j][i] = bi
    i = min(range(n), key=lambda x: cost[S - 1][x])
    if cost[S - 1][i] >= INF: return None
    sel = [i]
    for j in range(S - 1, 0, -1): i = back[j][i]; sel.append(i)
    return [cands[k] for k in reversed(sel)]

VIRT, POSW, REW = 3.0, 3.0, 1.5

def partir_bloque(items, bs, be, shorts):
    """Reparte las frases de un bloque de voz usando los silencios cortos reales. Devuelve [(s,e)], nº aproximadas."""
    K = len(items)
    if K == 1: return [(bs, be)], 0
    blk = max(be - bs, 0.5); tot = sum(w for _, w in items); acc = 0; epos = []
    for _, w in items[:-1]: acc += w; epos.append(bs + blk * acc / tot)
    pts = [(s, e, None) for s, e in shorts if s > bs + 0.04 and e < be - 0.04]
    pts += [(epos[k], epos[k], k) for k in range(K - 1)]
    pts.sort(key=lambda p: (p[0] + p[1]) / 2)
    n, B = len(pts), K - 1; INF = 1e18
    def c(k, i):
        s, e, v = pts[i]; mid = (s + e) / 2
        if v is not None: return VIRT if v == k else INF
        return POSW * abs(mid - epos[k]) / blk - REW * min(e - s, 0.6)
    cost = [[INF] * n for _ in range(B)]; back = [[-1] * n for _ in range(B)]
    for i in range(n): cost[0][i] = c(0, i)
    for k in range(1, B):
        best, bi = INF, -1
        for i in range(n):
            if i > 0 and cost[k - 1][i - 1] < best: best, bi = cost[k - 1][i - 1], i - 1
            if best < INF:
                ck = c(k, i)
                if ck < INF: cost[k][i] = best + ck; back[k][i] = bi
    i = min(range(n), key=lambda x: cost[B - 1][x]); sel = [i]
    for k in range(B - 1, 0, -1): i = back[k][i]; sel.append(i)
    sel = [pts[x] for x in reversed(sel)]
    out, prev, aprox = [], bs, 0
    for s, e, v in sel:
        out.append((prev, max(prev + 0.05, s))); prev = e
        if v is not None: aprox += 1
    out.append((prev, max(prev + 0.05, be)))
    return out, aprox

def alinear(atoms, est, dur, sil, log):
    """Devuelve (times, informe) con el tiempo real de cada átomo del guion, o (None, motivo)."""
    runs = []
    for i, a in enumerate(atoms):
        k = "speech" if a["kind"] == "speech" else "gap"
        if runs and runs[-1][0] == k: runs[-1][1].append(i)
        else: runs.append([k, [i]])
    if runs[0][0] == "gap": return None, "La lección no puede empezar con una pausa."
    tail = runs.pop()[1] if runs[-1][0] == "gap" else []
    speech_runs = [r[1] for r in runs if r[0] == "speech"]
    gap_runs = [r[1] for r in runs if r[0] == "gap"]
    # silencios de cabeza y cola
    s_start, s_end, inner = 0.0, dur, []
    for s, e in sil:
        if s < 0.2 and e - s >= 0.3 and not inner and s_start == 0.0: s_start = e
        elif e >= dur - 0.2: s_end = min(s_end, s)
        else: inner.append((s, e))
    longs = [(s, e) for s, e in inner if e - s >= 0.8]
    shorts = inner
    est_total = max(est[-1]["e"], 1.0); ratio = dur / est_total
    exp_lens = [sum(atoms[i]["exp"] for i in g) for g in gap_runs]
    est_pos = [est[g[0]]["s"] * ratio for g in gap_runs]
    inf = []
    if gap_runs:
        sel = elegir_pausas(longs, exp_lens, est_pos, dur)
        if sel is None:
            return None, (f"Esperaba {len(gap_runs)} pausas largas y solo encontré {len(longs)} silencios de 0,8 s o más. "
                          "Revisa que el audio se generó con TODAS las etiquetas <break>.")
    else: sel = []
    times = [None] * len(atoms); aprox_total = 0
    for r, run_ in enumerate(speech_runs):
        bs = s_start if r == 0 else sel[r - 1][1]
        be = sel[r][0] if r < len(sel) else s_end
        if be <= bs + 0.1: return None, f"Bloque de voz {r+1} sin audio entre {clock(bs)} y {clock(be)}."
        items = []   # (texto, peso en segundos hablados, índice de átomo)
        for i in run_:
            rate = 2.4 if atoms[i].get("en") else 2.9
            for sent in sentences(atoms[i]["text"]): items.append((sent, len(sent.split()) / rate + 0.3, i))
        pos, aprox = partir_bloque([(t, w) for t, w, _ in items], bs, be, shorts)
        aprox_total += aprox
        for (t, _, i), (ps, pe) in zip(items, pos):
            a = times[i]
            if a is None: times[i] = {"s": ps, "e": pe, "parts": [(ps, pe, t)]}
            else: a["e"] = pe; a["parts"].append((ps, pe, t))
    for j, g in enumerate(gap_runs):
        s, e = sel[j]; tot = sum(atoms[i]["exp"] for i in g); cur = s
        for i in g:
            d = (e - s) * atoms[i]["exp"] / tot; times[i] = {"s": cur, "e": cur + d, "parts": None}; cur += d
    if tail:
        last = max(t["e"] for t in times if t); tot = sum(atoms[i]["exp"] for i in tail)
        length = max(tot, dur - last); cur = last
        for i in tail:
            d = length * atoms[i]["exp"] / tot; times[i] = {"s": cur, "e": cur + d, "parts": None}; cur += d
    rep = [f"Audio: {dur:.1f} s · bloques de voz: {len(speech_runs)} · pausas largas: {len(gap_runs)} (silencios candidatos: {len(longs)})"]
    malas = 0
    for j, g in enumerate(gap_runs):
        s, e = sel[j]; real = e - s; esp = exp_lens[j]
        if abs(real - esp) > max(1.0, 0.35 * esp):
            malas += 1; rep.append(f"  · pausa en {clock(s)}: dura {real:.1f} s (el guion pedía {esp:.1f} s)")
    if malas == 0: rep.append("  Todas las pausas coinciden con el guion.")
    if aprox_total: rep.append(f"  {aprox_total} cortes entre frases son aproximados (la voz no dejó silencio claro).")
    return times, rep

# ---------------------------------------------------------------- imagen de fondo y miniatura
def fondo(w, h):
    top, bot = (17, 27, 52), (6, 10, 24)
    g = Image.linear_gradient("L").resize((w, h))
    im = Image.composite(Image.new("RGB", (w, h), bot), Image.new("RGB", (w, h), top), g)
    glow = ImageOps.invert(Image.radial_gradient("L")).resize((int(w * 1.2), int(h * 1.5)))
    mask = Image.new("L", (w, h), 0); mask.paste(glow.point(lambda v: int(v * 0.30)), (-int(w * 0.1), -int(h * 0.25)))
    im = Image.composite(Image.new("RGB", (w, h), (37, 80, 170)), im, mask)
    noise = Image.effect_noise((w, h), 18).convert("RGB")
    return Image.blend(im, noise, 0.022)

def miniatura(lesson, path):
    W2, H2 = 1280, 720
    im = fondo(W2, H2); d = ImageDraw.Draw(im)
    m = lesson.get("miniatura", {}); big = m.get("grande", lesson.get("titulo", "")).upper(); small = m.get("chico", "INGLÉS PRÁCTICO")
    d.rectangle([0, 0, 28, H2], fill="#" + COL["amarillo"])
    if lesson.get("numero"): d.text((90, 70), f"LECCIÓN {lesson['numero']}", font=font(54), fill="#" + COL["azul"])
    words = big.split(); lines, cur = [], ""
    f = font(130)
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=f) <= 1100: cur = t
        else: lines.append(cur); cur = w
    if cur: lines.append(cur)
    y = 190
    for ln in lines[:3]: d.text((90, y), ln, font=f, fill="#" + COL["amarillo"]); y += 150
    d.text((90, min(y + 20, 620)), small, font=font(58), fill="#" + COL["blanco"])
    if lesson.get("canal"):
        d.rounded_rectangle([90, 640, 90 + int(d.textlength(lesson["canal"], font=font(40))) + 56, 700], radius=30, fill="#" + COL["amarillo"])
        d.text((118, 647), lesson["canal"], font=font(40), fill="#" + COL["oscuro"])
    im.save(path)

# ---------------------------------------------------------------- principal
def main():
    ap = argparse.ArgumentParser(description="Crear vídeo de una lección")
    ap.add_argument("leccion"); ap.add_argument("--solo-guion", action="store_true", help="solo textos, tiempos y verificación (sin renderizar)")
    ap.add_argument("--720p", dest="p720", action="store_true", help="renderizar a 1280x720 (más rápido)")
    ap.add_argument("--audio", help="ruta de un audio ya hecho (por defecto audio\\<leccion>\\narracion.*)")
    ap.add_argument("--sin-voz", action="store_true", help="no generar la voz automática (vídeo mudo de prueba)")
    a = ap.parse_args()
    lp = Path(a.leccion).resolve()
    if not lp.is_file(): raise FileNotFoundError(f"No se encuentra el JSON: {lp}")
    lesson = json.loads(lp.read_text(encoding="utf-8-sig"))
    if not lesson.get("escenas") or any("pasos" not in s for s in lesson["escenas"]):
        raise ValueError("Formato antiguo: cada escena debe tener \"pasos\". Usa el formato v2/v3 (ver lecciones/leccion-01.json).")
    name = lp.stem; out = ROOT / "salida" / name; out.mkdir(parents=True, exist_ok=True)
    est = Builder(lesson).build()                       # 1ª pasada: guion y tiempos estimados
    (out / "texto-para-elevenlabs.txt").write_text(est.elevenlabs(), encoding="utf-8")
    miniatura(lesson, out / "miniatura.png")
    audio_dir = ROOT / "audio" / name; audio_dir.mkdir(parents=True, exist_ok=True)
    narr = Path(a.audio).resolve() if a.audio else next((audio_dir / ("narracion" + e) for e in AUDIO_EXTS if (audio_dir / ("narracion" + e)).exists()), None)
    b, real, informe = est, False, []
    wav = None
    vcfg = None
    if not narr and not a.sin_voz:
        try:
            import voz
            vcfg = voz.cargar_config()
            if not voz.configurada(vcfg): vcfg = None
        except Exception as e:
            print("AVISO voz:", e); vcfg = None
    if narr:
        if not shutil.which("ffmpeg"): raise RuntimeError("No se encuentra ffmpeg/ffprobe en el PATH.")
        wav = out / "narracion.wav"
        run(["ffmpeg", "-y", "-i", str(narr), "-ac", "1", "-ar", "44100", "-c:a", "pcm_s16le", str(wav)])
        dur = probe_dur(wav)
        print(f"Midiendo el audio ({dur/60:.1f} min)…")
        sil = silencios(wav, dur)
        times, rep = alinear(est.atoms, est.used, dur, sil, print)
        if times is None:
            informe = ["NO SE PUDO SINCRONIZAR: " + rep, "Se usa un reparto proporcional (aproximado)."]
            r = dur / max(est.t_end, 1.0)
            times = [{"s": u["s"] * r, "e": u["e"] * r, "parts": None} for u in est.used]
        else: informe, real = rep, True
        b = Builder(lesson, times=times, audio_dur=dur).build()
        for ln in informe: print(ln)
    elif vcfg and a.solo_guion:
        import voz
        print(f"Voz automática lista ({voz.nombre_motor(vcfg)}). Esta lección tiene unos {voz.caracteres(est.atoms)} caracteres de voz. "
              "Al crear el vídeo la voz se genera sola y el tiempo queda exacto (aquí se muestran tiempos estimados).")
    elif vcfg:
        import voz
        if not shutil.which("ffmpeg"): raise RuntimeError("No se encuentra ffmpeg/ffprobe en el PATH.")
        wav = out / "narracion.wav"
        times, dur = voz.generar_narracion(est.atoms, vcfg, wav, print)
        b = Builder(lesson, times=times, audio_dur=dur).build(); real = True
        informe = [f"Voz generada ({voz.nombre_motor(vcfg)}). Audio y vídeo nacen juntos: sincronía exacta."]
        print(informe[0])
    (out / "leccion.ass").write_text(b.ass(), encoding="utf-8-sig")
    (out / "guion-tiempos.txt").write_text(b.guion(real), encoding="utf-8")
    (out / "sincronizacion.txt").write_text("\n".join(informe or ["Sin audio: tiempos estimados."]) + "\n", encoding="utf-8")
    chapters = "\n".join(f"{int(t//60)}:{int(t%60):02d} {c}" for t, c in b.chapters)
    (out / "capitulos.txt").write_text(chapters + "\n", encoding="utf-8")
    title = lesson.get("titulo", name)
    desc = lesson.get("descripcion", title) + "\n\nCAPÍTULOS:\n" + chapters + "\n\n" + lesson.get("hashtags", "#inglés #aprenderinglés #inglésparahispanohablantes") + "\n"
    (out / "descripcion-youtube.txt").write_text(desc, encoding="utf-8")
    minimo = float(lesson.get("minimo_minutos", 8)) * 60; total = b.total
    print(f"Duración {'real' if real else 'estimada'}: {int(total//60)} min {int(total%60):02d} s")
    if total < minimo: print(f"AVISO: dura menos de {minimo/60:.0f} min (faltan {minimo-total:.0f} s). Añade práctica o ejemplos a la lección.")
    else: print("OK: cumple el mínimo de duración.")
    maximo = float(lesson.get("maximo_minutos", 0)) * 60
    if maximo and total > maximo: print(f"AVISO: dura más de {maximo/60:.0f} min (sobran {total-maximo:.0f} s). Quita alguna repetición.")
    if a.solo_guion:
        print(f"Textos, tiempos y verificación listos en: {out}"); return
    missing = [t for t in ("ffmpeg", "ffprobe") if shutil.which(t) is None]
    if missing: raise RuntimeError("No se encuentra " + " y ".join(missing) + ". Comprueba FFmpeg y su carpeta bin en el PATH.")
    fondo(W, H).save(out / "fondo.png")
    final = out / f"{name}.mp4"
    vf = "zoompan=z='1.0+0.025*(1-cos(on/625))/2':x='iw/2-(iw/zoom/2)':y='ih/2-(ih/zoom/2)':d=1:s=1920x1080:fps=25," + (("scale=1280:720,") if a.p720 else "") + "ass=leccion.ass,format=yuv420p"
    cmd = ["ffmpeg", "-y", "-loop", "1", "-framerate", "25", "-i", "fondo.png"]
    cmd += ["-i", "narracion.wav"] if wav else ["-f", "lavfi", "-i", "anullsrc=r=44100:cl=stereo"]
    cmd += ["-vf", vf, "-af", "apad", "-t", f"{total:.3f}", "-r", "25", "-c:v", "libx264", "-preset", "veryfast",
            "-crf", "18", "-c:a", "aac", "-b:a", "192k", "-movflags", "+faststart", str(final)]
    print("Renderizando vídeo (puede tardar unos minutos)…")
    run(cmd, cwd=out)
    print("Narración incorporada y sincronizada." if wav else "Sin narración: pulsa «Configurar voz» para que el programa la genere, o pon tu audio en audio\\" + name + "\\narracion.mp3.")
    print(f"Vídeo creado: {final}")
    print(f"Resultados: {out}")

if __name__ == "__main__":
    try: main()
    except Exception as e:
        print(f"ERROR: {e}", file=sys.stderr); sys.exit(1)
