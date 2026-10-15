#!/usr/bin/env python3
"""Interfaz sencilla para Canal de Inglés en Windows."""
import os, sys, json, shutil, subprocess, threading
from pathlib import Path
import tkinter as tk
from tkinter import ttk, filedialog, messagebox

ROOT = Path(__file__).resolve().parent
FFBIN = Path(r"G:\INSTALL\!!!Proyectos Yeinier\ffmpeg\bin")
if FFBIN.is_dir():
    os.environ["PATH"] = str(FFBIN) + os.pathsep + os.environ.get("PATH", "")

class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("Canal de Inglés · Generador de lecciones")
        self.geometry("780x520")
        self.minsize(680, 440)
        self.configure(bg="#0f172a")
        style = ttk.Style(self)
        try: style.theme_use("clam")
        except tk.TclError: pass
        style.configure("TFrame", background="#0f172a")
        style.configure("TLabel", background="#0f172a", foreground="#f8fafc", font=("Arial", 10))
        style.configure("Title.TLabel", font=("Arial", 20, "bold"), foreground="#fbbf24")
        style.configure("TButton", font=("Arial", 10, "bold"), padding=8)
        style.configure("TCombobox", padding=5)
        root = ttk.Frame(self, padding=22); root.pack(fill="both", expand=True)
        ttk.Label(root, text="CANAL DE INGLÉS", style="Title.TLabel").pack(anchor="w")
        ttk.Label(root, text="Prepara lecciones y genera vídeos educativos").pack(anchor="w", pady=(3,18))
        ttk.Label(root, text="Lección disponible").pack(anchor="w")
        self.lesson = tk.StringVar()
        self.combo = ttk.Combobox(root, textvariable=self.lesson, state="readonly")
        self.combo.pack(fill="x", pady=(5,10))
        self.refresh_lessons()
        buttons = ttk.Frame(root); buttons.pack(fill="x", pady=4)
        ttk.Button(buttons, text="Elegir archivo JSON…", command=self.choose).pack(side="left")
        ttk.Button(buttons, text="Abrir carpeta de resultados", command=self.open_output).pack(side="left", padx=8)
        ttk.Button(buttons, text="Configurar voz…", command=self.config_voz).pack(side="left")
        ttk.Button(buttons, text="Usar un audio ya hecho…", command=self.choose_audio).pack(side="left", padx=8)
        self.audio_state = tk.StringVar()
        ttk.Label(root, textvariable=self.audio_state).pack(anchor="w", pady=(2,0))
        self.combo.bind("<<ComboboxSelected>>", lambda e: self.update_audio_state())
        self.update_audio_state()
        self.runbtn = ttk.Button(root, text="▶  CREAR VÍDEO", command=self.start)
        self.runbtn.pack(anchor="w", pady=(14,4))
        self.solo = tk.BooleanVar(value=False)
        tk.Checkbutton(root, text="Solo comprobar sincronía y textos (rápido, sin vídeo)", variable=self.solo, bg="#0f172a", fg="#f8fafc",
                       selectcolor="#111827", activebackground="#0f172a", activeforeground="#f8fafc").pack(anchor="w", pady=(0,8))
        ttk.Label(root, text="Registro").pack(anchor="w")
        self.log = tk.Text(root, height=12, bg="#111827", fg="#e5e7eb", insertbackground="white",
                           relief="flat", font=("Consolas", 9), wrap="word")
        self.log.pack(fill="both", expand=True, pady=(5,0))
        self.write("Listo. Configura la voz una vez, elige una lección y pulsa CREAR VÍDEO.")
        self.write("FFmpeg detectado en: " + (str(FFBIN) if FFBIN.is_dir() else "PATH de Windows"))

    def refresh_lessons(self):
        files = sorted((ROOT / "lecciones").glob("*.json"))
        self.combo["values"] = [str(p.relative_to(ROOT)) for p in files]
        if files: self.lesson.set(str(files[0].relative_to(ROOT)))

    AUDIO_EXTS = (".mp3", ".wav", ".m4a", ".aac", ".ogg", ".opus", ".flac")

    def audio_dir(self):
        return ROOT / "audio" / Path(self.lesson.get() or "leccion").stem

    def update_audio_state(self):
        d = self.audio_dir()
        found = next((f for f in d.glob("narracion.*") if f.suffix.lower() in self.AUDIO_EXTS), None) if d.is_dir() else None
        try:
            sys.path.insert(0, str(ROOT)); import voz
            cfg = voz.cargar_config(); ok = voz.configurada(cfg)
        except Exception:
            ok, cfg = False, {}
        if found: txt = "Audio propio: " + found.name + "  ✔ el vídeo se ajustará a esta voz (bórralo para usar la voz automática)"
        elif ok: txt = "Voz automática: ✔ " + voz.nombre_motor(cfg) + ". El programa genera la voz y el vídeo juntos."
        else: txt = "Voz: sin configurar. Pulsa «Configurar voz…» para que el programa la genere solo."
        self.audio_state.set(txt)

    def config_voz(self):
        sys.path.insert(0, str(ROOT)); import voz
        cfg = voz.cargar_config()
        win = tk.Toplevel(self); win.title("Configurar voz"); win.configure(bg="#0f172a"); win.geometry("600x470")
        f = ttk.Frame(win, padding=18); f.pack(fill="both", expand=True)
        ttk.Label(f, text="Motor de voz").pack(anchor="w")
        MOT = {"Gratis · Voz clonada local (Chatterbox, la de voz_mujer.mp3)": "chatterbox", "ElevenLabs (de pago, la mejor calidad)": "elevenlabs", "Gratis · Microsoft Edge (sin API key)": "edge"}
        mot = tk.StringVar(value=[k for k, v in MOT.items() if v == cfg.get("motor", "chatterbox")][0])
        ttk.Combobox(f, textvariable=mot, values=list(MOT), state="readonly", width=58).pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="— Gratis: voz de Microsoft (mujer, sirve para español e inglés) —").pack(anchor="w")
        ve = tk.StringVar(value=cfg.get("voz_edge", "en-US-EmmaMultilingualNeural")); ttk.Entry(f, textvariable=ve, width=60).pack(fill="x", pady=(2, 2))
        ttk.Label(f, text="Alternativas: en-US-AvaMultilingualNeural · es-MX-DaliaNeural (solo para español)").pack(anchor="w", pady=(0, 10))
        ttk.Label(f, text="— ElevenLabs —").pack(anchor="w")
        ttk.Label(f, text="API key de ElevenLabs").pack(anchor="w")
        key = tk.StringVar(value=cfg.get("api_key", "")); ttk.Entry(f, textvariable=key, show="•", width=60).pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="Nombre de la voz (como sale en My Voices)").pack(anchor="w")
        nom = tk.StringVar(value=cfg.get("nombre_voz", "Angela")); ttk.Entry(f, textvariable=nom, width=60).pack(fill="x", pady=(2, 10))
        ttk.Label(f, text="Voice ID (opcional: si lo pones, se usa en vez del nombre)").pack(anchor="w")
        vid = tk.StringVar(value=cfg.get("voice_id", "")); ttk.Entry(f, textvariable=vid, width=60).pack(fill="x", pady=(2, 12))
        def guardar():
            cfg.update(motor=MOT[mot.get()], voz_edge=ve.get().strip() or "en-US-EmmaMultilingualNeural", api_key=key.get().strip(), nombre_voz=nom.get().strip(), voice_id=vid.get().strip())
            voz.guardar_config(cfg); self.update_audio_state(); return cfg
        def probar():
            guardar(); self.write("Probando la voz…")
            def w():
                try:
                    c = voz.cargar_config(); vi = "" if c.get("motor") in ("edge", "chatterbox") else voz.resolver_voz(c)
                    pcm, _ = voz.sintetizar("Hola, soy Sara. Hello, I'm Sara. Welcome to English with Sara.", c, vi)
                    import wave
                    out = ROOT / "cache_voz" / "prueba_voz.wav"; out.parent.mkdir(exist_ok=True)
                    with wave.open(str(out), "wb") as wv: wv.setnchannels(1); wv.setsampwidth(2); wv.setframerate(voz.SR); wv.writeframes(pcm)
                    self.after(0, self.write, "Voz OK. Reproduciendo la prueba…")
                    if hasattr(os, "startfile"): os.startfile(str(out))
                except Exception as e:
                    self.after(0, self.write, "ERROR de voz: " + str(e))
            threading.Thread(target=w, daemon=True).start()
        def cerrar(): guardar(); self.write("Voz guardada."); win.destroy()
        b = ttk.Frame(f); b.pack(fill="x", pady=6)
        ttk.Button(b, text="Probar voz", command=probar).pack(side="left")
        ttk.Button(b, text="Guardar y cerrar", command=cerrar).pack(side="left", padx=8)
        ttk.Label(f, text="La configuración se guarda en config_voz.json de esta carpeta (no compartas ese archivo si tiene tu API key).").pack(anchor="w", pady=(10, 0))

    def choose_audio(self):
        p = filedialog.askopenfilename(title="Audio generado en ElevenLabs",
              filetypes=[("Audio", "*.mp3 *.wav *.m4a *.aac *.ogg *.opus *.flac"), ("Todos los archivos", "*.*")])
        if not p: return
        d = self.audio_dir(); d.mkdir(parents=True, exist_ok=True)
        for old in d.glob("narracion.*"): old.unlink()
        shutil.copy2(p, d / ("narracion" + Path(p).suffix.lower()))
        self.update_audio_state()
        self.write("Audio copiado a: " + str(d))

    def write(self, text):
        self.log.insert("end", text.rstrip() + "\n"); self.log.see("end")

    def choose(self):
        p = filedialog.askopenfilename(title="Seleccionar lección JSON",
              initialdir=str(ROOT / "lecciones"), filetypes=[("Lecciones JSON","*.json"),("Todos los archivos","*.*")])
        if p:
            try:
                data = json.loads(Path(p).read_text(encoding="utf-8-sig"))
                if not data.get("escenas"): raise ValueError("El JSON no contiene escenas.")
            except Exception as e:
                messagebox.showerror("Lección inválida", str(e)); return
            self.lesson.set(os.path.relpath(p, ROOT)); self.update_audio_state()

    def start(self):
        p = (ROOT / self.lesson.get()).resolve()
        if not p.is_file():
            messagebox.showerror("Falta la lección", "Selecciona un archivo JSON válido."); return
        missing = [x for x in ("ffmpeg.exe","ffprobe.exe") if not ((FFBIN / x).is_file() or any((Path(d)/x).is_file() for d in os.environ.get("PATH","").split(os.pathsep) if d))]
        if missing:
            messagebox.showerror("Falta FFmpeg", "No encuentro ffmpeg.exe y ffprobe.exe. Revisa la carpeta bin de FFmpeg."); return
        self.runbtn.configure(state="disabled")
        self.write("\nGenerando: " + p.name)
        threading.Thread(target=self.worker, args=(p, self.solo.get()), daemon=True).start()

    def worker(self, p, solo=False):
        env = os.environ.copy()
        if FFBIN.is_dir(): env["PATH"] = str(FFBIN) + os.pathsep + env.get("PATH","")
        try:
            proc = subprocess.Popen([sys.executable, str(ROOT/"crear_video.py"), str(p)] + (["--solo-guion"] if solo else []),
                 cwd=str(ROOT), env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
                 text=True, encoding="utf-8", errors="replace")
            for line in proc.stdout:
                self.after(0, self.write, line)
            code = proc.wait()
            self.after(0, self.write, "Proceso terminado correctamente." if code == 0 else f"El proceso terminó con código {code}.")
        except Exception as e:
            self.after(0, self.write, "ERROR: " + str(e))
        finally:
            self.after(0, lambda: self.runbtn.configure(state="normal"))

    def open_output(self):
        out = ROOT / "salida"
        out.mkdir(exist_ok=True)
        os.startfile(str(out))

if __name__ == "__main__":
    App().mainloop()
