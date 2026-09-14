#!/usr/bin/env bash
# Оборачивает dist/RamusRSFEditor.app (результат PyInstaller BUNDLE(), см.
# packaging/pyinstaller/ramus-rsf-gui.spec) в обычный для macOS
# установочный образ .dmg: открыл -> перетащил значок в Applications ->
# готово, без прав администратора и без Terminal.
#
# Использование (обычно вызывается из CI на macos-latest, см.
# .github/workflows/release.yml):
#   packaging/macos/build_dmg.sh <версия>
#
# Требует: create-dmg (macOS: `brew install create-dmg`).
set -euo pipefail

VERSION="${1:?Использование: build_dmg.sh <версия>, например build_dmg.sh 1.1.0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
APP_PATH="$ROOT_DIR/dist/RamusRSFEditor.app"
OUT_DIR="$ROOT_DIR/dist/installer"
OUT_DMG="$OUT_DIR/RamusRSFEditor-$VERSION.dmg"
VOLICON="$ROOT_DIR/packaging/icons/ramus-rsf-tool.icns"

if [ ! -d "$APP_PATH" ]; then
    echo "error: $APP_PATH не найден -- сначала соберите его через" >&2
    echo "       pyinstaller packaging/pyinstaller/ramus-rsf-gui.spec --noconfirm" >&2
    exit 1
fi

if ! command -v create-dmg >/dev/null 2>&1; then
    echo "error: create-dmg не найден в PATH -- установите: brew install create-dmg" >&2
    exit 1
fi

mkdir -p "$OUT_DIR"
rm -f "$OUT_DMG"

# create-dmg возвращает ненулевой код, если "finder polish" (позиции
# иконок и т.п.) не удался в headless-окружении CI -- сам образ при этом
# обычно всё равно валиден, поэтому не считаем это фатальной ошибкой, но
# проверяем, что файл реально появился.
create-dmg \
    --volname "Редактор Ramus RSF $VERSION" \
    --volicon "$VOLICON" \
    --window-size 540 380 \
    --icon-size 128 \
    --icon "RamusRSFEditor.app" 140 170 \
    --hide-extension "RamusRSFEditor.app" \
    --app-drop-link 400 170 \
    "$OUT_DMG" \
    "$APP_PATH" \
    || true

if [ ! -f "$OUT_DMG" ]; then
    echo "error: $OUT_DMG не был создан" >&2
    exit 1
fi

echo "wrote $OUT_DMG"
