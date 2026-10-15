# -*- coding: utf-8 -*-
"""Voz automática: voz clonada gratis (Chatterbox, local), ElevenLabs o Microsoft Edge.

El programa pide cada frase a ElevenLabs CON TIEMPOS por letra, une todo con las pausas exactas
y construye el vídeo sobre ese audio. No hay nada que sincronizar ni editar a mano.
Las frases ya generadas se guardan en `cache_voz\\` para no gastar créditos al repetir.
"""
import base64, hashlib, json, os, re, subprocess, time, wave
import urllib.error, urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
CFG_FILE = ROOT / "config_voz.json"
CACHE = ROOT / "cache_voz"
SR = 44100
API = "https://api.elevenlabs.io"

DEFAULT = {"motor": "chatterbox",
           "ref_voz": "voz_mujer.mp3", "cb_exaggeration": 0.4, "cb_cfg": 0.3, "cb_temperature": 0.7, "cb_semilla": 12345,
           "volumen_rms_db": -17.0,
           "voz_edge": "en-US-EmmaMultilingualNeural", "voz_edge_es": "", "velocidad_edge": "-5%",
           "api_key": "", "voice_id": "", "nombre_voz": "Angela", "modelo": "eleven_multilingual_v2",
           "stability": 0.5, "similarity_boost": 0.8, "style": 0.0, "speed": 1.0,
           "pausa_entre_frases": 0.35, "margen_inicio": 0.06, "margen_final": 0.14}

class VozError(RuntimeError): pass

# ---------------------------------------------------------------- configuración
def cargar_config():
    cfg = dict(DEFAULT)
    if CFG_FILE.is_file():
        try: cfg.update(json.loads(CFG_FILE.read_text(encoding="utf-8-sig")))
        except Exception as e: raise VozError(f"config_voz.json está dañado: {e}")
    cfg["api_key"] = (cfg.get("api_key") or os.environ.get("ELEVENLABS_API_KEY", "")).strip()
    return cfg

def guardar_config(cfg):
    CFG_FILE.write_text(json.dumps(cfg, ensure_ascii=False, indent=2), encoding="utf-8")

def configurada(cfg=None):
    cfg = cfg or cargar_config()
    if cfg.get("motor") in ("edge", "chatterbox"): return True   # gratis: no necesitan API key
    return bool(cfg["api_key"] and (cfg["voice_id"] or cfg["nombre_voz"]))

def nombre_motor(cfg):
    if cfg.get("motor") == "chatterbox": return "Gratis · Voz clonada local (Chatterbox, " + str(cfg.get("ref_voz", "")) + ")"
    return ("Gratis · Microsoft Edge (" + cfg.get("voz_edge", "") + ")") if cfg.get("motor") == "edge" else ("ElevenLabs · " + (cfg.get("nombre_voz") or cfg.get("voice_id") or ""))

# ---------------------------------------------------------------- HTTP
def _request(method, path, key, body=None, retries=3):
    data = json.dumps(body).encode("utf-8") if body is not None else None
    for intento in range(retries + 1):
        req = urllib.request.Request(API + path, data=data, method=method,
                                     headers={"xi-api-key": key, "Content-Type": "application/json", "Accept": "application/json"})
        try:
            with urllib.request.urlopen(req, timeout=120) as r: return json.loads(r.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            txt = e.read().decode("utf-8", "replace")
            if e.code in (429, 500, 502, 503) and intento < retries:
                time.sleep(2 + 3 * intento); continue
            raise VozError(_explicar(e.code, txt))
        except urllib.error.URLError as e:
            if intento < retries: time.sleep(2 + 2 * intento); continue
            raise VozError(f"No hay conexión con ElevenLabs ({e.reason}). Revisa tu internet.")
    raise VozError("ElevenLabs no respondió.")

def _explicar(code, txt):
    low = txt.lower()
    if code == 401 or "invalid_api_key" in low: return "La API key de ElevenLabs no es válida. Cópiala de nuevo (ElevenLabs → Developers → API Keys)."
    if "paid_plan_required" in low or "payment_required" in low or code == 402:
        return "Tu plan de ElevenLabs no permite usar esta voz por API (las voces de la biblioteca suelen requerir un plan de pago). Prueba con una voz propia o sube de plan."
    if "quota" in low or "credits" in low: return "Se acabaron los créditos de tu plan de ElevenLabs. Lo ya generado queda guardado: cuando tengas créditos, vuelve a pulsar CREAR y continúa donde se quedó."
    if code == 429: return "ElevenLabs limitó las peticiones. Espera un minuto y vuelve a intentarlo (lo ya generado no se pierde)."
    if code == 404 or "voice_not_found" in low: return "ElevenLabs no encuentra esa voz. Revisa el Voice ID."
    return f"Error de ElevenLabs ({code}): {txt[:300]}"

def resolver_voz(cfg):
    """Devuelve el voice_id: el escrito en la configuración o el de la voz con ese nombre en tu cuenta."""
    if cfg.get("voice_id"): return cfg["voice_id"]
    data = _request("GET", "/v1/voices", cfg["api_key"])
    nombre = (cfg.get("nombre_voz") or "").strip().lower()
    voces = data.get("voices", [])
    for v in voces:
        if v.get("name", "").strip().lower() == nombre: return v["voice_id"]
    for v in voces:
        if nombre and nombre in v.get("name", "").lower(): return v["voice_id"]
    raise VozError(f"No encuentro la voz «{cfg.get('nombre_voz')}» en tu cuenta. Añádela a «My Voices» en ElevenLabs o escribe su Voice ID.")

# ---------------------------------------------------------------- síntesis de una frase
def _wav_a_pcm(path):
    with wave.open(str(path), "rb") as w:
        return w.readframes(w.getnframes())

def _mp3_a_pcm(mp3_bytes, tmp):
    src = tmp.with_suffix(".mp3"); dst = tmp.with_suffix(".wav")
    src.write_bytes(mp3_bytes)
    p = subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)],
                       capture_output=True, text=True)
    if p.returncode: raise VozError("FFmpeg no pudo leer el audio de ElevenLabs: " + p.stderr[-300:])
    pcm = _wav_a_pcm(dst); src.unlink(missing_ok=True); dst.unlink(missing_ok=True)
    return pcm

def _palabras(alignment):
    """Agrupa el alineamiento por letra en palabras con (inicio, fin, texto)."""
    chars = alignment.get("characters") or []
    ini = alignment.get("character_start_times_seconds") or []
    fin = alignment.get("character_end_times_seconds") or []
    out, cur, s, e = [], "", None, None
    for ch, a, b in zip(chars, ini, fin):
        if ch.isspace():
            if cur: out.append((s, e, cur)); cur, s, e = "", None, None
            continue
        if s is None: s = a
        cur += ch; e = b
    if cur: out.append((s, e, cur))
    return out

def _recortar(pcm, mi, mf):
    """Quita el silencio de los extremos. Devuelve (pcm recortado, segundos quitados al inicio)."""
    import array
    a = array.array("h"); a.frombytes(pcm[:len(pcm) // 2 * 2]); n = len(a); th = 500
    i = 0
    while i < n and abs(a[i]) < th: i += 1
    j = n - 1
    while j > i and abs(a[j]) < th: j -= 1
    t0 = max(0.0, i / SR - mi); t1 = min(n / SR, (j + 1) / SR + mf)
    return pcm[int(t0 * SR) * 2:int(t1 * SR) * 2], t0

def _edge_stream(texto, voz, rate):
    try: import edge_tts
    except ImportError: raise VozError("Falta instalar edge-tts. Ejecuta instalar.bat otra vez, o escribe: python -m pip install edge-tts")
    import asyncio
    async def go(boundary):
        kw = {"rate": rate}
        if boundary: kw["boundary"] = boundary
        com = edge_tts.Communicate(texto, voz, **kw)
        audio = bytearray(); ev = []
        async for ch in com.stream():
            if ch["type"] == "audio": audio += ch["data"]
            elif ch["type"] in ("WordBoundary", "SentenceBoundary"):
                ev.append([ch["offset"] / 1e7, (ch["offset"] + ch["duration"]) / 1e7, ch["text"], ch["type"]])
        if not audio: raise RuntimeError("el servicio no devolvió audio")
        return bytes(audio), ev
    ultimo = None
    for intento in range(4):
        try:
            try: return asyncio.run(go("WordBoundary"))
            except TypeError: return asyncio.run(go(None))
        except Exception as e:
            ultimo = e; time.sleep(2 + 2 * intento)
    raise VozError(f"Falló la voz gratuita de Microsoft ({ultimo}). Revisa tu internet y vuelve a intentarlo; lo ya generado queda guardado.")

def _sintetizar_edge(texto, cfg, en):
    voz = cfg["voz_edge"] if (en or not cfg.get("voz_edge_es")) else cfg["voz_edge_es"]
    k = clave(texto, cfg, "edge:" + voz, cfg.get("velocidad_edge"))
    CACHE.mkdir(exist_ok=True)
    f_mp3, f_json = CACHE / f"{k}.mp3", CACHE / f"{k}.json"
    if f_mp3.is_file() and f_json.is_file():
        audio = f_mp3.read_bytes(); ev = json.loads(f_json.read_text(encoding="utf-8"))
    else:
        audio, ev = _edge_stream(texto, voz, cfg.get("velocidad_edge") or "+0%")
        f_mp3.write_bytes(audio); f_json.write_text(json.dumps(ev), encoding="utf-8")
    pcm = _mp3_a_pcm(audio, CACHE / ("tmp_" + k))
    pcm, t0 = _recortar(pcm, cfg["margen_inicio"], cfg["margen_final"])
    pal = [(max(0.0, s - t0), max(0.0, e - t0), w) for s, e, w, tipo in ev if tipo == "WordBoundary"]
    return pcm, pal

# ---------------------------------------------------------------- Chatterbox (voz clonada, gratis, local)
_CB = {}

def _ref_path(cfg):
    """Busca el audio de referencia (tu voz de mujer) junto al programa."""
    nombre = (cfg.get("ref_voz") or "voz_mujer.mp3").strip()
    cand = [Path(nombre)] if Path(nombre).is_absolute() else [ROOT / nombre]
    cand += [ROOT / "voces_ref" / nombre] + sorted(ROOT.glob("voz_mujer.*")) + sorted((ROOT / "voces_ref").glob("*.*"))
    for c in cand:
        if c.is_file() and c.suffix.lower() in (".wav", ".mp3", ".flac", ".m4a", ".ogg"): return c
    raise VozError(f"No encuentro el audio de tu voz de referencia («{nombre}»). Copia tu audio de mujer (5-10 segundos, "
                   f"una sola voz, limpio) a esta carpeta con el nombre voz_mujer.mp3:\n  {ROOT}")

def _ref_preparada(cfg):
    """Deja la referencia en WAV 24 kHz mono, ≤10 s, sin silencio inicial y con volumen normal.
    (Una referencia grabada muy baja hace que toda la voz salga baja.)"""
    ref = _ref_path(cfg)
    CACHE.mkdir(exist_ok=True)
    firma = hashlib.sha1(f"{ref.name}|{ref.stat().st_size}|{int(ref.stat().st_mtime)}".encode()).hexdigest()[:10]
    dst = CACHE / f"ref_{firma}.wav"
    if dst.is_file(): return dst
    def ff(entrada, salida, af=None):
        c = ["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(entrada), "-t", "10", "-ac", "1", "-ar", "24000"]
        if af: c += ["-af", af]
        c += ["-c:a", "pcm_s16le", str(salida)]
        try: return subprocess.run(c, capture_output=True, text=True, timeout=120)
        except subprocess.TimeoutExpired: return subprocess.CompletedProcess(c, 1, "", "ffmpeg tardó demasiado")
    paso1, paso2 = CACHE / f"ref_{firma}_1.wav", CACHE / f"ref_{firma}_2.wav"
    # dos pasadas separadas (juntar los dos filtros en una sola puede colgar ffmpeg en algunos equipos)
    ok = (ff(ref, paso1, "silenceremove=start_periods=1:start_threshold=-45dB:start_silence=0.05").returncode == 0 and paso1.is_file()
          and ff(paso1, paso2, "loudnorm=I=-20:TP=-2:LRA=7").returncode == 0 and paso2.is_file())
    if ok: paso2.replace(dst)
    else:
        p = ff(ref, dst)                                  # plan B: solo convertir
        if p.returncode or not dst.is_file(): raise VozError("FFmpeg no pudo leer tu audio de referencia: " + (p.stderr or "")[-300:])
    paso1.unlink(missing_ok=True); paso2.unlink(missing_ok=True)
    return dst

def _cb_modelo():
    if "m" in _CB: return _CB["m"]
    try:
        import torch
        from chatterbox.mtl_tts import ChatterboxMultilingualTTS
    except ImportError as e:
        raise VozError("Falta instalar Chatterbox en este Python (necesita Python 3.11). Ejecuta INSTALAR_VOZ_CLONADA.bat. Detalle: " + str(e))
    try:
        import perth
        if getattr(perth, "PerthImplicitWatermarker", None) is None:      # perth no carga en algunos PCs
            class _SinMarca:
                def apply_watermark(self, wav, *a, **k): return wav
            perth.PerthImplicitWatermarker = _SinMarca
    except ImportError: pass
    dev = "cuda" if torch.cuda.is_available() else "cpu"
    print(f"Cargando la voz clonada (Chatterbox, {dev})…" + ("  OJO: sin tarjeta NVIDIA tarda MINUTOS por frase." if dev == "cpu" else ""))
    m = ChatterboxMultilingualTTS.from_pretrained(device=dev)
    # El T3 multilingüe usa por defecto hasta 1000 tokens por frase. En CPU,
    # limitar ese máximo evita colas de generación excesivamente largas. El EOS
    # normal sigue terminando antes; si una frase es larga, se puede subir el
    # límite con CHATTERBOX_MAX_NEW_TOKENS.
    try:
        original_inference = m.t3.inference
        limite = max(150, int(os.environ.get("CHATTERBOX_MAX_NEW_TOKENS", "500")))
        def _inference_con_limite(*args, **kwargs):
            pedido = kwargs.get("max_new_tokens")
            kwargs["max_new_tokens"] = min(int(pedido or limite), limite)
            return original_inference(*args, **kwargs)
        m.t3.inference = _inference_con_limite
        print(f"Límite máximo de generación por frase: {limite} tokens.")
    except Exception as e:
        print(f"AVISO: no se pudo ajustar el límite de Chatterbox: {e}")
    _CB.update(m=m, torch=torch, dev=dev)
    return _CB["m"]

def _cb_generar(texto, lang, cfg, ref):
    """Una frase con Chatterbox. Devuelve (bytes PCM 16 bit mono, frecuencia)."""
    m = _cb_modelo(); torch = _CB["torch"]
    torch.manual_seed(int(cfg.get("cb_semilla", 12345)))
    wav = m.generate(texto, language_id=lang, audio_prompt_path=str(ref), exaggeration=float(cfg["cb_exaggeration"]),
                     cfg_weight=float(cfg["cb_cfg"]), temperature=float(cfg["cb_temperature"]))
    x = wav.detach().cpu().float().reshape(-1).clamp(-1, 1)
    return (x * 32767).short().numpy().tobytes(), int(m.sr)

def _trozos(texto, maxc=230):
    """Parte frases largas en trozos (Chatterbox rinde mejor con frases cortas)."""
    if len(texto) <= maxc: return [texto]
    out, cur = [], ""
    for f in re.split(r"(?<=[.!?¿¡;:])\s+", texto):
        if cur and len(cur) + 1 + len(f) > maxc: out.append(cur); cur = f
        else: cur = (cur + " " + f).strip()
    if cur: out.append(cur)
    return out

def _pcm_a_44k(pcm, sr, tmp):
    src = tmp.with_suffix(".src.wav"); dst = tmp.with_suffix(".wav")
    with wave.open(str(src), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    p = subprocess.run(["ffmpeg", "-nostdin", "-y", "-loglevel", "error", "-i", str(src), "-ac", "1", "-ar", str(SR), "-c:a", "pcm_s16le", str(dst)],
                       capture_output=True, text=True, timeout=120)
    if p.returncode: raise VozError("FFmpeg no pudo convertir la voz: " + p.stderr[-300:])
    out = _wav_a_pcm(dst); src.unlink(missing_ok=True); dst.unlink(missing_ok=True)
    return out

def _normalizar(pcm, rms_db):
    """Sube (o baja) el volumen hasta un nivel de voz de YouTube, con limitador suave para no distorsionar."""
    import array, math
    a = array.array("h"); a.frombytes(pcm[:len(pcm) // 2 * 2])
    act = [abs(x) for x in a if abs(x) > 400]
    if len(act) < 200: return pcm
    rms = math.sqrt(sum(x * x for x in act) / len(act))
    g = min(max(32768 * 10 ** (rms_db / 20) / rms, 0.1), 40.0)
    T, L = 0.70 * 32768, 0.97 * 32767
    out = array.array("h", bytes(len(a) * 2))
    for i, x in enumerate(a):
        y = x * g; m = abs(y)
        if m > T: y = math.copysign(T + (L - T) * math.tanh((m - T) / (L - T)), y)
        out[i] = int(y)
    return out.tobytes()

def _sintetizar_chatterbox(texto, cfg, en):
    lang = "en" if en else "es"
    ref = _ref_preparada(cfg)
    firma = f"{ref.name}|{cfg['cb_exaggeration']}|{cfg['cb_cfg']}|{cfg['cb_temperature']}|{cfg.get('cb_semilla')}"
    k = hashlib.sha1(json.dumps([texto, "chatterbox", lang, firma], ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    CACHE.mkdir(exist_ok=True)
    f_wav = CACHE / f"cb_{k}.wav"                      # sin normalizar: cambiar el volumen no obliga a regenerar
    if f_wav.is_file():
        with wave.open(str(f_wav), "rb") as w: sr = w.getframerate(); pcm = w.readframes(w.getnframes())
    else:
        piezas = []
        for t in _trozos(texto):
            p, sr = _cb_generar(t, lang, cfg, ref); piezas.append(p)
        pausa = bytes(int(0.22 * sr) * 2)
        pcm = pausa.join(piezas)
        with wave.open(str(f_wav), "wb") as w:
            w.setnchannels(1); w.setsampwidth(2); w.setframerate(sr); w.writeframes(pcm)
    pcm = _pcm_a_44k(pcm, sr, CACHE / ("tmp_" + k))
    pcm, _ = _recortar(pcm, cfg["margen_inicio"], cfg["margen_final"])
    pcm = _normalizar(pcm, float(cfg.get("volumen_rms_db", -17.0)))
    return pcm, []          # sin tiempos por palabra: el karaoke se reparte por la duración real de cada frase

def clave(texto, cfg, voice_id, ctx):
    base = json.dumps([texto, voice_id, cfg["modelo"], cfg["stability"], cfg["similarity_boost"], cfg["style"], cfg["speed"], ctx], ensure_ascii=False)
    return hashlib.sha1(base.encode("utf-8")).hexdigest()[:20]

def sintetizar(texto, cfg, voice_id, ctx=None, en=True):
    """Devuelve (pcm 16 bit mono 44.1 kHz recortado, [(inicio, fin, palabra)]) con tiempos relativos al pcm."""
    if cfg.get("motor") == "edge": return _sintetizar_edge(texto, cfg, en)
    if cfg.get("motor") == "chatterbox": return _sintetizar_chatterbox(texto, cfg, en)
    CACHE.mkdir(exist_ok=True)
    k = clave(texto, cfg, voice_id, ctx)
    f_mp3, f_json = CACHE / f"{k}.mp3", CACHE / f"{k}.json"
    if f_mp3.is_file() and f_json.is_file():
        audio = f_mp3.read_bytes(); alin = json.loads(f_json.read_text(encoding="utf-8"))
    else:
        body = {"text": texto, "model_id": cfg["modelo"],
                "voice_settings": {"stability": cfg["stability"], "similarity_boost": cfg["similarity_boost"], "style": cfg["style"],
                                   "use_speaker_boost": True, "speed": cfg["speed"]}}
        if ctx:
            if ctx.get("prev"): body["previous_text"] = ctx["prev"]
            if ctx.get("next"): body["next_text"] = ctx["next"]
        r = _request("POST", f"/v1/text-to-speech/{voice_id}/with-timestamps?output_format=mp3_44100_128", cfg["api_key"], body)
        audio = base64.b64decode(r["audio_base64"]); alin = r.get("alignment") or r.get("normalized_alignment") or {}
        f_mp3.write_bytes(audio); f_json.write_text(json.dumps(alin), encoding="utf-8")
    pcm = _mp3_a_pcm(audio, CACHE / ("tmp_" + k))
    pal = _palabras(alin)
    n = len(pcm) // 2
    t0 = max(0.0, (pal[0][0] if pal else 0.0) - cfg["margen_inicio"])
    t1 = min(n / SR, (pal[-1][1] if pal else n / SR) + cfg["margen_final"])
    a, b = int(t0 * SR), int(t1 * SR)
    return pcm[a * 2:b * 2], [(max(0.0, s - t0), max(0.0, e - t0), w) for s, e, w in pal]

def caracteres(atoms):
    return sum(len(a["text"]) for a in atoms if a["kind"] == "speech")

# ---------------------------------------------------------------- narración completa
def generar_narracion(atoms, cfg, out_wav, log=print):
    """Genera la voz de todos los átomos del guion. Devuelve (times, duración) con tiempos exactos."""
    if not configurada(cfg): raise VozError("Falta configurar la voz (API key y voz). Usa el botón «Configurar voz».")
    voice_id = "" if cfg.get("motor") in ("edge", "chatterbox") else resolver_voz(cfg)
    log(f"Voz: {nombre_motor(cfg)} · {caracteres(atoms)} caracteres")
    buf = bytearray(); times = []; t = 0.0
    prev_speech = False; pausa = cfg["pausa_entre_frases"]
    n_sp = sum(1 for a in atoms if a["kind"] == "speech"); hecho = 0
    for i, a in enumerate(atoms):
        if a["kind"] != "speech":
            n = int(round(a["exp"] * SR)); buf += bytes(n * 2); times.append({"s": t, "e": t + n / SR, "parts": None}); t += n / SR
            prev_speech = False; continue
        if prev_speech:
            n = int(round(pausa * SR)); buf += bytes(n * 2); t += n / SR
        ctx = None
        if not a.get("en"):
            ant = atoms[i - 1] if i > 0 else None; sig = atoms[i + 1] if i + 1 < len(atoms) else None
            ctx = {"prev": ant["text"] if ant and ant["kind"] == "speech" and not ant.get("en") else "",
                   "next": sig["text"] if sig and sig["kind"] == "speech" and not sig.get("en") else ""}
        pcm, pal = sintetizar(a["text"], cfg, voice_id, ctx, a.get("en", False))
        dur = len(pcm) // 2 / SR
        palabras_texto = a["text"].split()
        if len(pal) == len(palabras_texto): parts = [(t + s, t + e, w) for (s, e, _), w in zip(pal, palabras_texto)]
        else: parts = None
        buf += pcm; times.append({"s": t, "e": t + dur, "parts": parts}); t += dur
        prev_speech = True; hecho += 1
        if hecho % 10 == 0 or hecho == n_sp or cfg.get("motor") == "chatterbox": log(f"  voz generada: {hecho}/{n_sp} frases")
    with wave.open(str(out_wav), "wb") as w:
        w.setnchannels(1); w.setsampwidth(2); w.setframerate(SR); w.writeframes(bytes(buf))
    return times, t
