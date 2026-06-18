"""Dark theme tokens mirroring the AstralBody web palette, applied via Qt
stylesheets so the native widgets read as the same product."""
from __future__ import annotations

# Core palette (approximates the web app's astral-* CSS variables).
BG = "#0b0f14"
SURFACE = "#141a21"
SURFACE_2 = "#1b232c"
BORDER = "#243040"
TEXT = "#e6edf3"
MUTED = "#8b97a6"
PRIMARY = "#3b82f6"
PRIMARY_SOFT = "rgba(59,130,246,0.15)"

VARIANT_COLORS = {
    "info": ("#3b82f6", "rgba(59,130,246,0.12)"),
    "success": ("#22c55e", "rgba(34,197,94,0.12)"),
    "warning": ("#f59e0b", "rgba(245,158,11,0.12)"),
    "error": ("#ef4444", "rgba(239,68,68,0.12)"),
    "accent": ("#a855f7", "rgba(168,85,247,0.12)"),
    "default": (MUTED, "rgba(139,151,166,0.12)"),
}

APP_STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-size: 14px;
           font-family: 'Segoe UI', system-ui, sans-serif; }}
QScrollArea, QScrollArea > QWidget > QWidget {{ background: {BG}; border: none; }}
QLineEdit, QPlainTextEdit, QTextEdit {{ background: {SURFACE_2}; border: 1px solid {BORDER};
           border-radius: 8px; padding: 8px; color: {TEXT}; selection-background-color: {PRIMARY}; }}
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px;
           padding: 7px 14px; color: {TEXT}; }}
QPushButton:hover {{ border-color: {PRIMARY}; }}
QPushButton#primary {{ background: {PRIMARY}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: #2f6fe0; }}
QTableWidget {{ background: {SURFACE}; gridline-color: {BORDER}; border: 1px solid {BORDER};
           border-radius: 8px; }}
QHeaderView::section {{ background: {SURFACE_2}; color: {MUTED}; border: none;
           border-bottom: 1px solid {BORDER}; padding: 6px 10px; font-weight: 600; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 14px; border: none; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {PRIMARY}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 8px; }}
QScrollBar:vertical {{ background: {BG}; width: 10px; }}
QScrollBar::handle:vertical {{ background: {BORDER}; border-radius: 5px; min-height: 24px; }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
"""
