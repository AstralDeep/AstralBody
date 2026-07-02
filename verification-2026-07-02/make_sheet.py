"""Builds settings-parity-android-vs-windows.png from the captured evidence."""
import os
from PIL import Image, ImageDraw

HERE = os.path.dirname(os.path.abspath(__file__))
A = os.path.join(HERE, "android")
W = os.path.join(HERE, "win")

pairs = [
    ("Settings menu",        "03-settings-dropdown.png",     "win_02_settings_menu.png"),
    ("LLM settings",         "10-llm-fixed.png",             "win_03_llm.png"),
    ("Personalization",      "12-personalization-fixed.png", "win_04_personalization.png"),
    ("Theme",                "11-theme-fixed.png",           "win_05_theme.png"),
    ("User guide",           "09-guide.png",                 "win_06_guide.png"),
    ("Agents & permissions", "04b-agents.png",               "win_07_agents.png"),
    ("Audit log",            "07-audit.png",                 "win_08_audit.png"),
]
TH = 620
rows = []
for label, ap, wp in pairs:
    a = Image.open(os.path.join(A, ap)); a.load()
    w = Image.open(os.path.join(W, wp)); w.load()
    a = a.resize((int(a.width * TH / a.height), TH))
    w = w.resize((int(w.width * TH / w.height), TH))
    rows.append((label, a, w))
maxw = max(a.width + w.width for _, a, w in rows) + 30
sheet = Image.new("RGB", (maxw, (TH + 46) * len(rows) + 10), (8, 10, 18))
d = ImageDraw.Draw(sheet)
y = 10
for label, a, w in rows:
    d.text((12, y + 2), f"{label}   -   Android (left)  |  Windows (right)", fill=(225, 225, 240))
    sheet.paste(a, (10, y + 22))
    sheet.paste(w, (20 + a.width, y + 22))
    y += TH + 46
out = os.path.join(HERE, "settings-parity-android-vs-windows.png")
sheet.save(out)
print("saved", out, sheet.size)
