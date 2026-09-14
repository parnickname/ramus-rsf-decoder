"""
Переключатель светлой/тёмной темы.

Реализовано через QPalette на стиле "Fusion", без сторонних зависимостей
(qdarkstyle и т. п.) -- это даёт одинаковый вид на Windows/macOS/Linux,
чего нативные стили Qt по отдельности не гарантируют. Настройка
запоминается через QSettings (ключ "ui/dark_theme") и применяется заново
при следующем запуске приложения.
"""
from __future__ import annotations

from PyQt6.QtCore import QSettings
from PyQt6.QtGui import QColor, QPalette
from PyQt6.QtWidgets import QApplication, QStyleFactory

_SETTINGS_KEY = "ui/dark_theme"

# Стиль "Fusion" не зависит от платформы и полностью подчиняется палитре,
# в отличие от нативных стилей (windowsvista, macos, ...), которые часть
# цветов берут из системной темы и игнорируют QPalette.
_BASE_STYLE = "Fusion"


def _dark_palette() -> QPalette:
    p = QPalette()
    window = QColor(45, 45, 48)
    base = QColor(30, 30, 30)
    alt_base = QColor(40, 40, 40)
    text = QColor(225, 225, 225)
    disabled_text = QColor(127, 127, 127)
    highlight = QColor(58, 110, 165)

    p.setColor(QPalette.ColorRole.Window, window)
    p.setColor(QPalette.ColorRole.WindowText, text)
    p.setColor(QPalette.ColorRole.Base, base)
    p.setColor(QPalette.ColorRole.AlternateBase, alt_base)
    p.setColor(QPalette.ColorRole.ToolTipBase, window)
    p.setColor(QPalette.ColorRole.ToolTipText, text)
    p.setColor(QPalette.ColorRole.Text, text)
    p.setColor(QPalette.ColorRole.Button, window)
    p.setColor(QPalette.ColorRole.ButtonText, text)
    p.setColor(QPalette.ColorRole.BrightText, QColor(255, 80, 80))
    p.setColor(QPalette.ColorRole.Link, QColor(100, 160, 220))
    p.setColor(QPalette.ColorRole.Highlight, highlight)
    p.setColor(QPalette.ColorRole.HighlightedText, QColor(255, 255, 255))

    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.WindowText, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Text, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.ButtonText, disabled_text)
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.Highlight, QColor(80, 80, 80))
    p.setColor(QPalette.ColorGroup.Disabled, QPalette.ColorRole.HighlightedText, disabled_text)
    return p


# Палитра по умолчанию для выбранного стиля, снятая один раз при первом
# импорте (до того, как к ней кто-либо прикоснётся) -- используется, чтобы
# вернуться к светлой теме точно в её исходном виде.
_LIGHT_PALETTE: QPalette = QStyleFactory.create(_BASE_STYLE).standardPalette()


def apply_theme(app: QApplication, dark: bool) -> None:
    """Применить тёмную или светлую тему ко всему приложению немедленно."""
    app.setStyle(_BASE_STYLE)
    app.setPalette(_dark_palette() if dark else _LIGHT_PALETTE)


def is_dark_saved() -> bool:
    return QSettings().value(_SETTINGS_KEY, False, type=bool)


def set_dark_saved(dark: bool) -> None:
    QSettings().setValue(_SETTINGS_KEY, dark)


def apply_saved_theme(app: QApplication) -> None:
    """Вызывается при запуске: применяет тему, сохранённую с прошлого
    раза (по умолчанию -- светлая)."""
    apply_theme(app, is_dark_saved())
