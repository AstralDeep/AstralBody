"""Theme tokens mirroring the AstralBody web palette (backend/webrender/static/
astral.css `:root`) so the native client reads as the same product:
indigo→purple accent, #0F1221 bg with corner glows, layered translucent
surfaces, soft white borders, Inter type."""
from __future__ import annotations

# Core palette — exact web tokens.
BG = "#0F1221"          # --astral-bg
SURFACE = "#14172a"     # --surface-1 (astral-surface @ ~45% over bg)
SURFACE_2 = "#1a1e2e"   # --surface-3 (raised, solid)
BORDER = "rgba(255,255,255,0.08)"  # --border-soft
TEXT = "#F3F4F6"        # --astral-text
MUTED = "#9CA3AF"       # --astral-muted
PRIMARY = "#6366F1"     # --astral-primary (indigo)
SECONDARY = "#8B5CF6"   # --astral-secondary (purple)
ACCENT = "#06B6D4"      # --astral-accent (cyan)
PRIMARY_SOFT = "rgba(99,102,241,0.15)"

# 135° indigo→purple accent gradient (hero / primary button).
GRAD = (f"qlineargradient(x1:0, y1:0, x2:1, y2:1, "
        f"stop:0 {PRIMARY}, stop:1 {SECONDARY})")

VARIANT_COLORS = {
    "info": ("#3B82F6", "rgba(59,130,246,0.14)"),
    "success": ("#22C55E", "rgba(34,197,94,0.14)"),
    "warning": ("#EAB308", "rgba(234,179,8,0.14)"),
    "error": ("#EF4444", "rgba(239,68,68,0.14)"),
    "accent": ("#06B6D4", "rgba(6,182,212,0.14)"),
    "default": (PRIMARY, "rgba(99,102,241,0.14)"),
}

FONT = "'Inter', 'Segoe UI', system-ui, sans-serif"
MONO = "'JetBrains Mono', 'Cascadia Code', Consolas, monospace"

# Root background carries the same corner radial glows as the web body.
_ROOT_BG = (f"qradialgradient(cx:0.85, cy:-0.05, radius:0.9, "
            f"stop:0 rgba(139,92,246,0.10), stop:0.6 transparent), "
            f"qradialgradient(cx:-0.05, cy:1.05, radius:0.9, "
            f"stop:0 rgba(99,102,241,0.08), stop:0.55 transparent), {BG}")

APP_STYLESHEET = f"""
* {{ font-family: {FONT}; }}
QWidget {{ background: transparent; color: {TEXT}; font-size: 14px; }}
QLabel {{ background: transparent; border: none; }}
QMainWindow, QWidget#root {{ background: {BG}; }}
QScrollArea {{ background: transparent; border: none; }}
QLineEdit, QPlainTextEdit, QTextEdit {{ background: {SURFACE_2}; border: 1px solid {BORDER};
           border-radius: 10px; padding: 9px 12px; color: {TEXT};
           selection-background-color: {PRIMARY}; }}
QLineEdit:focus {{ border: 1px solid rgba(99,102,241,0.8); }}
QPushButton {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 10px;
           padding: 8px 16px; color: {TEXT}; }}
QPushButton:hover {{ border-color: {PRIMARY}; }}
QPushButton#primary {{ background: {GRAD}; border: none; color: white; font-weight: 600; }}
QPushButton#primary:hover {{ background: {SECONDARY}; }}
QTableWidget {{ background: {SURFACE}; gridline-color: {BORDER}; border: 1px solid {BORDER};
           border-radius: 10px; }}
QTableWidget::item {{ padding: 4px 8px; color: {TEXT}; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none;
           border-bottom: 1px solid {BORDER}; padding: 8px 10px; font-weight: 600; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 8px 16px; border: none; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {PRIMARY}; }}
QTabWidget::pane {{ border: 1px solid {BORDER}; border-radius: 10px; }}
QSplitter::handle {{ background: {BORDER}; width: 1px; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(99,102,241,0.3); border-radius: 5px; min-height: 28px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(99,102,241,0.55); }}
QScrollBar::add-line, QScrollBar::sub-line {{ height: 0; }}
QScrollBar::add-page, QScrollBar::sub-page {{ background: transparent; }}
"""

ROOT_BG_STYLE = f"QWidget#root {{ background: {_ROOT_BG}; }}"
