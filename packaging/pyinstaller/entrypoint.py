"""Точка входа для PyInstaller-сборки GUI.

Отдельный файл (а не сам ramus_rsf_tool/gui/app.py) нужен, чтобы
PyInstaller анализировал зависимости от корня "скрипта", а сам пакет
ramus_rsf_tool оставался обычным импортируемым модулем -- так его можно
по-прежнему `pip install -e .` и использовать как библиотеку отдельно от
сборки установщиков.
"""
import sys

from ramus_rsf_tool.gui.app import main

if __name__ == "__main__":
    sys.exit(main())
