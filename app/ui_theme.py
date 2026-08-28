"""Shared visual system for the desktop application.

The stylesheet intentionally lives outside feature widgets. Hardware panels
only declare semantic roles (primary, danger, status, muted), which keeps visual
changes independent from protocol logic.
"""

from PyQt6.QtGui import QColor


DARK = {
    "window": "#0F172A", "surface": "#111827", "raised": "#1E293B",
    "input": "#0B1220", "border": "#334155", "border_hover": "#64748B",
    "text": "#E5E7EB", "muted": "#94A3B8", "accent": "#3B82F6",
    "accent_hover": "#60A5FA", "accent_soft": "#172554",
    "success": "#22C55E", "success_bg": "#052E16",
    "warning": "#F59E0B", "warning_bg": "#451A03",
    "danger": "#EF4444", "danger_bg": "#450A0A",
    "selection": "#1D4ED8", "disabled": "#475569",
}

LIGHT = {
    "window": "#F1F5F9", "surface": "#FFFFFF", "raised": "#F8FAFC",
    "input": "#FFFFFF", "border": "#CBD5E1", "border_hover": "#64748B",
    "text": "#0F172A", "muted": "#64748B", "accent": "#2563EB",
    "accent_hover": "#1D4ED8", "accent_soft": "#DBEAFE",
    "success": "#15803D", "success_bg": "#DCFCE7",
    "warning": "#B45309", "warning_bg": "#FEF3C7",
    "danger": "#DC2626", "danger_bg": "#FEE2E2",
    "selection": "#BFDBFE", "disabled": "#94A3B8",
}


def stylesheet(theme="dark"):
    """Return the complete application QSS for one color theme."""
    c = LIGHT if str(theme).lower() == "light" else DARK
    return f"""
    * {{
        font-family: "Inter", "Noto Sans", "DejaVu Sans", sans-serif;
        font-size: 10pt;
    }}
    QMainWindow, QDialog {{ background: {c['window']}; color: {c['text']}; }}
    QWidget {{ color: {c['text']}; }}
    QWidget#appSurface {{ background: {c['window']}; }}
    QLabel {{ background: transparent; }}
    QLabel#pageTitle {{ font-size: 17pt; font-weight: 700; color: {c['text']}; }}
    QLabel#pageSubtitle, QLabel[role="muted"] {{ color: {c['muted']}; }}
    QLabel[role="hint"] {{
        color: {c['muted']}; background: {c['raised']};
        border: 1px solid {c['border']}; border-radius: 7px; padding: 8px 10px;
    }}
    QLabel[role="warning"] {{
        color: {c['warning']}; background: {c['warning_bg']};
        border: 1px solid {c['warning']}; border-radius: 7px; padding: 8px 10px;
    }}
    QLabel[status="ok"] {{
        color: {c['success']}; background: {c['success_bg']};
        border: 1px solid {c['success']}; border-radius: 7px; padding: 7px 10px;
        font-weight: 600;
    }}
    QLabel[status="error"] {{
        color: {c['danger']}; background: {c['danger_bg']};
        border: 1px solid {c['danger']}; border-radius: 7px; padding: 7px 10px;
        font-weight: 600;
    }}
    QLabel[status="busy"] {{
        color: {c['warning']}; background: {c['warning_bg']};
        border: 1px solid {c['warning']}; border-radius: 7px; padding: 7px 10px;
        font-weight: 600;
    }}
    QGroupBox {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 9px; margin-top: 15px; padding: 14px 10px 10px 10px;
        font-weight: 650;
    }}
    QGroupBox::title {{
        subcontrol-origin: margin; subcontrol-position: top left;
        left: 12px; padding: 0 6px; color: {c['text']};
    }}
    QFrame[role="card"], QWidget[role="card"] {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 9px;
    }}
    QLineEdit, QTextEdit, QPlainTextEdit, QComboBox, QSpinBox, QDoubleSpinBox {{
        background: {c['input']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 5px 8px; min-height: 20px; selection-background-color: {c['selection']};
    }}
    QLineEdit:focus, QTextEdit:focus, QPlainTextEdit:focus, QComboBox:focus,
    QSpinBox:focus, QDoubleSpinBox:focus {{ border: 1px solid {c['accent']}; }}
    QLineEdit:disabled, QComboBox:disabled, QSpinBox:disabled {{
        color: {c['disabled']}; background: {c['raised']};
    }}
    QComboBox::drop-down {{ border: 0; width: 24px; }}
    QComboBox QAbstractItemView {{
        background: {c['surface']}; color: {c['text']}; border: 1px solid {c['border']};
        selection-background-color: {c['accent']}; padding: 4px;
    }}
    QPushButton {{
        background: {c['raised']}; color: {c['text']};
        border: 1px solid {c['border']}; border-radius: 6px;
        padding: 6px 11px; min-height: 20px; font-weight: 550;
    }}
    QPushButton:hover {{ border-color: {c['border_hover']}; background: {c['surface']}; }}
    QPushButton:pressed {{ background: {c['input']}; }}
    QPushButton:disabled {{ color: {c['disabled']}; border-color: {c['border']}; }}
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
    QCheckBox {{ spacing: 7px; }}
    QCheckBox::indicator {{ width: 16px; height: 16px; }}
    QTabWidget::pane {{
        background: {c['surface']}; border: 1px solid {c['border']};
        border-radius: 8px; top: -1px;
    }}
    QTabBar::tab {{
        background: transparent; color: {c['muted']};
        padding: 8px 13px; margin-right: 2px; border-bottom: 2px solid transparent;
        font-weight: 600;
    }}
    QTabBar::tab:hover {{ color: {c['text']}; background: {c['raised']}; }}
    QTabBar::tab:selected {{ color: {c['accent']}; border-bottom-color: {c['accent']}; }}
    QScrollArea {{ background: {c['surface']}; border: 0; }}
    QScrollArea > QWidget > QWidget {{ background: {c['surface']}; }}
    QTableWidget, QTableView {{
        background: {c['surface']}; alternate-background-color: {c['raised']};
        color: {c['text']}; border: 1px solid {c['border']}; border-radius: 7px;
        gridline-color: {c['border']}; selection-background-color: {c['selection']};
        selection-color: {c['text']}; outline: 0;
    }}
    QTableWidget::item, QTableView::item {{ padding: 5px; border: 0; }}
    QHeaderView::section {{
        background: {c['raised']}; color: {c['muted']}; border: 0;
        border-bottom: 1px solid {c['border']}; border-right: 1px solid {c['border']};
        padding: 7px 8px; font-weight: 700;
    }}
    QSplitter::handle {{ background: {c['border']}; margin: 3px; border-radius: 2px; }}
    QProgressBar {{
        background: {c['input']}; border: 1px solid {c['border']}; border-radius: 5px;
        text-align: center; min-height: 16px;
    }}
    QProgressBar::chunk {{ background: {c['accent']}; border-radius: 4px; }}
    QStatusBar {{ background: {c['surface']}; color: {c['muted']}; border-top: 1px solid {c['border']}; }}
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
    """


def set_role(widget, role):
    """Assign a semantic role and force Qt to refresh its style."""
    widget.setProperty("role", role)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def set_status(widget, status):
    """Assign ready/busy/ok/error presentation without protocol coupling."""
    widget.setProperty("status", status)
    widget.style().unpolish(widget)
    widget.style().polish(widget)


def contrast_text(background):
    color = QColor(background)
    luminance = 0.299 * color.red() + 0.587 * color.green() + 0.114 * color.blue()
    return "#000000" if luminance > 145 else "#FFFFFF"
