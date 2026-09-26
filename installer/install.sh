#!/usr/bin/env bash
# CreatorWatch Linux installer — install path khud do (default: ~/.local/share/creatorwatch)
set -e
DEFAULT_DIR="$HOME/.local/share/creatorwatch"
APP_DIR="${1:-$DEFAULT_DIR}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
ROOT="$(dirname "$SCRIPT_DIR")"
SRC="$ROOT"

echo "== CreatorWatch installer =="
echo "Install path: $APP_DIR"
command -v python3 >/dev/null || { echo "python3 chahiye: sudo apt install python3 python3-venv python3-pip"; exit 1; }
echo "(Desktop window ke liye webkit: sudo apt install python3-gi gir1.2-webkit2-4.1  — warna browser mode chalega)"

mkdir -p "$APP_DIR"
cp -r "$SRC/app.py" "$SRC/database.py" "$SRC/downloader.py" "$SRC/paths.py" "$SRC/engines.py" "$SRC/translations.py" "$SRC/requirements.txt" "$SRC/templates" "$APP_DIR/"
python3 -m venv "$APP_DIR/venv"
"$APP_DIR/venv/bin/python" -m pip install --upgrade pip
"$APP_DIR/venv/bin/python" -m pip install -r "$APP_DIR/requirements.txt"

mkdir -p "$HOME/.local/bin" "$HOME/.local/share/applications"
cat > "$HOME/.local/bin/creatorwatch" <<EOF
#!/usr/bin/env bash
cd "$APP_DIR" && exec "$APP_DIR/venv/bin/python" app.py --app "\$@"
EOF
chmod +x "$HOME/.local/bin/creatorwatch"
cat > "$HOME/.local/share/applications/creatorwatch.desktop" <<EOF
[Desktop Entry]
Name=CreatorWatch
Comment=Auto-track YouTube/TikTok/Instagram/X
Exec=$HOME/.local/bin/creatorwatch
Icon=video
Terminal=false
Type=Application
Categories=AudioVideo;
EOF
echo "Done. Run: creatorwatch  (ya app menu se CreatorWatch)"
echo "Uninstall: $APP_DIR/uninstall.sh"
cp "$SCRIPT_DIR/uninstall.sh" "$APP_DIR/uninstall.sh" 2>/dev/null || true
