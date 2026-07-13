"""GEDCOM Navigator — Toga UI (migration target).

New view layer, built parallel to the legacy tkinter GUI (`gedcom_gui_*`) so the
tkinter app stays runnable until parity. Sits on the untouched, tkinter-free domain
layer (`gedcom_data_model`, `gedcom_name_search`, `gedcom_family_tree`, …).
"""
