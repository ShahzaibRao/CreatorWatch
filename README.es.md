# 📥 CreatorWatch — v0.1.0

🌐 Idioma: [English](README.md) · [Roman Urdu](README.ur.md) · **Español** · [中文](README.zh.md)

Sigue automáticamente canales/perfiles de YouTube, TikTok, Instagram y X (Twitter).
Añade un enlace → se crea una carpeta → **solo se descarga el video más reciente** →
luego solo las **nuevas subidas** en cada intervalo.

---

## 1. Instalación (primera vez)

```bash
cd downloader
python -m venv venv

# Windows:
venv\Scripts\activate
# Git-Bash / Linux / Mac:
source venv/bin/activate

pip install -r requirements.txt
python app.py
```

Luego abre: **http://127.0.0.1:5000**

> No hace falta instalar `ffmpeg` — viene incluido con `imageio-ffmpeg`.

---

## 2. Añadir un prospecto (canal)

El formulario **Add prospect** del panel:

| Campo | Significado |
|---|---|
| Name | Nombre, p. ej. `ali_tiktok` → se crea `downloads/youtube_ali_tiktok/` |
| Channel / Profile link | Canal de YouTube, `@user` de TikTok, perfil de Instagram o de X |
| Every (min) | Cada cuántos minutos buscar videos nuevos (5–1440, defecto 15) |
| Quality | `720p` (defecto) / `1080p` / `480p` / `360p` / `Best` — solo YouTube |

**Al añadir:**
1. Se crea la carpeta en `downloads/`
2. **Solo el video más reciente** se descarga en segundo plano
3. Los videos viejos quedan `skipped` — **nunca se descargarán**

---

## 3. Uso diario

| Botón | Acción |
|---|---|
| **Check** | Comprobar ahora + descargar lo nuevo en segundo plano (verás la barra de progreso) |
| **Check all now** | Comprobar todos los prospectos activos a la vez |
| **⏸ Stop / ▶ Resume** | Pausar / reanudar el auto-chequeo |
| **Edit** | Cambiar nombre, enlace, intervalo, calidad (la carpeta no cambia) |
| **Del** | Borrar prospecto + su historial |

**Estados:** `OK` · `Error` (pasa el ratón para ver por qué) · `Working` · `Paused`.

**Ten en cuenta:**
- Cada perfil se revisa solo según su intervalo.
- Las descargas quedan en la **base de datos** — aunque borres un archivo, **no se vuelve a descargar**.
- `0 new` = el creador no ha subido nada nuevo.

**Extras:** 🔔 campana con contador + pills NEW, barras de progreso en vivo, indicador ⚙ workers, selector de idioma 🌐 (EN/UR/ES/中文), tema ◐ claro/oscuro.

---

## 4. 🍪 Gestor de Cookies (página `/cookies`, botón del encabezado)

Instagram y X (Twitter) **no dan datos sin sesión iniciada**.
YouTube + TikTok suelen funcionar sin cookies.

**Cómo importar:**
1. Instala la extensión **"Get cookies.txt LOCALLY"**
2. Inicia sesión en ese sitio (p. ej. instagram.com)
3. Exporta con la extensión → copia el texto
4. Pégalo en `/cookies` y pulsa **Save** (el formato se valida solo)

**La página muestra:** estado del archivo, tarjetas por sitio (✅ Ready · ❌ Login missing · ⚠️ Expired · ○ Optional), **prueba en vivo** (Test Now, 10–30 seg) y borrado en un clic. Sin reiniciar.

---

## 5. Problemas comunes

| Error / Síntoma | Causa + solución |
|---|---|
| `members-only / Join this channel` | Video de pago — prueba con un canal público |
| `Unable to extract data` (Instagram) | Falta sesión → importa cookies |
| `login required` / `AuthRequired` / 0 items | Cookies ausentes/expiradas → reimporta + Test (X necesita `auth_token` con sesión) |
| Check girando mucho rato | Normal — hay una descarga en curso, mira la barra de progreso |
| `0 new` | Sin subidas nuevas, o todo ya está en la BD |

---

## 6. Estructura del proyecto

```
downloader/
├── app.py               # Panel Flask + planificador + pool de hilos
├── downloader.py        # Motor yt-dlp/gallery-dl
├── database.py          # SQLite: perfiles, videos (done/skipped/seen), ajustes
├── translations.py      # Textos UI: en / ur / es / zh
├── data.db              # Base de datos (auto-creada)
├── downloads/           # Una carpeta por prospecto
├── cookies.txt          # Tus cookies (desde el panel, nunca hacer commit)
├── templates/           # dashboard, edit, cookies, settings
├── requirements.txt
└── server.log
```

**⚙ Rendimiento (`/settings`):** workers paralelos 1–10 + calculadora auto (CPU/RAM/red).
