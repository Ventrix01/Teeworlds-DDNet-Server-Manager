#!/usr/bin/env python3
"""DDNet Server Manager (Qt) - run and manage a DDNet or Teeworlds server (Raspberry Pi / Linux / Windows).

Install the one dependency with:  sudo apt install -y python3-pyqt5      (Linux)
                                  py -m pip install PyQt5                (Windows)
"""
import codecs
import difflib
import html
import json
import os
import queue
import random
import re
import shutil
import signal
import socket
import sqlite3
import subprocess
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import zipfile
import zlib
from collections import deque
from datetime import datetime, timezone
from pathlib import Path

from PyQt5.QtCore import Qt, QEvent, QLockFile, QPointF, QProcess, QSettings, QTimer, QUrl, pyqtSignal
from PyQt5.QtNetwork import QAbstractSocket, QTcpSocket
from PyQt5.QtGui import (QBrush, QColor, QConicalGradient, QDesktopServices, QFont, QGuiApplication,
                         QIcon, QKeySequence, QPainter, QPainterPath, QPen, QPixmap, QRadialGradient,
                         QTextCursor, QTextDocument)
from PyQt5.QtWidgets import (
    QAbstractItemView, QApplication, QButtonGroup, QCheckBox, QColorDialog, QComboBox, QDialog, QFileDialog,
    QFrame, QGridLayout, QHBoxLayout, QHeaderView, QLabel, QLineEdit, QListWidget, QListWidgetItem,
    QMainWindow, QMessageBox, QPlainTextEdit, QProgressBar, QPushButton, QScrollArea,
    QMenu, QShortcut, QSlider, QSpinBox, QStackedWidget, QSystemTrayIcon, QTextEdit, QTableWidget, QTableWidgetItem, QVBoxLayout, QWidget,
)



def _read_text(self, encoding=None, errors=None):
    return self.read_bytes().decode(encoding or "utf-8", errors or "replace")


def _write_text(self, data, encoding=None, errors=None, newline=None):
    # Always UTF-8 with plain "\n" line ends, the same on every OS (the game servers expect it).
    return self.write_bytes(data.encode(encoding or "utf-8", errors or "strict"))


Path.read_text, Path.write_text = _read_text, _write_text

HOME = Path.home()
IS_WIN = sys.platform.startswith("win")
EXE = ".exe" if IS_WIN else ""
DEVICE = "PC" if IS_WIN else "Pi"
APPDATA = Path(os.environ.get("APPDATA") or (HOME / "AppData" / "Roaming"))
DD_DIR = ""        # folder holding the stock DDNet server; chosen by the user on Windows


def stock_ddnet_dir():
    """Where the stock DDNet server lives: the saved choice, $DDNET_DIR, or the usual place for this OS."""
    if DD_DIR:
        return Path(DD_DIR)
    if os.environ.get("DDNET_DIR"):
        return Path(os.environ["DDNET_DIR"])
    if IS_WIN:
        local = Path(os.environ.get("LOCALAPPDATA") or (HOME / "AppData" / "Local"))
        pf = Path(os.environ.get("PROGRAMFILES") or "C:/Program Files")
        for d in (HOME / "ddnet", HOME / "DDNet", HOME / "Downloads" / "DDNet", HOME / "Desktop" / "DDNet",
                  local / "Programs" / "DDNet", pf / "DDNet"):
            if (d / "DDNet-Server.exe").is_file():
                return d
        return HOME / "ddnet"
    return HOME / "ddnet" / "build"


SERVER_DIR = stock_ddnet_dir()
SERVER_BIN = SERVER_DIR / ("DDNet-Server" + EXE)
USER_DIR = (APPDATA / "DDNet") if IS_WIN else (HOME / ".local" / "share" / "ddnet")
CONFIG = USER_DIR / "autoexec_server.cfg"
FIFO = None if IS_WIN else USER_DIR / "server_input.fifo"     # Windows has no FIFOs: commands use the external console
MAP_IMPORT_DIR = SERVER_DIR / "data" / "maps"
MAP_DIRS = [MAP_IMPORT_DIR]
CLIENT_CMD = ["flatpak", "run", "tw.ddnet.ddnet"]     # Linux; Windows starts DDNet.exe next to the server
GAME, GAME_LABEL, DEFAULT_PORT, TW_PROTO = "ddnet", "DDNet", "8303", "0.7"
BACKUP_DIR = HOME / "ddnet-backups"
AUTOSTART_FILE = HOME / ".config" / "autostart" / "ddnet-manager.desktop"
WIN_RUN_KEY = r"Software\Microsoft\Windows\CurrentVersion\Run"

ACCENT = "#2f86ff"
QSS = """
QWidget { background: #07101f; color: #dce8f7; font-size: 14px; }
QLabel { background: transparent; }
QLabel#h1 { font-size: 24px; font-weight: 700; }
QLabel#muted { color: #879ab5; }
QLabel#big { font-size: 26px; font-weight: 700; }
QPushButton#seg { padding: 8px 22px; }
QPushButton#seg:checked { background: #2f86ff; border: none; color: #050b19; }
QLabel#logo { font-size: 20px; font-weight: 800; color: #49a9ff; }
#sidebar { background: #050a14; border-right: 1px solid #17264a; }
#sidebar QPushButton { text-align: left; padding: 10px 18px; border: none; border-radius: 10px;
    color: #879ab5; background: transparent; font-weight: 600; }
#sidebar QPushButton:hover { background: #0b1530; color: #dce8f7; }
#sidebar QPushButton:checked { background: #0d1d45; color: #49a9ff; }
#sidebar QPushButton#launch { text-align: center; padding: 10px 8px; background: #101d3a; color: #dce8f7;
    border: 1px solid #1d3566; }
#sidebar QPushButton#launch:hover { background: #172b57; }
#card { background: #0b1530; border: 1px solid #142744; border-radius: 14px; }
QFrame#card[clickable="true"]:hover { border: 1px solid #2f86ff; }
QPushButton { background: #101d3a; border: 1px solid #1d3566; border-radius: 10px;
    padding: 9px 18px; font-weight: 600; }
QPushButton:hover { background: #172b57; }
QPushButton:disabled { color: #4f6485; background: #0b1226; border-color: #0f1a33; }
QPushButton#primary { background: #2f86ff; border: none; color: #050b19; }
QPushButton#primary:hover { background: #49a9ff; }
QPushButton#primary:disabled { background: #12306b; color: #4c72a8; }
QPushButton#danger { background: #3a2028; border: 1px solid #60313d; color: #e68191; }
QPushButton#danger:hover { background: #482730; }
QPushButton#danger:disabled { background: #241a20; color: #76525e; border-color: #30232a; }
QLineEdit, QPlainTextEdit, QListWidget, QComboBox {
    background: #050a14; border: 1px solid #142744; border-radius: 10px; padding: 8px 10px;
    selection-background-color: #2f86ff; selection-color: #050b19; }
QLineEdit:focus, QPlainTextEdit:focus, QComboBox:focus { border: 1px solid #2f86ff; }
QComboBox::drop-down { border: none; width: 26px; }
QComboBox QAbstractItemView { background: #0b1530; border: 1px solid #142744;
    selection-background-color: #2f86ff; selection-color: #050b19; }
QListWidget::item { padding: 8px 10px; border-radius: 8px; }
QListWidget::item:hover { background: #0b1530; }
QListWidget::item:selected { background: #0d1d45; color: #49a9ff; }
QTableWidget { background: #050a14; border: 1px solid #142744; border-radius: 10px;
    gridline-color: transparent; }
QTableWidget::item { padding: 6px; }
QTableWidget::item:selected { background: #0d1d45; color: #49a9ff; }
QHeaderView::section { background: #0b1530; color: #879ab5; border: none; padding: 8px;
    font-weight: 600; }
QProgressBar { background: #050a14; border: none; border-radius: 4px; }
QProgressBar::chunk { background: #2f86ff; border-radius: 4px; }
QCheckBox { spacing: 8px; background: transparent; }
QCheckBox::indicator { width: 18px; height: 18px; border-radius: 5px;
    border: 1px solid #304d7e; background: #050a14; }
QCheckBox::indicator:checked { background: #2f86ff; border-color: #2f86ff; }
QScrollBar:vertical { background: transparent; width: 10px; margin: 2px; }
QScrollBar::handle:vertical { background: #1d3566; border-radius: 4px; min-height: 30px; }
QScrollBar::handle:vertical:hover { background: #304d7e; }
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical { height: 0; }
QScrollBar:horizontal { background: transparent; height: 10px; margin: 2px; }
QScrollBar::handle:horizontal { background: #1d3566; border-radius: 4px; min-width: 30px; }
QScrollBar::handle:horizontal:hover { background: #304d7e; }
QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal { width: 0; }
QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal,
QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical { background: transparent; }
"""

LOG_RE = re.compile(r"^\S+ \S+ ([EWIDT]) ([^:]+): (.*)$")
TW_LOG_RE = re.compile(r"^(?:\[[^\]]*\])?\[([^\]]+)\]: (.*)$")
PROFILE_DIR = HOME / "ddnet-manager-profiles"
ACCENTS = {"Blue": ("#2f86ff", "#49a9ff"), "Cyan": ("#06b6d4", "#22d3ee"), "Teal": ("#14b8a6", "#2dd4bf"),
           "Green": ("#22c55e", "#4ade80"), "Lime": ("#84cc16", "#a3e635"), "Yellow": ("#eab308", "#facc15"),
           "Orange": ("#f59e0b", "#fbbf24"), "Red": ("#ef4444", "#f87171"), "Rose": ("#f43f5e", "#fb7185"),
           "Pink": ("#ec4899", "#f472b6"), "Purple": ("#8b5cf6", "#a78bfa"), "Mono": ("#d1d5db", "#ffffff")}
_PAL_KEYS = ["#07101f", "#050a14", "#0b1530", "#101d3a", "#0d1d45", "#172b57", "#142744", "#17264a",
             "#1d3566", "#304d7e"]
PALETTES = {"Navy": None}
for _n, _v in {
    "Midnight": "#000000 #000000 #0d0d0d #161616 #1a1a1a #242424 #1f1f1f #1f1f1f #2e2e2e #454545",
    "Slate":    "#0f1115 #0a0c10 #171a21 #1e222b #232833 #2b303c #252a34 #252a34 #333a48 #4a5366",
    "Forest":   "#07140f #040c09 #0b1d15 #10281c #0d2d1f #173d2b #14322a #17402f #1d5a3c #307e58",
    "Plum":     "#120a1f #0b0514 #1a0f30 #24143f #2a1650 #35205f #2b1a4a #2f1c55 #4a2a80 #6a3fb0",
    "Ocean":    "#06141a #030b0f #0a1f28 #0f2c38 #0d3342 #164556 #12303c #163a48 #1d566b #2e7f9b",
    "Mocha":    "#16110d #0d0a07 #211913 #2d221a #362a1f #45362a #33271e #3a2c21 #5a4232 #82624b",
    "Crimson":  "#170a0c #0d0506 #241014 #33171c #421c23 #542530 #3a1a21 #40202a #64303c #8f4656",
}.items():
    PALETTES[_n] = dict(zip(_PAL_KEYS, _v.split()))


def resolve_accent(accent, custom=""):
    if accent == "Custom":
        c = QColor(custom or "#2f86ff")
        if c.isValid():
            return c.name(), c.lighter(130).name()
    return ACCENTS.get(accent, ACCENTS["Blue"])


def derive_palette(hexcolor):
    """Build a whole dark palette from one background color."""
    c = QColor(hexcolor or "#07101f")
    h, s, v, _a = c.getHsv()
    h, v = max(h, 0), min(v, 60)

    def col(dv):
        return QColor.fromHsv(h, s, max(0, min(255, v + dv))).name()

    vals = [col(0), col(-int(v * 0.35)), col(10), col(18), col(26), col(36), col(16), col(14), col(34), col(56)]
    return dict(zip(_PAL_KEYS, vals))


def mix(c1, c2, t):
    """Blend hex color c1 toward c2 by t (0..1)."""
    a, b = QColor(c1), QColor(c2)
    return QColor(*(int(x + (y - x) * t) for x, y in
                    ((a.red(), b.red()), (a.green(), b.green()), (a.blue(), b.blue())))).name()


THEME = {"muted": "#879ab5", "accent": "#2f86ff", "accent_hi": "#49a9ff", "bg": "#07101f"}


def build_qss(accent="Blue", palette="Navy", font_px=14, custom_accent="", custom_bg=""):
    a, a2 = resolve_accent(accent, custom_accent)
    pal = derive_palette(custom_bg) if palette == "Custom" else PALETTES.get(palette)
    bg = (pal or {}).get("#07101f", "#07101f")
    # Muted text takes a faint tint of the background color so it suits every palette.
    h, s_, _v, _a = QColor(bg).getHsv()
    muted = QColor.fromHsv(max(h, 0), min(int(s_ * 0.33), 70), 181).name()
    dim = mix(bg, muted, 0.45)
    THEME.update(muted=muted, accent=a, accent_hi=a2, bg=bg)
    # Text on the solid accent flips dark/white so it stays readable on any custom color.
    fg = "#050b19" if QColor(a).lightness() > 120 else "#ffffff"
    # One single pass, so a replacement can never be replaced again by a later rule.
    repl = {"#2f86ff": a, "#49a9ff": a2, "#879ab5": muted, "#4f6485": dim, "#050b19": fg}
    repl.update(pal or {})
    q = re.sub(r"#[0-9a-fA-F]{6}\b", lambda m: repl.get(m.group(0).lower(), m.group(0)), QSS)
    q += f"""
QPushButton#primary:pressed {{ background: {mix(a, "#000000", 0.25)}; }}
QPushButton#primary:disabled {{ background: {mix(bg, a, 0.25)}; color: {mix(bg, a, 0.55)}; }}
QPushButton#restart {{ background: {mix(bg, a, 0.16)}; border: 1px solid {mix(bg, a, 0.45)}; color: {a2}; }}
QPushButton#restart:hover {{ background: {mix(bg, a, 0.28)}; border: 1px solid {a}; }}
QPushButton#restart:pressed {{ background: {mix(bg, a, 0.42)}; }}
QPushButton#restart:disabled {{ background: {mix(bg, a, 0.06)}; border: 1px solid {mix(bg, a, 0.14)};
    color: {mix(bg, a, 0.35)}; }}
"""
    return q.replace("font-size: 14px", f"font-size: {int(font_px)}px", 1)


class ColorWheel(QWidget):
    """Hue/saturation disc. Angle = hue, distance from center = saturation."""
    changed = pyqtSignal(int, int)

    def __init__(self):
        super().__init__()
        self.setMinimumSize(190, 190)
        self.h, self.s, self.v = 0, 0, 255

    def set_hsv(self, h, s, v):
        self.h, self.s, self.v = max(h, 0), s, v
        self.update()

    def _geom(self):
        d = min(self.width(), self.height()) - 12
        return QPointF(self.width() / 2, self.height() / 2), d / 2

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        c, r = self._geom()
        hue = QConicalGradient(c, 0)
        for i in range(0, 361, 30):
            hue.setColorAt(min(i / 360, 1), QColor.fromHsv(min(i, 359), 255, 255))
        p.setPen(Qt.NoPen)
        p.setBrush(QBrush(hue))
        p.drawEllipse(c, r, r)
        sat = QRadialGradient(c, r)
        sat.setColorAt(0, QColor(255, 255, 255, 255))
        sat.setColorAt(1, QColor(255, 255, 255, 0))
        p.setBrush(QBrush(sat))
        p.drawEllipse(c, r, r)
        p.setBrush(QColor(0, 0, 0, 255 - self.v))  # brightness dims the whole disc
        p.drawEllipse(c, r, r)
        import math
        ang = math.radians(self.h)
        pt = QPointF(c.x() + math.cos(ang) * r * self.s / 255, c.y() - math.sin(ang) * r * self.s / 255)
        p.setBrush(Qt.NoBrush)
        p.setPen(QPen(QColor("#000000"), 3))
        p.drawEllipse(pt, 7, 7)
        p.setPen(QPen(QColor("#ffffff"), 2))
        p.drawEllipse(pt, 7, 7)

    def _pick(self, pos):
        import math
        c, r = self._geom()
        dx, dy = pos.x() - c.x(), c.y() - pos.y()
        self.h = int(math.degrees(math.atan2(dy, dx))) % 360
        self.s = int(min(1.0, math.hypot(dx, dy) / r) * 255)
        self.update()
        self.changed.emit(self.h, self.s)

    def mousePressEvent(self, e):
        self._pick(e.pos())

    def mouseMoveEvent(self, e):
        self._pick(e.pos())


class ColorPicker(QDialog):
    """Color wheel + brightness + RGB sliders + hex box, all kept in sync."""

    def __init__(self, parent, initial, title="Pick a color"):
        super().__init__(parent)
        self.setWindowTitle(title)
        self.color = QColor(initial) if QColor(initial).isValid() else QColor("#2f86ff")
        self._busy = False
        lay = QVBoxLayout(self)
        top = QHBoxLayout()
        self.wheel = ColorWheel()
        self.wheel.changed.connect(self._from_wheel)
        top.addWidget(self.wheel, 1)
        side = QVBoxLayout()
        self.swatch = QLabel()
        self.swatch.setMinimumSize(90, 44)
        self.hex = QLineEdit()
        self.hex.setMaxLength(7)
        self.hex.editingFinished.connect(self._from_hex)
        side.addWidget(self.swatch)
        side.addWidget(self.hex)
        side.addStretch(1)
        top.addLayout(side)
        lay.addLayout(top)
        self.sliders, self.spins = {}, {}
        grid = QGridLayout()
        for i, (key, name) in enumerate((("v", "Bright"), ("r", "R"), ("g", "G"), ("b", "B"))):
            sl, sp = QSlider(Qt.Horizontal), QSpinBox()
            sl.setRange(0, 255)
            sp.setRange(0, 255)
            sl.valueChanged.connect(sp.setValue)
            sp.valueChanged.connect(sl.setValue)
            sl.valueChanged.connect(lambda _v, k=key: self._from_slider(k))
            self.sliders[key], self.spins[key] = sl, sp
            grid.addWidget(QLabel(name), i, 0)
            grid.addWidget(sl, i, 1)
            grid.addWidget(sp, i, 2)
        lay.addLayout(grid)
        btns = QHBoxLayout()
        btns.addStretch(1)
        cancel, ok = QPushButton("Cancel"), QPushButton("OK")
        ok.setObjectName("primary")
        cancel.clicked.connect(self.reject)
        ok.clicked.connect(self.accept)
        btns.addWidget(cancel)
        btns.addWidget(ok)
        lay.addLayout(btns)
        self._sync()

    def _sync(self):
        """Push self.color into every control without feedback loops."""
        self._busy = True
        c = self.color
        h, s, v, _ = c.getHsv()
        if s > 0:
            self._hue = h  # keep the last hue when a color goes grey/black
        h = getattr(self, "_hue", 0) if s == 0 else h
        self.wheel.set_hsv(h, s, v)
        for k, val in (("r", c.red()), ("g", c.green()), ("b", c.blue()), ("v", v)):
            self.sliders[k].setValue(val)
        self.hex.setText(c.name())
        self.swatch.setStyleSheet(f"background: {c.name()}; border-radius: 8px; border: 1px solid #ffffff40;")
        self._busy = False

    def _from_wheel(self, h, s):
        self._hue = h
        self.color = QColor.fromHsv(h, s, self.sliders["v"].value())
        self._sync()

    def _from_slider(self, key):
        if self._busy:
            return
        g = {k: self.sliders[k].value() for k in "rgbv"}
        if key == "v":
            h, s, _, _ = self.color.getHsv()
            self.color = QColor.fromHsv(getattr(self, "_hue", max(h, 0)), s, g["v"])
        else:
            self.color = QColor(g["r"], g["g"], g["b"])
        self._sync()

    def _from_hex(self):
        c = QColor(self.hex.text().strip() if self.hex.text().startswith("#") else "#" + self.hex.text().strip())
        if c.isValid():
            self.color = c
        self._sync()

    @staticmethod
    def get_color(parent, initial, title="Pick a color"):
        d = ColorPicker(parent, initial, title)
        return d.color if d.exec_() == QDialog.Accepted else QColor()


VOTE_BEGIN, VOTE_END = "# --- manager mode votes (auto) ---", "# --- end manager mode votes ---"


# ---------------------------------------------------------------- helpers
def local_ip():
    for target in ("10.255.255.255", "192.0.2.1", "8.8.8.8"):     # UDP connect() sends nothing
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.connect((target, 1))
            ip = s.getsockname()[0]
            s.close()
            if ip and not ip.startswith("0."):
                return ip
        except Exception:
            pass
    return "your-pi-ip"


def _win_api():
    import ctypes
    from ctypes import wintypes
    return ctypes, wintypes


def read_cpu():
    if IS_WIN:
        try:
            ctypes, wt = _win_api()
            idle, kern, user = wt.FILETIME(), wt.FILETIME(), wt.FILETIME()
            ctypes.windll.kernel32.GetSystemTimes(ctypes.byref(idle), ctypes.byref(kern), ctypes.byref(user))
            val = lambda f: (f.dwHighDateTime << 32) | f.dwLowDateTime
            return val(idle), val(kern) + val(user)      # kernel time already includes idle time
        except Exception:
            return 0, 0
    try:
        with open("/proc/stat") as f:
            v = [int(x) for x in f.readline().split()[1:9]]
        return v[3] + v[4], sum(v)
    except Exception:
        return 0, 0


def read_mem():
    """(used, total) in kB."""
    if IS_WIN:
        try:
            ctypes, _wt = _win_api()

            class MEMSTATUS(ctypes.Structure):
                _fields_ = [("dwLength", ctypes.c_ulong), ("dwMemoryLoad", ctypes.c_ulong),
                            ("ullTotalPhys", ctypes.c_ulonglong), ("ullAvailPhys", ctypes.c_ulonglong),
                            ("ullTotalPageFile", ctypes.c_ulonglong), ("ullAvailPageFile", ctypes.c_ulonglong),
                            ("ullTotalVirtual", ctypes.c_ulonglong), ("ullAvailVirtual", ctypes.c_ulonglong),
                            ("ullAvailExtendedVirtual", ctypes.c_ulonglong)]
            m = MEMSTATUS()
            m.dwLength = ctypes.sizeof(MEMSTATUS)
            ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(m))
            return (m.ullTotalPhys - m.ullAvailPhys) // 1024, max(1, m.ullTotalPhys // 1024)
        except Exception:
            return 0, 1
    try:
        info = {}
        with open("/proc/meminfo") as f:
            for line in f:
                k, v = line.split(":")
                info[k] = int(v.split()[0])
        total, avail = info["MemTotal"], info["MemAvailable"]
        return total - avail, total
    except Exception:
        return 0, 1


def read_temp():
    if IS_WIN:
        return None          # Windows exposes no simple CPU temperature
    try:
        return int(Path("/sys/class/thermal/thermal_zone0/temp").read_text()) / 1000
    except Exception:
        return None


def read_rss(pid):
    """Resident memory of a process in kB (0 if unknown)."""
    if IS_WIN:
        try:
            ctypes, wt = _win_api()

            class PMC(ctypes.Structure):
                _fields_ = [("cb", ctypes.c_ulong), ("PageFaultCount", ctypes.c_ulong),
                            ("PeakWorkingSetSize", ctypes.c_size_t), ("WorkingSetSize", ctypes.c_size_t),
                            ("QuotaPeakPagedPoolUsage", ctypes.c_size_t), ("QuotaPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
                            ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
                            ("PagefileUsage", ctypes.c_size_t), ("PeakPagefileUsage", ctypes.c_size_t)]
            k32 = ctypes.WinDLL("kernel32", use_last_error=True)
            k32.OpenProcess.restype = wt.HANDLE
            k32.OpenProcess.argtypes = [wt.DWORD, wt.BOOL, wt.DWORD]
            k32.CloseHandle.argtypes = [wt.HANDLE]
            psapi = ctypes.WinDLL("psapi", use_last_error=True)
            psapi.GetProcessMemoryInfo.argtypes = [wt.HANDLE, ctypes.POINTER(PMC), wt.DWORD]
            h = k32.OpenProcess(0x1000 | 0x0010, False, int(pid))    # QUERY_LIMITED_INFORMATION | VM_READ
            if not h:
                return 0
            try:
                c = PMC()
                c.cb = ctypes.sizeof(PMC)
                if psapi.GetProcessMemoryInfo(h, ctypes.byref(c), c.cb):
                    return int(c.WorkingSetSize) // 1024
            finally:
                k32.CloseHandle(h)
        except Exception:
            pass
        return 0
    try:
        for line in Path(f"/proc/{int(pid)}/status").read_text().splitlines():
            if line.startswith("VmRSS:"):
                return int(line.split()[1])
    except (OSError, ValueError):
        pass
    return 0


def parse_cfg(text):
    vals = {}
    for line in text.splitlines():
        if line.lstrip().startswith("#"):
            continue
        m = re.match(r"^\s*(\w+)\s+(.*?)\s*$", line)
        if m:
            v = m.group(2)
            if len(v) >= 2 and v[0] == '"' and v[-1] == '"':
                v = v[1:-1]
            vals.setdefault(m.group(1), v)
    return vals


def set_cfg(text, key, value, quote=True):
    value = value.replace('"', "")
    pat = re.compile(r"^\s*" + re.escape(key) + r"\s")
    out, done = [], False
    new_line = (f'{key} "{value}"' if quote else f"{key} {value}") if value else None
    for line in text.splitlines():
        if pat.match(line):
            if new_line and not done:
                out.append(new_line)
                done = True
            continue
        out.append(line)
    if new_line and not done:
        out.append(new_line)
    return "\n".join(out) + "\n"


def fmt_duration(sec):
    sec = int(sec)
    h, r = divmod(sec, 3600)
    m, s = divmod(r, 60)
    return f"{h}h {m:02d}m" if h else f"{m}m {s:02d}s"


DEFAULT_EVENTS = {"start": True, "stop": True, "crash": True, "join": True,
                  "leave": False, "map": False, "chat": True, "backup": True, "recap": True, "mod": True}
DEFAULT_CHAT_FMT = "🎮 **{name}** (in game): {message}"
STATS_FILE = HOME / ".config" / "ddnet-manager-stats.json"


def load_stats():
    try:
        d = json.loads(STATS_FILE.read_text())
    except (OSError, ValueError):
        d = {}
    return d if isinstance(d, dict) else {}


def save_stats(d):
    try:
        STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
        STATS_FILE.write_text(json.dumps(d))
    except OSError:
        pass


def game_stats(d):
    """Lifetime numbers for the current game, with defaults filled in."""
    g = d.setdefault(GAME, {})
    for k in ("peak", "uptime", "sessions", "joins"):
        if not isinstance(g.get(k), (int, float)):
            g[k] = 0
    if not isinstance(g.get("hours"), list) or len(g["hours"]) != 24:
        g["hours"] = [0] * 24
    return g


class HourBars(QWidget):
    """24 small bars: how many players joined in each hour of the day."""

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(120)
        self.vals, self.color = [0] * 24, QColor("#2f86ff")

    def set_data(self, vals, color):
        self.vals, self.color = list(vals), QColor(color)
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height() - 18
        top, bw = max(max(self.vals), 1), self.width() / 24
        p.setPen(Qt.NoPen)
        for i, v in enumerate(self.vals):
            bh = max(2, int((h - 4) * v / top)) if v else 2
            p.setBrush(self.color if v else QColor(255, 255, 255, 25))
            p.drawRoundedRect(int(i * bw + 2), h - bh, max(int(bw - 4), 2), bh, 3, 3)
        p.setPen(QColor(THEME["muted"]))
        for i in (0, 6, 12, 18):
            p.drawText(int(i * bw), h + 4, int(bw * 2), 14, Qt.AlignLeft, f"{i:02d}")
WEBHOOK_RE = re.compile(
    r"^https://(?:(?:canary|ptb)\.)?discord(?:app)?\.com/api/(?:v\d+/)?webhooks/\d+/[\w-]+/?(?:\?.*)?$")


def esc_md(text):
    """Escape Discord markdown so a player name can't restyle a message."""
    return re.sub(r"([\\*_~`|>])", r"\\\1", text)


def safe_console_text(text):
    """Player-controlled text must never be able to smuggle in extra console commands."""
    text = text.replace(";", ",").replace('"', "").replace("\\", "")
    return " ".join(text.split())


def valid_hm(text):
    return re.fullmatch(r"([01]\d|2[0-3]):[0-5]\d", text or "") is not None


def fetch_public_ip():
    try:
        req = urllib.request.Request("https://api.ipify.org", headers={"User-Agent": "DDNet-Server-Manager"})
        with urllib.request.urlopen(req, timeout=6) as r:
            ip = r.read().decode().strip()
        if re.fullmatch(r"[0-9a-fA-F:.]{3,45}", ip):
            return True, ip
        return False, "Unexpected reply from the lookup service."
    except Exception as e:
        return False, f"Could not look up the public IP: {e}"


def upnp_open(port):
    if not shutil.which("upnpc"):
        if IS_WIN:
            return False, (f"Automatic port opening isn't available on Windows. In your router's settings forward "
                           f"UDP port {port} to this PC ({local_ip()}), and click Allow if Windows Firewall asks.")
        return False, "The UPnP tool isn't installed. Run: sudo apt install -y miniupnpc"
    try:
        r = subprocess.run(["upnpc", "-a", local_ip(), str(port), str(port), "UDP", "0"],
                           capture_output=True, text=True, timeout=25)
    except Exception as e:
        return False, f"UPnP failed: {e}"
    out = (r.stdout + r.stderr).strip()
    if "redirected" in out.lower():
        return True, f"Port {port}/UDP is now forwarded to this computer."
    tail = out.splitlines()[-1] if out else "no response"
    return False, f"The router didn't accept it ({tail}). Is UPnP enabled in the router settings?"


def make_backup(keep=7):
    """Zip the config, rank/save databases and imported maps. Returns (ok, message)."""
    try:
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        dest = BACKUP_DIR / time.strftime("ddnet-backup-%Y%m%d-%H%M%S.zip")
        count = 0
        with tempfile.TemporaryDirectory() as tmp, zipfile.ZipFile(dest, "w", zipfile.ZIP_DEFLATED) as z:
            if USER_DIR.is_dir():
                for f in sorted(USER_DIR.iterdir()):
                    if not f.is_file():
                        continue
                    if f.suffix in (".sqlite", ".db"):
                        copy = Path(tmp) / f.name
                        try:  # safe copy even while the server is writing to it
                            src, dst = sqlite3.connect(str(f)), sqlite3.connect(str(copy))
                            src.backup(dst)
                            dst.close()
                            src.close()
                        except sqlite3.Error:
                            shutil.copy2(f, copy)
                        z.write(copy, f.name)
                        count += 1
                    elif f.suffix == ".cfg":
                        z.write(f, f.name)
                        count += 1
                for folder in ("maps", "saves"):
                    d = USER_DIR / folder
                    if d.is_dir():
                        for p in sorted(d.rglob("*")):
                            if p.is_file():
                                z.write(p, f"{folder}/{p.relative_to(d)}")
                                count += 1
        if count == 0:
            dest.unlink()
            return False, "Nothing to back up yet (no config, database or maps found)."
        for old in sorted(BACKUP_DIR.glob("ddnet-backup-*.zip"))[:-max(1, keep)]:
            old.unlink()
        return True, f"Saved {dest.name} ({count} files, {dest.stat().st_size / 1024:.0f} KB) in {BACKUP_DIR}"
    except OSError as e:
        return False, f"Backup failed: {e}"


def launch_command():
    """How to start this app again: the packaged binary itself, or python + this script."""
    if getattr(sys, "frozen", False):
        return f'"{sys.executable}"'
    exe = sys.executable
    if IS_WIN and exe.lower().endswith("python.exe"):
        exe = exe[:-10] + "pythonw.exe"            # no console window
    return f'"{exe}" "{Path(__file__).resolve()}"' if IS_WIN else f'{exe} "{Path(__file__).resolve()}"'


def login_autostart_enabled():
    if IS_WIN:
        try:
            import winreg
            with winreg.OpenKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as k:
                winreg.QueryValueEx(k, "DDNetServerManager")
            return True
        except OSError:
            return False
    return AUTOSTART_FILE.exists()


def set_login_autostart(enabled):
    if IS_WIN:
        import winreg
        with winreg.CreateKey(winreg.HKEY_CURRENT_USER, WIN_RUN_KEY) as k:
            if enabled:
                winreg.SetValueEx(k, "DDNetServerManager", 0, winreg.REG_SZ, f"{launch_command()} --minimized")
            else:
                try:
                    winreg.DeleteValue(k, "DDNetServerManager")
                except OSError:
                    pass
        return
    if enabled:
        AUTOSTART_FILE.parent.mkdir(parents=True, exist_ok=True)
        AUTOSTART_FILE.write_text(
            "[Desktop Entry]\nType=Application\nName=DDNet Server Manager\n"
            f'Exec={launch_command()} --minimized\n'
            "Terminal=false\nX-GNOME-Autostart-enabled=true\n")
    else:
        AUTOSTART_FILE.unlink(missing_ok=True)


GUARD_DURATIONS = (("1 hour", 3600), ("1 day", 86400), ("7 days", 604800), ("30 days", 2592000),
                   ("Permanent", 0))
IP_RE = re.compile(r"^[0-9a-fA-F:.]{3,45}$")


def clean_guard(d):
    if not isinstance(d, dict) or not IP_RE.match(str(d.get("ip", "")).strip()):
        return None
    try:
        until = float(d.get("until", 0))
    except (TypeError, ValueError):
        until = 0.0
    return dict(kind="mute" if d.get("kind") == "mute" else "ban", ip=str(d["ip"]).strip(),
                name=str(d.get("name", ""))[:40], reason=safe_console_text(str(d.get("reason", "")))[:80], until=until)


def guard_command(e, now=None):
    """The console command that (re)applies one entry, or None if it expired or this game can't do it."""
    now = now or time.time()
    left = (e["until"] - now) if e["until"] else 0
    if e["until"] and left <= 0:
        return None
    if e["kind"] == "mute":
        if GAME != "ddnet":                       # stock Teeworlds has no mute command
            return None
        return f'muteip {e["ip"]} {int(left) if e["until"] else 31536000} {e["reason"] or "muted"}'
    mins = (int(left // 60) + (1 if left % 60 else 0)) if e["until"] else 0     # 0 = permanent
    return f'ban {e["ip"]} {mins} {e["reason"] or "banned"}'


class GuardDialog(QDialog):
    """Ban/mute list kept by the manager. Entries are re-applied whenever the server starts."""

    def __init__(self, mgr, prefill=None):
        super().__init__(mgr)
        self.mgr = mgr
        self.setWindowTitle("Ban & mute list")
        self.resize(780, 470)
        lay = QVBoxLayout(self)
        info = QLabel("Entries are re-applied every time the server starts, so bans survive restarts. "
                      "Expired ones drop off by themselves.")
        info.setObjectName("muted")
        info.setWordWrap(True)
        lay.addWidget(info)
        self.tbl = QTableWidget(0, 5)
        self.tbl.setHorizontalHeaderLabels(["Type", "Name", "IP address", "Reason", "Expires"])
        self.tbl.verticalHeader().setVisible(False)
        self.tbl.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tbl.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tbl.setShowGrid(False)
        self.tbl.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        lay.addWidget(self.tbl, 1)
        form = QHBoxLayout()
        self.kind, self.dur = QComboBox(), QComboBox()
        self.kind.addItem("Ban", "ban")
        if GAME == "ddnet":
            self.kind.addItem("Mute", "mute")
        for label, sec in GUARD_DURATIONS:
            self.dur.addItem(label, sec)
        self.dur.setCurrentIndex(1)
        self.ip, self.name, self.reason = QLineEdit(), QLineEdit(), QLineEdit()
        self.ip.setPlaceholderText("IP address")
        self.name.setPlaceholderText("Name (just a label)")
        self.reason.setPlaceholderText("Reason")
        add = QPushButton("Add")
        add.setObjectName("primary")
        add.clicked.connect(self.add)
        for w, st in ((self.kind, 0), (self.ip, 2), (self.name, 2), (self.dur, 0), (self.reason, 3), (add, 0)):
            form.addWidget(w, st)
        lay.addLayout(form)
        bar = QHBoxLayout()
        rm, ap, close = QPushButton("Remove selected"), QPushButton("Apply now"), QPushButton("Close")
        rm.clicked.connect(self.remove)
        ap.clicked.connect(self.apply_now)
        close.clicked.connect(self.accept)
        for b in (rm, ap):
            bar.addWidget(b)
        bar.addStretch(1)
        bar.addWidget(close)
        lay.addLayout(bar)
        if prefill:
            self.ip.setText(prefill.get("ip", ""))
            self.name.setText(prefill.get("name", ""))
            self.reason.setFocus()
        self.reload()

    def reload(self):
        entries = self.mgr.guard_entries()
        self.tbl.setRowCount(len(entries))
        for r, e in enumerate(entries):
            exp = datetime.fromtimestamp(e["until"]).strftime("%b %d %H:%M") if e["until"] else "Permanent"
            for c, v in enumerate((e["kind"].title(), e["name"], e["ip"], e["reason"], exp)):
                self.tbl.setItem(r, c, QTableWidgetItem(v))

    def add(self):
        ip = self.ip.text().strip()
        if not IP_RE.match(ip):
            QMessageBox.warning(self, "Check the address", "Enter the player's IP address (see the Players tab).")
            return
        sec = self.dur.currentData()
        e = clean_guard(dict(kind=self.kind.currentData(), ip=ip, name=self.name.text().strip(),
                             reason=self.reason.text().strip(), until=time.time() + sec if sec else 0))
        self.mgr.guard_save(self.mgr.guard_entries() + [e])
        cmd = guard_command(e)
        if cmd and self.mgr.running():
            self.mgr.send_cmd(cmd)
        self.ip.clear()
        self.name.clear()
        self.reason.clear()
        self.reload()

    def remove(self):
        entries, r = self.mgr.guard_entries(), self.tbl.currentRow()
        if not 0 <= r < len(entries):
            return
        e = entries.pop(r)
        self.mgr.guard_save(entries)
        if e["kind"] == "ban" and self.mgr.running():
            self.mgr.send_cmd(f"unban {e['ip']}")
        self.reload()

    def apply_now(self):
        if not self.mgr.running():
            QMessageBox.information(self, "Server not running", "The list is applied automatically when the server starts.")
            return
        self.mgr.guard_apply()


class DiscordNotifier:
    """Posts to a Discord webhook on a background thread, one message at a time."""

    def __init__(self, on_result):
        self.q = queue.Queue()
        self.on_result = on_result
        threading.Thread(target=self._loop, daemon=True).start()

    def post(self, url, payload, report=False):
        self.q.put((url, payload, report, None))

    def post_card(self, url, payload, msg_id, on_id):
        """Edit the existing status message (or create it once) instead of posting a new one."""
        self.q.put((url, payload, False, (msg_id, on_id)))

    def _loop(self):
        while True:
            url, payload, report, card = self.q.get()
            if card:
                ok, msg = self._card(url, payload, card[0])
                if ok:
                    card[1](msg)
            else:
                ok, msg = self._send(url, payload)
            if report or not ok:
                self.on_result(ok, msg)
            time.sleep(1.0)  # stay well under Discord's rate limit

    @staticmethod
    def _card(url, payload, msg_id):
        """PATCH the message if we have its id, else POST a new one. Returns (ok, message_id or error)."""
        base = url.split("?")[0].rstrip("/")

        def call(u, method):
            req = urllib.request.Request(
                u, data=json.dumps(payload).encode("utf-8"), method=method,
                headers={"Content-Type": "application/json", "User-Agent": "DDNet-Server-Manager"})
            with urllib.request.urlopen(req, timeout=10) as r:
                return json.loads(r.read() or b"{}")
        try:
            if msg_id:
                try:
                    call(f"{base}/messages/{msg_id}", "PATCH")
                    return True, msg_id
                except urllib.error.HTTPError as e:
                    if e.code != 404:              # 404 = someone deleted it; post a fresh one
                        raise
            return True, str(call(base + "?wait=true", "POST").get("id", ""))
        except urllib.error.HTTPError as e:
            return False, f"Discord said {e.code} while updating the status message."
        except Exception as e:
            return False, f"Status message failed: {e}"

    @staticmethod
    def _send(url, payload):
        data = json.dumps(payload).encode("utf-8")
        for attempt in range(2):
            req = urllib.request.Request(
                url, data=data, method="POST",
                headers={"Content-Type": "application/json", "User-Agent": "DDNet-Server-Manager"})
            try:
                with urllib.request.urlopen(req, timeout=10):
                    return True, "Message delivered to Discord."
            except urllib.error.HTTPError as e:
                if e.code == 429 and attempt == 0:
                    try:
                        wait = float(json.loads(e.read()).get("retry_after", 2))
                    except Exception:
                        wait = 2.0
                    time.sleep(min(wait, 10))
                    continue
                if e.code in (401, 403, 404):
                    return False, (f"Discord rejected the webhook (HTTP {e.code}). Check the URL is "
                                   "complete and the webhook still exists.")
                return False, f"Discord returned HTTP {e.code}."
            except Exception as e:
                return False, f"Could not reach Discord: {e}"
        return False, "Discord is rate limiting this webhook. Try again in a moment."


# ---------------------------------------------------------------- widgets
class Stat(QFrame):
    def __init__(self, title, bar=False):
        super().__init__()
        self.setObjectName("card")
        lay = QVBoxLayout(self)
        lay.setContentsMargins(18, 16, 18, 16)
        lay.setSpacing(6)
        t = QLabel(title)
        t.setObjectName("muted")
        self.v = QLabel("-")
        self.v.setObjectName("big")
        lay.addWidget(t)
        lay.addWidget(self.v)
        self.bar = None
        if bar:
            self.bar = QProgressBar()
            self.bar.setRange(0, 100)
            self.bar.setTextVisible(False)
            self.bar.setFixedHeight(8)
            lay.addWidget(self.bar)

    def set(self, text, pct=None):
        self.v.setText(text)
        if self.bar is not None and pct is not None:
            self.bar.setValue(int(max(0, min(100, pct))))


class HistoryEdit(QLineEdit):
    def __init__(self):
        super().__init__()
        self.hist, self.pos = [], 0

    def remember(self, text):
        self.hist.append(text)
        self.pos = len(self.hist)

    def keyPressEvent(self, e):
        if e.key() == Qt.Key_Up and self.hist:
            self.pos = max(0, self.pos - 1)
            self.setText(self.hist[self.pos])
        elif e.key() == Qt.Key_Down and self.hist:
            self.pos = min(len(self.hist), self.pos + 1)
            self.setText(self.hist[self.pos] if self.pos < len(self.hist) else "")
        else:
            super().keyPressEvent(e)


def card_frame():
    f = QFrame()
    f.setObjectName("card")
    return f


def run_text(cmd):
    try:
        return subprocess.run(cmd, capture_output=True, text=True, timeout=2).stdout
    except Exception:
        return ""


def pi_throttle():
    exe = shutil.which("vcgencmd")
    m = re.search(r"0x([0-9a-fA-F]+)", run_text([exe, "get_throttled"])) if exe else None
    if not m:
        return None
    v = int(m.group(1), 16)
    now = [n for b, n in ((0, "under-voltage"), (1, "frequency capped"), (2, "throttled"),
                          (3, "soft temperature limit")) if v >> b & 1]
    past = [n for b, n in ((16, "under-voltage"), (17, "frequency capped"), (18, "throttled"),
                           (19, "soft temperature limit")) if v >> b & 1]
    return now, past


class HistoryGraph(QWidget):
    """Simple live line graph of the last ~10 minutes (300 samples, one per 2 s)."""
    MAXLEN = 300

    def __init__(self):
        super().__init__()
        self.setMinimumHeight(230)
        self.values, self.lo, self.hi, self.unit = [], 0, 100, "%"
        self.color, self.warn = QColor("#2f86ff"), None

    def set_data(self, values, lo, hi, unit, color, warn=None):
        self.values, self.lo, self.hi, self.unit, self.color, self.warn = values, lo, max(hi, lo + 1), unit, color, warn
        self.update()

    def paintEvent(self, _e):
        p = QPainter(self)
        p.setRenderHint(QPainter.Antialiasing)
        w, h = self.width(), self.height()
        left, right, top, bottom = 52, 14, 10, 24
        pw, ph = max(1, w - left - right), max(1, h - top - bottom)
        muted = QColor(THEME["muted"])
        grid = QColor(255, 255, 255, 28)
        span = self.hi - self.lo

        def ypos(v):
            return top + ph * (1 - (min(max(v, self.lo), self.hi) - self.lo) / span)

        for i in range(5):
            y = top + ph * i / 4
            p.setPen(QPen(grid, 1))
            p.drawLine(left, int(y), left + pw, int(y))
            p.setPen(muted)
            p.drawText(0, int(y) - 8, left - 6, 16, int(Qt.AlignRight | Qt.AlignVCenter),
                       f"{self.hi - span * i / 4:.0f}{self.unit}")
        p.setPen(muted)
        p.drawText(left, h - 18, 120, 16, Qt.AlignLeft, "10 min ago")
        p.drawText(left + pw - 120, h - 18, 120, 16, Qt.AlignRight, "now")
        if self.warn is not None and self.lo < self.warn < self.hi:
            p.setPen(QPen(QColor("#e68191"), 1, Qt.DashLine))
            p.drawLine(left, int(ypos(self.warn)), left + pw, int(ypos(self.warn)))
        n = len(self.values)
        if n < 2:
            p.setPen(muted)
            p.drawText(self.rect(), Qt.AlignCenter, "Collecting data...")
            return
        step = pw / (self.MAXLEN - 1)
        pts = [(left + pw - (n - 1 - i) * step, ypos(v)) for i, v in enumerate(self.values)]
        line = QPainterPath()
        line.moveTo(*pts[0])
        for x, y in pts[1:]:
            line.lineTo(x, y)
        fill = QPainterPath(line)
        fill.lineTo(pts[-1][0], top + ph)
        fill.lineTo(pts[0][0], top + ph)
        fill.closeSubpath()
        fc = QColor(self.color)
        fc.setAlpha(55)
        p.fillPath(fill, fc)
        p.setPen(QPen(self.color, 2))
        p.drawPath(line)


class ExpandDialog(QDialog):
    """Bigger, live view of a dashboard stat: history graph plus details."""
    TITLES = {"cpu": f"{DEVICE} CPU", "mem": "Memory", "temp": "Temperature", "uptime": "Uptime & players"}

    def __init__(self, mgr, key):
        super().__init__(mgr)
        self.mgr, self.key = mgr, key
        self.setAttribute(Qt.WA_DeleteOnClose)
        self.setWindowTitle(self.TITLES[key])
        self.resize(740, 600)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        lay.setSpacing(12)
        head = QHBoxLayout()
        t = QLabel(self.TITLES[key])
        t.setObjectName("h1")
        self.now = QLabel("-")
        self.now.setObjectName("big")
        head.addWidget(t)
        head.addStretch(1)
        head.addWidget(self.now)
        lay.addLayout(head)
        self.graph = HistoryGraph()
        lay.addWidget(self.graph)
        self.summary = QLabel("")
        self.summary.setObjectName("muted")
        lay.addWidget(self.summary)
        self.info = QPlainTextEdit()
        self.info.setReadOnly(True)
        f = QFont("monospace")
        f.setStyleHint(QFont.Monospace)
        self.info.setFont(f)
        lay.addWidget(self.info, 1)
        close = QPushButton("Close")
        close.clicked.connect(self.close)
        lay.addWidget(close, 0, Qt.AlignRight)
        self.refresh()

    def refresh(self):
        m, key = self.mgr, self.key
        h = list(m.hist["players" if key == "uptime" else key])
        color, unit, lo, hi, warn = m.accent_color, "%", 0, 100, None
        lines = []
        if key == "cpu":
            now = f"{h[-1]:.0f}%" if h else "-"
            try:
                la = os.getloadavg()
                lines.append(f"Load average   {la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}   ({os.cpu_count()} cores)")
            except (OSError, AttributeError):        # no load average on Windows
                pass
            try:
                mhz = int(Path("/sys/devices/system/cpu/cpu0/cpufreq/scaling_cur_freq").read_text()) // 1000
                lines.append(f"Clock          {mhz} MHz")
            except (OSError, ValueError):
                pass
            rows = []
            for ln in run_text(["ps", "-eo", "pcpu,comm", "--sort=-pcpu"]).splitlines()[1:7]:
                parts = ln.split(None, 1)
                if len(parts) == 2:
                    rows.append(f"{parts[0]:>6}%   {parts[1]}")
            lines += (["", "Busiest processes"] + rows) if rows else []
        elif key == "mem":
            used, tot = read_mem()
            now = f"{used / 1048576:.1f} / {tot / 1048576:.0f} GB"
            lines.append(f"In use         {used / 1048576:.2f} GB of {tot / 1048576:.2f} GB")
            try:
                info = {}
                for ln in Path("/proc/meminfo").read_text().splitlines():
                    k, v = ln.split(":")
                    info[k] = int(v.split()[0])
                lines.append(f"Swap           {(info['SwapTotal'] - info['SwapFree']) / 1024:.0f} MB used "
                             f"of {info['SwapTotal'] / 1024:.0f} MB")
            except (OSError, ValueError, KeyError):
                pass
            rows = []
            for ln in run_text(["ps", "-eo", "rss,comm", "--sort=-rss"]).splitlines()[1:7]:
                parts = ln.split(None, 1)
                if len(parts) == 2 and parts[0].isdigit():
                    rows.append(f"{int(parts[0]) / 1024:7.0f} MB   {parts[1]}")
            lines += (["", "Biggest processes"] + rows) if rows else []
        elif key == "temp":
            unit, warn = " C", int(m.dset("temp_warn_c", 80))
            now = f"{h[-1]:.0f} C" if h else "n/a"
            lo, hi = min(30, int(min(h, default=30)) - 5), max(85, int(max(h, default=85)) + 5)
            th = pi_throttle()
            if th is None:
                lines.append("Throttle status isn't available (no vcgencmd found).")
            else:
                lines.append("Right now      " + (", ".join(th[0]) or "all good"))
                lines.append("Since boot     " + (", ".join(th[1]) or "nothing"))
            lines.append(f"Warning line   {warn} C (change it on the Customize tab)")
        else:  # uptime & players
            unit, lo = "", 0
            hi = max(2, int(max(h, default=0)) + 1)
            now = fmt_duration(time.time() - m.started_at) if m.started_at and m.running() else "-"
            lines.append(f"Game           {GAME_LABEL}")
            lines.append("Started        " + (datetime.fromtimestamp(m.started_at).strftime("%a %H:%M:%S")
                                              if m.started_at and m.running() else "not running"))
            lines.append(f"Players now    {len(m.players)}")
            lines.append(f"Peak (graph)   {int(max(h, default=0))}")
        self.now.setText(now)
        self.graph.set_data(h, lo, hi, unit, color, warn)
        if h:
            self.summary.setText(f"Last {max(1, len(h) * 2 // 60)} min   min {min(h):.0f}{unit}   "
                                 f"avg {sum(h) / len(h):.0f}{unit}   max {max(h):.0f}{unit}")
        else:
            self.summary.setText("")
        self.info.setPlainText("\n".join(lines))


# ---------------------------------------------------------------- game switch
# The manager can drive either DDNet's server or a stock Teeworlds server
# (fight / CTF / casual / zombie mod...). apply_game() repoints the paths below.
MODE_PRESETS = {
    "Casual (free-for-all)":   dict(gt="dm",  map="dm1",  score=0,   time=0,  maxc=16),
    "Fight (deathmatch)":      dict(gt="dm",  map="dm2",  score=50,  time=10, maxc=16),
    "Fight (team deathmatch)": dict(gt="tdm", map="dm1",  score=100, time=10, maxc=16),
    "Capture the Flag":        dict(gt="ctf", map="ctf5", score=300, time=20, maxc=16),
    "Last Man Standing":       dict(gt="lms", map="lms1", score=0,   time=0,  maxc=16),
    "Zombie (needs a mod)":    dict(gt="zombie", map="dm1", score=0, time=0,  maxc=16),
    "Custom":                  dict(gt="dm",  map="dm1",  score=0,   time=0,  maxc=16),
}
TW_DEFAULT_CFG = ('sv_name "My Teeworlds server"\nsv_port 8304\nsv_gametype "dm"\n'
                  'sv_map "dm1"\nsv_max_clients 16\nsv_register 0\n')


def find_tw_server():
    cands = [os.environ.get("TW_SERVER", "")]
    dirs = [HOME / "teeworlds" / "build", HOME / "teeworlds", HOME / "teeworlds-server"]
    if IS_WIN:
        pf = Path(os.environ.get("PROGRAMFILES(X86)") or "C:/Program Files (x86)")
        dirs += [HOME / "Downloads" / "teeworlds", HOME / "Desktop" / "teeworlds", pf / "Teeworlds",
                 pf / "Steam" / "steamapps" / "common" / "Teeworlds"]
    for d in dirs:
        for n in ("teeworlds_srv", "teeworlds-server", "teeworlds-srv"):
            cands.append(str(d / (n + EXE)))
    for n in ("teeworlds-server", "teeworlds_srv", "teeworlds-srv"):
        cands.append(shutil.which(n) or "")
        if not IS_WIN:
            cands.append(f"/usr/games/{n}")
            cands.append(f"/usr/bin/{n}")
    for c in cands:
        if c and Path(c).is_file() and os.access(c, os.X_OK):
            return c
    return ""


def apply_game(game, tw_bin="", proto="0.7", dd_bin=""):
    global GAME, GAME_LABEL, SERVER_DIR, SERVER_BIN, USER_DIR, CONFIG, FIFO
    global MAP_DIRS, MAP_IMPORT_DIR, DEFAULT_PORT, TW_PROTO
    TW_PROTO = proto if proto in ("0.6", "0.7") else "0.7"
    if game == "teeworlds":
        b = Path(tw_bin) if tw_bin else Path(find_tw_server() or HOME / "teeworlds" / "build" / ("teeworlds_srv" + EXE))
        GAME, GAME_LABEL, DEFAULT_PORT = "teeworlds", "Teeworlds", "8304"
        SERVER_BIN, SERVER_DIR = b, b.parent
        USER_DIR = (APPDATA / "Teeworlds") if IS_WIN else (HOME / ".teeworlds")
        CONFIG = USER_DIR / "teeworlds_server.cfg"
        FIFO = None
        MAP_IMPORT_DIR = USER_DIR / "maps"
        MAP_DIRS = [MAP_IMPORT_DIR, SERVER_DIR / "data" / "maps",
                    Path("/usr/share/games/teeworlds/data/maps"), Path("/usr/share/teeworlds/data/maps")]
        if IS_WIN:
            MAP_DIRS = [MAP_IMPORT_DIR, SERVER_DIR / "data" / "maps"]
    else:
        GAME, GAME_LABEL, DEFAULT_PORT = "ddnet", "DDNet", "8303"
        SERVER_DIR = stock_ddnet_dir()
        SERVER_BIN = SERVER_DIR / ("DDNet-Server" + EXE)
        if dd_bin:                                     # a DDNet-based mod's own binary (Mods page)
            SERVER_BIN = Path(dd_bin)
            SERVER_DIR = SERVER_BIN.parent
        USER_DIR = (APPDATA / "DDNet") if IS_WIN else (HOME / ".local" / "share" / "ddnet")
        CONFIG = USER_DIR / "autoexec_server.cfg"
        FIFO = None if IS_WIN else USER_DIR / "server_input.fifo"
        MAP_IMPORT_DIR = SERVER_DIR / "data" / "maps"
        MAP_DIRS = [MAP_IMPORT_DIR]


def use_econ():
    """Commands go through the server's external console (Teeworlds always; DDNet where FIFOs don't exist)."""
    return GAME == "teeworlds" or IS_WIN


def interrupt_process(proc):
    """Ask the server to stop cleanly. Returns True if a stop request was sent."""
    if IS_WIN:
        proc.terminate()          # console programs ignore this; the caller's timer force-kills
        return False
    try:
        os.kill(proc.processId(), signal.SIGINT)
        return True
    except OSError:
        proc.terminate()
        return False


def fmt_addr(host, port):
    """host:port, with brackets around IPv6 addresses."""
    return f"[{host}]:{port}" if ":" in str(host) else f"{host}:{port}"


def addr_text(host, port):
    """Address as the game wants it typed: Teeworlds 0.7 needs the tw-0.7+udp:// prefix."""
    prefix = "tw-0.7+udp://" if GAME == "teeworlds" and TW_PROTO == "0.7" else ""
    return f"{prefix}{fmt_addr(host, port)}"


def connect_text(host, port):
    return f"connect {addr_text(host, port)}"


class ModesPage(QWidget):
    """Teeworlds-only tab: pick a game mode/preset and write it into the server config."""

    def __init__(self, manager):
        super().__init__()
        self.mgr = manager
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        card = card_frame()
        g = QGridLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.f_mode = QComboBox()
        self.f_mode.addItems(list(MODE_PRESETS))
        self.f_gt, self.f_map = QLineEdit(), QLineEdit()
        self.f_max, self.f_score, self.f_time = QLineEdit(), QLineEdit(), QLineEdit()
        self.f_bin = QLineEdit()
        self.f_bin.setPlaceholderText("auto-detect, or path to a teeworlds server / zombie mod binary")
        browse = QPushButton("Browse")
        browse.clicked.connect(self.browse_bin)
        self.f_proto = QComboBox()
        self.f_proto.addItems(["0.7", "0.6"])
        self.f_votes = QCheckBox("Let players vote to switch modes and favorite maps in-game (adds vote entries)")
        self.bin_status = QLabel("")
        self.inst = None
        rows = [("Mode", self.f_mode), ("Gametype", self.f_gt), ("Map", self.f_map),
                ("Max players", self.f_max), ("Score limit (0 = none)", self.f_score),
                ("Time limit, min (0 = none)", self.f_time), ("Client protocol", self.f_proto)]
        for i, (label, w) in enumerate(rows):
            g.addWidget(QLabel(label), i, 0)
            g.addWidget(w, i, 1, 1, 2)
        n = len(rows)
        g.addWidget(QLabel("Server binary"), n, 0)
        g.addWidget(self.f_bin, n, 1)
        g.addWidget(browse, n, 2)
        g.addWidget(self.f_votes, n + 1, 1, 1, 2)
        g.addWidget(self.bin_status, n + 2, 1)
        ib = QPushButton("Get server (download)" if IS_WIN else "Install server (apt)")
        ib.clicked.connect(self.install_tw)
        g.addWidget(ib, n + 2, 2)
        g.setColumnStretch(1, 1)
        lay.addWidget(card)
        self.note = QLabel("")
        self.note.setObjectName("muted")
        self.note.setWordWrap(True)
        lay.addWidget(self.note)
        bar = QHBoxLayout()
        b1, b2 = QPushButton("Apply to config"), QPushButton("Apply && restart")
        b2.setObjectName("primary")
        b1.clicked.connect(lambda: self.apply(False))
        b2.clicked.connect(lambda: self.apply(True))
        bar.addWidget(b1)
        bar.addWidget(b2)
        bar.addStretch(1)
        lay.addLayout(bar)
        lay.addStretch(1)
        self.f_mode.currentTextChanged.connect(self.apply_preset)
        self.refresh()

    def refresh(self):
        s = self.mgr.settings
        v = parse_cfg(CONFIG.read_text() if CONFIG.exists() else "")
        p = MODE_PRESETS["Custom"]
        self.f_gt.setText(v.get("sv_gametype", p["gt"]))
        self.f_map.setText(v.get("sv_map", p["map"]))
        self.f_max.setText(v.get("sv_max_clients", str(p["maxc"])))
        self.f_score.setText(v.get("sv_scorelimit", "0"))
        self.f_time.setText(v.get("sv_timelimit", "0"))
        self.f_bin.setText(s.value("tw_bin", ""))
        self.f_proto.setCurrentText(s.value("tw_proto", "0.7"))
        self.f_votes.setChecked(VOTE_BEGIN in (CONFIG.read_text() if CONFIG.exists() else ""))
        found = GAME == "teeworlds" and Path(SERVER_BIN).is_file()
        self.mgr.set_status(self.bin_status, found,
                            f"Found: {SERVER_BIN}" if found else "No Teeworlds server found yet")
        self.f_mode.blockSignals(True)
        self.f_mode.setCurrentText("Custom")
        for name, q in MODE_PRESETS.items():
            if name != "Custom" and q["gt"] == self.f_gt.text() and self.f_gt.text() != "dm":
                self.f_mode.setCurrentText(name)
        self.f_mode.blockSignals(False)
        self.show_note()

    def apply_preset(self, name):
        if name != "Custom":
            p = MODE_PRESETS[name]
            self.f_gt.setText(p["gt"])
            self.f_map.setText(p["map"])
            self.f_score.setText(str(p["score"]))
            self.f_time.setText(str(p["time"]))
            self.f_max.setText(str(p["maxc"]))
        self.show_note()

    def show_note(self):
        m = self.f_mode.currentText()
        if m.startswith("Zombie"):
            t = ("Stock Teeworlds has no zombie mode - it's a mod. Build/download a zombie mod server, "
                 "set 'Server binary' to it, and set Gametype to whatever that mod expects.")
        elif m == "Custom":
            t = "Set any gametype/map your server binary supports."
        else:
            t = ("Maps must exist on the server (ctf1-8, dm1-9, lms1 ship with Teeworlds). "
                 "Import more from the Maps tab.")
        self.note.setText(t)

    def browse_bin(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select Teeworlds server binary", "",
                                           "Programs (*.exe)" if IS_WIN else "All files (*)")
        if f:
            self.f_bin.setText(f)

    def install_tw(self):
        if self.inst is not None and self.inst.state() != QProcess.NotRunning:
            return
        if IS_WIN:
            QDesktopServices.openUrl(QUrl("https://teeworlds.com/?page=downloads"))
            QMessageBox.information(self, "Get the server",
                                    "Download Teeworlds for Windows, unzip it, then use Browse to pick teeworlds_srv.exe.")
            return
        cmd = "sudo apt install -y teeworlds-server"
        if not shutil.which("pkexec"):
            QGuiApplication.clipboard().setText(cmd)
            QMessageBox.information(self, "Install manually",
                                    f"Run this in a terminal (copied to your clipboard):\n\n{cmd}")
            return
        self.inst = QProcess(self)
        self.inst.setProcessChannelMode(QProcess.MergedChannels)
        self.inst.readyRead.connect(lambda: self.mgr.append_log(
            "[install] " + bytes(self.inst.readAll()).decode("utf-8", "replace").rstrip()))
        self.inst.finished.connect(self.install_done)
        self.mgr.set_status(self.bin_status, True, "Installing... (progress shows in the Console tab)")
        self.inst.start("pkexec", ["apt-get", "install", "-y", "teeworlds-server"])

    def install_done(self, code, _status):
        apply_game("teeworlds", self.mgr.settings.value("tw_bin", ""), TW_PROTO)
        self.refresh()
        if code != 0:
            self.mgr.set_status(self.bin_status, False,
                                "Install failed - run 'sudo apt install teeworlds-server' in a terminal")
        self.mgr.add_event("Teeworlds server installed" if code == 0 else "Teeworlds install failed")

    def apply(self, restart):
        for w, what in ((self.f_max, "Max players"), (self.f_score, "Score limit"), (self.f_time, "Time limit")):
            if not w.text().strip().isdigit():
                QMessageBox.warning(self, "Check settings", f"{what} must be a number.")
                return
        m = self.mgr
        s = m.settings
        binary, proto = self.f_bin.text().strip(), self.f_proto.currentText()
        if binary != s.value("tw_bin", "") and m.running():
            QMessageBox.warning(self, "Server running", "Stop the server before changing the server binary.")
            return
        s.setValue("tw_bin", binary)
        s.setValue("tw_proto", proto)
        if not m.running():
            apply_game("teeworlds", binary, proto)
        else:
            apply_game("teeworlds", str(SERVER_BIN) if SERVER_BIN else "", proto)
        text = CONFIG.read_text() if CONFIG.exists() else TW_DEFAULT_CFG
        for k, val in (("sv_gametype", self.f_gt.text().strip()), ("sv_map", self.f_map.text().strip())):
            text = set_cfg(text, k, val)
        for k, w in (("sv_max_clients", self.f_max), ("sv_scorelimit", self.f_score), ("sv_timelimit", self.f_time)):
            text = set_cfg(text, k, w.text().strip(), quote=False)
        lines, skip = [], False
        for ln in text.splitlines():           # drop the old auto-generated vote block
            if ln.strip() == VOTE_BEGIN:
                skip = True
            if not skip:
                lines.append(ln)
            if ln.strip() == VOTE_END:
                skip = False
        text = "\n".join(lines).rstrip("\n") + "\n"
        if self.f_votes.isChecked():
            block = [VOTE_BEGIN, "clear_votes"]
            for name, p in MODE_PRESETS.items():
                if name != "Custom" and not name.startswith("Zombie"):
                    block.append(f'add_vote "{name}" "sv_gametype {p["gt"]}; change_map {p["map"]}"')
            for n in sorted(self.mgr.map_meta()[0])[:20]:
                n = n.replace('"', "")
                block.append(f'add_vote "\u2605 {n}" "change_map {n}"')
            block.append(VOTE_END)
            text += "\n".join(block) + "\n"
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(text)
        except OSError as e:
            QMessageBox.critical(self, "Could not save", str(e))
            return
        m.load_config()
        m.refresh_maps()
        self.refresh()
        m.add_event(f"Mode set to {self.f_mode.currentText()}")
        if restart:
            m.restart_server()
        elif m.running():
            QMessageBox.information(self, "Saved", "Saved. Restart the server to apply the changes.")


MOD_BEGIN, MOD_END = "# --- manager mod settings (auto) ---", "# --- end manager mod settings ---"
MOD_NOTE = ("Gametype names differ between mod builds - check your mod's readme for the exact "
            "sv_gametype value and any extra settings it needs.")
MOD_TEMPLATES = {
    "teeworlds": [
        dict(name="Zombie", bin="", gt="zombie", map="dm1", extra="", note="Humans vs infected."),
        dict(name="FreezeTag", bin="", gt="freezetag", map="ctf5", extra="",
             note="Frozen players get thawed by teammates."),
    ],
    "ddnet": [
        dict(name="Stock DDNet", bin="", gt="", map="", extra="", note="The regular DDNet server (blank binary)."),
        dict(name="Custom fork", bin="", gt="", map="", extra="", note="Point at a DDNet-based mod's server binary."),
    ],
}
MOD_KEYS = ("name", "bin", "gt", "map", "extra", "note")


def clean_mod(d):
    return {k: str(d.get(k, "")) for k in MOD_KEYS} if isinstance(d, dict) else None


class ModsPage(QWidget):
    """A library of server mods (zombie, freeze tag, DDNet forks...) you can switch between.
    Each game keeps its own list; each entry remembers its binary, gametype, map and extra commands."""

    def __init__(self, manager):
        super().__init__()
        self.mgr = manager
        self.mods, self._cur = [], -1
        root = QHBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(14)

        left = card_frame()
        ll = QVBoxLayout(left)
        ll.setContentsMargins(14, 14, 14, 14)
        self.lst = QListWidget()
        ll.addWidget(self.lst, 1)
        for label, fn in (("New", self.new_mod), ("Duplicate", self.dup_mod), ("Delete", self.del_mod),
                          ("Export", self.export_mod), ("Import", self.import_mod)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            ll.addWidget(b)
        left.setFixedWidth(210)
        root.addWidget(left)

        right = QVBoxLayout()
        card = card_frame()
        g = QGridLayout(card)
        g.setContentsMargins(18, 16, 18, 16)
        g.setHorizontalSpacing(12)
        g.setVerticalSpacing(10)
        self.f_name, self.f_bin, self.f_gt, self.f_map, self.f_note = (QLineEdit() for _ in range(5))
        self.f_bin.setPlaceholderText("path to this mod's server binary")
        self.f_extra = QPlainTextEdit()
        self.f_extra.setPlaceholderText("Extra server commands, one per line - e.g.\nsv_scorelimit 20\nsv_spectator_slots 2")
        self.f_extra.setFixedHeight(110)
        browse, opn = QPushButton("Browse"), QPushButton("Open folder")
        browse.clicked.connect(self.browse)
        opn.clicked.connect(self.open_folder)
        rows = [("Name", self.f_name), ("Gametype", self.f_gt), ("Map", self.f_map), ("Notes", self.f_note)]
        for i, (label, w) in enumerate(rows):
            g.addWidget(QLabel(label), i, 0)
            g.addWidget(w, i, 1, 1, 3)
        n = len(rows)
        g.addWidget(QLabel("Server binary"), n, 0)
        g.addWidget(self.f_bin, n, 1)
        g.addWidget(browse, n, 2)
        g.addWidget(opn, n, 3)
        g.addWidget(QLabel("Extra commands"), n + 1, 0, Qt.AlignTop)
        g.addWidget(self.f_extra, n + 1, 1, 1, 3)
        g.setColumnStretch(1, 1)
        right.addWidget(card)
        self.status = QLabel("")
        right.addWidget(self.status)
        hint = QLabel(MOD_NOTE)
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        right.addWidget(hint)
        bar = QHBoxLayout()
        save, live = QPushButton("Save"), QPushButton("Send extras to running server")
        act, actr = QPushButton("Activate"), QPushButton("Activate && restart")
        actr.setObjectName("primary")
        save.clicked.connect(self.save)
        live.clicked.connect(self.send_live)
        act.clicked.connect(lambda: self.activate(False))
        actr.clicked.connect(lambda: self.activate(True))
        for b in (save, live, act, actr):
            bar.addWidget(b)
        bar.addStretch(1)
        right.addLayout(bar)
        right.addStretch(1)
        root.addLayout(right, 1)

        self.lst.currentRowChanged.connect(self._switch)
        self.reload()

    def _k(self, name):
        return ("tw_" if GAME == "teeworlds" else "dd_") + name

    def _label(self, name):
        return ("\u25cf " if name == str(self.mgr.settings.value(self._k("active_mod"), "")) else "") + name

    def _relabel(self):
        for i, m in enumerate(self.mods):
            self.lst.item(i).setText(self._label(m["name"]))

    def reload(self):
        """(Re)load the list for the current game."""
        self._cur = -1
        self.lst.blockSignals(True)
        self.load()
        self.lst.blockSignals(False)
        row, self._cur = self._cur, -1
        self.lst.setCurrentRow(row)
        if self._cur != row:
            self._switch(row)

    # ---- storage
    def load(self):
        s = self.mgr.settings
        try:
            self.mods = [m for m in map(clean_mod, json.loads(str(s.value(self._k("mods"), "")))) if m]
        except (ValueError, TypeError):
            self.mods = []
        if not self.mods:
            self.mods = [dict(m) for m in MOD_TEMPLATES[GAME]]
        self.lst.clear()
        for m in self.mods:
            self.lst.addItem(self._label(m["name"]))
        active = str(s.value(self._k("active_mod"), ""))
        self._cur = next((i for i, m in enumerate(self.mods) if m.get("name") == active), 0)

    def persist(self):
        self.mgr.settings.setValue(self._k("mods"), json.dumps(self.mods))
        self.mgr.settings.sync()

    def _store(self):
        if not 0 <= self._cur < len(self.mods):
            return
        name = self.f_name.text().strip() or "Mod"
        self.mods[self._cur] = dict(name=name, bin=self.f_bin.text().strip(), gt=self.f_gt.text().strip(),
                                    map=self.f_map.text().strip(), extra=self.f_extra.toPlainText(),
                                    note=self.f_note.text().strip())
        item = self.lst.item(self._cur)
        if item:
            item.setText(self._label(name))

    def _switch(self, row):
        self._store()
        self._cur = row
        if row < 0:
            return
        m = self.mods[row]
        self.f_name.setText(m.get("name", ""))
        self.f_bin.setText(m.get("bin", ""))
        self.f_gt.setText(m.get("gt", ""))
        self.f_map.setText(m.get("map", ""))
        self.f_extra.setPlainText(m.get("extra", ""))
        self.f_note.setText(m.get("note", ""))
        self.refresh_status()

    def refresh_status(self):
        active = str(self.mgr.settings.value(self._k("active_mod"), ""))
        self.mgr.set_status(self.status, bool(active), f"Active mod: {active}" if active else "No mod activated yet")

    # ---- list buttons
    def new_mod(self):
        self._store()
        self.mods.append(dict(name="New mod", bin="", gt="", map="", extra="", note=""))
        self.lst.addItem("New mod")
        self.lst.setCurrentRow(len(self.mods) - 1)

    def dup_mod(self):
        self._store()
        if self._cur < 0:
            return
        c = dict(self.mods[self._cur])
        c["name"] += " copy"
        self.mods.append(c)
        self.lst.addItem(c["name"])
        self.lst.setCurrentRow(len(self.mods) - 1)

    def del_mod(self):
        if self._cur < 0 or QMessageBox.question(self, "Delete mod",
                                                 f"Delete \"{self.mods[self._cur]['name']}\"?") != QMessageBox.Yes:
            return
        row = self._cur
        self._cur = -1                      # don't let _switch re-store the deleted entry
        del self.mods[row]
        self.lst.takeItem(row)
        if not self.mods:
            self.mods = [dict(name="New mod", bin="", gt="", map="", extra="", note="")]
            self.lst.addItem("New mod")
        self.lst.setCurrentRow(min(row, len(self.mods) - 1))
        self.persist()

    def export_mod(self):
        self._store()
        if self._cur < 0:
            return
        m = dict(self.mods[self._cur], bin="")      # binary paths are machine-specific
        f, _ = QFileDialog.getSaveFileName(self, "Export mod", f"{m['name']}.json", "JSON (*.json)")
        if f:
            try:
                Path(f).write_text(json.dumps(m, indent=2))
            except OSError as e:
                QMessageBox.critical(self, "Could not export", str(e))

    def import_mod(self):
        f, _ = QFileDialog.getOpenFileName(self, "Import mod", "", "JSON (*.json)")
        if not f:
            return
        try:
            data = json.loads(Path(f).read_text())
        except (OSError, ValueError) as e:
            QMessageBox.critical(self, "Could not import", str(e))
            return
        new = [m for m in map(clean_mod, data if isinstance(data, list) else [data]) if m and m["name"]]
        if not new:
            QMessageBox.warning(self, "Could not import", "That file doesn't look like an exported mod.")
            return
        self._store()
        for m in new:
            while any(m["name"] == x["name"] for x in self.mods):
                m["name"] += " (imported)"
            self.mods.append(m)
            self.lst.addItem(self._label(m["name"]))
        self.lst.setCurrentRow(len(self.mods) - 1)
        self.persist()

    def browse(self):
        f, _ = QFileDialog.getOpenFileName(self, "Select this mod's server binary")
        if f:
            self.f_bin.setText(f)

    def open_folder(self):
        b = self.f_bin.text().strip()
        if b and Path(b).parent.is_dir():
            QDesktopServices.openUrl(QUrl.fromLocalFile(str(Path(b).parent)))

    def save(self):
        self._store()
        self.persist()

    # ---- actions
    def send_live(self):
        self._store()
        lines = [l.strip() for l in self.mods[self._cur]["extra"].splitlines() if l.strip()] if self._cur >= 0 else []
        if not lines:
            QMessageBox.information(self, "Nothing to send", "This mod has no extra commands.")
            return
        for l in lines:
            if not self.mgr.send_cmd(l):
                break

    def activate(self, restart):
        self._store()
        self.persist()
        if self._cur < 0:
            return
        mod, m, st = self.mods[self._cur], self.mgr, self.mgr.settings
        tw, binary = GAME == "teeworlds", mod["bin"]
        stock = stock_ddnet_dir() / ("DDNet-Server" + EXE)
        if binary or tw:                              # blank on DDNet = the stock server
            if not binary or not Path(binary).is_file() or not os.access(binary, os.X_OK):
                QMessageBox.warning(self, "Check mod", "Set a server binary that exists and is executable.")
                return
        if tw and not mod["gt"]:
            QMessageBox.warning(self, "Check mod", "Set the gametype this mod expects.")
            return
        if m.running() and str(Path(binary) if binary else stock) != str(SERVER_BIN):
            QMessageBox.warning(self, "Server running", "Stop the server before switching to a different binary.")
            return
        st.setValue("tw_bin" if tw else "dd_bin", binary)
        if not m.running():
            apply_game(GAME, str(st.value("tw_bin", "")), str(st.value("tw_proto", "0.7")),
                       str(st.value("dd_bin", "")))
        text = CONFIG.read_text() if CONFIG.exists() else (TW_DEFAULT_CFG if tw else "")
        lines, skip = [], False
        for ln in text.splitlines():           # drop the previous mod's auto block
            if ln.strip() == MOD_BEGIN:
                skip = True
            if not skip:
                lines.append(ln)
            if ln.strip() == MOD_END:
                skip = False
        text = "\n".join(lines).rstrip("\n") + "\n"
        if mod["gt"]:                              # blank = leave the config's value alone
            text = set_cfg(text, "sv_gametype", mod["gt"])
        if mod["map"]:
            text = set_cfg(text, "sv_map", mod["map"])
        extra = [l.strip() for l in mod["extra"].splitlines() if l.strip()]
        if extra:
            text = text.rstrip("\n") + "\n" + "\n".join([MOD_BEGIN] + extra + [MOD_END]) + "\n"
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            if CONFIG.exists():                    # one-step undo if a mod's settings go wrong
                shutil.copy2(CONFIG, CONFIG.with_name(CONFIG.name + ".bak"))
            CONFIG.write_text(text)
        except OSError as e:
            QMessageBox.critical(self, "Could not save", str(e))
            return
        st.setValue(self._k("active_mod"), mod["name"])
        m.load_config()
        m.refresh_maps()
        if tw:
            m.modes.refresh()
        self._relabel()
        self.refresh_status()
        m.add_event(f"Mod set to {mod['name']}")
        m.discord_event("mod", "🧩 Mod changed", f"Now set to **{esc_md(mod['name'])}**.", 0x8B5CF6)
        m.card_touch()
        m.refresh_ann_box()
        if restart:
            m.restart_server()
        elif m.running():
            QMessageBox.information(self, "Saved", "Saved. Restart the server to apply the mod.")


# ---------------------------------------------------------------- main window
class Manager(QMainWindow):
    sig_log = pyqtSignal(str)
    sig_discord = pyqtSignal(bool, str)
    sig_tool = pyqtSignal(str, bool, str)

    def __init__(self):
        super().__init__()
        self.setWindowTitle("DDNet Server Manager")
        self.resize(1120, 720)
        self.setMinimumSize(900, 600)
        self.setAcceptDrops(True)
        self.settings = QSettings("ddnet-manager", "ddnet-manager")
        self.apply_theme()
        global DD_DIR
        DD_DIR = str(self.settings.value("dd_dir", "") or "")
        g = self.settings.value("game", "ddnet")
        apply_game(g if g in ("ddnet", "teeworlds") else "ddnet",
                   self.settings.value("tw_bin", ""), self.settings.value("tw_proto", "0.7"),
                   self.settings.value("dd_bin", ""))
        self.players = {}          # cid -> {"name":..., "ip":...}
        self.player_team = {}      # cid -> team number (0 = no team)
        self.pending = []          # cids waiting for their name, in join order
        self.started_at = None
        self.restart_pending = False
        self.buf = ""
        self.cpu_prev = read_cpu()
        self.stopping = False
        self.public_ip = ""
        self.public_ip_at = 0
        self._ip_busy = False
        self.crash_times = []
        self.last_restart_day = None
        self.last_backup_day = None
        self.decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        self.notifier = DiscordNotifier(lambda ok, msg: self.sig_discord.emit(ok, msg))
        self.stats = load_stats()
        self._batch, self.sess, self.cur_map = [], None, ""
        self.card_id = str(self.settings.value("discord_card_id", ""))
        self.batch_timer, self.card_timer = QTimer(self), QTimer(self)
        for t, ms, fn in ((self.batch_timer, 20000, self.flush_batch), (self.card_timer, 3000, self.push_card)):
            t.setSingleShot(True)
            t.setInterval(ms)
            t.timeout.connect(fn)
        self.tray, self._tray_run, self._quitting = None, None, False
        self.rss_hist, self.err_times, self._rss_at = deque(maxlen=240), deque(maxlen=200), 0
        QTimer.singleShot(0, self.apply_tray)

        self.proc = QProcess(self)
        self.proc.setProcessChannelMode(QProcess.MergedChannels)
        if IS_WIN:
            try:        # keep the server's console window from popping up
                def _no_window(args):
                    args.flags |= 0x08000000        # CREATE_NO_WINDOW
                self.proc.setCreateProcessArgumentsModifier(_no_window)
            except Exception:
                pass
        self.proc.readyRead.connect(self.on_output)
        self.proc.started.connect(self.on_started)
        self.proc.finished.connect(self.on_finished)
        self.proc.errorOccurred.connect(self.on_error)
        # Teeworlds has no input FIFO, so commands go through its external console (ec_port)
        self.econ = QTcpSocket(self)
        self.econ_ok, self.econ_sent_pw = False, False
        self.econ_pw, self.econ_port, self.econ_tries = "", 0, 0
        self.econ.readyRead.connect(self.on_econ_read)
        self.econ.disconnected.connect(self.on_econ_down)
        self.econ_timer = QTimer(self)
        self.econ_timer.timeout.connect(self.econ_poll)
        self.econ_timer.start(1000)
        self.last_warn_day = None
        self.rot_next, self.rot_idx, self.ann_next, self.ann_idx = 0, 0, 0, 0
        self.hist = {k: deque(maxlen=HistoryGraph.MAXLEN) for k in ("cpu", "mem", "temp", "players")}
        self.expanded, self.click_targets, self.temp_alert_at = None, {}, 0
        self.sig_log.connect(self.append_log)
        self.sig_discord.connect(self.on_discord_result)
        self.sig_tool.connect(self.on_tool_result)
        geo = self.settings.value("geometry")
        if geo:
            self.restoreGeometry(geo)

        self.build_ui()
        self.load_config()
        self.load_discord_settings()
        self.load_tools_settings()
        self.load_custom_settings()
        self.refresh_maps()
        self.update_state()

        self.timer = QTimer(self)
        self.timer.timeout.connect(self.tick)
        self.timer.start(2000)
        self.tick()

        if self.settings.value("autostart", False, type=bool):
            QTimer.singleShot(500, self.start_server)

    # ------------------------------------------------------------ UI build
    def build_ui(self):
        root = QWidget()
        root.setAcceptDrops(True)
        self.setCentralWidget(root)
        outer = QHBoxLayout(root)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.setSpacing(0)

        # sidebar
        side = QFrame()
        side.setObjectName("sidebar")
        side.setFixedWidth(220)
        self._sidebar = side
        sl = QVBoxLayout(side)
        sl.setContentsMargins(14, 22, 14, 18)
        sl.setSpacing(4)
        logo = QLabel("DDNet")
        logo.setObjectName("logo")
        self.logo = logo
        sub = QLabel("Server Manager")
        sub.setObjectName("muted")
        sl.addWidget(logo)
        sl.addWidget(sub)
        sl.addSpacing(18)

        self.pages = QStackedWidget()
        self.titles = ["Dashboard", "Players", "Teams", "Chat", "Console", "Maps", "Alerts", "Tools", "Config", "Modes", "Mods", "Customize", "System Details"]
        self.nav = QButtonGroup(self)
        for i, name in enumerate(self.titles):
            b = QPushButton(name)
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.nav.addButton(b, i)
            sl.addWidget(b)
        self.nav.button(0).setChecked(True)
        # System Details is an internal dashboard screen, not a sidebar item.
        self.nav.button(12).setVisible(False)
        self.nav.buttonClicked[int].connect(self.goto)
        for i in range(len(self.titles)):
            sc = QShortcut(QKeySequence(f"Ctrl+{i + 1}"), self)
            sc.activated.connect(lambda i=i: self.nav.button(i).isVisibleTo(self) and self.nav.button(i).click())
        sl.addStretch(1)
        launch = QPushButton("Launch client")
        launch.setObjectName("launch")
        launch.setCursor(Qt.PointingHandCursor)
        launch.clicked.connect(self.launch_client)
        sl.addWidget(launch)
        outer.addWidget(side)

        # main area
        main = QVBoxLayout()
        main.setContentsMargins(28, 22, 28, 22)
        self._outer_main = main
        main.setSpacing(16)
        head = QHBoxLayout()
        self.title = QLabel("Dashboard")
        self.title.setObjectName("h1")
        self.pill = QLabel("Stopped")
        head.addWidget(self.title)
        head.addStretch(1)
        head.addWidget(self.pill)
        main.addLayout(head)
        main.addWidget(self.pages, 1)
        outer.addLayout(main, 1)

        self.pages.addWidget(self.build_dashboard())
        self.pages.addWidget(self.build_players())
        self.pages.addWidget(self.build_teams())
        self.pages.addWidget(self.build_chat())
        self.pages.addWidget(self.build_console())
        self.pages.addWidget(self.build_maps())
        self.pages.addWidget(self.build_alerts())
        self.pages.addWidget(self.build_tools())
        self.pages.addWidget(self.build_config())
        self.modes = ModesPage(self)
        self.pages.addWidget(self.modes)
        self.mod_page = ModsPage(self)
        self.pages.addWidget(self.mod_page)
        self.pages.addWidget(self.build_customize())
        self.pages.addWidget(self.build_system_details())
        self.apply_game_ui()

    def build_dashboard(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(16)

        gcard = card_frame()
        gl = QHBoxLayout(gcard)
        gl.setContentsMargins(22, 14, 22, 14)
        gt = QLabel("Game")
        gt.setObjectName("muted")
        gl.addWidget(gt)
        self.game_group = QButtonGroup(self)
        self.game_btns = {}
        for key, label in (("ddnet", "DDNet"), ("teeworlds", "Teeworlds")):
            b = QPushButton(label)
            b.setObjectName("seg")
            b.setCheckable(True)
            b.setCursor(Qt.PointingHandCursor)
            self.game_group.addButton(b)
            self.game_btns[key] = b
            b.clicked.connect(lambda _c, k=key: self.switch_game(k))
            gl.addWidget(b)
        gl.addStretch(1)
        lay.addWidget(gcard)

        ctl = card_frame()
        cl = QHBoxLayout(ctl)
        cl.setContentsMargins(22, 18, 22, 18)
        col = QVBoxLayout()
        self.srv_name = QLabel("My Server")
        self.srv_name.setObjectName("big")
        self.srv_sub = QLabel("")
        self.srv_sub.setObjectName("muted")
        col.addWidget(self.srv_name)
        col.addWidget(self.srv_sub)
        cl.addLayout(col, 1)
        self.btn_start = QPushButton("Start")
        self.btn_start.setObjectName("primary")
        self.btn_restart = QPushButton("Restart")
        self.btn_restart.setObjectName("restart")
        self.btn_stop = QPushButton("Stop")
        self.btn_stop.setObjectName("danger")
        self.btn_start.clicked.connect(self.start_server)
        self.btn_restart.clicked.connect(self.restart_server)
        self.btn_stop.clicked.connect(self.stop_server)
        for b in (self.btn_start, self.btn_restart, self.btn_stop):
            b.setCursor(Qt.PointingHandCursor)
            b.setMinimumWidth(96)
            cl.addWidget(b)
        lay.addWidget(ctl)
        self.health = QLabel("")
        self.health.setWordWrap(True)
        lay.addWidget(self.health)
        self.make_clickable(ctl, lambda: self.nav.button(8).click())

        grid = QGridLayout()
        grid.setSpacing(14)
        self.st_players = Stat("Players")
        self.st_uptime = Stat("Uptime")
        self.st_cpu = Stat(f"{DEVICE} CPU", bar=True)
        self.st_mem = Stat("Memory", bar=True)
        self.st_temp = Stat("Temperature", bar=True)
        for i, s in enumerate((self.st_players, self.st_uptime, self.st_cpu,
                               self.st_mem, self.st_temp)):
            grid.addWidget(s, 0, i)
            grid.setColumnStretch(i, 1)
        if IS_WIN:
            self.st_temp.setVisible(False)          # Windows has no simple CPU temperature reading
        lay.addLayout(grid)
        self.make_clickable(self.st_players, lambda: self.nav.button(1).click())
        for key, st in (('uptime', self.st_uptime), ('cpu', self.st_cpu), ('mem', self.st_mem),
                        ('temp', self.st_temp)):
            self.make_clickable(st, lambda k=key: self.expand_stat(k))

        bottom = QHBoxLayout()
        bottom.setSpacing(14)

        conn = card_frame()
        cv = QVBoxLayout(conn)
        cv.setContentsMargins(20, 18, 20, 18)
        cv.setSpacing(8)
        t = QLabel("Connect")
        t.setObjectName("muted")
        self._local_ip, self._port, self._pw, self._sname = "", DEFAULT_PORT, "", ""
        self._conn_key = None
        self._pub_failed = False

        rows = QGridLayout()
        rows.setHorizontalSpacing(12)
        rows.setVerticalSpacing(6)
        self.conn_vals = {}
        self.conn_btns = {}

        def add_row(r, key, label):
            lab = QLabel(label)
            lab.setObjectName("muted")
            val = QLabel("")
            val.setTextInteractionFlags(Qt.TextSelectableByMouse)
            btn = QPushButton("Copy")
            btn.setCursor(Qt.PointingHandCursor)
            btn.clicked.connect(lambda _c, k=key: self.copy_field(k))
            rows.addWidget(lab, r, 0)
            rows.addWidget(val, r, 1)
            rows.addWidget(btn, r, 2)
            self.conn_vals[key] = (lab, val)
            self.conn_btns[key] = btn

        add_row(0, "local", "Local")
        add_row(1, "public", "Public")
        add_row(2, "pass", "Password")
        rows.setColumnStretch(1, 1)
        self.conn_btns["public"].setEnabled(False)

        hint = QLabel("Use Local at home. Friends elsewhere use Public "
                      "(the UDP port must be forwarded - see Tools). Both update by themselves.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)

        qa = QLabel("Quick access")
        qa.setObjectName("muted")
        qgrid = QGridLayout()
        qgrid.setSpacing(8)
        quick = (
            ("Copy invite message", lambda: self.copy_field("invite")),
            ("Back up now", lambda: self.backup_now(False)),
            ("Open router port (UPnP)", self.open_upnp),
            ("Backups folder", self.open_backups_folder),
            ("Server files folder", self.open_server_folder),
            ("Refresh addresses", self.refresh_addresses),
        )
        for i, (label, fn) in enumerate(quick):
            b_ = QPushButton(label)
            b_.setCursor(Qt.PointingHandCursor)
            b_.clicked.connect(fn)
            qgrid.addWidget(b_, i // 2, i % 2)
        self.conn_status = QLabel("")
        self.conn_status.setWordWrap(True)

        self.q_crash = QCheckBox("Restart the server automatically if it crashes")
        self.q_crash.setChecked(self.settings.value("auto_restart_crash", True, type=bool))
        self.q_crash.toggled.connect(self.quick_crash_toggle)
        self.autostart = QCheckBox("Start the server when this app opens")
        self.autostart.setChecked(self.settings.value("autostart", False, type=bool))
        self.autostart.toggled.connect(lambda v: self.settings.setValue("autostart", v))
        cv.addWidget(t)
        cv.addLayout(rows)
        cv.addWidget(hint)
        cv.addWidget(qa)
        cv.addLayout(qgrid)
        cv.addWidget(self.conn_status)
        cv.addStretch(1)
        cv.addWidget(self.q_crash)
        cv.addWidget(self.autostart)
        bottom.addWidget(conn, 2)
        self.make_clickable(conn, lambda: self.nav.button(7).click())

        act = card_frame()
        av = QVBoxLayout(act)
        av.setContentsMargins(20, 18, 20, 18)
        t2 = QLabel("Recent activity")
        t2.setObjectName("muted")
        self.activity = QPlainTextEdit()
        self.activity.setReadOnly(True)
        self.activity.setMaximumBlockCount(60)
        self.activity.setStyleSheet("border: none; background: transparent;")
        av.addWidget(t2)
        av.addWidget(self.activity, 1)
        bottom.addWidget(act, 3)
        self.make_clickable(act, lambda: self.nav.button(4).click())
        self.make_clickable(self.activity.viewport(), lambda: self.nav.button(4).click(), frame=False)
        lay.addLayout(bottom, 1)
        return w

    def build_players(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)
        self.empty_players = QLabel("No players connected. Start the server and have a friend join.")
        self.empty_players.setObjectName("muted")
        self.empty_players.setAlignment(Qt.AlignCenter)
        self.table = QTableWidget(0, 3)
        self.table.setHorizontalHeaderLabels(["ID", "Name", "IP address"])
        self.table.verticalHeader().setVisible(False)
        self.table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.table.setShowGrid(False)
        hh = self.table.horizontalHeader()
        hh.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        self.table.verticalHeader().setDefaultSectionSize(38)
        hh.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        hh.setSectionResizeMode(1, QHeaderView.Stretch)
        hh.setSectionResizeMode(2, QHeaderView.Stretch)
        row = QHBoxLayout()
        kick = QPushButton("Kick")
        mute = QPushButton("Mute 10 min")
        self.ban_len = QComboBox()
        for label, mins in (("10 minutes", 10), ("1 hour", 60), ("1 day", 1440)):
            self.ban_len.addItem(label, mins)
        self.ban_len.setCurrentIndex(1)
        ban = QPushButton("Ban")
        ban.setObjectName("danger")
        kick.clicked.connect(lambda: self.player_action("kick {id}"))
        mute.clicked.connect(lambda: self.player_action("muteid {id} 600"))
        ban.clicked.connect(lambda: self.player_action("ban {id} " + str(self.ban_len.currentData()), confirm=True))
        save_g, open_g = QPushButton("Save to ban list..."), QPushButton("Ban list...")
        save_g.setToolTip("Add the selected player's IP to the list that is re-applied on every start.")
        save_g.clicked.connect(self.guard_add_selected)
        open_g.clicked.connect(self.guard_dialog)
        for wdg in (kick, mute, ban, self.ban_len, save_g, open_g):
            row.addWidget(wdg)
        row.addStretch(1)
        row2 = QHBoxLayout()
        row2.addStretch(1)
        for label, cmd in (("Show bans", "bans"), ("Show mutes", "mutes"), ("Refresh (status)", "status")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c, c=cmd: self.send_cmd(c))
            row2.addWidget(b)
        lay.addWidget(self.empty_players, 1)
        lay.addWidget(self.table, 1)
        lay.addLayout(row)
        lay.addLayout(row2)
        vt = QLabel("Recent votes")
        vt.setObjectName("muted")
        self.votes_box = QPlainTextEdit()
        self.votes_box.setReadOnly(True)
        self.votes_box.setMaximumBlockCount(40)
        self.votes_box.setFixedHeight(76)
        vrow = QHBoxLayout()
        yes, no = QPushButton("Pass current vote"), QPushButton("Fail current vote")
        yes.clicked.connect(lambda: self.send_cmd("vote yes"))
        no.clicked.connect(lambda: self.send_cmd("vote no"))
        vrow.addWidget(yes)
        vrow.addWidget(no)
        vrow.addStretch(1)
        for wdg in (vt, self.votes_box):
            lay.addWidget(wdg)
        lay.addLayout(vrow)
        self.table.hide()
        return w

    def build_teams(self):
        self.teams_stack = QStackedWidget()
        self.teams_stack.addWidget(self.build_teams_ddnet())
        self.teams_stack.addWidget(self.build_teams_tw())
        return self.teams_stack

    def build_teams_tw(self):
        w = QWidget()
        lay = QHBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)
        left = QVBoxLayout()
        left.setSpacing(10)
        self.tw_empty = QLabel("No players connected yet.")
        self.tw_empty.setObjectName("muted")
        self.tw_empty.setAlignment(Qt.AlignCenter)
        self.tw_table = QTableWidget(0, 3)
        self.tw_table.setHorizontalHeaderLabels(["ID", "Name", "Team"])
        self.tw_table.verticalHeader().setVisible(False)
        self.tw_table.verticalHeader().setDefaultSectionSize(38)
        self.tw_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.tw_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.tw_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.tw_table.setShowGrid(False)
        th = self.tw_table.horizontalHeader()
        th.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        th.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.Stretch)
        th.setSectionResizeMode(2, QHeaderView.Stretch)
        self.tw_table.hide()
        summary = card_frame()
        sv = QVBoxLayout(summary)
        sv.setContentsMargins(18, 14, 18, 14)
        st = QLabel("Teams overview")
        st.setObjectName("muted")
        self.tw_summary = QLabel("No players yet")
        self.tw_summary.setWordWrap(True)
        self.tw_summary.setTextFormat(Qt.RichText)
        sv.addWidget(st)
        sv.addWidget(self.tw_summary)
        left.addWidget(self.tw_empty, 1)
        left.addWidget(self.tw_table, 1)
        left.addWidget(summary)
        lay.addLayout(left, 3)

        act = card_frame()
        av = QVBoxLayout(act)
        av.setContentsMargins(20, 18, 20, 18)
        av.setSpacing(8)

        def heading(text):
            h = QLabel(text)
            h.setObjectName("muted")
            return h

        av.addWidget(heading("Selected player"))
        for label, team in (("Move to Red", 0), ("Move to Blue", 1), ("Move to Spectators", -1)):
            b = QPushButton(label)
            b.clicked.connect(lambda _c, t=team: self.tw_move(t))
            av.addWidget(b)
        av.addSpacing(10)
        av.addWidget(heading("Everyone"))
        rnd = QPushButton("Shuffle into Red / Blue")
        rnd.setObjectName("primary")
        rnd.clicked.connect(self.tw_shuffle)
        av.addWidget(rnd)
        swap = QPushButton("Swap Red and Blue")
        swap.clicked.connect(lambda: self.send_cmd("swap_teams"))
        av.addWidget(swap)
        spec = QPushButton("Everyone to Spectators")
        spec.setObjectName("danger")
        spec.clicked.connect(self.tw_all_spec)
        av.addWidget(spec)
        av.addStretch(1)
        tip = QLabel("Team info shows once players join or you move them. Needs a team gametype "
                     "(tdm / ctf) to matter.")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        av.addWidget(tip)
        lay.addWidget(act, 2)
        return w

    TW_TEAMS = {0: ("Red", "#e6647a"), 1: ("Blue", "#49a9ff")}

    @classmethod
    def tw_team_info(cls, t):
        if t == -1:
            return "Spectators", THEME["muted"]
        return cls.TW_TEAMS.get(t, ("Unknown", THEME["muted"]))

    def refresh_tw_teams(self):
        if not hasattr(self, "tw_table"):
            return
        keep = self.sel_cid(self.tw_table)
        ids = sorted(self.players)
        self.tw_table.setRowCount(len(ids))
        groups = {}
        for row, cid in enumerate(ids):
            p = self.players[cid]
            t = self.player_team.get(cid)
            label, color = self.tw_team_info(t)
            groups.setdefault(t, []).append(p["name"])
            for col, val in enumerate((str(cid), p["name"], label)):
                it = QTableWidgetItem(val)
                if col == 2:
                    it.setForeground(QColor(color))
                self.tw_table.setItem(row, col, it)
            if cid == keep:
                self.tw_table.selectRow(row)
        self.tw_table.setVisible(bool(ids))
        self.tw_empty.setVisible(not ids)
        parts = []
        for t in (0, 1, -1, None):
            if t in groups:
                label, color = self.tw_team_info(t)
                names = ", ".join(html.escape(n) for n in groups[t])
                parts.append(f'<span style="color:{color}; font-weight:700;">{label}</span> &nbsp; {names}')
        self.tw_summary.setText("<br>".join(parts) if parts else "No players yet")

    def tw_set_team(self, cid, team):
        if self.send_cmd(f"set_team {cid} {team}"):
            self.player_team[cid] = team
            self.refresh_tw_teams()

    def tw_move(self, team):
        cid = self.sel_cid(self.tw_table)
        if cid is None:
            QMessageBox.information(self, "Pick a player", "Select a player in the table first.")
            return
        self.tw_set_team(cid, team)

    def tw_shuffle(self):
        ids = list(self.players)
        if len(ids) < 2:
            QMessageBox.information(self, "Not enough players", "Need at least 2 players to make teams.")
            return
        random.shuffle(ids)
        for n, cid in enumerate(ids):
            self.tw_set_team(cid, n % 2)
        self.add_event(f"Shuffled {len(ids)} players into Red / Blue")

    def tw_all_spec(self):
        for cid in list(self.players):
            self.tw_set_team(cid, -1)

    def build_teams_ddnet(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(14)

        mode = card_frame()
        ml = QHBoxLayout(mode)
        ml.setContentsMargins(20, 14, 20, 14)
        ml.setSpacing(12)
        lb = QLabel("Team mode")
        lb.setObjectName("muted")
        self.tm_mode = QComboBox()
        self.tm_mode.addItem("Optional - players choose (default)", "1")
        self.tm_mode.addItem("Required - everyone must be in a team", "2")
        self.tm_mode.addItem("Off - no teams", "0")
        self.tm_mode.addItem("Locked - nobody can join teams", "3")
        self.tm_remember = QCheckBox("Save to config")
        self.tm_remember.setChecked(True)
        apply_b = QPushButton("Apply")
        apply_b.setObjectName("primary")
        apply_b.clicked.connect(self.apply_team_mode)
        ml.addWidget(lb)
        ml.addWidget(self.tm_mode, 1)
        ml.addWidget(self.tm_remember)
        ml.addWidget(apply_b)
        lay.addWidget(mode)

        body = QHBoxLayout()
        body.setSpacing(14)

        left = QVBoxLayout()
        left.setSpacing(10)
        self.team_empty = QLabel("No players connected yet.")
        self.team_empty.setObjectName("muted")
        self.team_empty.setAlignment(Qt.AlignCenter)
        self.team_table = QTableWidget(0, 3)
        self.team_table.setHorizontalHeaderLabels(["ID", "Name", "Team"])
        self.team_table.verticalHeader().setVisible(False)
        self.team_table.verticalHeader().setDefaultSectionSize(38)
        self.team_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        self.team_table.setSelectionBehavior(QAbstractItemView.SelectRows)
        self.team_table.setSelectionMode(QAbstractItemView.SingleSelection)
        self.team_table.setShowGrid(False)
        th = self.team_table.horizontalHeader()
        th.setDefaultAlignment(Qt.AlignLeft | Qt.AlignVCenter)
        th.setSectionResizeMode(0, QHeaderView.ResizeToContents)
        th.setSectionResizeMode(1, QHeaderView.Stretch)
        th.setSectionResizeMode(2, QHeaderView.Stretch)
        self.team_table.hide()
        summary = card_frame()
        sv = QVBoxLayout(summary)
        sv.setContentsMargins(18, 14, 18, 14)
        st = QLabel("Teams overview")
        st.setObjectName("muted")
        self.team_summary = QLabel("No teams yet")
        self.team_summary.setWordWrap(True)
        self.team_summary.setTextFormat(Qt.RichText)
        sv.addWidget(st)
        sv.addWidget(self.team_summary)
        left.addWidget(self.team_empty, 1)
        left.addWidget(self.team_table, 1)
        left.addWidget(summary)
        body.addLayout(left, 3)

        act = card_frame()
        av = QVBoxLayout(act)
        av.setContentsMargins(20, 18, 20, 18)
        av.setSpacing(8)

        def heading(text):
            h = QLabel(text)
            h.setObjectName("muted")
            return h

        nums = [str(i) for i in range(1, 33)]
        self.tm_team = QComboBox()
        self.tm_team.addItems(nums)
        mv = QPushButton("Move selected player")
        mv.clicked.connect(lambda: self.team_move(int(self.tm_team.currentText())))
        out = QPushButton("Take selected out of team")
        out.clicked.connect(lambda: self.team_move(0))
        av.addWidget(heading("Selected player"))
        r1 = QHBoxLayout()
        r1.addWidget(QLabel("Team"))
        r1.addWidget(self.tm_team, 1)
        av.addLayout(r1)
        av.addWidget(mv)
        av.addWidget(out)
        av.addSpacing(10)

        self.tm_all = QComboBox()
        self.tm_all.addItems(nums)
        allb = QPushButton("Everyone into this team")
        allb.clicked.connect(lambda: self.team_all(int(self.tm_all.currentText())))
        reset = QPushButton("Reset everyone (no team)")
        reset.setObjectName("danger")
        reset.clicked.connect(lambda: self.team_all(0))
        av.addWidget(heading("Everyone"))
        r2 = QHBoxLayout()
        r2.addWidget(QLabel("Team"))
        r2.addWidget(self.tm_all, 1)
        av.addLayout(r2)
        av.addWidget(allb)
        av.addWidget(reset)
        av.addSpacing(10)

        self.tm_size = QComboBox()
        self.tm_size.addItems([str(i) for i in range(2, 9)])
        shuf = QPushButton("Shuffle into random teams")
        shuf.setObjectName("primary")
        shuf.clicked.connect(self.team_shuffle)
        av.addWidget(heading("Random teams"))
        r3 = QHBoxLayout()
        r3.addWidget(QLabel("Players per team"))
        r3.addWidget(self.tm_size, 1)
        av.addLayout(r3)
        av.addWidget(shuf)
        av.addStretch(1)
        tip = QLabel("Do this before anyone starts running. On most maps a team can't "
                     "change once it has left the start area.")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        av.addWidget(tip)
        body.addWidget(act, 2)
        lay.addLayout(body, 1)
        return w

    def build_chat(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        chat_card = card_frame()
        cl = QVBoxLayout(chat_card)
        cl.setContentsMargins(18, 16, 18, 16)
        title = QLabel("In-game chat")
        title.setObjectName("big")
        sub = QLabel("Live messages from players and the server.")
        sub.setObjectName("muted")
        self.chat_log = QPlainTextEdit()
        self.chat_log.setReadOnly(True)
        self.chat_log.setMaximumBlockCount(2000)
        self.chat_log.setStyleSheet("border: none; background: transparent;")
        cl.addWidget(title)
        cl.addWidget(sub)
        cl.addWidget(self.chat_log, 1)
        lay.addWidget(chat_card, 1)

        send_card = card_frame()
        sl = QVBoxLayout(send_card)
        sl.setContentsMargins(18, 14, 18, 14)
        sl.setSpacing(8)
        row = QHBoxLayout()
        self.broadcast_input = QLineEdit()
        self.broadcast_input.setPlaceholderText("Type a message to your players...")
        self.broadcast_input.returnPressed.connect(self.send_say)
        say = QPushButton("Say in chat")
        say.setObjectName("primary")
        say.clicked.connect(self.send_say)
        banner = QPushButton("Broadcast banner")
        banner.clicked.connect(self.send_broadcast)
        row.addWidget(self.broadcast_input, 1)
        row.addWidget(say)
        row.addWidget(banner)
        hint = QLabel("Chat shows in everyone's chat box. A broadcast is a big banner on screen for a few seconds.")
        hint.setObjectName("muted")
        hint.setWordWrap(True)
        sl.addLayout(row)
        sl.addWidget(hint)
        lay.addWidget(send_card)
        return w

    def build_console(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.log = QPlainTextEdit()
        self.log.setReadOnly(True)
        self.log.setMaximumBlockCount(4000)
        self.log.setLineWrapMode(QPlainTextEdit.NoWrap)
        f = QFont("monospace")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(10)
        self.log.setFont(f)
        srow = QHBoxLayout()
        self.log_find = QLineEdit()
        self.log_find.setPlaceholderText("Find in the log - a player name or keyword...")
        self.log_find.textChanged.connect(self.highlight_log)
        self.log_find.returnPressed.connect(lambda: self.find_log(False))
        srow.addWidget(self.log_find, 1)
        for label, fn in (("Prev", lambda: self.find_log(True)), ("Next", lambda: self.find_log(False)),
                          ("Last error", self.jump_last_error)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            srow.addWidget(b)
        lay.addLayout(srow)
        lay.addWidget(self.log, 1)
        quick = QHBoxLayout()
        self.quick_row = quick
        self.quick_btns = []
        for label, cmd in (("Status", "status"), ("Reload map", "reload")):
            b = QPushButton(label)
            b.clicked.connect(lambda _c, c=cmd: self.send_cmd(c))
            quick.addWidget(b)
        save = QPushButton("Save log...")
        save.clicked.connect(self.save_log)
        clear = QPushButton("Clear log")
        clear.clicked.connect(self.log.clear)
        self.autoscroll = QCheckBox("Auto-scroll")
        self.autoscroll.setChecked(True)
        quick.addStretch(1)
        quick.addWidget(self.autoscroll)
        quick.addWidget(save)
        quick.addWidget(clear)
        lay.addLayout(quick)
        row = QHBoxLayout()
        self.cmd = HistoryEdit()
        self.cmd.setPlaceholderText("Type a server command, e.g. change_map Kobra 4, then press Enter")
        self.cmd.returnPressed.connect(self.on_cmd)
        send = QPushButton("Send")
        send.setObjectName("primary")
        send.clicked.connect(self.on_cmd)
        row.addWidget(self.cmd, 1)
        row.addWidget(send)
        lay.addLayout(row)
        return w

    def build_system_details(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(12)

        top = QHBoxLayout()
        back = QPushButton("← Back to Dashboard")
        back.clicked.connect(lambda: self.goto(0))
        self.detail_title = QLabel("System Details")
        self.detail_title.setObjectName("h1")
        top.addWidget(back)
        top.addWidget(self.detail_title)
        top.addStretch(1)
        lay.addLayout(top)

        card = card_frame()
        cv = QVBoxLayout(card)
        cv.setContentsMargins(20, 18, 20, 18)
        self.detail_now = QLabel("-")
        self.detail_now.setObjectName("big")
        cv.addWidget(self.detail_now)
        self.detail_graph = HistoryGraph()
        cv.addWidget(self.detail_graph)
        self.detail_summary = QLabel("")
        self.detail_summary.setObjectName("muted")
        cv.addWidget(self.detail_summary)
        self.detail_info = QPlainTextEdit()
        self.detail_info.setReadOnly(True)
        cv.addWidget(self.detail_info, 1)
        lay.addWidget(card, 1)
        return w

    def refresh_system_details(self):
        key = getattr(self, "detail_key", "cpu")
        titles = {"cpu": f"{DEVICE} CPU", "mem": "Memory", "temp": "Temperature", "uptime": "Uptime & Players"}
        if not hasattr(self, "detail_graph"):
            return
        h = list(self.hist["players" if key == "uptime" else key])
        color, unit, lo, hi, warn = self.accent_color, "%", 0, 100, None
        lines = []
        if key == "cpu":
            now = f"{h[-1]:.0f}%" if h else "-"
            try:
                la = os.getloadavg()
                lines.append(f"Load average   {la[0]:.2f}  {la[1]:.2f}  {la[2]:.2f}   ({os.cpu_count()} cores)")
            except OSError:
                pass
        elif key == "mem":
            used, tot = read_mem()
            now = f"{used / 1048576:.1f} / {tot / 1048576:.0f} GB"
            lines.append(f"In use         {used / 1048576:.2f} GB of {tot / 1048576:.2f} GB")
        elif key == "temp":
            unit, warn = " C", int(self.dset("temp_warn_c", 80))
            now = f"{h[-1]:.0f} C" if h else "n/a"
            lo, hi = min(30, int(min(h, default=30)) - 5), max(85, int(max(h, default=85)) + 5)
            th = pi_throttle()
            if th:
                lines.append("Right now      " + (", ".join(th[0]) or "all good"))
                lines.append("Since boot     " + (", ".join(th[1]) or "nothing"))
            lines.append(f"Warning line   {warn} C")
        else:
            unit, lo, hi = "", 0, max(2, int(max(h, default=0)) + 1)
            now = fmt_duration(time.time() - self.started_at) if self.started_at and self.running() else "-"
            lines.append(f"Game           {GAME_LABEL}")
            lines.append("Started        " + (datetime.fromtimestamp(self.started_at).strftime("%a %H:%M:%S") if self.started_at and self.running() else "not running"))
            lines.append(f"Players now    {len(self.players)}")
            lines.append(f"Peak (graph)   {int(max(h, default=0))}")
        self.detail_title.setText(titles.get(key, "System Details"))
        self.detail_now.setText(now)
        self.detail_graph.set_data(h, lo, hi, unit, color, warn)
        self.detail_summary.setText(
            f"Last {max(1, len(h) * 2 // 60)} min   min {min(h):.0f}{unit}   avg {sum(h) / len(h):.0f}{unit}   max {max(h):.0f}{unit}"
            if h else "")
        self.detail_info.setPlainText("\n".join(lines))

    def build_maps(self):
        w = QWidget()
        lay = QVBoxLayout(w)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(10)
        self.map_search = QLineEdit()
        self.map_search.setPlaceholderText("Search maps...")
        self.map_search.textChanged.connect(self.filter_maps)
        self.map_list = QListWidget()
        self.map_list.itemDoubleClicked.connect(lambda _i: self.change_map())
        row = QHBoxLayout()
        go = QPushButton("Change to selected map")
        go.setObjectName("primary")
        go.clicked.connect(self.change_map)
        import_btn = QPushButton("Import Map")
        import_btn.clicked.connect(self.import_map_dialog)
        folder = QPushButton("Open my maps folder")
        folder.clicked.connect(self.open_maps_folder)
        rescan = QPushButton("Rescan")
        rescan.clicked.connect(self.refresh_maps)
        fav_b = QPushButton("\u2605 Favorite")
        fav_b.setToolTip("Star or unstar the selected map. Favorites are listed first.")
        fav_b.clicked.connect(self.toggle_fav)
        row.addWidget(go)
        row.addWidget(fav_b)
        row.addStretch(1)
        row.addWidget(import_btn)
        row.addWidget(folder)
        row.addWidget(rescan)
        lay.addWidget(self.map_search)
        lay.addWidget(self.map_list, 1)
        lay.addLayout(row)
        return w

    @staticmethod
    def scroll_page():
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        grid = QGridLayout(content)
        grid.setContentsMargins(0, 0, 8, 12)
        grid.setSpacing(14)
        scroll.setWidget(content)
        return scroll, grid

    def build_config(self):
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.NoFrame)
        content = QWidget()
        lay = QVBoxLayout(content)
        lay.setContentsMargins(0, 0, 8, 12)
        lay.setSpacing(12)

        form = card_frame()
        g = QGridLayout(form)
        g.setContentsMargins(20, 18, 20, 18)
        g.setHorizontalSpacing(16)
        g.setVerticalSpacing(10)
        self.f_name = QLineEdit()
        self.f_port = QLineEdit()
        self.f_max = QLineEdit()
        self.f_max.setPlaceholderText("leave empty for the default")
        self.f_pass = QLineEdit()
        self.f_pass.setPlaceholderText("leave empty for no join password")
        self.f_rcon = QLineEdit()
        self.f_motd = QLineEdit()
        self.f_motd.setPlaceholderText("shown to players when they join (optional)")
        self.f_reg = QComboBox()
        self.f_reg.addItem("Public - DDNet clients over IPv4 (recommended)", "tw0.6/ipv4")
        self.f_reg.addItem("Public - all protocols", "1")
        self.f_reg.addItem("Private - not listed in the browser", "0")
        self.show_pw = QCheckBox("Show passwords")
        self.show_pw.toggled.connect(self.toggle_pw)
        self.toggle_pw(False)
        self.f_ipv4 = QCheckBox("IPv4 only - sv_ipv4only 1 (removes the duplicate fe80:: entry in the LAN list)")
        rows = [("Server name", self.f_name), ("Port (UDP)", self.f_port),
                ("Max players", self.f_max), ("Join password", self.f_pass),
                ("Admin (rcon) password", self.f_rcon), ("Welcome message", self.f_motd),
                ("Server listing", self.f_reg)]
        for i, (label, wd) in enumerate(rows):
            lb = QLabel(label)
            lb.setObjectName("muted")
            g.addWidget(lb, i, 0)
            g.addWidget(wd, i, 1)
        g.addWidget(self.show_pw, len(rows), 1)
        g.addWidget(self.f_ipv4, len(rows) + 1, 1)
        g.setColumnStretch(1, 1)
        lay.addWidget(form)

        t = QLabel("Full config file (advanced - shows passwords in plain text)")
        t.setObjectName("muted")
        self.raw = QPlainTextEdit()
        f = QFont("monospace")
        f.setStyleHint(QFont.Monospace)
        f.setPointSize(10)
        self.raw.setFont(f)
        self.raw.setMinimumHeight(260)
        lay.addWidget(t)
        lay.addWidget(self.raw)

        row = QHBoxLayout()
        save = QPushButton("Save")
        saver = QPushButton("Save && restart server")
        saver.setObjectName("primary")
        reload_b = QPushButton("Reload from file")
        save.clicked.connect(lambda: self.save_config(False))
        saver.clicked.connect(lambda: self.save_config(True))
        reload_b.clicked.connect(self.load_config)
        row.addWidget(save)
        row.addWidget(saver)
        restore_b = QPushButton("Restore previous config")
        restore_b.setToolTip("Swap back to the config from before your last save (click again to undo).")
        restore_b.clicked.connect(self.restore_config)
        self.cfg_review = QCheckBox("Review changes before saving")
        self.cfg_review.setChecked(self.settings.value("cfg_review", True, type=bool))
        self.cfg_review.toggled.connect(lambda v: self.settings.setValue("cfg_review", v))
        row.addStretch(1)
        row.addWidget(self.cfg_review)
        row.addWidget(restore_b)
        row.addWidget(reload_b)
        lay.addLayout(row)
        lay.addStretch(1)
        scroll.setWidget(content)
        return scroll

    def build_alerts(self):
        scroll, grid = self.scroll_page()

        conn = card_frame()
        cv = QVBoxLayout(conn)
        cv.setContentsMargins(20, 18, 20, 18)
        cv.setSpacing(8)
        title = QLabel("Discord alerts")
        title.setStyleSheet("font-size: 16px; font-weight: 700;")
        sub = QLabel("Post to a Discord channel when things happen on your server.")
        sub.setObjectName("muted")
        sub.setWordWrap(True)
        self.discord_enabled = QCheckBox("Enable Discord alerts")
        self.discord_webhook = QLineEdit()
        self.discord_webhook.setPlaceholderText("https://discord.com/api/webhooks/...")
        self.discord_webhook.setEchoMode(QLineEdit.Password)
        self.discord_show_webhook = QCheckBox("Show webhook URL")
        self.discord_show_webhook.toggled.connect(
            lambda show: self.discord_webhook.setEchoMode(QLineEdit.Normal if show else QLineEdit.Password))
        self.discord_name = QLineEdit()
        self.discord_name.setPlaceholderText("DDNet Server Manager")
        howto = QLabel(
            "<b>Setup (1 minute):</b> in your Discord server open the channel's settings, then "
            "Integrations, then Webhooks, then New Webhook, and copy its URL here.<br><br>"
            "<b>Group chats:</b> Discord doesn't allow webhooks or bots in group DMs. Make a small "
            "free server for your friends and add a channel for alerts.")
        howto.setObjectName("muted")
        howto.setWordWrap(True)
        howto.setTextFormat(Qt.RichText)
        cv.addWidget(title)
        cv.addWidget(sub)
        cv.addSpacing(4)
        cv.addWidget(self.discord_enabled)
        lb1 = QLabel("Webhook URL")
        lb1.setObjectName("muted")
        cv.addWidget(lb1)
        cv.addWidget(self.discord_webhook)
        cv.addWidget(self.discord_show_webhook)
        lb2 = QLabel("Name shown in Discord")
        lb2.setObjectName("muted")
        cv.addWidget(lb2)
        cv.addWidget(self.discord_name)
        cv.addSpacing(6)
        cv.addWidget(howto)
        cv.addStretch(1)
        grid.addWidget(conn, 0, 0)

        ev = card_frame()
        ev_l = QVBoxLayout(ev)
        ev_l.setContentsMargins(20, 18, 20, 18)
        ev_l.setSpacing(8)
        et = QLabel("What to send")
        et.setStyleSheet("font-size: 16px; font-weight: 700;")
        ev_l.addWidget(et)
        labels = {"start": "Server started", "stop": "Server stopped", "crash": "Server crashed",
                  "join": "Player joined", "leave": "Player left", "map": "Map changed",
                  "chat": "In-game chat with the tag below", "backup": "Scheduled backup finished",
                  "recap": "Session recap when the last player leaves", "mod": "Mod changed"}
        self.discord_events = {}
        for key, text in labels.items():
            box = QCheckBox(text)
            self.discord_events[key] = box
            ev_l.addWidget(box)
        self.discord_tag = QLineEdit()
        self.discord_tag.setPlaceholderText("#discord")
        self.discord_tag.setToolTip("Players type this in game chat to send a message to Discord.")
        lb3 = QLabel("Chat tag (players type it to message Discord)")
        lb3.setObjectName("muted")
        ev_l.addSpacing(4)
        ev_l.addWidget(lb3)
        ev_l.addWidget(self.discord_tag)
        lb4 = QLabel("Chat message format ({name} and {message} are filled in)")
        lb4.setObjectName("muted")
        self.discord_chat_fmt = QLineEdit()
        self.discord_chat_fmt.setPlaceholderText(DEFAULT_CHAT_FMT)
        ev_l.addWidget(lb4)
        ev_l.addWidget(self.discord_chat_fmt)
        self.discord_ping = QCheckBox("Ping @here when the first player joins")
        self.discord_addr = QCheckBox("Include the connect address")
        ev_l.addSpacing(4)
        ev_l.addWidget(self.discord_ping)
        ev_l.addWidget(self.discord_addr)
        self.discord_batch = QCheckBox("Combine busy join/leave messages (20 s)")
        self.discord_card = QCheckBox("Keep one live status message updated")
        self.discord_card.setToolTip("Edits a single message with the map, players and address "
                                     "instead of posting a new one each time.")
        ev_l.addWidget(self.discord_batch)
        ev_l.addWidget(self.discord_card)
        ev_l.addStretch(1)
        grid.addWidget(ev, 0, 1)

        row = QHBoxLayout()
        save = QPushButton("Save alert settings")
        save.setObjectName("primary")
        save.clicked.connect(lambda: self.save_discord_settings())
        test = QPushButton("Send test message")
        test.clicked.connect(self.send_discord_test)
        self.discord_status = QLabel("")
        self.discord_status.setWordWrap(True)
        row.addWidget(save)
        row.addWidget(test)
        row.addWidget(self.discord_status, 1)
        holder = QWidget()
        holder.setLayout(row)
        row.setContentsMargins(0, 0, 0, 0)
        grid.addWidget(holder, 1, 0, 1, 2)
        grid.setColumnStretch(0, 1)
        grid.setColumnStretch(1, 1)
        grid.setRowStretch(2, 1)
        return scroll

    def build_tools(self):
        scroll, grid = self.scroll_page()

        def heading(box_layout, text, sub):
            t = QLabel(text)
            t.setStyleSheet("font-size: 16px; font-weight: 700;")
            d = QLabel(sub)
            d.setObjectName("muted")
            d.setWordWrap(True)
            box_layout.addWidget(t)
            box_layout.addWidget(d)

        def status_label():
            lb = QLabel("")
            lb.setWordWrap(True)
            return lb

        def time_edit():
            e = QLineEdit()
            e.setFixedWidth(84)
            e.setMaxLength(5)
            e.setPlaceholderText("HH:MM")
            return e

        # ---- network
        net = card_frame()
        nl = QVBoxLayout(net)
        nl.setContentsMargins(20, 18, 20, 18)
        nl.setSpacing(8)
        heading(nl, "Network", "Help friends outside your house connect.")
        nrow = QHBoxLayout()
        b_ip = QPushButton("Look up public IP")
        b_ip.clicked.connect(self.lookup_public_ip)
        b_up = QPushButton("Open router port (UPnP)")
        b_up.clicked.connect(self.open_upnp)
        nrow.addWidget(b_ip)
        nrow.addWidget(b_up)
        nrow.addStretch(1)
        nl.addLayout(nrow)
        self.net_status = status_label()
        nl.addWidget(self.net_status)
        tip = QLabel("On Windows, forward the server's UDP port in your router's settings (automatic opening isn't "
                     "available), and click Allow when Windows Firewall asks." if IS_WIN else
                     "UPnP needs the miniupnpc package (sudo apt install -y miniupnpc) and UPnP turned on "
                     "in your router. If it can't work, forward UDP 8303 in the router by hand.")
        tip.setObjectName("muted")
        tip.setWordWrap(True)
        nl.addWidget(tip)
        nl.addStretch(1)
        grid.addWidget(net, 0, 0)

        # ---- backups
        bk = card_frame()
        bl = QVBoxLayout(bk)
        bl.setContentsMargins(20, 18, 20, 18)
        bl.setSpacing(8)
        heading(bl, "Backups", "Zips your config, rank/save databases and imported maps.")
        brow = QHBoxLayout()
        self.t_backup_daily = QCheckBox("Back up every day at")
        self.t_backup_time = time_edit()
        brow.addWidget(self.t_backup_daily)
        brow.addWidget(self.t_backup_time)
        brow.addStretch(1)
        bl.addLayout(brow)
        krow = QHBoxLayout()
        krow.addWidget(QLabel("Keep the last"))
        self.t_backup_keep = QComboBox()
        self.t_backup_keep.addItems(["3", "7", "14", "30"])
        krow.addWidget(self.t_backup_keep)
        krow.addWidget(QLabel("backups"))
        krow.addStretch(1)
        bl.addLayout(krow)
        arow = QHBoxLayout()
        b_now = QPushButton("Back up now")
        b_now.setObjectName("primary")
        b_now.clicked.connect(lambda: self.backup_now(False))
        b_open = QPushButton("Open backups folder")
        b_open.clicked.connect(self.open_backups_folder)
        arow.addWidget(b_now)
        arow.addWidget(b_open)
        arow.addStretch(1)
        bl.addLayout(arow)
        self.backup_status = status_label()
        bl.addWidget(self.backup_status)
        bl.addStretch(1)
        grid.addWidget(bk, 1, 0)

        # ---- automation
        au = card_frame()
        al = QVBoxLayout(au)
        al.setContentsMargins(20, 18, 20, 18)
        al.setSpacing(10)
        heading(al, "Automation", "Runs while this app is open (see 'open on login' below).")
        self.t_crash = QCheckBox("Restart the server automatically if it crashes")
        al.addWidget(self.t_crash)
        r1 = QHBoxLayout()
        self.t_daily_restart = QCheckBox("Restart the server every day at")
        self.t_restart_time = time_edit()
        r1.addWidget(self.t_daily_restart)
        r1.addWidget(self.t_restart_time)
        r1.addStretch(1)
        al.addLayout(r1)
        self.t_welcome = QCheckBox("Greet players in chat when they join")
        self.t_welcome_text = QLineEdit()
        self.t_welcome_text.setPlaceholderText("Welcome, {name}!")
        al.addWidget(self.t_welcome)
        al.addWidget(self.t_welcome_text)
        self.t_login = QCheckBox("Open this app (minimized) when I log in")
        al.addWidget(self.t_login)
        self.t_tray = QCheckBox("Show a tray icon (closing the window keeps the server running)")
        self.t_notify = QCheckBox("Desktop notifications for player joins and crashes")
        for box, key in ((self.t_tray, "tray_enabled"), (self.t_notify, "notify_desktop")):
            box.setChecked(self.settings.value(key, False, type=bool))
            box.toggled.connect(lambda v, k=key: self.set_tray_pref(k, v))
            al.addWidget(box)
        note = QLabel("Tip: turn on 'Start the server when this app opens' on the Dashboard too, and the "
                      "server will come back on its own after a power cut.")
        note.setObjectName("muted")
        note.setWordWrap(True)
        al.addWidget(note)
        save = QPushButton("Save automation settings")
        save.setObjectName("primary")
        save.clicked.connect(self.save_tools_settings)
        al.addWidget(save, 0, Qt.AlignLeft)
        self.tools_status = status_label()
        al.addWidget(self.tools_status)
        al.addStretch(1)
        grid.addWidget(au, 2, 0)
        stc = card_frame()
        sv = QVBoxLayout(stc)
        sv.setContentsMargins(20, 18, 20, 18)
        sv.setSpacing(8)
        stt = QLabel("Lifetime stats")
        stt.setStyleSheet("font-size: 16px; font-weight: 700;")
        sts = QLabel("Kept between launches, separately for each game. Bars show joins by hour of the day.")
        sts.setObjectName("muted")
        sts.setWordWrap(True)
        self.stat_lbl = QLabel("")
        self.hour_bars = HourBars()
        for w in (stt, sts, self.stat_lbl, self.hour_bars):
            sv.addWidget(w)
        grid.addWidget(stc, 3, 0)
        grid.setColumnStretch(0, 1)
        grid.setRowStretch(4, 1)
        return scroll

    # ------------------------------------------------------------ navigation
    def apply_game_ui(self):
        tw = GAME == "teeworlds"
        self.logo.setText(GAME_LABEL)
        self.setWindowTitle(f"{GAME_LABEL} Server Manager")
        self.game_btns[GAME].setChecked(True)
        self.refresh_profiles()
        self.teams_stack.setCurrentIndex(1 if tw else 0)   # Teams: DDRace teams vs Red/Blue
        self.f_ipv4.setVisible(not tw)                    # sv_ipv4only is DDNet-only
        self.nav.button(9).setVisible(tw)       # Modes is Teeworlds-only; Mods works for both games
        self.mod_page.reload()
        self.refresh_ann_box()
        self.refresh_stats()
        if not self.nav.button(self.pages.currentIndex()).isVisibleTo(self):
            self.nav.button(0).click()
        self.f_reg.clear()
        if tw:
            self.f_reg.addItem("Public - list on the master server", "1")
            self.f_reg.addItem("Private - not listed (LAN / direct connect)", "0")
        else:
            self.f_reg.addItem("Public - DDNet clients over IPv4 (recommended)", "tw0.6/ipv4")
            self.f_reg.addItem("Public - all protocols", "1")
            self.f_reg.addItem("Private - not listed in the browser", "0")

    def switch_game(self, key):
        if key == GAME:
            return
        if self.running():
            QMessageBox.information(self, "Stop the server first",
                                    f"Stop the {GAME_LABEL} server before switching games.")
            self.game_btns[GAME].setChecked(True)
            return
        self.settings.setValue("game", key)
        self.mod_page.save()                      # store edits under the game we're leaving
        apply_game(key, self.settings.value("tw_bin", ""), self.settings.value("tw_proto", "0.7"),
                   self.settings.value("dd_bin", ""))
        self.apply_game_ui()
        self.load_config()
        self.modes.refresh()
        self.refresh_maps()
        self.update_state()
        self.add_event(f"Switched to {GAME_LABEL}")

    # ------------------------------------------------------------ customize
    def build_customize(self):
        scroll, grid = self.scroll_page()

        def card(title, sub):
            f = card_frame()
            v = QVBoxLayout(f)
            v.setContentsMargins(20, 18, 20, 18)
            v.setSpacing(8)
            t = QLabel(title)
            t.setStyleSheet("font-size: 16px; font-weight: 700;")
            d = QLabel(sub)
            d.setObjectName("muted")
            d.setWordWrap(True)
            v.addWidget(t)
            v.addWidget(d)
            return f, v

        def row(label, widget):
            r = QHBoxLayout()
            r.addWidget(QLabel(label))
            r.addWidget(widget, 1)
            return r

        def small(placeholder, width=70):
            e = QLineEdit()
            e.setFixedWidth(width)
            e.setPlaceholderText(placeholder)
            return e

        # ---- appearance
        ap, av = card("Appearance", "Colors and text size. Changes apply instantly.")
        self.c_accent, self.c_palette, self.c_font = QComboBox(), QComboBox(), QComboBox()
        self.c_accent.addItems(list(ACCENTS) + ["Custom"])
        self.c_palette.addItems(list(PALETTES) + ["Custom"])
        self.c_font.addItems([str(i) for i in range(11, 21)])
        av.addLayout(row("Accent color", self.c_accent))
        av.addLayout(row("Background", self.c_palette))
        av.addLayout(row("Text size", self.c_font))
        cr = QHBoxLayout()
        for label, fn in (("Custom accent...", self.pick_accent), ("Custom background...", self.pick_bg),
                          ("Reset", self.reset_appearance)):
            b = QPushButton(label)
            b.clicked.connect(fn)
            cr.addWidget(b)
        av.addLayout(cr)
        for cb in (self.c_accent, self.c_palette, self.c_font):
            cb.activated.connect(self.save_appearance)
        av.addStretch(1)
        grid.addWidget(ap, 0, 0)

        # ---- profiles
        pf, pv = card("Config profiles", "Save the current server config under a name and switch back to it "
                      "any time. Profiles are per game.")
        self.prof_list = QListWidget()
        self.prof_list.setMaximumHeight(110)
        self.prof_name = QLineEdit()
        self.prof_name.setPlaceholderText("profile name, e.g. Friday CTF night")
        pv.addWidget(self.prof_list)
        pv.addWidget(self.prof_name)
        pr = QHBoxLayout()
        for label, fn, oid in (("Save current", self.profile_save, "primary"), ("Load", self.profile_load, ""),
                               ("Delete", self.profile_delete, "danger")):
            b = QPushButton(label)
            if oid:
                b.setObjectName(oid)
            b.clicked.connect(fn)
            pr.addWidget(b)
        pv.addLayout(pr)
        self.prof_status = QLabel("")
        self.prof_status.setWordWrap(True)
        pv.addWidget(self.prof_status)
        grid.addWidget(pf, 0, 1)

        # ---- map rotation
        rt, rv = card("Map rotation", "Changes the map on a timer while the server is running. One map per line.")
        self.c_rot_on = QCheckBox("Rotate maps automatically")
        self.c_rot_maps = QPlainTextEdit()
        self.c_rot_maps.setMaximumHeight(100)
        self.c_rot_maps.setPlaceholderText("Kobra 4\nMulana\nctf5")
        self.c_rot_min = small("min")
        self.c_rot_rand = QCheckBox("Random order")
        rr = QHBoxLayout()
        rr.addWidget(QLabel("Every"))
        rr.addWidget(self.c_rot_min)
        rr.addWidget(QLabel("minutes"))
        rr.addStretch(1)
        rr.addWidget(self.c_rot_rand)
        add_sel = QPushButton("Add map selected on Maps tab")
        add_sel.clicked.connect(self.rot_add_selected)
        sv = QPushButton("Save rotation")
        sv.setObjectName("primary")
        sv.clicked.connect(self.save_rotation)
        self.rot_status = QLabel("")
        self.rot_status.setWordWrap(True)
        for w in (self.c_rot_on, self.c_rot_maps):
            rv.addWidget(w)
        rv.addLayout(rr)
        br = QHBoxLayout()
        br.addWidget(add_sel)
        br.addWidget(sv)
        rv.addLayout(br)
        rv.addWidget(self.rot_status)
        grid.addWidget(rt, 1, 0)

        # ---- announcements
        an, nv = card("Announcements", "Cycles through your messages while players are online.")
        self.c_ann_on = QCheckBox("Send announcements automatically")
        self.c_ann_text = QPlainTextEdit()
        self.c_ann_text.setMaximumHeight(100)
        self.c_ann_text.setPlaceholderText("Join our Discord!\nBe nice to each other.")
        self.c_ann_min = small("min")
        self.c_ann_bc = QCheckBox("Use broadcast (on-screen) instead of chat")
        ar = QHBoxLayout()
        ar.addWidget(QLabel("Every"))
        ar.addWidget(self.c_ann_min)
        ar.addWidget(QLabel("minutes"))
        ar.addStretch(1)
        sa = QPushButton("Save announcements")
        sa.setObjectName("primary")
        sa.clicked.connect(self.save_announcements)
        self.ann_status = QLabel("")
        self.ann_status.setWordWrap(True)
        self.ann_for = QLabel("")
        self.ann_for.setObjectName("muted")
        for w in (self.c_ann_on, self.c_ann_text, self.ann_for):
            nv.addWidget(w)
        nv.addLayout(ar)
        nv.addWidget(self.c_ann_bc)
        nv.addWidget(sa)
        nv.addWidget(self.ann_status)
        grid.addWidget(an, 1, 1)

        # ---- console buttons + misc
        qk, kv = card("Console buttons & alerts", "Your own one-click commands for the Console tab, "
                      "as Label=command, one per line.")
        self.c_quick = QPlainTextEdit()
        self.c_quick.setMaximumHeight(90)
        self.c_quick.setPlaceholderText("Restart map=reload\nMute chat=sv_chat_delay 5")
        self.c_beep = QCheckBox("Play a sound when a player joins")
        self.c_temp_on = QCheckBox(f"Warn me when the {DEVICE} reaches")
        self.c_temp_val = small("C", 60)
        tr = QHBoxLayout()
        tr.addWidget(self.c_temp_on)
        tr.addWidget(self.c_temp_val)
        tr.addWidget(QLabel("C"))
        tr.addStretch(1)
        sq = QPushButton("Save")
        sq.setObjectName("primary")
        sq.clicked.connect(self.save_quick)
        self.quick_status = QLabel("")
        kv.addWidget(self.c_quick)
        kv.addWidget(self.c_beep)
        kv.addLayout(tr)
        kv.addWidget(sq)
        kv.addWidget(self.quick_status)
        grid.addWidget(qk, 2, 0, 1, 2)
        grid.setRowStretch(3, 1)
        return scroll

    def apply_theme(self):
        s = self.settings
        try:
            font = int(s.value("ui_font", 14))
        except (TypeError, ValueError):
            font = 14
        accent = str(s.value("ui_accent", "Blue"))
        custom = str(s.value("ui_accent_custom", "#2f86ff"))
        self.accent_color = QColor(resolve_accent(accent, custom)[0])
        self.accent_hi = resolve_accent(accent, custom)[1]
        QApplication.instance().setStyleSheet(build_qss(accent, str(s.value("ui_palette", "Navy")), font,
                                                        custom, str(s.value("ui_bg_custom", "#07101f"))))
        if getattr(self, "expanded", None) is not None:
            self.expanded.refresh()
        if getattr(self, "pill", None) is not None:
            self.update_state()
        if getattr(self, "tray", None) is not None:
            self.tray.setIcon(self.tray_icon())
        self.refresh_stats()
        self.restyle_statuses()
        for w_ in self.findChildren((HourBars, HistoryGraph)):
            w_.update()
        if getattr(self, "health", None) is not None:
            self.update_health()
        if getattr(self, "conn_vals", None):
            self.refresh_connect(force=True)

    def pick_accent(self):
        c = ColorPicker.get_color(self, str(self.settings.value("ui_accent_custom", "#2f86ff")),
                                  "Pick an accent color")
        if c.isValid():
            self.settings.setValue("ui_accent_custom", c.name())
            self.c_accent.setCurrentText("Custom")
            self.save_appearance()

    def pick_bg(self):
        c = ColorPicker.get_color(self, str(self.settings.value("ui_bg_custom", "#07101f")),
                                  "Pick a background color (dark colors work best)")
        if c.isValid():
            self.settings.setValue("ui_bg_custom", c.name())
            self.c_palette.setCurrentText("Custom")
            self.save_appearance()

    def reset_appearance(self):
        self.c_accent.setCurrentText("Blue")
        self.c_palette.setCurrentText("Navy")
        self.c_font.setCurrentText("14")
        self.save_appearance()

    def save_appearance(self, *_):
        s = self.settings
        s.setValue("ui_accent", self.c_accent.currentText())
        s.setValue("ui_palette", self.c_palette.currentText())
        s.setValue("ui_font", int(self.c_font.currentText()))
        s.sync()
        self.apply_theme()

    def load_custom_settings(self):
        s, d = self.settings, self.dset
        self.c_accent.setCurrentText(str(s.value("ui_accent", "Blue")))
        self.c_palette.setCurrentText(str(s.value("ui_palette", "Navy")))
        self.c_font.setCurrentText(str(s.value("ui_font", 14)))
        self.c_rot_on.setChecked(d("rot_on", False))
        self.c_rot_maps.setPlainText(d("rot_maps", ""))
        self.c_rot_min.setText(str(d("rot_min", 30)))
        self.c_rot_rand.setChecked(d("rot_random", False))
        self.c_ann_on.setChecked(d("ann_on", False))
        self.refresh_ann_box()
        self.c_ann_min.setText(str(d("ann_min", 10)))
        self.c_ann_bc.setChecked(d("ann_bc", False))
        self.c_quick.setPlainText(d("quick_cmds", ""))
        self.c_beep.setChecked(d("beep_join", False))
        self.c_temp_on.setChecked(d("temp_warn_on", True))
        self.c_temp_val.setText(str(d("temp_warn_c", 80)))
        self.refresh_profiles()
        self.rebuild_quick()

    # -- profiles
    @staticmethod
    def profile_path(name):
        safe = re.sub(r"[^\w\- ]", "", name).strip()
        return (PROFILE_DIR / f"{GAME}-{safe}.cfg") if safe else None

    def refresh_profiles(self):
        if not hasattr(self, "prof_list"):
            return
        self.prof_list.clear()
        if PROFILE_DIR.is_dir():
            for p in sorted(PROFILE_DIR.glob(f"{GAME}-*.cfg"), key=lambda x: x.name.lower()):
                self.prof_list.addItem(p.stem[len(GAME) + 1:])

    def profile_save(self):
        p = self.profile_path(self.prof_name.text())
        if p is None:
            self.set_status(self.prof_status, False, "Type a name for the profile first.")
            return
        try:
            PROFILE_DIR.mkdir(parents=True, exist_ok=True)
            p.write_text(CONFIG.read_text() if CONFIG.exists() else "")
        except OSError as e:
            self.set_status(self.prof_status, False, f"Couldn't save: {e}")
            return
        self.refresh_profiles()
        self.set_status(self.prof_status, True, f"Saved profile \"{p.stem[len(GAME) + 1:]}\".")

    def profile_load(self):
        it = self.prof_list.currentItem()
        p = self.profile_path(it.text()) if it else None
        if p is None or not p.exists():
            self.set_status(self.prof_status, False, "Pick a profile from the list.")
            return
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            CONFIG.write_text(p.read_text())
        except OSError as e:
            self.set_status(self.prof_status, False, f"Couldn't load: {e}")
            return
        self.load_config()
        self.modes.refresh()
        self.add_event(f"Loaded profile {it.text()}")
        self.set_status(self.prof_status, True, f"Loaded \"{it.text()}\".")
        if self.running() and QMessageBox.question(self, "Restart?",
                                                   "Restart the server now to apply this profile?") == QMessageBox.Yes:
            self.restart_server()

    def profile_delete(self):
        it = self.prof_list.currentItem()
        p = self.profile_path(it.text()) if it else None
        if p is None:
            return
        if QMessageBox.question(self, "Delete profile", f"Delete \"{it.text()}\"?") != QMessageBox.Yes:
            return
        try:
            p.unlink()
        except OSError as e:
            self.set_status(self.prof_status, False, f"Couldn't delete: {e}")
            return
        self.refresh_profiles()
        self.set_status(self.prof_status, True, "Deleted.")

    # -- rotation / announcements / console buttons
    def rot_add_selected(self):
        item = self.map_list.currentItem()
        if item is None:
            self.set_status(self.rot_status, False, "Select a map on the Maps tab first.")
            return
        cur = self.c_rot_maps.toPlainText().rstrip("\n")
        self.c_rot_maps.setPlainText((cur + "\n" if cur else "") + self.map_name(item))

    def save_rotation(self):
        mins = self.c_rot_min.text().strip()
        if not (mins.isdigit() and int(mins) >= 1):
            self.set_status(self.rot_status, False, "Minutes must be a whole number, 1 or more.")
            return
        s = self.settings
        s.setValue("rot_on", self.c_rot_on.isChecked())
        s.setValue("rot_maps", self.c_rot_maps.toPlainText())
        s.setValue("rot_min", int(mins))
        s.setValue("rot_random", self.c_rot_rand.isChecked())
        s.sync()
        self.rot_next = 0
        self.set_status(self.rot_status, True, "Saved." if self.c_rot_on.isChecked() else "Saved (rotation is off).")

    def run_rotation(self):
        if not self.dset("rot_on", False) or not self.running() or self.stopping:
            self.rot_next = 0
            return
        now, gap = time.time(), max(1, int(self.dset("rot_min", 30))) * 60
        if not self.rot_next:
            self.rot_next = now + gap
            return
        if now < self.rot_next:
            return
        maps = [m.strip() for m in str(self.dset("rot_maps", "")).splitlines() if m.strip()]
        if not maps:
            self.rot_next = now + 60
            return
        if self.dset("rot_random", False) and len(maps) > 1:
            name = random.choice(maps)
        else:
            name = maps[self.rot_idx % len(maps)]
            self.rot_idx += 1
        if self.send_cmd(f"change_map {name}", echo=False):
            self.on_map_changed(name)
            self.rot_next = now + gap
        else:
            self.rot_next = now + 30

    def save_announcements(self):
        mins = self.c_ann_min.text().strip()
        if not (mins.isdigit() and int(mins) >= 1):
            self.set_status(self.ann_status, False, "Minutes must be a whole number, 1 or more.")
            return
        s = self.settings
        s.setValue("ann_on", self.c_ann_on.isChecked())
        s.setValue(self.ann_key(), self.c_ann_text.toPlainText())
        s.setValue("ann_min", int(mins))
        s.setValue("ann_bc", self.c_ann_bc.isChecked())
        s.sync()
        self.ann_next = 0
        self.set_status(self.ann_status, True, "Saved.")

    def run_announcements(self):
        if not self.dset("ann_on", False) or not self.running() or self.stopping:
            self.ann_next = 0
            return
        now, gap = time.time(), max(1, int(self.dset("ann_min", 10))) * 60
        if not self.ann_next:
            self.ann_next = now + gap
            return
        if now < self.ann_next:
            return
        self.ann_next = now + gap
        lines = [safe_console_text(l.strip())[:200] for l in self.ann_text_value().splitlines() if l.strip()]
        if not lines or not self.players:
            return
        text = lines[self.ann_idx % len(lines)]
        self.ann_idx += 1
        self.send_cmd(f"{'broadcast' if self.dset('ann_bc', False) else 'say'} {text}", echo=False)

    def save_quick(self):
        tv = self.c_temp_val.text().strip()
        if not (tv.isdigit() and 40 <= int(tv) <= 100):
            self.set_status(self.quick_status, False, "Temperature warning must be between 40 and 100 C.")
            return
        self.settings.setValue("temp_warn_on", self.c_temp_on.isChecked())
        self.settings.setValue("temp_warn_c", int(tv))
        self.settings.setValue("quick_cmds", self.c_quick.toPlainText())
        self.settings.setValue("beep_join", self.c_beep.isChecked())
        self.settings.sync()
        self.rebuild_quick()
        self.set_status(self.quick_status, True, "Saved - buttons are on the Console tab.")

    def rebuild_quick(self):
        for b in self.quick_btns:
            self.quick_row.removeWidget(b)
            b.deleteLater()
        self.quick_btns = []
        for line in str(self.dset("quick_cmds", "")).splitlines():
            label, sep, cmd = line.partition("=")
            label, cmd = label.strip(), cmd.strip()
            if not sep or not label or not cmd:
                continue
            b = QPushButton(label)
            b.clicked.connect(lambda _c, c=cmd: self.send_cmd(c))
            self.quick_row.insertWidget(2 + len(self.quick_btns), b)
            self.quick_btns.append(b)

    def make_clickable(self, w, callback, frame=True):
        self.click_targets[w] = callback
        w.installEventFilter(self)
        w.setCursor(Qt.PointingHandCursor)
        if frame:
            w.setProperty("clickable", True)

    def eventFilter(self, obj, ev):
        cb = self.click_targets.get(obj)
        if cb is not None and ev.type() == QEvent.MouseButtonRelease and ev.button() == Qt.LeftButton \
                and obj.rect().contains(ev.pos()):
            cb()
        return super().eventFilter(obj, ev)

    def expand_stat(self, key):
        # Keep dashboard navigation inside the manager instead of opening another window.
        self.detail_key = key
        self.goto(12)
        self.refresh_system_details()

    def goto(self, i):
        self.pages.setCurrentIndex(i)
        self.title.setText(self.titles[i])

    def toggle_pw(self, show):
        mode = QLineEdit.Normal if show else QLineEdit.Password
        self.f_pass.setEchoMode(mode)
        self.f_rcon.setEchoMode(mode)

    # ------------------------------------------------------------ state
    def running(self):
        return self.proc.state() != QProcess.NotRunning

    def set_pill(self, text, fg, bg):
        self.pill.setText(text)
        self.pill.setStyleSheet(
            f"background: {bg}; color: {fg}; border-radius: 15px; padding: 7px 18px; font-weight: 700;")

    def update_state(self):
        run = self.running()
        if self.stopping:
            self.set_pill("Stopping...", "#d7b45a", "#3a321d")
        elif run:
            self.set_pill("Running", self.accent_hi, mix(self.accent_color.name(), THEME["bg"], 0.72))
        else:
            self.set_pill("Stopped", "#e68191", "#3a2028")
        self.btn_start.setEnabled(not run)
        self.btn_stop.setEnabled(run and not self.stopping)
        self.btn_restart.setEnabled(run and not self.stopping)
        if getattr(self, "tray", None) is not None and self._tray_run != run:
            self._tray_run = run
            self.tray.setIcon(self.tray_icon())

    stopping = False

    def tick(self):
        idle, total = read_cpu()
        di, dt = idle - self.cpu_prev[0], total - self.cpu_prev[1]
        self.cpu_prev = (idle, total)
        cpu = 100 * (1 - di / dt) if dt > 0 else 0
        self.st_cpu.set(f"{cpu:.0f}%", cpu)
        self.hist["cpu"].append(cpu)
        used, tot = read_mem()
        self.st_mem.set(f"{used / 1048576:.1f} / {tot / 1048576:.0f} GB", 100 * used / tot)
        self.hist["mem"].append(100 * used / tot)
        t = read_temp()
        self.st_temp.set(f"{t:.0f} C" if t is not None else "n/a", (t or 0) / 85 * 100)
        if t is not None:
            self.hist["temp"].append(t)
        hot = (t is not None and self.dset("temp_warn_on", True) and t >= int(self.dset("temp_warn_c", 80)))
        self.st_temp.v.setStyleSheet("color: #e68191;" if hot else "")
        if hot and time.time() - self.temp_alert_at > 600:
            self.temp_alert_at = time.time()
            self.add_event(f"Pi is running hot: {t:.0f} C")
        if self.started_at and self.running():
            self.st_uptime.set(fmt_duration(time.time() - self.started_at))
        else:
            self.st_uptime.set("-")
        self.st_players.set(str(len(self.players)) if self.running() else "-")
        self.hist["players"].append(len(self.players) if self.running() else 0)
        if getattr(self, "detail_key", None) is not None and self.pages.currentIndex() == 12:
            self.refresh_system_details()
        self.run_schedules()
        self.refresh_public_ip_if_needed()
        self.refresh_connect()
        want = self.settings.value("auto_restart_crash", True, type=bool)
        if self.q_crash.isChecked() != want:
            self.q_crash.blockSignals(True)
            self.q_crash.setChecked(want)
            self.q_crash.blockSignals(False)
        self.update_health()

    # ------------------------------------------------------------ server control
    def _find_installed_ddnet(self):
        candidates = [
            shutil.which("DDNet-Server") or "",
            "/usr/games/DDNet-Server",
            "/usr/lib/games/ddnet/DDNet-Server",
            "/usr/libexec/DDNet-Server",
        ]
        for c in candidates:
            if c and Path(c).is_file() and os.access(c, os.X_OK):
                return c
        return ""

    def pick_server_windows(self):
        """Windows has no package manager: point the app at an unzipped DDNet / Teeworlds server."""
        global DD_DIR
        tw = GAME == "teeworlds"
        name = "teeworlds_srv.exe" if tw else "DDNet-Server.exe"
        url = "https://teeworlds.com/?page=downloads" if tw else "https://ddnet.org/downloads/"
        box = QMessageBox(self)
        box.setWindowTitle("Server files needed")
        box.setText(f"{GAME_LABEL} server files were not found.\n\nDownload {GAME_LABEL} for Windows, unzip it, "
                    f"then choose {name}.")
        dl, pick = box.addButton("Open download page", QMessageBox.ActionRole), box.addButton(f"Choose {name}", QMessageBox.AcceptRole)
        box.addButton(QMessageBox.Cancel)
        box.exec_()
        if box.clickedButton() is dl:
            QDesktopServices.openUrl(QUrl(url))
            return
        if box.clickedButton() is not pick:
            return
        f, _ = QFileDialog.getOpenFileName(self, f"Select {name}", str(HOME), "Server (*.exe)")
        if not f:
            return
        if tw:
            self.settings.setValue("tw_bin", f)
        else:
            DD_DIR = str(Path(f).parent)
            self.settings.setValue("dd_dir", DD_DIR)
        apply_game(GAME, str(self.settings.value("tw_bin", "")), TW_PROTO, str(self.settings.value("dd_bin", "")))
        self.load_config()
        self.refresh_maps()
        self.append_log(f"[manager] using {f}")
        self.update_state()
        QTimer.singleShot(250, self.start_server)

    def auto_install_server(self):
        if IS_WIN:
            self.pick_server_windows()
            return
        if getattr(self, "server_installer", None) is not None and self.server_installer.state() != QProcess.NotRunning:
            return
        pkg = "ddnet-server" if GAME == "ddnet" else "teeworlds-server"
        if not shutil.which("pkexec"):
            QMessageBox.information(self, "Server files missing", f"Install them with: sudo apt install -y {pkg}")
            return
        self.server_installer = QProcess(self)
        self.server_installer.setProcessChannelMode(QProcess.MergedChannels)
        self.server_installer.readyRead.connect(lambda: self.append_log(
            "[auto-install] " + bytes(self.server_installer.readAll()).decode("utf-8", "replace").rstrip()))
        self.server_installer.finished.connect(self.auto_install_done)
        self.set_pill("Installing...", "#d7b45a", "#3a321d")
        self.append_log(f"[manager] Server files are missing; installing {pkg}...")
        self.server_installer.start("pkexec", ["apt-get", "install", "-y", pkg])

    def auto_install_done(self, code, _status):
        self.server_installer = None
        if code != 0:
            self.append_log("[manager] Automatic server install failed.")
            self.update_state()
            return
        if GAME == "ddnet":
            found = self._find_installed_ddnet()
            if found:
                SERVER_BIN = Path(found)
                globals()["SERVER_BIN"] = SERVER_BIN
                globals()["SERVER_DIR"] = SERVER_BIN.parent
        else:
            apply_game("teeworlds", self.settings.value("tw_bin", ""), TW_PROTO)
        self.append_log(f"[manager] {GAME_LABEL} server files installed.")
        self.update_state()
        QTimer.singleShot(250, self.start_server)

    def start_server(self):
        if self.running():
            return
        if GAME == "teeworlds" and not SERVER_BIN.exists():
            apply_game("teeworlds", self.settings.value("tw_bin", ""), TW_PROTO)  # re-detect
        if not SERVER_BIN.exists():
            # Only install when the selected server is actually missing.
            self.auto_install_server()
            return
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            if GAME == "teeworlds":
                if not CONFIG.exists():
                    CONFIG.write_text(TW_DEFAULT_CFG)
            elif FIFO and not FIFO.exists():
                os.mkfifo(FIFO)
        except OSError as e:
            self.append_log(f"[manager] could not prepare server files: {e}")
        self.players.clear()
        self.player_team.clear()
        self.pending.clear()
        self.refresh_players()
        self.stopping = False
        self.proc.setWorkingDirectory(str(SERVER_DIR))
        text = CONFIG.read_text() if CONFIG.exists() else ""
        args = []
        if GAME == "teeworlds":
            # pass settings as arguments: works no matter where the server looks for config files
            args = [l.strip() for l in text.splitlines() if l.strip() and not l.strip().startswith("#")]
        elif not IS_WIN:
            args = [f"sv_input_fifo {FIFO}"]
        if use_econ():
            try:
                port = int(parse_cfg(text).get("sv_port", DEFAULT_PORT))
            except ValueError:
                port = int(DEFAULT_PORT)
            self.econ_port = port + 1000 if port + 1000 <= 65535 else port - 1000
            self.econ_pw = "%032x" % random.getrandbits(128)
            self.econ_tries, self.econ_ok, self.econ_sent_pw = 0, False, False
            self.econ.abort()
            args += ["ec_bindaddr 127.0.0.1", f"ec_port {self.econ_port}", f"ec_password {self.econ_pw}"]
        self.proc.start(str(SERVER_BIN), args)
        self.update_state()

    def stop_server(self):
        if not self.running() or self.stopping:
            return
        self.stopping = True
        if IS_WIN and self.econ_ok:
            self.econ.write(b"shutdown\n")      # the clean way to stop a console server on Windows
        else:
            interrupt_process(self.proc)
        QTimer.singleShot(5000, self.force_kill)
        self.update_state()

    def force_kill(self):
        if self.running():
            self.append_log("[manager] server did not exit, killing it")
            self.proc.kill()

    def restart_server(self):
        if self.running():
            self.restart_pending = True
            self.stop_server()
        else:
            self.start_server()

    def on_started(self):
        self.started_at = time.time()
        game_stats(self.stats)["sessions"] += 1
        self.rss_hist.clear()
        QTimer.singleShot(3000, self.guard_apply)
        save_stats(self.stats)
        self.refresh_stats()
        self.card_touch()
        self.append_log("[manager] server started")
        self.add_event("Server started")
        self.update_state()
        self.discord_event("start", "🟢 Server is online", f"The {GAME_LABEL} server has started.", 0x35C46A)

    def on_finished(self, code, status):
        crashed = (not self.stopping and not self.restart_pending
                   and (status == QProcess.CrashExit or code != 0))
        self.append_log(f"[manager] server exited (code {code})")
        self.econ.abort()
        self.econ_ok = False
        self.stopping = False
        if self.started_at:
            game_stats(self.stats)["uptime"] += int(time.time() - self.started_at)
            save_stats(self.stats)
        self.started_at = None
        self.sess, self.cur_map = None, ""
        self._batch.clear()
        self.players.clear()
        self.player_team.clear()
        self.pending.clear()
        self.refresh_players()
        self.update_state()
        self.refresh_stats()
        self.card_touch()
        if crashed:
            self.notify("Server crashed", f"The {GAME_LABEL} server exited unexpectedly.")
            self.add_event("Server crashed")
            self.discord_event("crash", "🟠 Server crashed",
                               f"The {GAME_LABEL} server exited unexpectedly (code {code}).", 0xE0A030)
        else:
            self.add_event("Server stopped")
            self.discord_event("stop", "🔴 Server is offline", f"The {GAME_LABEL} server has stopped.", 0xE05260)
        if self.restart_pending:
            self.restart_pending = False
            QTimer.singleShot(400, self.start_server)
        elif crashed and self.dset("auto_restart_crash", True):
            self.schedule_crash_restart()

    def schedule_crash_restart(self):
        now = time.time()
        self.crash_times = [t for t in self.crash_times if now - t < 300] + [now]
        if len(self.crash_times) > 3:
            self.append_log("[manager] crashed 4 times in 5 minutes - not restarting automatically")
            self.add_event("Auto-restart gave up (crash loop)")
            self.discord_event("crash", "⛔ Auto-restart gave up",
                               "The server keeps crashing, so it was left stopped.", 0xE05260)
            return
        self.append_log("[manager] restarting the server in 5 seconds...")

        def go():
            if not self.running():
                self.start_server()
        QTimer.singleShot(5000, go)

    def on_error(self, err):
        if err == QProcess.FailedToStart:
            self.append_log("[manager] failed to start the server")
            QMessageBox.critical(self, "Failed to start", f"Could not start:\n{SERVER_BIN}")
        self.update_state()

    def send_cmd(self, cmd, echo=True):
        if not self.running():
            self.append_log("[manager] server is not running")
            return False
        if use_econ():  # stock Teeworlds has no FIFO (and neither does Windows); use the external console
            if not self.econ_ok:
                self.append_log("[manager] console isn't connected yet - give it a few seconds after start")
                return False
            self.econ.write((cmd + "\n").encode())
            if echo:
                self.append_log(f"> {cmd}")
            return True
        try:
            fd = os.open(FIFO, os.O_WRONLY | os.O_NONBLOCK)
            try:
                os.write(fd, (cmd + "\n").encode())
            finally:
                os.close(fd)
            if echo:
                self.append_log(f"> {cmd}")
            return True
        except OSError as e:
            self.append_log(f"[manager] could not send command ({e})")
            return False

    def save_log(self):
        name = f"{GAME}-server-log-{time.strftime('%Y%m%d-%H%M')}.txt"
        f, _ = QFileDialog.getSaveFileName(self, "Save console log", str(HOME / name), "Text (*.txt)")
        if f:
            try:
                Path(f).write_text(self.log.toPlainText())
                self.add_event("Console log saved")
            except OSError as e:
                QMessageBox.critical(self, "Could not save", str(e))

    def on_cmd(self):
        text = self.cmd.text().strip()
        if not text:
            return
        self.cmd.remember(text)
        self.cmd.clear()
        self.send_cmd(text)

    def send_say(self):
        message = safe_console_text(self.broadcast_input.text().strip())
        if not message:
            return
        if len(message) > 256:
            QMessageBox.warning(self, "Message too long", "Chat messages are limited to 256 characters.")
            return
        if self.send_cmd(f"say {message}", echo=False):
            self.broadcast_input.clear()
            self.add_event("Sent a chat message")
            self.discord_from_chat("Server", message)

    def send_broadcast(self):
        message = safe_console_text(self.broadcast_input.text().strip())
        if not message:
            return
        if len(message) > 1024:
            QMessageBox.warning(self, "Announcement too long", "Keep announcements to 1024 characters or fewer.")
            return
        if self.send_cmd(f"broadcast {message}", echo=False):
            self.broadcast_input.clear()
            self.append_chat("SERVER", f"[banner] {message}", system=True)
            self.add_event("Broadcast banner sent")
            self.discord_from_chat("Server", message)

    @staticmethod
    def chat_color(name):
        return QColor.fromHsv(zlib.crc32(name.encode()) % 360, 110, 245).name()

    def append_chat(self, sender, message, team=False, system=False):
        stamp = f'<span style="color:{THEME["muted"]};">[{time.strftime("%H:%M")}]</span>'
        msg = html.escape(message)
        if system:
            row = f'{stamp} <span style="color:{THEME["muted"]};">{msg}</span>'
        else:
            tag = '<span style="color:#d7b45a;">[Team]</span> ' if team else ""
            row = f'{stamp} {tag}<b style="color:{self.chat_color(sender)};">{html.escape(sender)}</b>: {msg}'
        self.chat_log.appendHtml(row)
        sb = self.chat_log.verticalScrollBar()
        sb.setValue(sb.maximum())

    def parse_chat_message(self, cat, msg):
        if cat not in ("chat", "teamchat"):
            return False
        # DDNet logs player chat as  client_id:team:player_name: message
        m = re.match(r"^(\d+):(-?\d+):(.*)$", msg)
        if m:
            cid, rest = int(m.group(1)), m.group(3)
            known = self.players.get(cid, {}).get("name")
            if known and rest.startswith(known + ": "):
                name, text = known, rest[len(known) + 2:]
            else:
                name, sep, text = rest.partition(": ")
                if not sep:
                    name, text = "Unknown", rest
            self.append_chat(name, text, cat == "teamchat")
            self.discord_from_chat(name, text)
            return True
        self.append_chat("SERVER", msg[3:].strip() if msg.startswith("***") else msg, system=True)
        return True

    # ------------------------------------------------------------ output
    def on_output(self):
        data = self.decoder.decode(bytes(self.proc.readAll()))
        self.buf += data
        *lines, self.buf = self.buf.split("\n")
        for line in lines:
            self.handle_line(line.rstrip("\r"))

    def append_log(self, line):
        m = LOG_RE.match(line)
        level, cat, msg = m.groups() if m else ("I", "", line)
        color = "#b8cbea"
        hi = THEME["accent_hi"]
        if line.startswith("[manager]"):
            color = hi
        elif line.startswith(">"):
            color = "#8196df"
        elif level == "E":
            color = "#e68191"
        elif level == "W":
            color = "#d7b45a"
        elif cat == "chat":
            color = mix(hi, "#ffffff", 0.3)
        elif "entered the game" in msg or "joined the game" in msg:
            color = hi
        elif "dropped" in msg or "left the game" in msg:
            color = "#d7b45a"
        elif cat.split("/")[0] in ("register", "http", "storage", "engine"):
            color = THEME["muted"]
        self.log.appendHtml(f'<span style="color:{color}; white-space:pre;">{html.escape(line)}</span>')
        if self.autoscroll.isChecked():
            sb = self.log.verticalScrollBar()
            sb.setValue(sb.maximum())

    def handle_line(self, line):
        self.append_log(line)
        self.note_vote(line)
        m = LOG_RE.match(line)
        if not m:
            if GAME == "teeworlds":
                t = TW_LOG_RE.match(line)
                if t:
                    self.handle_tw_line(*t.groups())
            return
        _lvl, cat, msg = m.groups()
        if _lvl == "E":
            self.err_times.append(time.time())

        # Player lifecycle lines first: DDNet files some of them under "chat", so the
        # generic chat parser would otherwise swallow them.
        j = re.search(r"entered the game\. ClientId=(\d+) addr=<\{([^}]*)\}>", msg)
        if j:
            cid, addr = int(j.group(1)), j.group(2)
            ip = addr.rsplit(":", 1)[0]
            if cid not in self.players:
                self.pending.append(cid)
            self.players.setdefault(cid, {"name": "connecting...", "ip": ip})["ip"] = ip
            self.player_team.pop(cid, None)
            self.refresh_players()
            return
        n = re.search(r"\*\*\* '(.+)' entered and joined the game", msg)
        if n:
            name = n.group(1)
            if self.pending:
                cid = self.pending.pop(0)
                if cid in self.players:
                    self.players[cid]["name"] = name
            self.refresh_players()
            self.append_chat("SERVER", f"{name} joined the game", system=True)
            self.on_player_join(name)
            return
        d = re.search(r"client dropped\. cid=(\d+)", msg)
        if d:
            self.drop_player(int(d.group(1)))
            return
        lf = re.search(r"\*\*\* '(.+)' has left the game", msg)
        if lf:
            self.append_chat("SERVER", f"{lf.group(1)} left the game", system=True)
            for cid, p in list(self.players.items()):
                if p["name"] == lf.group(1):
                    self.drop_player(cid)
                    break
            return

        # Team and admin lines. Team messages are logged as chat, so they must be
        # checked before the chat parser too.
        tj = re.search(r"'(.+)' joined team (\d+)", msg)
        if tj:
            for cid, p in self.players.items():
                if p["name"] == tj.group(1):
                    self.player_team[cid] = int(tj.group(2))
            self.refresh_teams()
            self.append_chat("SERVER", msg[3:].strip() if msg.startswith("***") else msg, system=True)
            return
        st = re.search(r"rcon='set_team (\d+) (\d+)'", msg)
        if st and int(st.group(1)) in self.players:
            self.set_local_team(int(st.group(1)), int(st.group(2)))
        sa = re.search(r"rcon='set_team_all (\d+)'", msg)
        if sa:
            for cid in self.players:
                self.set_local_team(cid, int(sa.group(1)))
        cm = re.search(r"rcon='change_map (.+?)'", msg)
        if cm:
            self.on_map_changed(cm.group(1))
        r = re.search(r"rcon='(.*)'", msg)
        if r and cat == "server":
            self.add_event(f"Admin ran: {r.group(1)}")

        self.parse_chat_message(cat, msg)

    def handle_tw_line(self, cat, msg):
        base = 16 if TW_PROTO == "0.7" else 10   # 0.7 servers log client ids in hex
        j = re.search(r"entered the game\. ClientI[dD]=([0-9a-fA-F]+) addr=<\{([^}]*)\}>", msg)
        if j:
            cid, ip = int(j.group(1), base), j.group(2).rsplit(":", 1)[0]
            self.players.setdefault(cid, {"name": "connecting...", "ip": ip})["ip"] = ip
            self.player_team.pop(cid, None)
            self.refresh_players()
            return
        t = re.search(r"team_join player='(\d+):(.+)' team=(-?\d+)", msg)
        if t:
            cid, name, team = int(t.group(1)), t.group(2), int(t.group(3))
            p = self.players.setdefault(cid, {"name": name, "ip": ""})
            new = p["name"] != name
            p["name"] = name
            self.player_team[cid] = team
            self.refresh_players()
            if new:
                self.append_chat("SERVER", f"{name} joined the game", system=True)
                self.on_player_join(name)
            return
        d = re.search(r"client dropped\. cid=([0-9a-fA-F]+)", msg)
        if d:
            self.drop_player(int(d.group(1), base))
            return
        lv = re.search(r"leave player='(\d+):(.+)'", msg)
        if lv:
            self.drop_player(int(lv.group(1)))
            return
        self.parse_chat_message(cat, msg)

    # -- Teeworlds external console
    def econ_poll(self):
        if not use_econ() or not self.running() or self.econ_ok or not self.econ_port or self.econ_tries > 90:
            return
        if self.econ.state() == QAbstractSocket.UnconnectedState:
            self.econ_tries += 1
            self.econ_sent_pw = False
            if self.econ_tries == 30:
                self.append_log("[manager] can't reach the server's external console; commands from "
                                "this app won't work (is it a stock server that supports ec_port?)")
            self.econ.connectToHost("127.0.0.1", self.econ_port)

    def on_econ_read(self):
        data = bytes(self.econ.readAll()).decode("utf-8", "replace").lower()
        if self.econ_ok:
            return
        if "authentication successful" in data:
            self.econ_ok = True
            self.append_log("[manager] console connected")
        elif "password" in data and not self.econ_sent_pw:
            self.econ_sent_pw = True
            self.econ.write((self.econ_pw + "\n").encode())

    def on_econ_down(self):
        self.econ_ok = False
        self.econ_sent_pw = False

    def drop_player(self, cid):
        self.player_team.pop(cid, None)
        if cid in self.pending:
            self.pending.remove(cid)
        p = self.players.pop(cid, None)
        self.refresh_players()
        if p:
            self.on_player_leave(p["name"])

    def on_player_join(self, name):
        self.add_event(f"{name} joined")
        if self.dset("beep_join", False):
            QApplication.beep()
        first = len(self.players) == 1
        self.track_join(name)
        self.notify("Player joined", f"{name} joined the server.")
        if first or not self.dset("discord_batch", True):   # the first join always goes out at once
            self.discord_event("join", "🟢 Player joined", f"**{esc_md(name)}** joined the server.", 0x35C46A,
                               ping=first and self.dset("discord_ping_first", False))
        else:
            self.batch_add("join", name)
        self.card_touch()
        if self.dset("welcome_enabled", False):
            text = self.dset("welcome_text", "Welcome, {name}!").replace("{name}", name)
            text = safe_console_text(text)[:200]
            if text:
                QTimer.singleShot(1500, lambda t=text: self.send_cmd(f"say {t}", echo=False))

    def on_player_leave(self, name):
        self.add_event(f"{name} left")
        last = not self.players
        if last or not self.dset("discord_batch", True):
            self.flush_batch()
            self.discord_event("leave", "🔴 Player left", f"**{esc_md(name)}** left the server.", 0xE05260)
        else:
            self.batch_add("leave", name)
        if last:
            self.finish_session()
        self.card_touch()

    def on_map_changed(self, name):
        if GAME != "teeworlds":
            self.player_team.clear()
        self.refresh_teams()
        self.add_event(f"Map changed to {name}")
        self.count_map_play(name)
        self.cur_map = name
        if self.sess:
            self.sess["maps"].append(name)
        self.card_touch()
        self.discord_event("map", "🗺️ Map changed", f"Now playing **{esc_md(name)}**.", 0x2F86FF)

    def add_event(self, text):
        self.activity.appendPlainText(f"{time.strftime('%H:%M')}   {text}")

    def refresh_players(self):
        self.table.setRowCount(len(self.players))
        for row, cid in enumerate(sorted(self.players)):
            p = self.players[cid]
            for col, val in enumerate((str(cid), p["name"], p["ip"])):
                self.table.setItem(row, col, QTableWidgetItem(val))
        has = bool(self.players)
        self.table.setVisible(has)
        self.empty_players.setVisible(not has)
        self.st_players.set(str(len(self.players)) if self.running() else "-")
        self.refresh_teams()

    def player_action(self, template, confirm=False):
        row = self.table.currentRow()
        item = self.table.item(row, 0) if row >= 0 else None
        if item is None:
            QMessageBox.information(self, "Pick a player", "Select a player in the table first.")
            return
        name = self.players.get(int(item.text()), {}).get("name", item.text())
        if confirm and QMessageBox.question(self, "Confirm ban", f"Ban {name}?") != QMessageBox.Yes:
            return
        self.send_cmd(template.format(id=item.text()))

    # ------------------------------------------------------------ teams
    @staticmethod
    def team_color(team):
        return QColor.fromHsv((team * 47) % 360, 120, 240)

    def set_local_team(self, cid, team):
        if team:
            self.player_team[cid] = team
        else:
            self.player_team.pop(cid, None)

    def refresh_teams(self):
        if GAME == "teeworlds":
            self.refresh_tw_teams()
            return
        keep = self.sel_cid(self.team_table)
        ids = sorted(self.players)
        self.team_table.setRowCount(len(ids))
        for row, cid in enumerate(ids):
            p = self.players[cid]
            t = self.player_team.get(cid, 0)
            for col, val in enumerate((str(cid), p["name"], f"Team {t}" if t else "No team")):
                it = QTableWidgetItem(val)
                if col == 2:
                    it.setForeground(self.team_color(t) if t else QColor(THEME["muted"]))
                self.team_table.setItem(row, col, it)
            if cid == keep:
                self.team_table.selectRow(row)
        self.team_table.setVisible(bool(ids))
        self.team_empty.setVisible(not ids)
        groups = {}
        for cid in ids:
            groups.setdefault(self.player_team.get(cid, 0), []).append(self.players[cid]["name"])
        parts = []
        for t in sorted(k for k in groups if k):
            names = ", ".join(html.escape(n) for n in groups[t])
            parts.append(f'<span style="color:{self.team_color(t).name()}; font-weight:700;">'
                         f'Team {t}</span> &nbsp; {names}')
        if 0 in groups:
            names = ", ".join(html.escape(n) for n in groups[0])
            parts.append(f'<span style="color:{THEME["muted"]};">No team</span> &nbsp; {names}')
        self.team_summary.setText("<br>".join(parts) if parts else "No teams yet")

    def sel_cid(self, table):
        row = table.currentRow()
        item = table.item(row, 0) if row >= 0 else None
        return int(item.text()) if item else None

    def set_team(self, cid, team):
        if self.send_cmd(f"set_team {cid} {team}"):
            self.set_local_team(cid, team)
            self.refresh_teams()

    def team_move(self, team):
        cid = self.sel_cid(self.team_table)
        if cid is None:
            QMessageBox.information(self, "Pick a player", "Select a player in the table first.")
            return
        self.set_team(cid, team)

    def team_all(self, team):
        if not self.players:
            return
        if self.send_cmd(f"set_team_all {team}"):
            for cid in self.players:
                self.set_local_team(cid, team)
            self.refresh_teams()
            self.add_event(f"Everyone moved to team {team}" if team else "All teams reset")

    def team_shuffle(self):
        ids = list(self.players)
        if len(ids) < 2:
            QMessageBox.information(self, "Not enough players", "Need at least 2 players to make teams.")
            return
        size = int(self.tm_size.currentText())
        random.shuffle(ids)
        chunks = [ids[i:i + size] for i in range(0, len(ids), size)]
        if len(chunks) > 1 and len(chunks[-1]) == 1:
            chunks[-2] += chunks.pop()
        for n, chunk in enumerate(chunks, 1):
            for cid in chunk:
                self.set_team(cid, n)
        self.add_event(f"Shuffled {len(ids)} players into {len(chunks)} teams")

    def apply_team_mode(self):
        val = self.tm_mode.currentData()
        self.send_cmd(f"sv_team {val}")
        if self.tm_remember.isChecked():
            text = CONFIG.read_text() if CONFIG.exists() else ""
            try:
                USER_DIR.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(set_cfg(text, "sv_team", val, quote=False))
                self.load_config()
            except OSError as e:
                QMessageBox.critical(self, "Could not save", str(e))
        self.add_event(f"Team mode set to {self.tm_mode.currentText().split(' - ')[0]}")

    # ------------------------------------------------------------ maps
    def refresh_maps(self):
        names = set()
        for d in MAP_DIRS:
            if d.is_dir():
                names.update(p.stem for p in d.glob("*.map"))
        self.all_maps = sorted(names, key=str.lower)
        self.filter_maps()

    def map_meta(self):
        """(favorite map names, {map: times played}) for the current game."""
        try:
            fav = set(json.loads(str(self.settings.value(f"fav_maps_{GAME}", "[]"))))
        except (ValueError, TypeError):
            fav = set()
        try:
            plays = dict(json.loads(str(self.settings.value(f"map_plays_{GAME}", "{}"))))
        except (ValueError, TypeError):
            plays = {}
        return fav, plays

    @staticmethod
    def map_name(item):
        return item.data(Qt.UserRole) or item.text()

    def filter_maps(self):
        q = self.map_search.text().strip().lower()
        keep = self.map_name(self.map_list.currentItem()) if self.map_list.currentItem() else None
        fav, plays = self.map_meta()
        self.map_list.clear()
        for n in sorted((n for n in self.all_maps if q in n.lower()), key=lambda n: (n not in fav, n.lower())):
            it = QListWidgetItem(("\u2605 " if n in fav else "") + n + (f"    {plays[n]}\u00d7" if plays.get(n) else ""))
            it.setData(Qt.UserRole, n)
            self.map_list.addItem(it)
            if n == keep:
                self.map_list.setCurrentItem(it)

    def toggle_fav(self):
        it = self.map_list.currentItem()
        if it is None:
            QMessageBox.information(self, "Pick a map", "Select a map from the list first.")
            return
        fav, _ = self.map_meta()
        fav ^= {self.map_name(it)}
        self.settings.setValue(f"fav_maps_{GAME}", json.dumps(sorted(fav)))
        self.filter_maps()

    def count_map_play(self, name):
        _, plays = self.map_meta()
        plays[name] = plays.get(name, 0) + 1
        self.settings.setValue(f"map_plays_{GAME}", json.dumps(plays))
        self.filter_maps()

    def import_map_dialog(self):
        files, _ = QFileDialog.getOpenFileNames(
            self, "Import DDNet Map", str(Path.home() / "Downloads"), "DDNet maps (*.map)"
        )
        if files:
            self.import_map_files(files)

    def import_map_files(self, files):
        target_dir = MAP_IMPORT_DIR
        try:
            target_dir.mkdir(parents=True, exist_ok=True)
        except OSError as e:
            QMessageBox.critical(self, "Could not create maps folder", str(e))
            return

        imported = []
        skipped = []
        errors = []

        for raw_path in files:
            source = Path(raw_path)
            if source.suffix.lower() != ".map":
                skipped.append(source.name)
                continue
            try:
                destination = target_dir / source.name
                shutil.copy2(source, destination)
                imported.append(source.name)
            except OSError as e:
                errors.append(f"{source.name}: {e}")

        self.refresh_maps()

        if imported:
            self.add_event(f"Imported {len(imported)} map{'s' if len(imported) != 1 else ''}")
            if len(imported) == 1:
                self.map_search.setText(Path(imported[0]).stem)

        if errors:
            QMessageBox.warning(
                self, "Some maps could not be imported",
                "\n".join(errors)
            )
        elif skipped:
            QMessageBox.information(
                self, "Maps skipped",
                "Only .map files can be imported."
            )

    def import_dropped_maps(self, urls):
        paths = []
        for url in urls:
            if not url.isLocalFile():
                continue
            path = Path(url.toLocalFile())
            if path.is_file() and path.suffix.lower() == ".map":
                paths.append(str(path))

        if paths:
            self.import_map_files(paths)
        elif urls:
            QMessageBox.information(self, "No map files found",
                                     "Drop one or more .map files into the app.")

    def dragEnterEvent(self, event):
        if event.mimeData().hasUrls():
            local_files = [
                Path(url.toLocalFile())
                for url in event.mimeData().urls()
                if url.isLocalFile()
            ]
            if any(p.is_file() and p.suffix.lower() == ".map" for p in local_files):
                event.acceptProposedAction()
                return
        event.ignore()

    def dropEvent(self, event):
        if event.mimeData().hasUrls():
            self.import_dropped_maps(event.mimeData().urls())
            event.acceptProposedAction()
        else:
            event.ignore()

    def change_map(self):
        item = self.map_list.currentItem()
        if item is None:
            QMessageBox.information(self, "Pick a map", "Select a map from the list first.")
            return
        if GAME == "teeworlds":
            try:
                text = CONFIG.read_text() if CONFIG.exists() else TW_DEFAULT_CFG
                USER_DIR.mkdir(parents=True, exist_ok=True)
                CONFIG.write_text(set_cfg(text, "sv_map", self.map_name(item)))
            except OSError as e:
                QMessageBox.critical(self, "Could not save", str(e))
                return
            self.load_config()
            self.modes.refresh()
            self.add_event(f"Map set to {self.map_name(item)}")
            if self.running():
                self.restart_server()
            return
        if self.send_cmd(f"change_map {self.map_name(item)}"):
            self.on_map_changed(self.map_name(item))

    def open_maps_folder(self):
        target_dir = MAP_IMPORT_DIR
        target_dir.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(target_dir)))

    # ------------------------------------------------------------ config
    def load_config(self):
        text = CONFIG.read_text() if CONFIG.exists() else ""
        self.raw.setPlainText(text)
        v = parse_cfg(text)
        self.f_name.setText(v.get("sv_name", f"My {GAME_LABEL} server"))
        self.f_port.setText(v.get("sv_port", DEFAULT_PORT))
        self.f_max.setText(v.get("sv_max_clients", ""))
        self.f_pass.setText(v.get("password", ""))
        self.f_rcon.setText(v.get("sv_rcon_password", ""))
        self.f_motd.setText(v.get("sv_motd", ""))
        idx = max(0, self.f_reg.findData(v.get("sv_register", "0" if GAME == "teeworlds" else "tw0.6/ipv4")))
        self.f_reg.setCurrentIndex(idx)
        self.bind_orig = v.get("bindaddr")
        self.f_ipv4.setChecked(v.get("sv_ipv4only") == "1")
        self.srv_name.setText(self.f_name.text())
        port = self.f_port.text() or DEFAULT_PORT
        self.refresh_connect(force=True)
        sub = f"Port {port}/UDP"
        if GAME == "teeworlds":
            sub += f"  -  {v.get('sv_gametype', 'dm')} on {v.get('sv_map', '?')}"
        self.srv_sub.setText(sub + ("  -  password protected" if self.f_pass.text() else ""))
        self.update_public_label()

    def save_config(self, restart):
        maxv = self.f_max.text().strip()
        if maxv and not (maxv.isdigit() and 1 <= int(maxv) <= 64):
            QMessageBox.warning(self, "Max players", "Max players must be a number from 1 to 64.")
            return
        port = self.f_port.text().strip() or DEFAULT_PORT
        if not (port.isdigit() and 1 <= int(port) <= 65535):
            QMessageBox.warning(self, "Port", "The port must be a number from 1 to 65535.")
            return
        text = self.raw.toPlainText()
        text = set_cfg(text, "sv_name", self.f_name.text())
        text = set_cfg(text, "sv_port", port, quote=False)
        text = set_cfg(text, "sv_max_clients", maxv, quote=False)
        text = set_cfg(text, "password", self.f_pass.text())
        text = set_cfg(text, "sv_rcon_password", self.f_rcon.text())
        text = set_cfg(text, "sv_motd", self.f_motd.text())
        text = set_cfg(text, "sv_register", self.f_reg.currentData(), quote=False)
        if GAME == "ddnet":
            text = set_cfg(text, "sv_ipv4only", "1" if self.f_ipv4.isChecked() else "", quote=False)
            if self.bind_orig == "0.0.0.0":  # older versions of this manager wrote this instead
                text = set_cfg(text, "bindaddr", "", quote=False)
        if self.cfg_review.isChecked() and not self.confirm_diff(CONFIG.read_text() if CONFIG.exists() else "", text):
            return
        try:
            USER_DIR.mkdir(parents=True, exist_ok=True)
            if CONFIG.exists():
                shutil.copy2(CONFIG, CONFIG.with_name(CONFIG.name + ".bak"))
            CONFIG.write_text(text)
        except OSError as e:
            QMessageBox.critical(self, "Could not save", str(e))
            return
        self.load_config()
        self.add_event("Config saved")
        if restart:
            self.restart_server()
        elif self.running():
            QMessageBox.information(self, "Saved", "Saved. Restart the server to apply the changes.")

    # ------------------------------------------------------------ Discord
    # ------------------------------------------------------------ tray + desktop notifications
    def set_tray_pref(self, key, value):
        self.settings.setValue(key, value)
        self.apply_tray()

    def tray_icon(self):
        pm = QPixmap(64, 64)
        pm.fill(Qt.transparent)
        p = QPainter(pm)
        p.setRenderHint(QPainter.Antialiasing)
        p.setPen(Qt.NoPen)
        p.setBrush(self.accent_color if self.running() else QColor("#e68191"))   # accent = running, red = stopped
        p.drawEllipse(6, 6, 52, 52)
        p.end()
        return QIcon(pm)

    def apply_tray(self):
        want = self.dset("tray_enabled", False) and QSystemTrayIcon.isSystemTrayAvailable()
        if want and self.tray is None:
            self.tray = QSystemTrayIcon(self)
            menu = QMenu()
            for label, fn in (("Show / hide", self.toggle_window), ("Start", self.start_server),
                              ("Restart", self.restart_server), ("Stop", self.stop_server),
                              ("Quit", self.quit_app)):
                menu.addAction(label, fn)
            self._tray_menu = menu
            self.tray.setContextMenu(menu)
            self.tray.activated.connect(lambda r: r == QSystemTrayIcon.Trigger and self.toggle_window())
        if self.tray is not None:
            self.tray.setIcon(self.tray_icon())
            self.tray.setToolTip(f"{GAME_LABEL} Server Manager")
            self.tray.setVisible(bool(want))

    def toggle_window(self):
        if self.isVisible() and not self.isMinimized():
            self.hide()
        else:
            self.showNormal()
            self.raise_()
            self.activateWindow()

    def quit_app(self):
        self._quitting = True
        if not self.close():
            self._quitting = False

    def notify(self, title, message):
        if (self.tray is not None and self.tray.isVisible() and self.dset("notify_desktop", False)
                and not self.isActiveWindow()):
            self.tray.showMessage(title, message, QSystemTrayIcon.Information, 5000)

    # ------------------------------------------------------------ lifetime stats + sessions
    def refresh_stats(self):
        if getattr(self, "stat_lbl", None) is None or getattr(self, "stats", None) is None:
            return
        g = game_stats(self.stats)
        up = fmt_duration(g["uptime"] + (time.time() - self.started_at if self.started_at else 0))
        text = f"Peak players  {g['peak']}   •   Sessions  {g['sessions']}   •   Joins  {g['joins']}\nTotal uptime  {up}"
        if any(g["hours"]):
            text += f"   •   Busiest hour  {max(range(24), key=lambda h: g['hours'][h]):02d}:00"
        self.stat_lbl.setText(text)
        self.hour_bars.set_data(g["hours"], self.accent_color.name())

    def track_join(self, name):
        now = time.time()
        if self.sess is None:
            self.sess = dict(start=now, peak=0, names=set(), maps=[self.cur_map] if self.cur_map else [])
        self.sess["peak"] = max(self.sess["peak"], len(self.players))
        self.sess["names"].add(name)
        g = game_stats(self.stats)
        g["joins"] += 1
        g["hours"][datetime.now().hour] += 1
        g["peak"] = max(g["peak"], len(self.players))
        save_stats(self.stats)
        self.refresh_stats()

    def finish_session(self):
        s, self.sess = self.sess, None
        if not s or time.time() - s["start"] < 60:          # ignore quick drop-ins
            return
        maps = ", ".join(dict.fromkeys(s["maps"])) or "-"
        self.discord_event("recap", "🏁 Session recap",
                           f"Lasted **{fmt_duration(time.time() - s['start'])}** • peak **{s['peak']}** at once • "
                           f"**{len(s['names'])}** different player(s)\nMaps: {esc_md(maps)}", 0x8B5CF6)

    # ------------------------------------------------------------ discord: batching + live status message
    def batch_add(self, kind, name):
        self._batch.append((kind, name))
        if not self.batch_timer.isActive():
            self.batch_timer.start()

    def flush_batch(self):
        self.batch_timer.stop()
        batch, self._batch = self._batch, []
        joins = [n for k, n in batch if k == "join"] if self.dset("discord_ev_join", DEFAULT_EVENTS["join"]) else []
        leaves = [n for k, n in batch if k == "leave"] if self.dset("discord_ev_leave", DEFAULT_EVENTS["leave"]) else []
        if not (joins or leaves) or not self.discord_ready():
            return
        if len(joins) + len(leaves) == 1:
            if joins:
                self.discord_event("join", "🟢 Player joined", f"**{esc_md(joins[0])}** joined the server.", 0x35C46A)
            else:
                self.discord_event("leave", "🔴 Player left", f"**{esc_md(leaves[0])}** left the server.", 0xE05260)
            return
        lines = []
        for icon, word, names in (("🟢", "Joined", joins), ("🔴", "Left", leaves)):
            if names:
                lines.append(f"{icon} {word}: " + ", ".join(f"**{esc_md(n)}**" for n in names[:15]))
        self.notifier.post(self.dset("discord_webhook", "").strip(),
                           self.discord_payload("👥 Player activity", "\n".join(lines), 0x2F86FF))

    def card_touch(self):
        if self.dset("discord_card", False) and self.discord_ready():
            self.card_timer.start()          # restarts the 3 s debounce

    def card_payload(self, offline=False):
        run = self.running() and not offline
        server = self.f_name.text().strip() or f"{GAME_LABEL} server"
        embed = {"title": f"{'🟢' if run else '🔴'} {server} is {'online' if run else 'offline'}"[:250],
                 "color": 0x35C46A if run else 0xE05260,
                 "footer": {"text": "Live status • updates automatically"},
                 "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")}
        if run:
            try:
                cfg_map = parse_cfg(CONFIG.read_text()).get("sv_map", "?")
            except OSError:
                cfg_map = "?"
            mp = (self.cur_map or cfg_map).replace("`", "")
            fields = [{"name": "🗺️ Map", "value": f"`{mp}`", "inline": True},
                      {"name": "👥 Players", "value": f"`{len(self.players)}`", "inline": True}]
            if self.started_at:
                fields.append({"name": "⏱️ Started", "value": f"<t:{int(self.started_at)}:R>", "inline": True})
            mod = str(self.settings.value(self.mod_page._k("active_mod"), ""))
            if mod:
                fields.append({"name": "🧩 Mod", "value": esc_md(mod)[:100], "inline": True})
            names = ", ".join(esc_md(p["name"]) for _, p in sorted(self.players.items()))
            if names:
                fields.append({"name": "Who's on", "value": names[:1000], "inline": False})
            if self.dset("discord_addr", True) and self.public_ip:
                addr = f"{self.public_ip}:{self.f_port.text().strip() or DEFAULT_PORT}"
                fields.append({"name": "🔗 Connect", "value": f"`connect {addr}`", "inline": False})
            embed["fields"] = fields
        return {"username": (self.dset("discord_name", "").strip() or "DDNet Server Manager")[:80],
                "embeds": [embed], "allowed_mentions": {"parse": []}}

    def push_card(self, offline=False, sync=False):
        if not (self.dset("discord_card", False) and self.discord_ready()):
            return
        if self.card_id != str(self.settings.value("discord_card_id", "")):
            self.settings.setValue("discord_card_id", self.card_id)
        url, payload = self.dset("discord_webhook", "").strip(), self.card_payload(offline)
        if sync:
            ok, val = DiscordNotifier._card(url, payload, self.card_id)
            if ok:
                self.card_id = val
        else:
            self.notifier.post_card(url, payload, self.card_id, self._set_card_id)

    def _set_card_id(self, mid):             # runs on the notifier thread: plain assignment only
        self.card_id = mid

    def restore_config(self):
        bak = CONFIG.with_name(CONFIG.name + ".bak")
        if not bak.exists():
            QMessageBox.information(self, "No backup yet", "A backup is made automatically each time the config is saved.")
            return
        if QMessageBox.question(self, "Restore previous config",
                                "Swap back to the config from before your last save?\n"
                                "(Click it again afterwards to undo the restore.)") != QMessageBox.Yes:
            return
        try:
            cur = CONFIG.read_text() if CONFIG.exists() else ""
            CONFIG.write_text(bak.read_text())
            bak.write_text(cur)
        except OSError as e:
            QMessageBox.critical(self, "Could not restore", str(e))
            return
        self.load_config()
        if GAME == "teeworlds":
            self.modes.refresh()
        self.refresh_maps()
        self.add_event("Config restored")
        if self.running():
            QMessageBox.information(self, "Restored", "Restart the server to apply it.")

    # ------------------------------------------------------------ ban list
    def guard_entries(self):
        try:
            raw = json.loads(str(self.settings.value("guard_list", "[]")))
        except (ValueError, TypeError):
            raw = []
        now = time.time()
        return [e for e in map(clean_guard, raw if isinstance(raw, list) else [])
                if e and (not e["until"] or e["until"] > now)]

    def guard_save(self, entries):
        self.settings.setValue("guard_list", json.dumps(entries))
        self.settings.sync()

    def guard_apply(self, tries=0):
        """Push every live entry to the running server (bans don't survive a restart on their own)."""
        if not self.running():
            return
        cmds = [c for c in map(guard_command, self.guard_entries()) if c]
        if not cmds:
            return
        ready = self.econ_ok if use_econ() else bool(FIFO and Path(FIFO).exists())
        if not ready:
            if tries < 15:
                QTimer.singleShot(4000, lambda: self.guard_apply(tries + 1))
            return
        for c in cmds:
            self.send_cmd(c, echo=False)
        self.add_event(f"Ban list applied ({len(cmds)})")

    def guard_dialog(self, prefill=None):
        GuardDialog(self, prefill if isinstance(prefill, dict) else None).exec_()

    def guard_add_selected(self):
        item = self.table.item(self.table.currentRow(), 0) if self.table.currentRow() >= 0 else None
        if item is None:
            QMessageBox.information(self, "Pick a player", "Select a player in the table first.")
            return
        p = self.players.get(int(item.text()), {})
        self.guard_dialog(dict(ip=p.get("ip", ""), name=p.get("name", "")))

    # ------------------------------------------------------------ votes, health, log search, diff
    def note_vote(self, line):
        m = LOG_RE.match(line)
        t = TW_LOG_RE.match(line) if (GAME == "teeworlds" and not m) else None
        cat, msg = (m.group(2), m.group(3)) if m else (t.groups() if t else ("", line))
        if cat == "chat" or line.startswith(("[manager]", ">")) or "rcon='" in msg or "vote" not in msg.lower():
            return
        self.votes_box.appendPlainText(f"{time.strftime('%H:%M')}   {msg.strip()[:160]}")

    def update_health(self):
        if not self.running() or not self.started_at:
            self.health.setText("")
            return
        now = time.time()
        if now - self._rss_at >= 60:
            self._rss_at = now
            rss = read_rss(self.proc.processId())
            if rss:
                self.rss_hist.append((now, rss))
        notes, up = [], now - self.started_at
        if up > 3 * 86400:
            notes.append(f"up for {int(up // 86400)} days - a restart clears any slow memory growth")
        if len(self.rss_hist) >= 10:
            first, last = self.rss_hist[0][1], self.rss_hist[-1][1]
            if last > first * 1.5 and last - first > 100 * 1024:
                notes.append(f"server memory grew from {first // 1024} to {last // 1024} MB")
        errs = sum(1 for t in self.err_times if now - t < 600)
        if errs >= 20:
            notes.append(f"{errs} errors in the last 10 minutes - check the Console")
        used = f" \u2022 server using {self.rss_hist[-1][1] // 1024} MB" if self.rss_hist else ""
        self.health.setText("\u26a0 " + "; ".join(notes) if notes else "\u2713 Server looks healthy" + used)
        self.health.setStyleSheet("color: #d7b45a;" if notes else f"color: {THEME['muted']};")

    def highlight_log(self):
        q, sels = self.log_find.text(), []
        if q:
            doc = self.log.document()
            color = QColor(self.accent_color)
            color.setAlpha(90)
            cur = doc.find(q)
            while not cur.isNull() and len(sels) < 400:
                sel = QTextEdit.ExtraSelection()
                sel.cursor = cur
                sel.format.setBackground(color)
                sels.append(sel)
                cur = doc.find(q, cur)
        self.log.setExtraSelections(sels)

    def find_log(self, back):
        q = self.log_find.text()
        if not q:
            return
        self.autoscroll.setChecked(False)
        flags = QTextDocument.FindBackward if back else QTextDocument.FindFlags()
        if not self.log.find(q, flags):                       # wrap around
            cur = self.log.textCursor()
            cur.movePosition(QTextCursor.End if back else QTextCursor.Start)
            self.log.setTextCursor(cur)
            self.log.find(q, flags)

    def jump_last_error(self):
        b = self.log.document().lastBlock()
        while b.isValid():
            m = LOG_RE.match(b.text())
            if m and m.group(1) == "E":
                self.autoscroll.setChecked(False)
                self.log.setTextCursor(QTextCursor(b))
                self.log.centerCursor()
                return
            b = b.previous()
        QMessageBox.information(self, "No errors", "There are no error lines in the log.")

    @staticmethod
    def diff_lines(old, new):
        """Changed lines only, with password values hidden."""
        out = [l for l in difflib.unified_diff(old.splitlines(), new.splitlines(), lineterm="", n=0)
               if not l.startswith(("---", "+++", "@@"))]
        return [re.sub(r"^([+-]\s*\w*password\w*\s+).*$", r'\1"****"', l, flags=re.I) for l in out]

    def confirm_diff(self, old, new):
        lines = self.diff_lines(old, new)
        if not lines:
            return True
        dlg = QDialog(self)
        dlg.setWindowTitle("Review changes")
        dlg.resize(580, 380)
        v = QVBoxLayout(dlg)
        v.addWidget(QLabel(f"{len(lines)} line(s) will change:"))
        box = QPlainTextEdit()
        box.setReadOnly(True)
        f = QFont("monospace")
        f.setStyleHint(QFont.Monospace)
        box.setFont(f)
        for l in lines:
            box.appendHtml(f'<span style="color:{"#e68191" if l[0] == "-" else "#5ad19a"}; white-space:pre;">'
                           f'{html.escape(l)}</span>')
        v.addWidget(box, 1)
        bar = QHBoxLayout()
        cancel, ok = QPushButton("Cancel"), QPushButton("Save")
        ok.setObjectName("primary")
        cancel.clicked.connect(dlg.reject)
        ok.clicked.connect(dlg.accept)
        bar.addStretch(1)
        bar.addWidget(cancel)
        bar.addWidget(ok)
        v.addLayout(bar)
        return dlg.exec_() == QDialog.Accepted

    def ann_key(self):
        mod = str(self.settings.value(self.mod_page._k("active_mod"), ""))
        return f"ann_text_{GAME}_{re.sub(r'[^A-Za-z0-9]+', '_', mod)}" if mod else "ann_text"

    def ann_text_value(self):
        return str(self.dset(self.ann_key(), str(self.dset("ann_text", ""))))   # falls back to the shared list

    def refresh_ann_box(self):
        mod = str(self.settings.value(self.mod_page._k("active_mod"), ""))
        self.c_ann_text.setPlainText(self.ann_text_value())
        self.ann_for.setText(f"Editing the list for the active mod: {mod}" if mod
                             else "Editing the shared list (no mod activated).")
        self.ann_idx = 0

    def dset(self, key, default=False):
        return self.settings.value(key, default, type=type(default))

    def load_discord_settings(self):
        self.discord_enabled.setChecked(self.dset("discord_enabled", False))
        self.discord_webhook.setText(self.dset("discord_webhook", ""))
        self.discord_name.setText(self.dset("discord_name", ""))
        self.discord_tag.setText(self.dset("discord_tag", "#discord"))
        self.discord_chat_fmt.setText(self.dset("discord_chat_fmt", DEFAULT_CHAT_FMT))
        self.discord_ping.setChecked(self.dset("discord_ping_first", False))
        self.discord_addr.setChecked(self.dset("discord_addr", True))
        self.discord_batch.setChecked(self.dset("discord_batch", True))
        self.discord_card.setChecked(self.dset("discord_card", False))
        for key, box in self.discord_events.items():
            box.setChecked(self.dset(f"discord_ev_{key}", DEFAULT_EVENTS[key]))

    def save_discord_settings(self, quiet=False):
        url = self.discord_webhook.text().strip()
        if url and not WEBHOOK_RE.match(url):
            self.set_status(self.discord_status, False,
                            "That doesn't look like a Discord webhook URL. It should start with "
                            "https://discord.com/api/webhooks/")
            return False
        self.settings.setValue("discord_enabled", self.discord_enabled.isChecked())
        self.settings.setValue("discord_webhook", url)
        self.settings.setValue("discord_name", self.discord_name.text().strip())
        self.settings.setValue("discord_tag", self.discord_tag.text().strip() or "#discord")
        self.settings.setValue("discord_chat_fmt", self.discord_chat_fmt.text().strip() or DEFAULT_CHAT_FMT)
        self.settings.setValue("discord_ping_first", self.discord_ping.isChecked())
        self.settings.setValue("discord_addr", self.discord_addr.isChecked())
        self.settings.setValue("discord_batch", self.discord_batch.isChecked())
        self.settings.setValue("discord_card", self.discord_card.isChecked())
        for key, box in self.discord_events.items():
            self.settings.setValue(f"discord_ev_{key}", box.isChecked())
        self.settings.sync()
        self.card_touch()
        if self.discord_addr.isChecked():
            self.public_ip_at = 0  # look the address up again soon
        if not quiet:
            self.set_status(self.discord_status, True, "Saved.")
        return True

    def discord_ready(self):
        return bool(self.dset("discord_enabled", False) and self.dset("discord_webhook", "").strip())

    def discord_payload(self, title, message, color=0x2F86FF, ping=False):
        fields = [{"name": "👥 Players", "value": f"`{len(self.players)}`", "inline": True}]
        if self.dset("discord_addr", True) and self.public_ip:
            addr = f"{self.public_ip}:{self.f_port.text().strip() or DEFAULT_PORT}"
            fields.append({"name": "🌐 Address", "value": f"`{addr}`", "inline": True})
            fields.append({"name": "🔗 Connect", "value": f"`connect {addr}`", "inline": False})
        server = self.f_name.text().strip() or "DDNet Server"
        payload = {
            "username": (self.dset("discord_name", "").strip() or "DDNet Server Manager")[:80],
            "embeds": [{
                "title": title[:250], "description": message[:1800], "color": color, "fields": fields,
                "footer": {"text": f"{server} • DDNet Server Manager"},
                "timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
            }],
            # Embeds can't ping anyone. Mentions are only ever allowed for the one
            # @here we add ourselves, never for text that came from players.
            "allowed_mentions": {"parse": []},
        }
        if ping:
            payload["content"] = "@here"
            payload["allowed_mentions"] = {"parse": ["everyone"]}
        return payload

    def discord_event(self, key, title, message, color=0x2F86FF, ping=False):
        if not self.discord_ready():
            return
        if not self.dset(f"discord_ev_{key}", DEFAULT_EVENTS.get(key, True)):
            return
        self.notifier.post(self.dset("discord_webhook", "").strip(),
                           self.discord_payload(title, message, color, ping))

    def discord_from_chat(self, sender, message):
        tag = self.dset("discord_tag", "#discord").strip()
        if not tag or tag.lower() not in message.lower():
            return
        clean = re.sub(re.escape(tag), "", message, flags=re.IGNORECASE).strip()
        if not clean or not self.discord_ready() or not self.dset("discord_ev_chat", DEFAULT_EVENTS["chat"]):
            return
        # One plain line using your format. No embed.
        fmt = str(self.dset("discord_chat_fmt", DEFAULT_CHAT_FMT)) or DEFAULT_CHAT_FMT
        if "{message}" not in fmt:
            fmt += " {message}"
        self.notifier.post(self.dset("discord_webhook", "").strip(), {
            "content": fmt.replace("{name}", esc_md(sender)).replace("{message}", esc_md(clean))[:1900],
            "username": (self.dset("discord_name", "").strip() or "DDNet Server Manager")[:80],
            "allowed_mentions": {"parse": []}})

    def send_discord_test(self):
        if not self.save_discord_settings(quiet=True):
            return
        url = self.discord_webhook.text().strip()
        if not url:
            self.set_status(self.discord_status, False, "Paste a webhook URL first.")
            return
        self.set_status(self.discord_status, True, "Sending...")
        self.notifier.post(url, self.discord_payload("🔧 Test message", "Your DDNet Server Manager is connected.",
                                                     0x2F86FF), report=True)

    def on_discord_result(self, ok, msg):
        self.set_status(self.discord_status, ok, msg)
        if not ok:
            self.append_log(f"[manager] Discord: {msg}")

    def set_status(self, label, ok, msg):
        label.setText(msg)
        label._ok = ok
        if not hasattr(self, "_status_labels"):
            self._status_labels = []
        if label not in self._status_labels:
            self._status_labels.append(label)
        self.style_status(label)

    def style_status(self, label):
        """Status text follows the accent color (errors stay red)."""
        hi = THEME["accent_hi"]
        label.setStyleSheet(f"color: {hi if getattr(label, '_ok', True) else '#e68191'};")

    def restyle_statuses(self):
        for lb in getattr(self, "_status_labels", []):
            self.style_status(lb)

    # ------------------------------------------------------------ tools
    def load_tools_settings(self):
        self.t_crash.setChecked(self.dset("auto_restart_crash", True))
        self.t_daily_restart.setChecked(self.dset("sched_restart", False))
        self.t_restart_time.setText(self.dset("sched_restart_time", "04:00"))
        self.t_welcome.setChecked(self.dset("welcome_enabled", False))
        self.t_welcome_text.setText(self.dset("welcome_text", "Welcome, {name}!"))
        self.t_login.setChecked(login_autostart_enabled())
        self.t_backup_daily.setChecked(self.dset("sched_backup", False))
        self.t_backup_time.setText(self.dset("sched_backup_time", "03:30"))
        self.t_backup_keep.setCurrentText(str(self.dset("backup_keep", 7)))

    def save_tools_settings(self):
        for enabled, edit, what in ((self.t_daily_restart, self.t_restart_time, "restart"),
                                    (self.t_backup_daily, self.t_backup_time, "backup")):
            if enabled.isChecked() and not valid_hm(edit.text().strip()):
                self.set_status(self.tools_status, False, f"Enter the {what} time as HH:MM (24-hour), e.g. 04:00.")
                return
        self.settings.setValue("auto_restart_crash", self.t_crash.isChecked())
        self.settings.setValue("sched_restart", self.t_daily_restart.isChecked())
        self.settings.setValue("sched_restart_time", self.t_restart_time.text().strip() or "04:00")
        self.settings.setValue("welcome_enabled", self.t_welcome.isChecked())
        self.settings.setValue("welcome_text", self.t_welcome_text.text().strip() or "Welcome, {name}!")
        self.settings.setValue("sched_backup", self.t_backup_daily.isChecked())
        self.settings.setValue("sched_backup_time", self.t_backup_time.text().strip() or "03:30")
        self.settings.setValue("backup_keep", int(self.t_backup_keep.currentText()))
        self.settings.sync()
        try:
            set_login_autostart(self.t_login.isChecked())
        except OSError as e:
            self.set_status(self.tools_status, False, f"Saved, but couldn't change the login entry: {e}")
            return
        self.set_status(self.tools_status, True, "Saved.")

    def run_schedules(self):
        self.run_rotation()
        self.run_announcements()
        now = datetime.now()
        today, hm = now.strftime("%Y-%m-%d"), now.strftime("%H:%M")
        if (self.dset("sched_restart", False) and hm == self.dset("sched_restart_time", "04:00")
                and self.last_restart_day != today and self.running() and not self.stopping):
            self.last_restart_day = today
            self.append_log("[manager] scheduled daily restart")
            self.add_event("Scheduled restart")
            self.restart_server()
        if self.dset("sched_restart", False) and self.running() and not self.stopping and self.last_warn_day != today:
            try:
                rh, rm = (int(x) for x in self.dset("sched_restart_time", "04:00").split(":"))
                w = (rh * 60 + rm - 1) % 1440
                if hm == f"{w // 60:02d}:{w % 60:02d}":
                    self.last_warn_day = today
                    self.send_cmd("broadcast Server restarting in 1 minute", echo=False)
            except ValueError:
                pass
        if (self.dset("sched_backup", False) and hm == self.dset("sched_backup_time", "03:30")
                and self.last_backup_day != today):
            self.last_backup_day = today
            self.backup_now(True)

    def backup_now(self, scheduled=False):
        keep = int(self.dset("backup_keep", 7))
        self.set_status(self.backup_status, True, "Backing up...")

        def work():
            ok, msg = make_backup(keep)
            self.sig_tool.emit("backup_sched" if scheduled else "backup", ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def open_backups_folder(self):
        BACKUP_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(BACKUP_DIR)))

    def lookup_public_ip(self, quiet=False):
        if self._ip_busy:
            return
        self._ip_busy = True
        if not quiet:
            self.set_status(self.net_status, True, "Looking up your public IP...")

        def work():
            ok, msg = fetch_public_ip()
            self.sig_tool.emit("ip", ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def refresh_public_ip_if_needed(self):
        if self._ip_busy:
            return
        if time.time() - self.public_ip_at > 600:      # also covers the very first lookup (at = 0)
            self.lookup_public_ip(quiet=True)

    def open_upnp(self):
        port = self.f_port.text().strip() or DEFAULT_PORT
        if not port.isdigit():
            self.set_status(self.net_status, False, "Fix the port on the Config page first.")
            return
        self.set_status(self.net_status, True, "Asking your router to open the port...")

        def work():
            ok, msg = upnp_open(int(port))
            self.sig_tool.emit("upnp", ok, msg)
        threading.Thread(target=work, daemon=True).start()

    def update_public_label(self):
        self.refresh_connect(force=True)

    def refresh_connect(self, force=False):
        """Keep the dashboard Connect widget in sync with the saved config, LAN IP and public IP."""
        try:
            cfg = parse_cfg(CONFIG.read_text()) if CONFIG.exists() else {}
        except OSError:
            cfg = {}
        port = str(cfg.get("sv_port", "") or DEFAULT_PORT).strip() or DEFAULT_PORT
        pw = cfg.get("password", "") or ""
        name = cfg.get("sv_name", "") or f"My {GAME_LABEL} server"
        lip = local_ip()
        key = (GAME, TW_PROTO, lip, port, pw, name, self.public_ip, self._pub_failed, THEME["accent_hi"])
        if key == self._conn_key and not force:
            return
        self._conn_key = key
        self._local_ip, self._port, self._pw, self._sname = lip, port, pw, name
        val_css = f"font-family: monospace; font-size: 15px; font-weight: 700; color: {THEME['accent_hi']};"
        dim_css = f"font-family: monospace; font-size: 15px; font-style: italic; color: {THEME['muted']};"
        loc = self.conn_vals["local"][1]
        have_lan = lip != "your-pi-ip"
        loc.setText(addr_text(lip, port) if have_lan else "no network connection")
        loc.setStyleSheet(val_css if have_lan else dim_css)
        self.conn_btns["local"].setEnabled(have_lan)
        pub = self.conn_vals["public"][1]
        if self.public_ip:
            pub.setText(addr_text(self.public_ip, port))
            pub.setStyleSheet(val_css)
        else:
            pub.setText("unavailable - retrying..." if self._pub_failed else "looking up...")
            pub.setStyleSheet(dim_css)
        self.conn_btns["public"].setEnabled(bool(self.public_ip))
        for w_ in self.conn_vals["pass"] + (self.conn_btns["pass"],):
            w_.setVisible(bool(pw))
        self.conn_vals["pass"][1].setText(pw)
        self.conn_vals["pass"][1].setStyleSheet(val_css)

    def refresh_addresses(self):
        self.refresh_connect(force=True)
        self.lookup_public_ip(quiet=True)
        self.dash_note(True, "Refreshing addresses...")

    def dash_note(self, ok, msg):
        if getattr(self, "conn_status", None) is not None:
            self.set_status(self.conn_status, ok, msg)

    def open_server_folder(self):
        USER_DIR.mkdir(parents=True, exist_ok=True)
        QDesktopServices.openUrl(QUrl.fromLocalFile(str(USER_DIR)))

    def quick_crash_toggle(self, v):
        self.settings.setValue("auto_restart_crash", v)
        self.t_crash.setChecked(v)
        self.dash_note(True, "Auto-restart on crash " + ("on." if v else "off."))

    def on_tool_result(self, tag, ok, msg):
        if tag == "ip":
            self._ip_busy = False
            if ok:
                if self.public_ip and self.public_ip != msg:
                    self.add_event(f"Public IP changed to {msg}")
                self.public_ip, self.public_ip_at = msg, time.time()
                self._pub_failed = False
                self.update_public_label()
                msg = f"Your public IP is {msg}"
            else:
                self.public_ip_at = time.time() - 600 + 120  # retry in ~2 minutes
                self._pub_failed = True
                self.update_public_label()
            self.set_status(self.net_status, ok, msg)
            self.dash_note(ok, msg)
        elif tag == "upnp":
            self.set_status(self.net_status, ok, msg)
            self.dash_note(ok, msg)
        elif tag in ("backup", "backup_sched"):
            self.set_status(self.backup_status, ok, msg)
            self.dash_note(ok, msg)
            self.add_event("Backup saved" if ok else "Backup failed")
            if ok and tag == "backup_sched":
                self.discord_event("backup", "💾 Backup saved", "The daily backup finished.", 0x2F86FF)

    # ------------------------------------------------------------ misc
    def copy_field(self, key):
        self.refresh_connect(force=True)
        port, pw = self._port, self._pw
        if key == "local":
            text, label = addr_text(self._local_ip, port), "Local address"
        elif key == "public":
            text, label = (addr_text(self.public_ip, port) if self.public_ip else ""), "Public address"
        elif key == "pass":
            text, label = pw, "Password"
        else:
            host = self.public_ip or self._local_ip
            if host == "your-pi-ip":
                self.dash_note(False, "No network connection - can't build an invite yet.")
                return
            lines = [f"Join my {GAME_LABEL} server: {self._sname}", f"Address: {addr_text(host, port)}"]
            if pw:
                lines.append(f"Password: {pw}")
            lines.append(f"Or type in console: {connect_text(host, port)}")
            text, label = "\n".join(lines), "Invite message"
        if not text:
            return
        QGuiApplication.clipboard().setText(text)
        self.add_event(f"{label} copied")
        self.dash_note(True, f"{label} copied.")

    def launch_client(self):
        if IS_WIN:
            name = "teeworlds.exe" if GAME == "teeworlds" else "DDNet.exe"
            for d in (SERVER_DIR, SERVER_DIR.parent):
                exe = d / name
                if exe.is_file():
                    if QProcess.startDetached(str(exe), [], str(d)):
                        return
            QMessageBox.warning(self, "Could not launch",
                                f"Couldn't find {name} next to the server ({SERVER_DIR}).")
            return
        if not QProcess.startDetached(CLIENT_CMD[0], CLIENT_CMD[1:]):
            QMessageBox.warning(self, "Could not launch",
                                "Flatpak or the DDNet client (tw.ddnet.ddnet) is not installed.")

    def resizeEvent(self, e):
        """Keep typography stable; adapt spacing/sidebar instead of scaling text."""
        super().resizeEvent(e)
        w = self.width()
        if hasattr(self, "_outer_main"):
            if w < 850:
                self._outer_main.setContentsMargins(10, 14, 10, 14)
            elif w < 1050:
                self._outer_main.setContentsMargins(16, 18, 16, 18)
            else:
                self._outer_main.setContentsMargins(28, 22, 28, 22)
        if hasattr(self, "_sidebar"):
            self._sidebar.setFixedWidth(180 if w < 850 else 200 if w < 1050 else 220)

    def closeEvent(self, e):
        if self.tray is not None and self.tray.isVisible() and not self._quitting:
            e.ignore()
            self.hide()
            if not self.settings.value("tray_hint_shown", False, type=bool):
                self.settings.setValue("tray_hint_shown", True)
                self.tray.showMessage("Still running", "The manager is in the tray. Right-click the icon to quit.",
                                      QSystemTrayIcon.Information, 4000)
            return
        if self.running():
            ans = QMessageBox.question(self, "Quit", "The server is running. Stop it and quit?")
            if ans != QMessageBox.Yes:
                e.ignore()
                return
            if IS_WIN and self.econ_ok:
                self.econ.write(b"shutdown\n")
                self.econ.flush()
            else:
                interrupt_process(self.proc)
            if not self.proc.waitForFinished(5000):
                self.proc.kill()
                self.proc.waitForFinished(2000)
        self.settings.setValue("geometry", self.saveGeometry())
        self.push_card(offline=True, sync=True)
        self.settings.setValue("discord_card_id", self.card_id)
        e.accept()


def main():
    if getattr(sys, "frozen", False):
        # A packaged build points LD_LIBRARY_PATH at its own bundled libraries; give the programs we
        # start (the game server, flatpak, upnpc) the system's original value back.
        for var in ("LD_LIBRARY_PATH", "LD_PRELOAD"):
            orig = os.environ.pop(var + "_ORIG", None)
            if orig is not None:
                os.environ[var] = orig
            else:
                os.environ.pop(var, None)
    if "--install-menu" in sys.argv and IS_WIN:
        print("Not needed on Windows: pin ddnet-manager.exe to Start or the taskbar yourself.")
        return
    if "--install-menu" in sys.argv:       # adds an entry to the desktop's application menu
        d = HOME / ".local" / "share" / "applications"
        d.mkdir(parents=True, exist_ok=True)
        (d / "ddnet-manager.desktop").write_text(
            "[Desktop Entry]\nType=Application\nName=DDNet Server Manager\n"
            f"Exec={launch_command()}\nTerminal=false\nCategories=Game;Utility;\n")
        print(f"Menu entry created: {d / 'ddnet-manager.desktop'}")
        return
    app = QApplication(sys.argv)
    app.setStyle("Fusion")
    app.setStyleSheet(QSS)
    lock = QLockFile(os.path.join(tempfile.gettempdir(), "ddnet-manager.lock"))
    if not lock.tryLock(200):
        QMessageBox.information(None, "Already running", "DDNet Server Manager is already open.")
        sys.exit(0)
    win = Manager()
    if "--minimized" in sys.argv:
        win.showMinimized()
    else:
        win.show()
    code = app.exec_()
    lock.unlock()
    sys.exit(code)


if __name__ == "__main__":
    main()
