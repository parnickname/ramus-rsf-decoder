#!/usr/bin/env bash
# Собирает переносимый Linux .AppImage из результата PyInstaller-сборки
# (dist/RamusRSFEditor/, --onedir): скачал файл -> дал право на
# исполнение -> запустил, без установки и без root. Дополняет, а не
# заменяет, .rsf-специфичную установку через packaging/PKGBUILD (для тех,
# кто предпочитает системный пакетный менеджер Arch).
#
# Использование (обычно вызывается из CI на ubuntu-latest, см.
# .github/workflows/release.yml):
#   packaging/linux/build_appimage.sh <версия>
set -euo pipefail

VERSION="${1:?Использование: build_appimage.sh <версия>, например build_appimage.sh 1.1.0}"

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
DIST_DIR="$ROOT_DIR/dist/RamusRSFEditor"
APPDIR="$ROOT_DIR/build/AppDir"
OUT_DIR="$ROOT_DIR/dist/installer"
OUT_APPIMAGE="$OUT_DIR/RamusRSFEditor-$VERSION-x86_64.AppImage"

if [ ! -d "$DIST_DIR" ]; then
    echo "error: $DIST_DIR не найден -- сначала соберите его через" >&2
    echo "       pyinstaller packaging/pyinstaller/ramus-rsf-gui.spec --noconfirm" >&2
    exit 1
fi

rm -rf "$APPDIR"
mkdir -p "$APPDIR/usr/bin"
cp -a "$DIST_DIR/." "$APPDIR/usr/bin/"

# AppRun -- точка входа AppImage; запускает основной исполняемый файл
# сборки independent от того, куда в итоге распакован/смонтирован образ.
cat > "$APPDIR/AppRun" <<'EOF'
#!/bin/sh
HERE="$(dirname "$(readlink -f "${0}")")"
exec "$HERE/usr/bin/RamusRSFEditor" "$@"
EOF
chmod +x "$APPDIR/AppRun"
chmod +x "$APPDIR/usr/bin/RamusRSFEditor"

# .desktop и значок обязательны в корне AppDir -- appimagetool берёт из
# них имя/иконку для итогового .AppImage.
cp "$ROOT_DIR/packaging/icons/png/256.png" "$APPDIR/ramus-rsf-tool.png"
cp "$ROOT_DIR/ramus_rsf_tool/gui/resources/ramus-rsf-tool.svg" "$APPDIR/ramus-rsf-tool.svg"
sed 's#^Exec=.*#Exec=AppRun %f#' "$ROOT_DIR/packaging/ramus-rsf-tool.desktop" \
    > "$APPDIR/ramus-rsf-tool.desktop"

mkdir -p "$OUT_DIR"
rm -f "$OUT_APPIMAGE"

APPIMAGETOOL="$(command -v appimagetool || true)"
if [ -z "$APPIMAGETOOL" ]; then
    APPIMAGETOOL="$ROOT_DIR/build/appimagetool.AppImage"
    if [ ! -x "$APPIMAGETOOL" ]; then
        echo "appimagetool не найден в PATH -- скачиваю..." >&2
        curl -fsSL -o "$APPIMAGETOOL" \
            "https://github.com/AppImage/appimagetool/releases/download/continuous/appimagetool-x86_64.AppImage"
        chmod +x "$APPIMAGETOOL"
    fi
fi

# CI-контейнеры часто не имеют FUSE, из-за чего сам appimagetool (он тоже
# .AppImage) не может смонтироваться -- официальный обход:
# запуск в режиме "распаковать и выполнить".
APPIMAGE_EXTRACT_AND_RUN=1 "$APPIMAGETOOL" "$APPDIR" "$OUT_APPIMAGE"

echo "wrote $OUT_APPIMAGE"
