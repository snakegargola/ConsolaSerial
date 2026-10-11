"""Shared visual system for the desktop application.

The stylesheet intentionally lives outside feature widgets. Hardware panels
only declare semantic roles (primary, danger, status, muted), which keeps visual
changes independent from protocol logic.
"""

from functools import lru_cache
from pathlib import Path

from PyQt6.QtGui import QColor, QPalette

_ICONS = (Path(__file__).resolve().parent.parent / "assets" / "ui").as_posix()


DARK = {
    "window": "#11151C", "surface": "#191F29", "raised": "#242D3A",
    "input": "#121821", "border": "#354152", "border_hover": "#738399",
    "text": "#E8EDF5", "muted": "#A6B3C5", "accent": "#2563EB",
    "accent_hover": "#1D4ED8", "accent_text": "#8AB4FF", "accent_soft": "#213452",
    "success": "#15803D", "success_text": "#86EFAC", "success_bg": "#172D25",
    "warning": "#FBBF24", "warning_bg": "#352C1D",
    "danger": "#B91C1C", "danger_text": "#FCA5A5", "danger_bg": "#36232A",
    "selection": "#284978", "disabled": "#8895A7",
}

LIGHT = {
    "window": "#EDF1F6", "surface": "#FFFFFF", "raised": "#F3F6FA",
    "input": "#FFFFFF", "border": "#B8C4D3", "border_hover": "#60738C",
    "text": "#172335", "muted": "#52637A", "accent": "#2563EB",
    "accent_hover": "#1D4ED8", "accent_text": "#1D4ED8", "accent_soft": "#EAF1FF",
    "success": "#15803D", "success_text": "#166534", "success_bg": "#EAF7EE",
    "warning": "#B45309", "warning_bg": "#FEF3C7",
    "danger": "#B91C1C", "danger_text": "#B91C1C", "danger_bg": "#FDEEEF",
    "selection": "#DCE8FC", "disabled": "#6F7E91",
}


@lru_cache(maxsize=2)
def stylesheet(theme="dark"):
    """Return the complete application QSS for one color theme."""
    c = LIGHT if str(theme).lower() == "light" else DARK
    icon_theme = "light" if c is LIGHT else "dark"
    return f"""
    QWidget {{
        font-family: "Noto Sans", "DejaVu Sans", sans-serif;
        font-size: 10pt;
        color: {c['text']};
    }}
    QMainWindow, QDialog {{ background: {c['window']}; color: {c['text']}; }}
    QWidget#appSurface {{ background: {c['window']}; }}
    QTextEdit[role="console"], QWidget[role="monospace"] {{
        font-family: "DejaVu Sans Mono", "Noto Sans Mono", monospace;
    }}
    QTextEdit[role="console"] {{ padding: 10px; min-height: 100px; }}
    QLabel {{ background: transparent; }}
    QLabel#pageTitle {{ font-size: 15pt; font-weight: 600; color: {c['text']}; }}
    QLabel#pageSubtitle, QLabel[role="muted"] {{ color: {c['muted']}; }}
    QLabel[role="hint"] {{
        color: {c['muted']}; background: {c['raised']};
        border: 1px solid {c['border']}; border-radius: 6px; padding: 7px 10px;
    }}
    QLabel[role="warning"] {{
        color: {c['warning']}; background: {c['warning_bg']};
        border: 1px solid {c['border']}; border-left: 3px solid {c['warning']};
        border-radius: 6px; padding: 7px 10px;
    }}
    QLabel[status="ok"] {{
        color: {c['success_text']}; background: {c['success_bg']};
        border: 1px solid {c['success']}; border-radius: 6px; padding: 7px 10px;
        font-weight: 600;
    }}
    QLabel[status="error"] {{
        color: {c['danger_text']}; background: {c['danger_bg']};
        border: 1px solid {c['danger']}; border-radius: 6px; padding: 7px 10px;
        font-weight: 600;
    }}
    QLabel[status="busy"] {{
        color: {c['warning']}; background: {c['warning_bg']};
        border: 1px solid {c['warning']}; border-radius: 7px; padding: 7px 10px;
        font-weight: 600;
    }}
    QGroupBox {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 8px; margin-top: 14px; padding: 8px 10px;
        font-weight: 600;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 12px; padding: 0 6px; color: {c['muted']};
    }}
    QFrame[role="card"], QWidget[role="card"] {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 9px;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {c['input']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 5px 8px; min-height: 20px;
        selection-background-color: {c['selection']}; selection-color: {c['text']};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['accent_text']}; }}
    QLineEdit[readOnly="true"] {{ background: {c['raised']}; }}
    QLineEdit[status="error"] {{ color: {c['danger_text']}; border-color: {c['danger']}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled {{
        color: {c['disabled']}; background: {c['raised']};
    }}
    QComboBox {{ padding-right: 8px; }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox::down-arrow {{ image: url("{_ICONS}/down-{icon_theme}.svg"); width: 14px; height: 14px; }}
    QSpinBox, QDoubleSpinBox {{ padding-right: 4px; }}
    QSpinBox::up-button, QDoubleSpinBox::up-button {{
        subcontrol-origin: border; subcontrol-position: top right;
        width: 20px; border-left: 1px solid {c['border']};
    }}
    QSpinBox::down-button, QDoubleSpinBox::down-button {{
        subcontrol-origin: border; subcontrol-position: bottom right;
        width: 20px; border-left: 1px solid {c['border']};
    }}
    QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
        image: url("{_ICONS}/up-{icon_theme}.svg"); width: 12px; height: 12px;
    }}
    QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
        image: url("{_ICONS}/down-{icon_theme}.svg"); width: 12px; height: 12px;
    }}
    QComboBox QAbstractItemView {{
        background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
        selection-background-color: {c['selection']}; selection-color: {c['text']}; padding: 4px;
    }}
    QPushButton {{
        background: {c['raised']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 6px 10px; min-height: 20px; font-weight: 600;
    }}
    QPushButton[role="compact"] {{ padding: 0; min-height: 0; }}
    QPushButton[role="compact"][action="send"] {{ color: {c['success_text']}; }}
    QPushButton[role="compact"][action="delete"] {{ color: {c['danger_text']}; }}
    QPushButton:hover {{ border-color: {c['border_hover']}; background: {c['surface']}; }}
    QPushButton:pressed {{ background: {c['input']}; }}
    QPushButton:focus {{ border-color: {c['accent_text']}; }}
    QPushButton:disabled {{ color: {c['disabled']}; background: {c['raised']}; border-color: {c['border']}; }}
    QPushButton[role="primary"] {{
        color: white; background: {c['accent']}; border-color: {c['accent']}; font-weight: 700;
    }}
    QPushButton[role="primary"]:hover {{ background: {c['accent_hover']}; }}
    QPushButton[role="success"] {{
        color: white; background: {c['success']}; border-color: {c['success']}; font-weight: 700;
    }}
    QPushButton[role="danger"] {{
        color: white; background: {c['danger']}; border-color: {c['danger']}; font-weight: 700;
    }}
    QPushButton[role="ghost"] {{ background: transparent; border-color: transparent; color: {c['muted']}; }}
    QPushButton[role="primary"]:disabled, QPushButton[role="success"]:disabled,
    QPushButton[role="danger"]:disabled {{
        color: {c['disabled']}; background: {c['raised']}; border-color: {c['border']};
    }}
    QPushButton[role="primary"]:focus, QPushButton[role="success"]:focus,
    QPushButton[role="danger"]:focus {{ border: 2px solid {c['text']}; padding: 5px 9px; }}
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    QCheckBox::indicator:unchecked {{
        background: {c['input']}; border: 1px solid {c['border_hover']}; border-radius: 3px;
    }}
    QCheckBox::indicator:checked {{
        background: {c['accent']}; border: 1px solid {c['accent']}; border-radius: 3px;
        image: url("{_ICONS}/check.svg");
    }}
    QCheckBox::indicator:disabled {{ background: {c['raised']}; border-color: {c['border']}; }}
    QCheckBox:focus {{ color: {c['accent_text']}; }}
    QLabel[role="indicator"] {{
        color: {c['muted']}; background: {c['raised']};
        border: 1px solid {c['border']}; border-radius: 4px; padding: 3px 6px;
    }}
    QLabel[role="indicator"][status="ok"] {{
        color: {c['success_text']}; background: {c['success_bg']}; border-color: {c['success']};
    }}
    QTabWidget::pane {{
        background: {c['surface']}; border: 0; top: -1px;
    }}
    QTabBar::tab {{
        background: transparent; color: {c['muted']};
        padding: 8px 12px; margin-right: 4px; border-bottom: 2px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {c['text']}; background: {c['raised']}; }}
    QTabBar::tab:selected {{
        color: {c['accent_text']}; background: {c['accent_soft']}; border-bottom-color: {c['accent_text']};
    }}
    QScrollArea {{ background: {c['surface']}; border: 0; }}
    QScrollArea > QWidget > QWidget {{ background: {c['surface']}; }}
    QTableWidget, QTableView {{
        background: {c['surface']}; alternate-background-color: {c['raised']};
        color: {c['text']}; border: 1px solid {c['border']}; border-radius: 7px;
        gridline-color: {c['border']}; selection-background-color: {c['selection']};
        selection-color: {c['text']};
    }}
    QTableWidget:focus, QTableView:focus {{ border-color: {c['accent_text']}; }}
    QTableWidget::item, QTableView::item {{ padding: 5px; border: 0; }}
    QHeaderView::section {{
        background: {c['raised']}; color: {c['muted']}; border: 0;
        border-bottom: 1px solid {c['border']}; border-right: 1px solid {c['border']};
        padding: 7px 8px; font-weight: 700;
    }}
    QTableCornerButton::section {{ background: {c['raised']}; border: 1px solid {c['border']}; }}
    QSplitter::handle {{ background: {c['border']}; margin: 3px; border-radius: 2px; }}
    QProgressBar {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 5px;
        text-align: center; min-height: 16px;
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
    QStatusBar {{ background: {c['surface']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
    QStatusBar::item {{ border: 0; }}
    QMenu {{ background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']}; padding: 4px; }}
    QMenu::item {{ padding: 6px 20px; }}
    QMenu::item:selected {{ background: {c['selection']}; }}
    QToolTip {{
        background: {c['raised']}; color: {c['text']}; border: 1px solid {c['border_hover']};
        padding: 5px; border-radius: 4px;
    }}
    QScrollBar:vertical {{ background: transparent; width: 11px; margin: 2px; }}
    QScrollBar::handle:vertical {{ background: {c['border_hover']}; min-height: 28px; border-radius: 5px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar:horizontal {{ background: transparent; height: 11px; margin: 2px; }}
    QScrollBar::handle:horizontal {{ background: {c['border_hover']}; min-width: 28px; border-radius: 5px; }}
    QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
    QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
    """


def palette(theme="dark"):
    """Match native Qt arrows, checkboxes and dialogs to the QSS colors."""
    c = LIGHT if str(theme).lower() == "light" else DARK
    result = QPalette()
    for role, key in (
        (QPalette.ColorRole.Window, "window"),
        (QPalette.ColorRole.WindowText, "text"),
        (QPalette.ColorRole.Base, "input"),
        (QPalette.ColorRole.AlternateBase, "raised"),
        (QPalette.ColorRole.Text, "text"),
        (QPalette.ColorRole.Button, "raised"),
        (QPalette.ColorRole.ButtonText, "text"),
        (QPalette.ColorRole.Highlight, "selection"),
        (QPalette.ColorRole.HighlightedText, "text"),
        (QPalette.ColorRole.ToolTipBase, "raised"),
        (QPalette.ColorRole.ToolTipText, "text"),
        (QPalette.ColorRole.PlaceholderText, "muted"),
        (QPalette.ColorRole.Light, "border_hover"),
        (QPalette.ColorRole.Mid, "border"),
        (QPalette.ColorRole.Dark, "input"),
    ):
        result.setColor(role, QColor(c[key]))
    for role in (QPalette.ColorRole.Text, QPalette.ColorRole.WindowText, QPalette.ColorRole.ButtonText):
        result.setColor(QPalette.ColorGroup.Disabled, role, QColor(c["disabled"]))
    return result


def _set_style_property(widget, name, value):
    if widget.property(name) == value:
        return
    widget.setProperty(name, value)
    style = widget.style()
    style.unpolish(widget)
    style.polish(widget)
    widget.update()


def set_role(widget, role):
    """Assign a semantic role and force Qt to refresh its style."""
    _set_style_property(widget, "role", role)


def set_status(widget, status):
    """Assign ready/busy/ok/error presentation without protocol coupling."""
    _set_style_property(widget, "status", status)


def contrast_text(background):
    color = QColor(background)
    luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
    return "#000000" if luminance > 145 else "#FFFFFF"
