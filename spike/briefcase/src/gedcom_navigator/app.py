"""Minimal Toga app for the Briefcase App Store packaging spike.

Deliberately tiny — the point is to validate the *packaging* pipeline (sandboxed,
signed .pkg accepted by App Store validation), not the app. It shows one window with a
label and a button so you can confirm the packaged, sandboxed bundle actually launches.
"""
import toga
from toga.style.pack import COLUMN, Pack


class GedcomSpike(toga.App):
    def startup(self):
        box = toga.Box(style=Pack(direction=COLUMN, margin=20))
        box.add(toga.Label("GEDCOM Navigator — Briefcase App Store spike", style=Pack(margin=(0, 0, 12, 0))))
        box.add(toga.Button("It launches (sandboxed).", on_press=self._ping))
        self.status = toga.Label("", style=Pack(margin=(12, 0, 0, 0)))
        box.add(self.status)
        self.main_window = toga.MainWindow(title=self.formal_name)
        self.main_window.content = box
        self.main_window.show()

    def _ping(self, widget):
        self.status.text = "OK — sandboxed Toga bundle is running."


def main():
    return GedcomSpike()
