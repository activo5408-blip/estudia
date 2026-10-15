# INGLÉS CON SARA — Windows (v3 · el audio manda)

Genera vídeos de clases de inglés con karaoke, pausas de práctica con cuenta atrás, miniatura, capítulos y descripción de YouTube.

## Instalar
1. Python 3.10+ (marca *Add Python to PATH*) y FFmpeg (`ffmpeg` y `ffprobe` en PATH).
2. Ejecuta `instalar.bat`.
3. Abre `ABRIR_CANAL_INGLES.bat`.

## NUEVO · Voz automática (recomendado)
1. En ElevenLabs: Developers → API Keys → crea una key y cópiala.
2. En el programa pulsa **Configurar voz…**, pega la key, deja el nombre de la voz (por ejemplo `Angela`, tal como sale en My Voices) y pulsa **Probar voz**.
3. Elige la lección y pulsa **CREAR VÍDEO**. El programa genera la voz (español e inglés con la misma voz), la une con las pausas exactas y construye el vídeo con esos tiempos. No hay audio aparte que editar ni sincronizar.
- Cada frase generada se guarda en `cache_voz\`: si vuelves a crear la lección no gasta créditos otra vez.
- Una lección usa unos 5 000-7 000 caracteres de tu plan de ElevenLabs.
- Si ya tienes un audio propio en `audio\<leccion>\narracion.mp3`, el programa usa ese en vez de generar la voz.

## Flujo manual (alternativa, sin API)
1. Elige la lección y pulsa **CREAR VÍDEO** (o marca *Solo comprobar…* para que sea instantáneo).
2. En `salida\<leccion>\` aparece `texto-para-elevenlabs.txt`. **Pégalo tal cual en ElevenLabs** (las pausas ya van como `<break>`; también la pausa de 2 s entre capítulos).
3. Guarda el audio con el botón **Elegir audio de ElevenLabs…** (o cópialo como `audio\<leccion>\narracion.mp3`).
4. Pulsa **CREAR VÍDEO** otra vez. El programa mide el audio real (silencios y frases) y coloca cada frase, cada cuenta atrás y cada capítulo donde la voz los pone.
5. Revisa `salida\<leccion>\sincronizacion.txt`: dice si todas las pausas coincidieron. Si algo no cuadra (por ejemplo, ElevenLabs recortó una pausa), lo indica con el minuto.
6. Sube `<leccion>.mp4`, `miniatura.png` y copia `descripcion-youtube.txt`.

Importante: no edites el texto de ElevenLabs al generarlo (no quites líneas ni etiquetas `<break>`); el programa usa esa estructura para saber qué es voz y qué es pausa.

## Formato de una lección (JSON)
Cada escena tiene `capitulo`, `kicker`, `tablero` (pizarra inicial) y `pasos`. Opcional por escena: `"traduccion": "despues"` (la traducción aparece al terminar la frase, útil para «solo escucha»).
- `{"d": "texto narrado"}` (opcional `"tablero": [...]`): subtítulo karaoke.
- `{"en": "Hi, I'm Ana.", "es": "...", "pron": "...", "quien": "Ana", "repite": true}`: frase en inglés con karaoke, traducción y pronunciación; `repite` añade pausa (número = segundos pedidos a ElevenLabs).
- `{"pausa": 6, "texto": "AHORA TÚ · ..."}`: cuenta atrás.
- `{"reto": {"p": "pregunta en español", "r": "respuesta en inglés", "es": "", "pron": "", "seg": 5}}`: el espectador piensa y luego aparece la respuesta.
Tipos de pizarra (`e`): `grande`, `medio`, `nota`, `bueno`, `malo`.

Plan completo del curso: `lecciones\PLAN_50_LECCIONES.md`.

## Curso incluido: Bloque 1 (lecciones 1-10, 8 a 9 minutos cada una)
`lecciones\leccion-01.json` … `leccion-10.json`. Todas siguen la misma fórmula: gancho -> repaso de la lección anterior -> conversación -> piezas con DOBLE repetición -> errores comunes -> juego rápido -> conversación contigo -> resumen, tarea, adelanto de la siguiente y suscripción.
Para cambiar el contenido: edita `herramientas\curso_datos.py` y ejecuta `python herramientas\generar_curso.py` (recalcula las duraciones para quedar entre 8:15 y 8:50 estimados).
El nombre del canal sale del campo `canal` de cada lección.

## Dos formas de trabajar
- **Recomendada (el audio manda):** genera la voz con `texto-para-elevenlabs.txt`, mete el audio y el programa ajusta el vídeo a la voz.
- **Si prefieres editar tú el audio:** usa `guion-tiempos.txt`: cada línea trae inicio -> fin y los segundos disponibles para esa voz o pausa. Si una voz dura más que su espacio, la lección se alarga; por eso conviene la forma recomendada.


## Voz clonada gratis (Chatterbox) — motor por defecto

1. Ejecuta `INSTALAR_VOZ_CLONADA.bat` una vez (necesita Python 3.11).
2. Copia tu audio de mujer (5-10 s, una sola voz, limpio) a esta carpeta con el nombre `voz_mujer.mp3`.
3. Abre el programa (`ABRIR_CANAL_INGLES.bat`), elige la lección y pulsa CREAR VÍDEO. En «Configurar voz…» puedes cambiar de motor.

Ajustes en `config_voz.json` (se crea al guardar la configuración): `cb_exaggeration` (emoción, 0.25-1.0), `cb_cfg` (ritmo; más bajo = menos acento de la referencia),
`cb_temperature` (variación) y `volumen_rms_db` (volumen de la voz; sube hacia -14 para más fuerte, baja hacia -20 para más suave).
Cada frase se guarda en `cache_voz\`: si cambias solo el volumen no se regenera nada; si cambias los otros ajustes se regenera.
Sin tarjeta NVIDIA cada frase tarda minutos; con GPU, segundos. El karaoke se reparte por la duración real de cada frase (no hay tiempos por palabra como en ElevenLabs).
