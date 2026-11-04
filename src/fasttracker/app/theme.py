"""Dark, professional, flat theme: graphite surfaces, one teal accent, modest radii."""

ACCENT = "#2dd4bf"       # teal
ACCENT_DIM = "rgba(45,212,191,0.18)"
GREEN = "#34d399"
RED = "#f87171"
ORANGE = "#fbbf24"
TEXT = "#e6e8ec"
MUTED = "rgba(230,232,236,0.62)"
FAINT = "rgba(230,232,236,0.36)"
MUTED_HEX = "#9ba0a8"      # opaque equivalents for QColor (which does not parse rgba())
FAINT_HEX = "#5f646c"
BG = "#121417"
SURFACE = "#1a1d22"
SURFACE_2 = "#20242a"
BORDER = "rgba(255,255,255,0.08)"
FIELD = "#0f1114"
FIELD_BORDER = "rgba(255,255,255,0.10)"

FONT_FAMILY = "Segoe UI Variable Text, Segoe UI, Inter, SF Pro Text, Helvetica Neue, Arial"
MONO = "Cascadia Mono, Consolas, JetBrains Mono, monospace"

STYLESHEET = f"""
* {{ font-family: {FONT_FAMILY}; }}
QWidget {{ color: {TEXT}; font-size: 13px; background: transparent; }}
QMainWindow, QDialog {{ background: {BG}; }}
QToolTip {{ background: {SURFACE_2}; color: {TEXT}; border: 1px solid {BORDER}; padding: 6px 8px; border-radius: 6px; }}

QFrame#Card {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#Panel {{ background: {SURFACE}; border: 1px solid {BORDER}; border-radius: 10px; }}
QFrame#TopBar {{ background: {SURFACE}; border-bottom: 1px solid {BORDER}; }}
QLabel#CardTitle {{ font-size: 12px; font-weight: 600; letter-spacing: 0.8px; color: {MUTED}; }}
QLabel#Hint {{ color: {MUTED}; font-size: 12px; }}
QLabel#Faint {{ color: {FAINT}; font-size: 12px; }}
QLabel#Big {{ font-size: 30px; font-weight: 700; }}
QLabel#Title {{ font-size: 17px; font-weight: 700; letter-spacing: -0.2px; }}
QLabel#Warn {{ color: {ORANGE}; font-size: 12px; }}
QLabel#Mono {{ font-family: {MONO}; font-size: 12px; color: {MUTED}; }}

QPushButton {{
    background: {SURFACE_2}; border: 1px solid {FIELD_BORDER}; border-radius: 7px;
    padding: 7px 14px; min-height: 18px; font-weight: 600;
}}
QPushButton:hover {{ background: #2a2f36; border-color: rgba(255,255,255,0.16); }}
QPushButton:pressed {{ background: #343a42; }}
QPushButton:disabled {{ color: {FAINT}; background: rgba(255,255,255,0.03); border-color: rgba(255,255,255,0.05); }}
QPushButton#Primary {{ background: {ACCENT}; border-color: transparent; color: #04211c; }}
QPushButton#Primary:hover {{ background: #5eead4; }}
QPushButton#Primary:disabled {{ background: rgba(45,212,191,0.25); color: rgba(255,255,255,0.45); }}
QPushButton#Go {{ background: {ACCENT}; border-color: transparent; color: #04211c; font-size: 14px; padding: 9px 22px; }}
QPushButton#Go:hover {{ background: #5eead4; }}
QPushButton#Go:disabled {{ background: rgba(45,212,191,0.22); color: rgba(255,255,255,0.4); }}
QPushButton#Danger {{ background: rgba(248,113,113,0.16); border-color: rgba(248,113,113,0.45); color: {RED}; }}
QPushButton#Danger:hover {{ background: rgba(248,113,113,0.28); }}
QPushButton#Danger:disabled {{ background: rgba(248,113,113,0.06); border-color: rgba(248,113,113,0.12); color: rgba(248,113,113,0.35); }}
QPushButton#Round {{ border-radius: 7px; padding: 0; min-width: 32px; max-width: 32px; min-height: 32px; max-height: 32px; }}
QPushButton#Seg {{ border-radius: 5px; padding: 5px 12px; min-height: 16px; font-weight: 500; background: transparent; border: none; color: {MUTED}; }}
QPushButton#Seg:checked {{ background: {SURFACE_2}; color: {TEXT}; font-weight: 600; border: 1px solid {FIELD_BORDER}; }}
QFrame#SegGroup {{ background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: 7px; }}
QPushButton#Link {{ background: transparent; border: none; color: {ACCENT}; padding: 2px 4px; font-weight: 500; }}
QPushButton#Link:hover {{ text-decoration: underline; }}

QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {{
    background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: 7px; padding: 6px 10px;
    selection-background-color: {ACCENT}; selection-color: #04211c;
}}
QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {{ border: 1px solid {ACCENT}; }}
QLineEdit:disabled, QSpinBox:disabled, QDoubleSpinBox:disabled, QComboBox:disabled {{ color: {FAINT}; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 16px; border: none; background: transparent; }}
QComboBox::drop-down {{ border: none; width: 24px; }}
QComboBox QAbstractItemView {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 6px;
    selection-background-color: {ACCENT_DIM}; selection-color: {TEXT}; padding: 4px; outline: none; }}

QSlider::groove:horizontal {{ height: 4px; background: rgba(255,255,255,0.14); border-radius: 2px; }}
QSlider::sub-page:horizontal {{ background: {ACCENT}; border-radius: 2px; }}
QSlider::handle:horizontal {{ background: {TEXT}; width: 14px; height: 14px; margin: -5px 0; border-radius: 7px; border: 1px solid rgba(0,0,0,0.3); }}

QCheckBox {{ spacing: 9px; }}
QCheckBox::indicator {{ width: 34px; height: 18px; border-radius: 9px; background: rgba(120,125,135,0.45); }}
QCheckBox::indicator:checked {{ background: {ACCENT}; }}
QCheckBox::indicator:disabled {{ background: rgba(120,125,135,0.2); }}
QCheckBox:disabled {{ color: {FAINT}; }}

QListWidget, QTableWidget {{ background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: 8px; padding: 4px; outline: none; gridline-color: transparent; }}
QListWidget::item {{ border-radius: 5px; padding: 5px 6px; color: {MUTED}; }}
QListWidget::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QListWidget::item:hover {{ background: rgba(255,255,255,0.05); }}
QListWidget::indicator {{ width: 15px; height: 15px; border-radius: 4px; border: 1px solid rgba(255,255,255,0.25); background: transparent; }}
QListWidget::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; }}
QTableWidget::item {{ padding: 4px 8px; }}
QTableWidget::item:selected {{ background: {ACCENT_DIM}; color: {TEXT}; }}
QHeaderView::section {{ background: transparent; color: {MUTED}; border: none; border-bottom: 1px solid {BORDER}; padding: 5px 8px; font-weight: 600; font-size: 11px; letter-spacing: 0.6px; }}
QTableWidget QTableCornerButton::section {{ background: transparent; border: none; }}

QPlainTextEdit {{ background: {FIELD}; border: 1px solid {FIELD_BORDER}; border-radius: 8px; padding: 6px; font-family: {MONO}; font-size: 12px; color: {MUTED}; }}
QScrollArea {{ border: none; }}
QScrollBar:vertical {{ background: transparent; width: 9px; margin: 2px; }}
QScrollBar::handle:vertical {{ background: rgba(255,255,255,0.18); border-radius: 4px; min-height: 30px; }}
QScrollBar::handle:vertical:hover {{ background: rgba(255,255,255,0.3); }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
QScrollBar:horizontal {{ background: transparent; height: 9px; margin: 2px; }}
QScrollBar::handle:horizontal {{ background: rgba(255,255,255,0.18); border-radius: 4px; min-width: 30px; }}
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{ width: 0; }}
QMenu {{ background: {SURFACE_2}; border: 1px solid {BORDER}; border-radius: 8px; padding: 5px; }}
QMenu::item {{ padding: 6px 20px; border-radius: 5px; }}
QMenu::item:selected {{ background: rgba(255,255,255,0.08); }}
QMessageBox {{ background: {SURFACE}; }}
QSplitter::handle {{ background: transparent; }}
QTabWidget::pane {{ border: none; }}
QTabBar::tab {{ background: transparent; color: {MUTED}; padding: 7px 14px; border-bottom: 2px solid transparent; font-weight: 600; }}
QTabBar::tab:selected {{ color: {TEXT}; border-bottom: 2px solid {ACCENT}; }}
QTabBar::tab:hover {{ color: {TEXT}; }}
"""
