#!/usr/bin/env bash
# CreatorWatch Linux uninstaller
set -e
APP_DIR="$(cd "$(dirname "$0")" && pwd)"
rm -f "$HOME/.local/bin/creatorwatch" "$HOME/.local/share/applications/creatorwatch.desktop"
rm -rf "$APP_DIR"
echo "CreatorWatch uninstalled."
