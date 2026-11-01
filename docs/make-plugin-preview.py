"""Render the marketplace preview from GameBuddy's own UI and demo text only."""

import os
from pathlib import Path

os.environ["QT_QPA_PLATFORM"] = "offscreen"
from PySide6.QtGui import QColor, QFont, QIcon, QImage, QPainter
from PySide6.QtWidgets import QApplication

from gamebuddy.i18n import Translator
from gamebuddy.ui.theme import DEFAULT, stylesheet
from gamebuddy.ui.widget import BuddyWidget

app = QApplication([])
app.setStyleSheet(stylesheet(DEFAULT))
widget = BuddyWidget(Translator("en"), "Buddy", "ALT, V", 390, 560, mode="panel")
widget.add_user("Help me prepare for the next quest.")
widget.add_bubble(
    "Check your equipment, restock potions and choose your next objective. Your checklist is pinned here.",
    "bro",
)
widget.show_pin(
    "Ready to play", "- [ ] Check equipment\n- [ ] Restock potions\n- [ ] Choose the next quest", "checklist"
)
widget.show()
app.processEvents()
frame = QImage(1400, 800, QImage.Format.Format_ARGB32_Premultiplied)
frame.fill(QColor("#101217"))
p = QPainter(frame)
p.setRenderHint(QPainter.RenderHint.Antialiasing)
p.setPen(QColor("#e8e9ed"))
p.setFont(QFont("DejaVu Sans", 40, QFont.Weight.Bold))
p.drawText(70, 125, "GameBuddy")
p.setFont(QFont("DejaVu Sans", 19))
p.setPen(QColor("#a7acb8"))
p.drawText(74, 172, "A voice companion for your game")
for y, text in [
    (260, "Talk with a shortcut"),
    (315, "Choose your AI and reasoning"),
    (370, "Keep checklists on screen"),
    (425, "Fits your laptop and desktop"),
]:
    p.setPen(QColor("#8b5cf6"))
    p.drawEllipse(77, y - 13, 10, 10)
    p.setPen(QColor("#e8e9ed"))
    p.setFont(QFont("DejaVu Sans", 16))
    p.drawText(105, y, text)
p.drawPixmap(900, 100, widget.grab())
icon = QIcon(str(Path(__file__).parents[1] / "src/gamebuddy/assets/gamebuddy-symbolic.svg"))
p.fillRect(70, 515, 540, 60, QColor("#1d2027"))
p.drawPixmap(85, 525, icon.pixmap(36, 36))
p.setFont(QFont("DejaVu Sans", 14))
p.drawText(140, 553, "Omarchy bar + system tray")
p.setPen(QColor("#9aa0ad"))
p.setFont(QFont("DejaVu Sans", 11))
p.drawText(75, 715, "Linux · Omarchy Quattro · Wayland / Hyprland")
p.drawText(75, 745, "Demo interface — no game content or private conversation shown")
p.end()
frame.save(str(Path(__file__).parents[1] / "preview.png"))
widget.close()
