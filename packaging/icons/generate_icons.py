#!/usr/bin/env python3
"""
Генерирует иконки приложения из единого источника
(ramus_rsf_tool/gui/resources/ramus-rsf-tool.svg) для всех трёх
устанавливаемых пакетов:

    packaging/icons/ramus-rsf-tool.ico    -- Windows (Inno Setup, .exe)
    packaging/icons/ramus-rsf-tool.icns   -- macOS (.app/.dmg)
    packaging/icons/png/<N>.png           -- растровые PNG, N = сторона
                                              в пикселях (используются
                                              Linux/AppImage-упаковкой и
                                              как источник для .ico/.icns)
    ramus_rsf_tool/gui/resources/icons/<N>.png -- те же PNG, но внутри
                                              самого пакета -- их использует
                                              приложение в рантайме для
                                              QApplication.setWindowIcon()
                                              (значок окна/панели задач),
                                              работает как из исходников,
                                              так и из PyInstaller-сборки.

Требует: pip install cairosvg Pillow icnsutil
Запуск:  python3 packaging/icons/generate_icons.py
Результат нужно перегенерировать только при изменении самого SVG --
готовые файлы уже закоммичены в репозиторий.
"""
from __future__ import annotations

import pathlib

import cairosvg
from PIL import Image

ROOT = pathlib.Path(__file__).resolve().parent.parent.parent
SVG_SRC = ROOT / "ramus_rsf_tool" / "gui" / "resources" / "ramus-rsf-tool.svg"
OUT_DIR = pathlib.Path(__file__).resolve().parent
PNG_DIR = OUT_DIR / "png"
APP_ICON_DIR = ROOT / "ramus_rsf_tool" / "gui" / "resources" / "icons"

SIZES = (16, 24, 32, 48, 64, 128, 256, 512, 1024)
# Подмножество, встраиваемое в сам пакет для QApplication.setWindowIcon().
APP_ICON_SIZES = (16, 32, 48, 128, 256)


def render_pngs() -> dict[int, pathlib.Path]:
    PNG_DIR.mkdir(parents=True, exist_ok=True)
    APP_ICON_DIR.mkdir(parents=True, exist_ok=True)
    paths = {}
    for size in SIZES:
        out = PNG_DIR / f"{size}.png"
        cairosvg.svg2png(url=str(SVG_SRC), write_to=str(out),
                          output_width=size, output_height=size)
        paths[size] = out
        if size in APP_ICON_SIZES:
            (APP_ICON_DIR / f"{size}.png").write_bytes(out.read_bytes())
    return paths


def build_ico(pngs: dict[int, pathlib.Path]) -> None:
    ico_sizes = [16, 24, 32, 48, 64, 128, 256]
    base = Image.open(pngs[max(ico_sizes)]).convert("RGBA")
    out = OUT_DIR / "ramus-rsf-tool.ico"
    base.save(out, format="ICO", sizes=[(s, s) for s in ico_sizes])
    print("wrote", out)


def build_icns(pngs: dict[int, pathlib.Path]) -> None:
    import icnsutil
    out = OUT_DIR / "ramus-rsf-tool.icns"
    img = icnsutil.IcnsFile()
    # icnsutil picks the correct OSType per size automatically. 64px has no
    # standalone classic OSType (only as the @2x retina render of 32px), so
    # it's deliberately left out here.
    for size in (16, 32, 128, 256, 512, 1024):
        img.add_media(file=str(pngs[size]))
    img.write(str(out))
    print("wrote", out)


def main():
    pngs = render_pngs()
    print("wrote", len(pngs), "PNGs to", PNG_DIR)
    print("wrote", len(APP_ICON_SIZES), "app-icon PNGs to", APP_ICON_DIR)
    build_ico(pngs)
    build_icns(pngs)


if __name__ == "__main__":
    main()
