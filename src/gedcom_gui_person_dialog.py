#!/usr/bin/env python3
"""
gedcom_gui_person_dialog.py

Person profile and family-tree detail windows for GedcomNavigatorApp.
"""

import re
import shutil
import sys
import tkinter as tk
import tkinter.font as tkfont
import webbrowser
from datetime import date
from pathlib import Path
from tkinter import filedialog, messagebox

import customtkinter as ctk

from gedcom_debug import debug_enabled
from gedcom_display import describe
from gedcom_family_tree import (
    INITIAL_TREE_CATEGORIES,
    build_descendant_tree_graph,
    build_pedigree_tree_graph,
    descendant_tree_expanded_requests,
    descendant_tree_expansion_options,
    layout_descendant_tree,
    layout_family_tree,
    layout_pedigree_tree,
)
from gedcom_platform import filedialog_parent
from gedcom_relationship import _extract_event
from gedcom_strings import *  # pylint: disable=unused-wildcard-import
from gedcom_tooltip import Tooltip
from gedcom_zoom import TextZoomController, bind_zoom_shortcuts, scaled_tag_font


class PersonDialogMixin:
    """Person detail window helpers."""

    _MEDIA_DIR_NAMES = (
        'media', 'Media', 'photos', 'Photos', 'images', 'Images',
        'pictures', 'Pictures'
    )
    _TREE_VIEW_MODES = ("tree", "pedigree", "descendant")
    _HTTPS_URL_RE = re.compile(r"https://[^\s<>\"']+")
    _URL_TRAILING_PUNCTUATION = ".,;:!?)]}"
    _FACT_EVENT_TAGS = {
        "ADOP",
        "BAPM",
        "CAST",
        "CENS",
        "CHR",
        "CREM",
        "DSCR",
        "EDUC",
        "EMIG",
        "EVEN",
        "FACT",
        "GRAD",
        "IMMI",
        "MILI",
        "NATI",
        "NATU",
        "OCCU",
        "PROB",
        "RELI",
        "RESI",
        "TITL",
        "WILL",
    }
    _FACT_EVENT_LABELS = {
        "ADOP": FACT_EVENT_ADOP,
        "BAPM": FACT_EVENT_BAPM,
        "CAST": FACT_EVENT_CAST,
        "CENS": FACT_EVENT_CENS,
        "CHR": FACT_EVENT_CHR,
        "CREM": FACT_EVENT_CREM,
        "DSCR": FACT_EVENT_DSCR,
        "EDUC": FACT_EVENT_EDUC,
        "EMIG": FACT_EVENT_EMIG,
        "EVEN": FACT_EVENT_EVEN,
        "FACT": FACT_EVENT_FACT,
        "GRAD": FACT_EVENT_GRAD,
        "IMMI": FACT_EVENT_IMMI,
        "MILI": FACT_EVENT_MILI,
        "NATI": FACT_EVENT_NATI,
        "NATU": FACT_EVENT_NATU,
        "OCCU": FACT_EVENT_OCCU,
        "PROB": FACT_EVENT_PROB,
        "RELI": FACT_EVENT_RELI,
        "RESI": FACT_EVENT_RESI,
        "TITL": FACT_EVENT_TITL,
        "WILL": FACT_EVENT_WILL,
    }

    @classmethod
    def _profile_fact_event_lines(cls, raw):
        """Return formatted Facts & Events lines from an individual raw record."""
        lines = []
        i = 0
        while i < len(raw):
            level, _xref, tag, value = raw[i]
            if level != 1 or tag not in cls._FACT_EVENT_TAGS:
                i += 1
                continue

            subrecords = []
            i += 1
            while i < len(raw) and raw[i][0] > 1:
                subrecords.append(raw[i])
                i += 1

            event = cls._format_profile_fact_event(tag, value, subrecords)
            if event:
                lines.append(event)
        return lines

    @classmethod
    def _format_profile_fact_event(cls, tag, value, subrecords):
        event_type = ""
        date_value = ""
        place_value = ""
        age_value = ""
        cause_value = ""
        note_parts = []
        source_pages = []
        active_note_level = None
        active_source_level = None

        for level, _xref, subtag, subvalue in subrecords:
            raw_text = subvalue or ""
            text = raw_text.strip()
            if active_note_level is not None and level <= active_note_level:
                active_note_level = None
            if active_source_level is not None and level <= active_source_level:
                active_source_level = None

            if level == 2 and subtag == "TYPE" and not event_type:
                event_type = text
            elif level == 2 and subtag == "DATE" and not date_value:
                date_value = text
            elif level == 2 and subtag == "PLAC" and not place_value:
                place_value = text
            elif level == 2 and subtag == "AGE" and not age_value:
                age_value = text
            elif level == 2 and subtag == "CAUS" and not cause_value:
                cause_value = text
            elif level == 2 and subtag == "NOTE":
                active_note_level = level
                if text and not (text.startswith("@") and text.endswith("@")):
                    note_parts.append(raw_text)
            elif active_note_level is not None and subtag in ("CONT", "CONC"):
                if not note_parts:
                    note_parts.append(text)
                elif subtag == "CONC":
                    note_parts[-1] += raw_text
                elif text:
                    note_parts.append(text)
            elif level == 2 and subtag == "SOUR":
                active_source_level = level
            elif (
                active_source_level is not None
                and subtag == "PAGE"
                and text
            ):
                source_pages.append(text)

        label = cls._FACT_EVENT_LABELS.get(tag, tag)
        if tag in ("EVEN", "FACT") and event_type:
            label = event_type

        value_text = (value or "").strip()
        details = []
        if value_text:
            details.append(value_text)
        if event_type and tag not in ("EVEN", "FACT"):
            details.append(event_type)
        for detail in (date_value, place_value):
            if detail:
                details.append(detail)
        if age_value:
            details.append(FACT_EVENT_AGE.format(value=age_value))
        if cause_value:
            details.append(FACT_EVENT_CAUSE.format(value=cause_value))
        if note_parts:
            details.append(FACT_EVENT_NOTE.format(value=" ".join(note_parts)))
        for page in source_pages:
            details.append(FACT_EVENT_SOURCE.format(value=page))

        if not details:
            return ""
        return FACTS_EVENTS_LINE.format(label=label, details=", ".join(details))

    def _show_profile_from_tree_context(self, indi_id, show_person_view):
        """Show indi_id's profile in the current person detail window."""
        show_person_view(indi_id)

    def _search_tree_center_context(self, pick_person, recenter_tree):
        """Prompt for a person and recenter the current tree if selected."""
        indi_id = pick_person()
        if indi_id:
            recenter_tree(indi_id)
        return indi_id

    @staticmethod
    def _add_canvas_highlighted_node(canvas, indi_id):
        """Add indi_id to a graph canvas highlight set and redraw if needed."""
        highlighted = set(getattr(canvas, "_highlighted_nodes", set()))
        if indi_id in highlighted:
            return False
        highlighted.add(indi_id)
        canvas._highlighted_nodes = highlighted
        redraw = getattr(canvas, "_redraw_fn", None)
        if redraw:
            redraw()
        return True

    def _profile_thumbnail_size(self):
        """Return profile thumbnail size in pixels for the current display."""
        font_based = int(round(self._mono_size * 7.5))
        try:
            screen_h = self.root.winfo_screenheight()
            display_based = int(round(screen_h * 0.12))
        except (AttributeError, tk.TclError):
            display_based = font_based
        size = min(176, max(112, font_based, display_based))
        return size, size

    def _graph_thumbnail_size(self, scale):
        """Return graph thumbnail size in canvas pixels."""
        size = scale(84)
        return size, size

    def _profile_gallery_thumbnail_size(self):
        """Return thumbnail size for the profile image gallery."""
        font_based = int(round(self._mono_size * 8.0))
        try:
            screen_h = self.root.winfo_screenheight()
            display_based = int(round(screen_h * 0.11))
        except (AttributeError, tk.TclError):
            display_based = font_based
        size = min(160, max(112, font_based, display_based))
        return size, size

    def _profile_media_payload(self, indi_id, size):
        """Return thumbnail payload for indi_id when profile images are enabled."""
        show_var = getattr(self, 'show_profile_image', None)
        if show_var is None or not show_var.get():
            return None
        media = getattr(self, '_media_service', None)
        if media is None or indi_id not in self.individuals:
            return None
        self._maybe_show_missing_profile_image_notice(
            self.individuals[indi_id], media)
        return media.profile_image_for_person(
            self.individuals[indi_id], self.gedcom_path.get(), size,
            media_dirs=self._profile_media_dirs())

    def _profile_media_dirs(self):
        """Return configured replacement media directories for the loaded GEDCOM."""
        config = getattr(self, '_config', None)
        gedcom_path = self.gedcom_path.get()
        if config is None or not hasattr(config, 'get_media_parent_dir'):
            return []
        directory = config.get_media_parent_dir(gedcom_path)
        return [directory] if directory else []

    def _initial_media_directory(self):
        """Return the best starting directory for selecting linked media."""
        for directory in self._profile_media_dirs():
            if directory and Path(directory).expanduser().is_dir():
                return str(Path(directory).expanduser())

        gedcom_path = self.gedcom_path.get()
        gedcom_dir = None
        if gedcom_path:
            try:
                gedcom_dir = Path(gedcom_path).expanduser().resolve().parent
            except OSError:
                gedcom_dir = Path(gedcom_path).expanduser().parent
            if gedcom_dir.is_dir():
                media_dir = self._nearby_media_directory(gedcom_dir)
                if media_dir is not None:
                    return str(media_dir)
                return str(gedcom_dir)

        pictures = Path.home() / 'Pictures'
        if pictures.is_dir():
            return str(pictures)
        return str(Path.home())

    def _nearby_media_directory(self, parent_dir):
        """Return a nearby media folder using the filesystem's actual casing."""
        try:
            entries = [entry for entry in Path(parent_dir).iterdir()
                       if entry.is_dir()]
        except OSError:
            return None
        by_exact = {entry.name: entry for entry in entries}
        by_lower = {}
        for entry in entries:
            by_lower.setdefault(entry.name.lower(), entry)
        for name in self._MEDIA_DIR_NAMES:
            if name in by_exact:
                return by_exact[name]
            match = by_lower.get(name.lower())
            if match is not None:
                return match
        return None

    def _maybe_show_missing_profile_image_notice(self, indi, media):
        """Show one per-session note when a selected FILE path is missing."""
        media_path = media.selected_media_file(indi)
        self._maybe_prompt_for_missing_media_file(media_path, media)

    def _maybe_prompt_for_missing_media_file(self, media_path, media):
        """Offer a replacement media folder for the first missing media path."""
        if getattr(self, '_profile_image_missing_notice_shown', False):
            return False
        if not media_path or not media.is_supported_path(media_path):
            return False
        gedcom_path = self.gedcom_path.get()
        if media.resolve_media_path(
                media_path, gedcom_path, self._profile_media_dirs()):
            return False
        self._profile_image_missing_notice_shown = True
        try:
            choose_dir = messagebox.askyesno(
                PROFILE_IMAGE_MISSING_TITLE,
                PROFILE_IMAGE_MISSING_MSG.format(path=media_path),
                parent=getattr(self, 'root', None),
            )
            if not choose_dir:
                return False
            directory = filedialog.askdirectory(
                parent=filedialog_parent(getattr(self, 'root', None)),
                title=PROFILE_IMAGE_DIR_TITLE,
                initialdir=self._initial_media_directory(),
            )
            if not directory:
                return False
            config = getattr(self, '_config', None)
            if config is not None and hasattr(config, 'set_media_parent_dir'):
                config.set_media_parent_dir(gedcom_path, directory)
            return True
        except tk.TclError:
            return False

    def _profile_gallery_candidates(self, indi_id):
        """Return non-profile image media candidates for the person."""
        show_var = getattr(self, 'show_profile_image', None)
        if show_var is None or not show_var.get():
            return []
        media = getattr(self, '_media_service', None)
        if media is None or indi_id not in self.individuals:
            return []
        candidates = self.individuals[indi_id].get('media_candidates') or []
        gallery = []
        seen = set()
        for candidate in candidates[1:]:
            media_path = (candidate.get('file') or '').strip()
            if not media_path or not media.is_supported_path(media_path):
                continue
            key = (media_path.replace('\\', '/').lower(),
                   (candidate.get('title') or '').strip().lower())
            if key in seen:
                continue
            seen.add(key)
            gallery.append(candidate)
        return gallery

    def _profile_gallery_items(self, indi_id, size, prompt_missing=False):
        """Return resolved gallery thumbnail payloads for non-profile images."""
        media = getattr(self, '_media_service', None)
        if media is None or indi_id not in self.individuals:
            return []
        gedcom_path = self.gedcom_path.get()
        candidates = self._profile_gallery_candidates(indi_id)

        def _resolve_items():
            resolved = []
            missing_path = None
            for candidate in candidates:
                media_path = (candidate.get('file') or '').strip()
                path = media.resolve_media_path(
                    media_path, gedcom_path, self._profile_media_dirs())
                if not path:
                    if missing_path is None:
                        missing_path = media_path
                    continue
                image = media.tk_thumbnail(path, size)
                if image is None:
                    continue
                resolved.append({
                    'path': path,
                    'image': image,
                    'title': (candidate.get('title') or '').strip(),
                    'file': media_path,
                })
            return resolved, missing_path

        items, missing = _resolve_items()
        if prompt_missing and missing:
            if self._maybe_prompt_for_missing_media_file(missing, media):
                items, _missing = _resolve_items()
        return items

    def _show_profile_image_gallery(self, indi_id, parent=None):
        """Open a thumbnail gallery for non-profile images linked to a person."""
        if indi_id not in self.individuals:
            return
        parent = parent or self.root
        size = self._profile_gallery_thumbnail_size()
        items = self._profile_gallery_items(
            indi_id, size, prompt_missing=True)
        indi = self.individuals[indi_id]
        name = indi.get('name') or indi_id

        win = getattr(self, '_profile_image_gallery_win', None)
        try:
            if win is not None and not win.winfo_exists():
                win = None
        except tk.TclError:
            win = None
        if win is None:
            win = ctk.CTkToplevel(parent)
            self._profile_image_gallery_win = win
            win.protocol('WM_DELETE_WINDOW', win.destroy)
            win.bind('<Escape>', lambda *_: win.destroy() or 'break')
        else:
            for child in win.winfo_children():
                child.destroy()
            try:
                win.deiconify()
            except tk.TclError:
                pass

        win.title(WIN_PROFILE_IMAGE_GALLERY.format(name=name))
        outer = ctk.CTkFrame(win, fg_color='transparent')
        outer.pack(fill='both', expand=True, padx=12, pady=12)

        win._profile_gallery_refs = []
        if not items:
            label = ctk.CTkLabel(outer, text=PROFILE_IMAGE_GALLERY_EMPTY)
            label.pack(fill='both', expand=True, padx=24, pady=24)
            win.geometry(self._clamped_toplevel_geometry(parent, 360, 160))
            win.lift()
            return

        scroll = ctk.CTkScrollableFrame(outer, fg_color='transparent')
        scroll.pack(fill='both', expand=True)
        columns = 4
        thumb_w, _thumb_h = size
        gallery_paths = [item['path'] for item in items]
        for idx, item in enumerate(items):
            row, col = divmod(idx, columns)
            tile = ctk.CTkFrame(scroll, corner_radius=6)
            tile.grid(row=row, column=col, padx=6, pady=6, sticky='n')
            label = tk.Label(
                tile,
                image=item['image'],
                borderwidth=0,
                highlightthickness=1,
                highlightbackground='#9ca3af',
                cursor='hand2',
            )
            label.pack(padx=8, pady=(8, 4))
            label.bind(
                '<Button-1>',
                lambda _event, path=item['path'], paths=gallery_paths:
                    self._show_gallery_full_profile_image(path, win, paths),
            )
            caption = item['title'] or Path(item['file']).name
            cap = ctk.CTkLabel(
                tile, text=caption, wraplength=thumb_w, justify='center')
            cap.pack(fill='x', padx=8, pady=(0, 8))
            win._profile_gallery_refs.extend([item['image'], label])
        for col in range(columns):
            scroll.columnconfigure(col, weight=1)

        try:
            screen_w = max(parent.winfo_screenwidth(), 640)
            screen_h = max(parent.winfo_screenheight(), 480)
        except tk.TclError:
            screen_w, screen_h = 1024, 768
        item_w = thumb_w + 32
        rows = (len(items) + columns - 1) // columns
        win_w = min(int(screen_w * 0.82), max(360, columns * item_w + 54))
        win_h = min(int(screen_h * 0.78), max(260, rows * (size[1] + 70) + 48))
        win.geometry(self._clamped_toplevel_geometry(parent, win_w, win_h))
        win.minsize(min(win_w, 360), min(win_h, 220))
        win.lift()

    @staticmethod
    def _clamped_toplevel_geometry(parent, width, height, margin=24):
        """Return geometry centered on parent and clamped to the screen."""
        width, height = int(width), int(height)
        try:
            parent.update_idletasks()
            screen_w = max(parent.winfo_screenwidth(), width)
            screen_h = max(parent.winfo_screenheight(), height)
            parent_x = parent.winfo_rootx()
            parent_y = parent.winfo_rooty()
            parent_w = max(parent.winfo_width(), 1)
            parent_h = max(parent.winfo_height(), 1)
            x = parent_x + (parent_w - width) // 2
            y = parent_y + (parent_h - height) // 2
        except tk.TclError:
            screen_w = max(1024, width)
            screen_h = max(768, height)
            x = (screen_w - width) // 2
            y = (screen_h - height) // 2

        max_x = max(0, screen_w - width - margin)
        max_y = max(0, screen_h - height - margin)
        x = max(margin if max_x else 0, min(x, max_x))
        y = max(margin if max_y else 0, min(y, max_y))
        return f'{width}x{height}+{int(x)}+{int(y)}'

    @staticmethod
    def _profile_image_navigation_state(image_path, gallery_paths):
        """Return valid gallery navigation paths and current image index."""
        paths = list(gallery_paths or [])
        if image_path not in paths:
            return [], 0
        return paths, paths.index(image_path)

    @staticmethod
    def _profile_full_image_title(image_path):
        """Return a compact title for a full-size profile image window."""
        path = Path(str(image_path).replace('\\', '/'))
        title = path.stem
        return title or path.name or image_path

    def _configure_full_profile_gallery_navigation(
            self, win, image_path, parent, gallery_paths):
        """Update gallery navigation metadata and controls for a preview."""
        win._profile_full_image_parent = parent
        paths, index = self._profile_image_navigation_state(
            image_path, gallery_paths)
        win._profile_full_image_gallery_paths = paths
        win._profile_full_image_gallery_index = index

        prev_btn = getattr(win, '_profile_full_image_prev_btn', None)
        next_btn = getattr(win, '_profile_full_image_next_btn', None)
        status_label = getattr(win, '_profile_full_image_status_label', None)
        if prev_btn is None or next_btn is None:
            return
        try:
            if len(paths) > 1:
                if not prev_btn.winfo_ismapped():
                    prev_btn.pack(side='left', padx=(0, 6))
                if not next_btn.winfo_ismapped():
                    next_btn.pack(side='left', padx=(0, 10))
                if (status_label is not None
                        and not status_label.winfo_ismapped()):
                    status_label.pack(side='left', padx=(0, 10))
                if status_label is not None:
                    status_label.configure(
                        text=PROFILE_IMAGE_NAV_STATUS.format(
                            current=index + 1, total=len(paths)))
                prev_btn.configure(state='normal')
                next_btn.configure(state='normal')
            else:
                prev_btn.pack_forget()
                next_btn.pack_forget()
                if status_label is not None:
                    status_label.pack_forget()
        except tk.TclError:
            pass

    def _draw_full_profile_image(self, win, image_path, media, *,
                                 base_size=None, zoom=None, canvas_size=None):
        """Draw image_path into the existing full-size preview canvas."""
        try:
            canvas = win._profile_full_image_canvas
            state = getattr(win, '_profile_full_image_state', {})
        except tk.TclError:
            return False
        if zoom is None:
            zoom = float(state.get('zoom', 1.0))
        zoom = max(0.1, min(8.0, float(zoom)))
        if base_size is None:
            base_size = (
                int(state.get('base_w', 0)),
                int(state.get('base_h', 0)),
            )
        try:
            base_w = max(1, int(base_size[0]))
            base_h = max(1, int(base_size[1]))
        except (TypeError, ValueError, IndexError):
            return False

        display_size = media.zoomed_display_size((base_w, base_h), zoom)
        image = media.photo_at_size(image_path, display_size)
        if image is None:
            messagebox.showerror(
                ERR_PARSE_TITLE,
                f"Could not open image:\n\n{image_path}",
                parent=win,
            )
            return False

        try:
            canvas.update_idletasks()
            if canvas_size is None:
                canvas_w = max(
                    canvas.winfo_width(),
                    int(state.get('canvas_w', 0)),
                    240,
                )
                canvas_h = max(
                    canvas.winfo_height(),
                    int(state.get('canvas_h', 0)),
                    180,
                )
            else:
                canvas_w = max(1, int(canvas_size[0]))
                canvas_h = max(1, int(canvas_size[1]))
        except (tk.TclError, ValueError, TypeError, IndexError):
            return False

        image_w, image_h = image.width(), image.height()
        scroll_w = max(canvas_w, image_w)
        scroll_h = max(canvas_h, image_h)
        image_x = max(0, (scroll_w - image_w) // 2)
        image_y = max(0, (scroll_h - image_h) // 2)

        canvas.delete('all')
        canvas._profile_full_image_ref = image
        canvas.configure(bg='#f3f4f6', width=canvas_w, height=canvas_h)
        canvas.create_image(image_x, image_y, image=image, anchor='nw')
        canvas.configure(scrollregion=(0, 0, scroll_w, scroll_h))
        win._profile_full_image_source_path = image_path
        win._profile_full_image_state = {
            'canvas_w': canvas_w,
            'canvas_h': canvas_h,
            'base_w': base_w,
            'base_h': base_h,
            'image_w': image_w,
            'image_h': image_h,
            'zoom': zoom,
        }
        return True

    def _set_full_profile_image_zoom(self, win, media, zoom):
        """Apply a new zoom level to the open full-size preview."""
        image_path = getattr(win, '_profile_full_image_source_path', '')
        if not image_path:
            return
        state = getattr(win, '_profile_full_image_state', {})
        base_size = (
            int(state.get('base_w', state.get('canvas_w', 1))),
            int(state.get('base_h', state.get('canvas_h', 1))),
        )
        if self._draw_full_profile_image(
                win, image_path, media, base_size=base_size, zoom=zoom):
            try:
                canvas = win._profile_full_image_canvas
                canvas.focus_set()
            except tk.TclError:
                pass

    def _replace_full_profile_image(self, win, image_path, media):
        """Replace the image inside an already-open full-size preview window."""
        try:
            canvas = win._profile_full_image_canvas
            win.update_idletasks()
            state = getattr(win, '_profile_full_image_state', {})
            canvas_w = max(
                canvas.winfo_width(),
                int(state.get('canvas_w', 0)),
                240,
            )
            canvas_h = max(
                canvas.winfo_height(),
                int(state.get('canvas_h', 0)),
                180,
            )
        except (tk.TclError, ValueError, TypeError):
            return False

        try:
            base_size = media.display_size_for_photo(
                image_path, (canvas_w, canvas_h))
        except Exception:  # pylint: disable=broad-exception-caught
            base_size = (canvas_w, canvas_h)
        zoom = float(state.get('zoom', 1.0))
        if not self._draw_full_profile_image(
                win, image_path, media, base_size=base_size, zoom=zoom,
                canvas_size=(canvas_w, canvas_h)):
            return False

        win.title(self._profile_full_image_title(image_path))
        paths = getattr(win, '_profile_full_image_gallery_paths', [])
        if image_path in paths:
            index = paths.index(image_path)
            win._profile_full_image_gallery_index = index
            status_label = getattr(
                win, '_profile_full_image_status_label', None)
            if status_label is not None and len(paths) > 1:
                try:
                    status_label.configure(
                        text=PROFILE_IMAGE_NAV_STATUS.format(
                            current=index + 1, total=len(paths)))
                except tk.TclError:
                    pass
        try:
            canvas.focus_set()
        except tk.TclError:
            pass
        return True

    def _show_gallery_full_profile_image(self, image_path, parent, gallery_paths):
        """Open or update the full-image preview from a gallery thumbnail."""
        win = getattr(self, '_profile_image_preview_win', None)
        try:
            exists = bool(win is not None and win.winfo_exists())
        except tk.TclError:
            exists = False
        if not exists:
            self._show_full_profile_image(
                image_path, parent=parent, gallery_paths=gallery_paths)
            return
        media = getattr(self, '_media_service', None)
        if media is None:
            return
        self._configure_full_profile_gallery_navigation(
            win, image_path, parent, gallery_paths)
        self._replace_full_profile_image(win, image_path, media)

    @staticmethod
    def _copy_windows_dib_bytes_to_clipboard(parent, dib_bytes):
        """Copy DIB bytes to the Windows clipboard."""
        import ctypes  # pylint: disable=import-outside-toplevel
        import time  # pylint: disable=import-outside-toplevel

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        handle = ctypes.c_void_p

        user32.OpenClipboard.argtypes = [handle]
        user32.OpenClipboard.restype = ctypes.c_bool
        user32.EmptyClipboard.argtypes = []
        user32.EmptyClipboard.restype = ctypes.c_bool
        user32.SetClipboardData.argtypes = [ctypes.c_uint, handle]
        user32.SetClipboardData.restype = handle
        user32.CloseClipboard.argtypes = []
        user32.CloseClipboard.restype = ctypes.c_bool

        kernel32.GlobalAlloc.argtypes = [ctypes.c_uint, ctypes.c_size_t]
        kernel32.GlobalAlloc.restype = handle
        kernel32.GlobalLock.argtypes = [handle]
        kernel32.GlobalLock.restype = handle
        kernel32.GlobalUnlock.argtypes = [handle]
        kernel32.GlobalUnlock.restype = ctypes.c_bool
        kernel32.GlobalFree.argtypes = [handle]
        kernel32.GlobalFree.restype = handle

        cf_dib = 8
        gmem_moveable = 0x0002
        hwnd = handle(parent.winfo_id())

        memory = kernel32.GlobalAlloc(gmem_moveable, len(dib_bytes))
        if not memory:
            raise tk.TclError("Could not allocate Windows clipboard image.")

        clipboard_open = False
        try:
            locked = kernel32.GlobalLock(memory)
            if not locked:
                raise tk.TclError("Could not lock Windows clipboard image.")
            try:
                ctypes.memmove(locked, dib_bytes, len(dib_bytes))
            finally:
                kernel32.GlobalUnlock(memory)

            for _ in range(8):
                if user32.OpenClipboard(hwnd):
                    clipboard_open = True
                    break
                time.sleep(0.05)
            if not clipboard_open:
                raise tk.TclError("Could not open the Windows clipboard.")
            if not user32.EmptyClipboard():
                raise tk.TclError("Could not clear the Windows clipboard.")
            if not user32.SetClipboardData(cf_dib, memory):
                raise tk.TclError("Could not set Windows clipboard bitmap.")
            memory = None
        finally:
            if clipboard_open:
                user32.CloseClipboard()
            if memory:
                kernel32.GlobalFree(memory)

    @staticmethod
    def _copy_macos_png_bytes_to_clipboard(png_bytes):
        """Copy PNG image bytes to the macOS pasteboard."""
        try:
            from AppKit import (  # pylint: disable=import-outside-toplevel
                NSPasteboard,
                NSPasteboardTypePNG,
            )
            from Foundation import NSData  # pylint: disable=import-outside-toplevel
        except ImportError as exc:
            raise tk.TclError(
                "PyObjC is required for macOS image clipboard copy."
            ) from exc

        png_data = NSData.dataWithBytes_length_(png_bytes, len(png_bytes))
        pasteboard = NSPasteboard.generalPasteboard()
        pasteboard.clearContents()
        if not pasteboard.setData_forType_(png_data, NSPasteboardTypePNG):
            raise tk.TclError("Could not set macOS clipboard image data.")

    def _show_full_profile_image(self, image_path, parent=None, gallery_paths=None):
        """Open or reuse a scrollable preview window for a resolved local image."""
        if not image_path:
            return
        media = getattr(self, '_media_service', None)
        if media is None:
            return
        parent = parent or self.root
        win = getattr(self, '_profile_image_preview_win', None)
        try:
            if win is not None and not win.winfo_exists():
                win = None
        except tk.TclError:
            win = None

        if win is None:
            win = ctk.CTkToplevel(parent)
            win.withdraw()
            self._profile_image_preview_win = win
            outer = ctk.CTkFrame(win, fg_color='transparent')
            outer.pack(fill='both', expand=True)
            frame = ctk.CTkFrame(outer, fg_color='transparent')
            frame.pack(fill='both', expand=True)
            canvas = tk.Canvas(frame, highlightthickness=0)
            ybar = tk.Scrollbar(frame, orient='vertical', command=canvas.yview)
            xbar = tk.Scrollbar(frame, orient='horizontal', command=canvas.xview)
            canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            canvas.grid(row=0, column=0, sticky='nsew')
            ybar.grid(row=0, column=1, sticky='ns')
            xbar.grid(row=1, column=0, sticky='ew')
            frame.rowconfigure(0, weight=1)
            frame.columnconfigure(0, weight=1)
            win._profile_full_image_canvas = canvas
            btn_frame = ctk.CTkFrame(outer, fg_color='transparent')
            btn_frame.pack(fill='x', padx=10, pady=(6, 8))
            win._profile_full_image_button_frame = btn_frame

            def _nav_image(delta):
                paths = getattr(win, '_profile_full_image_gallery_paths', [])
                if len(paths) <= 1:
                    return 'break'
                index = getattr(win, '_profile_full_image_gallery_index', 0)
                index = (index + delta) % len(paths)
                self._replace_full_profile_image(win, paths[index], media)
                return 'break'

            def _nav_image_to(index):
                paths = getattr(win, '_profile_full_image_gallery_paths', [])
                if len(paths) <= 1:
                    return 'break'
                index = max(0, min(len(paths) - 1, index))
                self._replace_full_profile_image(win, paths[index], media)
                return 'break'

            def _copy_image(*_):
                graph_state = getattr(win, '_profile_full_image_state', None)
                if not graph_state:
                    return 'break'
                try:
                    source_path = getattr(
                        win, '_profile_full_image_source_path', '')
                    png_size = (
                        graph_state.get('image_w', graph_state['canvas_w']),
                        graph_state.get('image_h', graph_state['canvas_h']),
                    )
                    if sys.platform == 'win32':
                        png_bytes = media.png_bytes_at_size(
                            source_path, png_size)
                        if png_bytes is None:
                            raise tk.TclError("Could not read profile image.")
                        if not hasattr(self, '_windows_dib_from_png_bytes'):
                            raise tk.TclError(
                                "Pillow is required for Windows image copy.")
                        dib_bytes = self._windows_dib_from_png_bytes(png_bytes)
                        self._copy_windows_dib_bytes_to_clipboard(
                            win, dib_bytes)
                    elif sys.platform == 'darwin':
                        png_bytes = media.png_bytes_at_size(
                            source_path, png_size)
                        if png_bytes is None:
                            raise tk.TclError("Could not read profile image.")
                        self._copy_macos_png_bytes_to_clipboard(png_bytes)
                    else:
                        postscript = canvas.postscript(
                            colormode='color', x=0, y=0,
                            width=graph_state['canvas_w'],
                            height=graph_state['canvas_h'])
                        win.clipboard_clear()
                        try:
                            win.clipboard_append(postscript, type='PostScript')
                        except tk.TclError:
                            win.clipboard_append(postscript)
                        win.update()
                except (OSError, tk.TclError, ImportError, ValueError) as exc:
                    messagebox.showerror(
                        ERR_COPY_GRAPH_TITLE,
                        ERR_COPY_PROFILE_IMAGE_MSG.format(error=exc),
                        parent=win,
                    )
                return 'break'

            def _save_image(*_):
                source_path = getattr(win, '_profile_full_image_source_path', '')
                if not source_path:
                    return 'break'
                ext = re.sub(r'[^A-Za-z0-9]', '', source_path.split('.')[-1])
                ext = f'.{ext.lower()}' if ext else '.png'
                path = filedialog.asksaveasfilename(
                    parent=filedialog_parent(win),
                    title=DLG_SAVE_PROFILE,
                    initialfile=source_path.split('/')[-1].split('\\')[-1],
                    defaultextension=ext,
                    filetypes=[
                        ("Image files", "*.png *.jpg *.jpeg *.gif *.bmp *.tif *.tiff *.webp"),
                        ("All files", "*.*"),
                    ],
                )
                if not path:
                    return 'break'
                try:
                    shutil.copyfile(source_path, path)
                except OSError as exc:
                    messagebox.showerror(
                        ERR_SAVE_GRAPH_TITLE,
                        ERR_SAVE_PROFILE_IMAGE_MSG.format(error=exc),
                        parent=win,
                    )
                return 'break'

            prev_btn = ctk.CTkButton(
                btn_frame, text=BTN_PROFILE_IMAGE_PREV, width=44,
                command=lambda: _nav_image(-1))
            Tooltip(prev_btn, get_tip_profile_image_previous())
            next_btn = ctk.CTkButton(
                btn_frame, text=BTN_PROFILE_IMAGE_NEXT, width=44,
                command=lambda: _nav_image(1))
            Tooltip(next_btn, get_tip_profile_image_next())
            status_label = ctk.CTkLabel(
                btn_frame, text='', width=70, anchor='center')
            win._profile_full_image_prev_btn = prev_btn
            win._profile_full_image_next_btn = next_btn
            win._profile_full_image_status_label = status_label

            def _profile_zoom_level():
                state = getattr(win, '_profile_full_image_state', {})
                return float(state.get('zoom', 1.0))

            def _zoom_image_in():
                self._set_full_profile_image_zoom(
                    win, media, _profile_zoom_level() * 1.1)

            def _zoom_image_out():
                self._set_full_profile_image_zoom(
                    win, media, _profile_zoom_level() / 1.1)

            def _zoom_image_reset():
                self._set_full_profile_image_zoom(win, media, 1.0)

            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=_copy_image)
            copy_btn.pack(side='right', padx=(6, 0))
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=_save_image)
            save_btn.pack(side='right')
            win.bind('<Left>', lambda *_: _nav_image(-1))
            win.bind('<Right>', lambda *_: _nav_image(1))
            win.bind('<Home>', lambda *_: _nav_image_to(0))
            win.bind('<End>', lambda *_: _nav_image_to(
                len(getattr(win, '_profile_full_image_gallery_paths', [])) - 1))
            canvas.bind('<Left>', lambda *_: _nav_image(-1))
            canvas.bind('<Right>', lambda *_: _nav_image(1))
            canvas.bind('<Home>', lambda *_: _nav_image_to(0))
            canvas.bind('<End>', lambda *_: _nav_image_to(
                len(getattr(win, '_profile_full_image_gallery_paths', [])) - 1))
            bind_zoom_shortcuts(
                win, _zoom_image_in, _zoom_image_out, _zoom_image_reset)
            bind_zoom_shortcuts(
                canvas, _zoom_image_in, _zoom_image_out, _zoom_image_reset)

            def _close_preview(*_):
                if getattr(self, '_profile_image_preview_win', None) is win:
                    self._profile_image_preview_win = None
                win.destroy()
                return 'break'

            win.bind('<Escape>', _close_preview)
            win.protocol('WM_DELETE_WINDOW', _close_preview)
        else:
            canvas = win._profile_full_image_canvas
            try:
                win.deiconify()
            except tk.TclError:
                pass

        try:
            win.transient(parent)
        except tk.TclError:
            pass
        win.title(self._profile_full_image_title(image_path))
        win._profile_full_image_source_path = image_path
        self._configure_full_profile_gallery_navigation(
            win, image_path, parent, gallery_paths)

        def _focus_preview():
            try:
                win.lift()
                win.focus_force()
                canvas.focus_set()
            except tk.TclError:
                pass

        def _render():
            screen_w = max(parent.winfo_screenwidth(), 640)
            screen_h = max(parent.winfo_screenheight(), 480)
            max_w = max(240, int(screen_w * 0.82))
            max_h = max(180, int(screen_h * 0.78))
            try:
                base_size = media.display_size_for_photo(
                    image_path, (max_w, max_h))
            except Exception:  # pylint: disable=broad-exception-caught
                messagebox.showerror(
                    ERR_PARSE_TITLE,
                    f"Could not open image:\n\n{image_path}",
                    parent=win,
                )
                return
            if not self._draw_full_profile_image(
                    win, image_path, media, base_size=base_size, zoom=1.0,
                    canvas_size=base_size):
                return
            btn_frame = getattr(win, '_profile_full_image_button_frame', None)
            button_h = 0
            button_w = 0
            if btn_frame is not None:
                btn_frame.update_idletasks()
                button_h = btn_frame.winfo_reqheight() + 44
                button_w = btn_frame.winfo_reqwidth() + 20
            win_w, win_h, min_w, min_h = self._profile_preview_window_dimensions(
                base_size[0], base_size[1], max_w, max_h, button_w,
                button_h)
            win.geometry(f'{win_w}x{win_h}')
            win.minsize(min_w, min_h)
            try:
                parent.update_idletasks()
                px = parent.winfo_rootx()
                py = parent.winfo_rooty()
                pw = parent.winfo_width()
                ph = parent.winfo_height()
                x = px + max(0, (pw - win_w) // 2)
                y = py + max(0, (ph - win_h) // 2)
            except tk.TclError:
                x = max(0, (screen_w - win_w) // 2)
                y = max(0, (screen_h - win_h) // 2)
            win.geometry(f'{win_w}x{win_h}+{x}+{y}')
            win.deiconify()
            _focus_preview()
            win.after(80, _focus_preview)

        win.after_idle(_render)

    def _clear_profile_thumbnail(self, text):
        """Remove any placed profile thumbnail from a reused textbox."""
        label = getattr(text, '_profile_image_label', None)
        if label is not None:
            try:
                label.destroy()
            except tk.TclError:
                pass
        text._profile_image_label = None
        text._profile_image_refs = []
        try:
            text._textbox.tag_delete('profile_image_wrap')
        except tk.TclError:
            pass

    @staticmethod
    def _profile_text_exists(text):
        """Return whether the wrapped Tk text widget still exists."""
        try:
            winfo_exists = getattr(text._textbox, 'winfo_exists', None)
            if winfo_exists is None:
                return True
            return bool(winfo_exists())
        except tk.TclError:
            return False

    def _place_profile_thumbnail(self, text, indi_id):
        """Place a top-right thumbnail over a profile textbox."""
        self._clear_profile_thumbnail(text)
        payload = self._profile_media_payload(indi_id, self._profile_thumbnail_size())
        if not payload or payload.get('image') is None:
            return None
        try:
            text.configure(wrap='word')
        except tk.TclError:
            return None
        pad = 8
        try:
            label = tk.Label(
                text._textbox,
                image=payload['image'],
                borderwidth=0,
                highlightthickness=1,
                highlightbackground='#9ca3af',
                cursor='hand2' if payload.get('kind') == 'real' else '',
            )
        except tk.TclError:
            return None
        label._profile_image_ref = payload['image']
        if payload.get('kind') == 'real':
            label.bind(
                '<Button-1>',
                lambda _event, path=payload.get('path'): self._show_full_profile_image(
                    path, parent=text.winfo_toplevel()),
            )
        refs = getattr(text, '_profile_image_refs', [])
        refs.extend([payload['image'], label])
        text._profile_image_refs = refs
        text._profile_image_label = label
        try:
            label.place(relx=1.0, x=-pad, y=pad, anchor='ne')
        except tk.TclError:
            return None
        return {
            'width': payload['image'].width(),
            'height': payload['image'].height(),
            'pad': pad,
        }

    def _apply_profile_thumbnail_wrap(self, text, layout):
        """Reserve right margin beside the placed profile thumbnail."""
        if not layout or not self._profile_text_exists(text):
            return
        try:
            font = tkfont.Font(font=text._textbox.cget('font'))
            line_space = max(font.metrics('linespace'), 1)
        except tk.TclError:
            line_space = max(int(self._mono_size * 1.4), 1)
        reserved_w = layout['width'] + layout['pad'] * 2
        reserved_h = layout['height'] + layout['pad'] * 2
        line_count = max(1, int((reserved_h + line_space - 1) // line_space))
        text._textbox.tag_configure(
            'profile_image_wrap', rmargin=reserved_w)
        text._textbox.tag_add(
            'profile_image_wrap', '1.0', f'{line_count + 1}.0')

    def _default_tree_view_mode(self):
        """Return the configured initial tree view for person detail windows."""
        config = getattr(self, "_config", None)
        if config is None or not hasattr(config, "get_default_tree"):
            return "tree"
        return config.get_default_tree()

    def _resolve_initial_person_view(self, initial_view):
        """Normalize the requested starting view for a person detail window."""
        initial_view = initial_view or "profile"
        if initial_view == "tree":
            return self._default_tree_view_mode()
        if initial_view in self._TREE_VIEW_MODES:
            return initial_view
        return "profile"

    @staticmethod
    def _button_bar_needed_width(btn_frame):
        """Return the requested width needed to show a dialog button bar."""
        try:
            btn_frame.update_idletasks()
            return btn_frame.winfo_reqwidth() + 24
        except tk.TclError:
            return 0

    @staticmethod
    def _profile_preview_window_dimensions(
            image_w, image_h, max_w, max_h, button_w, button_h):
        """Return window and minimum dimensions for a full-image preview."""
        chrome_w = 22 if image_w >= max_w else 2
        chrome_h = 22 if image_h >= max_h else 2
        min_w = max(240, button_w)
        win_w = max(image_w + chrome_w, min_w)
        win_h = image_h + button_h + chrome_h
        min_h = min(image_h + button_h + chrome_h, 180)
        return win_w, win_h, min_w, min_h

    def _show_person(self, initial_view=None):
        """Open the GEDCOM record viewer for the selected person."""
        if not self.individuals:
            messagebox.showwarning(ERR_NO_DATA_TITLE, ERR_NO_DATA_MSG)
            return
        sel = self.tree.selection()
        indi_id = sel[0] if sel else self._active_id
        if not indi_id:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        self._show_person_for(indi_id, initial_view=initial_view)

    def _insert_person_profile(
        self, text, current_id, navigate_callback, tag_callback=None, home_paths=None
    ):
        """Insert the textual profile for current_id into a textbox."""
        text._textbox.tag_configure(
            "bold",
            font=scaled_tag_font(
                text, self._mono_family, self._mono_size, weight="bold"),
        )
        text._textbox.tag_configure("person_link")
        text._textbox.tag_bind(
            "person_link", "<Enter>", lambda *_: text._textbox.config(cursor="hand2")
        )
        text._textbox.tag_bind(
            "person_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        text._textbox.tag_configure("tag_link")
        text._textbox.tag_bind(
            "tag_link", "<Enter>", lambda *_: text._textbox.config(cursor="hand2")
        )
        text._textbox.tag_bind(
            "tag_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        text._textbox.tag_configure(
            "gedcom_url_link", foreground=self._link_color, underline=1
        )
        text._textbox.tag_bind(
            "gedcom_url_link",
            "<Enter>",
            lambda *_: text._textbox.config(cursor="hand2"),
        )
        text._textbox.tag_bind(
            "gedcom_url_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        text._textbox.tag_configure(
            "relationship_link", foreground=self._link_color, underline=1
        )
        text._textbox.tag_bind(
            "relationship_link",
            "<Enter>",
            lambda *_: text._textbox.config(cursor="hand2"),
        )
        text._textbox.tag_bind(
            "relationship_link", "<Leave>", lambda *_: text._textbox.config(cursor="")
        )
        self._clear_person_tags(text)

        indi = self.individuals[current_id]
        thumbnail_layout = self._place_profile_thumbnail(text, current_id)
        if not self._profile_text_exists(text):
            return

        def add(line="", bold=False):
            text.insert("end", line + "\n", ("bold",) if bold else ())

        url_link_count = 0

        def add_with_https_links(line=""):
            nonlocal url_link_count
            last_end = 0
            for match in self._HTTPS_URL_RE.finditer(line):
                start, end = match.span()
                raw_url = match.group(0)
                url = raw_url.rstrip(self._URL_TRAILING_PUNCTUATION)
                if not url:
                    continue
                url_end = start + len(url)
                if start > last_end:
                    text.insert("end", line[last_end:start])
                tag = f"gedcom_url_{url_link_count}"
                url_link_count += 1
                text.insert("end", url, ("gedcom_url_link", tag))
                text._textbox.tag_bind(
                    tag, "<Button-1>", lambda _, u=url: webbrowser.open(u)
                )
                if url_end < end:
                    text.insert("end", line[url_end:end])
                last_end = end
            if last_end < len(line):
                text.insert("end", line[last_end:])
            text.insert("end", "\n")

        def person(pid, prefix=""):
            if prefix:
                text.insert("end", prefix)
            tag = f'pers_{pid.strip("@")}'
            text.insert(
                "end",
                describe(self.individuals[pid], show_id=self.show_ids.get()),
                ("person_link", tag),
            )
            text._textbox.tag_configure(tag, foreground=self._link_color)
            text._textbox.tag_bind(
                tag, "<Button-1>", lambda _, p=pid: navigate_callback(p)
            )
            text.insert("end", "\n")

        def person_inline(pid, prefix="", suffix=""):
            if prefix:
                text.insert("end", prefix)
            tag = f'pers_{pid.strip("@")}'
            text.insert(
                "end",
                describe(self.individuals[pid], show_id=self.show_ids.get()),
                ("person_link", tag),
            )
            text._textbox.tag_configure(tag, foreground=self._link_color)
            text._textbox.tag_bind(
                tag, "<Button-1>", lambda _, p=pid: navigate_callback(p)
            )
            if suffix:
                text.insert("end", suffix)

        def family_person(entry):
            prefix = FAM_MEMBER_ROLE_PREFIX.format(role=entry.get('role', ''))
            person(entry['id'], prefix=prefix)

        relationship_link_count = 0

        def relationship_line(rel, path, prefix=""):
            nonlocal relationship_link_count
            tag = f"path_graph_{relationship_link_count}"
            relationship_link_count += 1
            if prefix:
                text.insert("end", prefix)
            text.insert(
                "end", RESULT_RELATIONSHIP.format(rel=rel), ("relationship_link", tag)
            )
            text._textbox.tag_bind(
                tag,
                "<Button-1>",
                lambda _, p=tuple(path), r=rel: self._show_path_graph(p, r),
            )
            text.insert("end", "\n")

        def common_ancestor_line(ancestor_ids, prefix="", item_prefix="    "):
            if prefix:
                text.insert("end", prefix)
            if not ancestor_ids:
                text.insert("end", RESULT_COMMON_ANCESTOR)
                text.insert("end", RESULT_COMMON_ANCESTOR_NONE)
                text.insert("end", "\n")
                return
            if len(ancestor_ids) == 1:
                text.insert("end", RESULT_COMMON_ANCESTOR)
                person_inline(ancestor_ids[0])
                text.insert("end", "\n")
                return
            text.insert("end", RESULT_COMMON_ANCESTORS + "\n")
            for ancestor_id in ancestor_ids:
                person_inline(ancestor_id, prefix=item_prefix)
                text.insert("end", "\n")

        add(BIO_SECTION, bold=True)
        bio_found = False

        def fmt_event(date, place):
            parts = [p for p in (date, place) if p]
            return ", ".join(parts)

        b_date, b_place = _extract_event(indi["_raw"], "BIRT")
        if b_date or b_place:
            bio_found = True
            add(BIO_BORN.format(event=fmt_event(b_date, b_place)))

        for fam_id in indi["fams"]:
            fam = self.families.get(fam_id)
            if not fam:
                continue
            m_date = fam.get("marr_date", "")
            m_place = fam.get("marr_place", "")
            spouse_id = fam["wife"] if fam["husb"] == current_id else fam["husb"]
            spouse_name = (
                self._display_name(self.individuals[spouse_id])
                if spouse_id and spouse_id in self.individuals
                else ""
            )
            if spouse_name or m_date or m_place:
                bio_found = True
                parts = [p for p in (spouse_name, m_date, m_place) if p]
                add(BIO_MARRIED.format(spouses=", ".join(parts)))

        d_date, d_place = _extract_event(indi["_raw"], "DEAT")
        if d_date or d_place:
            bio_found = True
            add(BIO_DIED.format(event=fmt_event(d_date, d_place)))

        bu_date, bu_place = _extract_event(indi["_raw"], "BURI")
        if bu_date or bu_place:
            bio_found = True
            add(BIO_BURIED.format(event=fmt_event(bu_date, bu_place)))

        b_year = indi.get("birth_year")
        d_year = indi.get("death_year")
        is_deceased = bool(d_year or d_date or d_place or bu_date or bu_place)
        if is_deceased:
            if b_year and d_year:
                add(BIO_AGE_AT_DEATH.format(age=d_year - b_year))
        elif b_year and date.today().year - b_year < 120:
            # assumption that living people are <120 years old, otherwise death date is just missing
            add(BIO_AGE.format(age=date.today().year - b_year))

        if not bio_found:
            add(BIO_NO_INFO)
        add("")

        add(FAM_SECTION, bold=True)
        family_found = False
        family_entries = self._get_family_member_entries(current_id)
        parents = family_entries["parents"]
        siblings = family_entries["siblings"]
        spouses = family_entries["spouses"]
        children = family_entries["children"]

        if parents:
            family_found = True
            add(FAM_PARENTS)
            for entry in parents:
                family_person(entry)
        if siblings:
            family_found = True
            add(FAM_SIBLINGS)
            for entry in siblings:
                family_person(entry)
        if spouses:
            family_found = True
            add(FAM_SPOUSES if len(spouses) > 1 else FAM_SPOUSE)
            for entry in spouses:
                person(entry["id"], prefix="    ")
        if children:
            family_found = True
            add(FAM_CHILDREN)
            for entry in children:
                family_person(entry)
        if not family_found:
            add(FAM_NO_INFO)
        add("")

        self._render_home_path_section(
            home_paths,
            nl=add,
            person=person,
            relationship_line=relationship_line,
            common_ancestor_line=common_ancestor_line,
        )

        fact_event_lines = self._profile_fact_event_lines(indi.get("_raw", []))
        if fact_event_lines:
            add(FACTS_EVENTS_SECTION, bold=True)
            for line in fact_event_lines:
                add_with_https_links(line)
            add("")

        indi_tags = indi.get("tags", [])
        if indi_tags:
            add(TAGS_SECTION, bold=True)
            for i, tag_name in enumerate(indi_tags):
                tlink = f"taglink_{i}"
                text.insert("end", "  ")
                text.insert("end", tag_name, ("tag_link", tlink))
                text.insert("end", "\n")
                text._textbox.tag_configure(tlink, foreground=self._link_color)
                if tag_callback is not None:
                    text._textbox.tag_bind(
                        tlink, "<Button-1>", lambda _, n=tag_name: tag_callback(n)
                    )
            add("")

        if self.show_full_gedcom.get():
            add(GEDCOM_SECTION, bold=True)

            for level, xref, tag, value in indi.get("_raw", []):
                parts = [str(level)]
                if xref and self.show_ids.get():
                    parts.append(xref)
                parts.append(tag)
                if value:
                    parts.append(value)
                add_with_https_links(" ".join(parts))

        self._apply_profile_thumbnail_wrap(text, thumbnail_layout)

    def _show_person_for(self, indi_id, initial_view=None, existing_window=None):
        """Open a detail window for a specific individual ID."""
        if indi_id not in self.individuals:
            messagebox.showwarning(ERR_NO_SEL_TITLE, ERR_NO_SEL_MSG)
            return
        if existing_window is None:
            existing = getattr(self, "_secondary_win", None)
            if existing is not None:
                try:
                    if existing.winfo_exists():
                        existing_window = existing
                    else:
                        self._secondary_win = None
                        self._path_graph_win = None
                        self._path_graph_replace_fn = None
                except tk.TclError:
                    self._secondary_win = None
                    self._path_graph_win = None
                    self._path_graph_replace_fn = None
        reuse_window = existing_window is not None
        if reuse_window:
            win = existing_window
            if getattr(self, "_path_graph_win", None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            for sequence in self._reused_person_window_bindings():
                try:
                    win.unbind(sequence)
                except tk.TclError:
                    pass
            try:
                win.unbind("<Configure>")
            except tk.TclError:
                pass
            for child in win.winfo_children():
                child.destroy()
        else:
            win = ctk.CTkToplevel(self.root)
            self._secondary_win = win
            win.withdraw()
        win.resizable(True, True)
        if sys.platform != "win32":
            win.transient(self.root)

        _geo_after = [None]

        def _on_win_configure(event):
            if event.widget is not win:
                return
            if _geo_after[0]:
                win.after_cancel(_geo_after[0])
            _geo_after[0] = win.after(
                400, lambda: self._persist_show_person_geometry(win)
            )

        def _on_destroy_person_win(*_):
            if getattr(self, "_secondary_win", None) is win:
                self._secondary_win = None
            if getattr(self, "_path_graph_win", None) is win:
                self._path_graph_win = None
                self._path_graph_replace_fn = None
            self._expand_open_descendant_tree = None
            self._set_open_tree_zoom = None
            self._frame_open_descendant_top = None
            win.destroy()

        win.bind("<Escape>", _on_destroy_person_win)
        win.protocol("WM_DELETE_WINDOW", _on_destroy_person_win)

        content_frame = ctk.CTkFrame(win, fg_color="transparent")
        content_frame.pack(fill="both", expand=True)
        btn_frame = ctk.CTkFrame(win, fg_color="transparent")
        btn_frame.pack(fill="x", pady=(4, 8))

        copy_shortcut = "<Command-c>" if sys.platform == "darwin" else "<Control-c>"
        save_shortcut = "<Command-s>" if sys.platform == "darwin" else "<Control-s>"
        find_shortcut = "<Command-f>" if sys.platform == "darwin" else "<Control-f>"
        jump_shortcut = "<Command-j>" if sys.platform == "darwin" else "<Control-j>"
        toggle_shortcut = "<Command-t>" if sys.platform == "darwin" else "<Control-t>"
        state = {
            "person_id": indi_id,
            "mode": "person",
            "tree_view_mode": "tree",
            "tree_expanded": [(indi_id, cat) for cat in INITIAL_TREE_CATEGORIES],
            "descendant_expanded": {indi_id},
            "tree_zoom": 1.0,
            "zoom_controller": None,
            "history": [],
            "forward": [],
        }

        def _clear_content():
            for child in content_frame.winfo_children():
                child.destroy()

        def _clear_buttons():
            for child in btn_frame.winfo_children():
                child.destroy()

        def _bind_text_navigation(text_widget):
            win.bind(
                "<Up>", lambda *_: text_widget.yview_scroll(-1, "units") or "break"
            )
            win.bind(
                "<Down>", lambda *_: text_widget.yview_scroll(1, "units") or "break"
            )
            win.bind(
                "<Prior>", lambda *_: text_widget.yview_scroll(-1, "pages") or "break"
            )
            win.bind(
                "<Next>", lambda *_: text_widget.yview_scroll(1, "pages") or "break"
            )
            win.bind("<Home>", lambda *_: text_widget.yview_moveto(0) or "break")
            win.bind("<End>", lambda *_: text_widget.yview_moveto(1) or "break")

        def _bind_canvas_navigation(canvas):
            win.bind("<Up>", lambda *_: canvas.yview_scroll(-1, "units") or "break")
            win.bind("<Down>", lambda *_: canvas.yview_scroll(1, "units") or "break")
            win.bind("<Prior>", lambda *_: canvas.yview_scroll(-1, "pages") or "break")
            win.bind("<Next>", lambda *_: canvas.yview_scroll(1, "pages") or "break")
            win.bind(
                "<Home>",
                lambda *_: (canvas.xview_moveto(0), canvas.yview_moveto(0), "break")[
                    -1
                ],
            )
            win.bind(
                "<End>",
                lambda *_: (canvas.xview_moveto(1), canvas.yview_moveto(1), "break")[
                    -1
                ],
            )

        def _bind_tree_mouse_navigation(canvas):
            drag_state = {"x": 0, "y": 0}
            canvas._family_tree_dragged = False

            def _scroll_units(event):
                delta = getattr(event, "delta", 0)
                if not delta:
                    return 0
                if abs(delta) >= 120:
                    return int(-delta / 120)
                return -1 if delta > 0 else 1

            def _on_mouse_wheel(event):
                if getattr(event, "state", 0):
                    return None
                units = _scroll_units(event)
                if units:
                    canvas.yview_scroll(units, "units")
                return "break"

            def _on_linux_wheel_up(event):
                if getattr(event, "state", 0):
                    return None
                canvas.yview_scroll(-1, "units")
                return "break"

            def _on_linux_wheel_down(event):
                if getattr(event, "state", 0):
                    return None
                canvas.yview_scroll(1, "units")
                return "break"

            def _on_drag_start(event):
                canvas.focus_set()
                drag_state["x"] = event.x
                drag_state["y"] = event.y
                canvas._family_tree_dragged = False
                canvas.scan_mark(event.x, event.y)

            def _on_drag_motion(event):
                if (
                    abs(event.x - drag_state["x"]) > 3
                    or abs(event.y - drag_state["y"]) > 3
                ):
                    canvas._family_tree_dragged = True
                canvas.scan_dragto(event.x, event.y, gain=1)
                return "break"

            def _on_drag_release(_event):
                canvas.after_idle(
                    lambda: setattr(canvas, "_family_tree_dragged", False)
                )

            canvas.bind("<MouseWheel>", _on_mouse_wheel, add="+")
            canvas.bind("<Button-4>", _on_linux_wheel_up, add="+")
            canvas.bind("<Button-5>", _on_linux_wheel_down, add="+")
            canvas.bind("<ButtonPress-1>", _on_drag_start, add="+")
            canvas.bind("<B1-Motion>", _on_drag_motion, add="+")
            canvas.bind("<ButtonRelease-1>", _on_drag_release, add="+")

        view_mode_labels = {
            "tree": BTN_TREE_VIEW,
            "pedigree": BTN_PEDIGREE_VIEW,
            "descendant": BTN_DESCENDANT_VIEW,
            "person": BTN_PERSON_VIEW,
        }
        view_mode_by_label = {label: mode for mode, label in view_mode_labels.items()}
        view_mode_tooltips = {
            "tree": get_tip_tree_view_btn(),
            "pedigree": get_tip_pedigree_view_btn(),
            "descendant": get_tip_descendant_view_btn(),
            "person": get_tip_person_view_btn(),
        }
        view_mode_values = [
            view_mode_labels["tree"],
            view_mode_labels["pedigree"],
            view_mode_labels["descendant"],
            view_mode_labels["person"],
        ]

        def _current_window_view():
            return "person" if state["mode"] == "person" else state["tree_view_mode"]

        def _render_view_selector(select_window_view):
            mode_frame = ctk.CTkFrame(btn_frame, fg_color="transparent")
            mode_frame.pack(side="left", padx=8)

            def _select_mode(value):
                select_window_view(view_mode_by_label.get(value, "tree"))

            if hasattr(ctk, "CTkSegmentedButton"):
                mode_selector = ctk.CTkSegmentedButton(
                    mode_frame,
                    values=view_mode_values,
                    command=_select_mode,
                )
                mode_selector.pack(side="left")
                mode_selector.set(view_mode_labels[_current_window_view()])
                for mode, label in view_mode_labels.items():
                    button = mode_selector._buttons_dict.get(label)
                    if button is not None:
                        Tooltip(button, view_mode_tooltips[mode])
            else:
                mode_var = tk.StringVar(value=view_mode_labels[_current_window_view()])
                for mode, value in view_mode_labels.items():
                    radio = ctk.CTkRadioButton(
                        mode_frame,
                        text=value,
                        variable=mode_var,
                        value=value,
                        command=lambda v=value: _select_mode(v),
                    )
                    radio.pack(side="left", padx=(0, 6))
                    Tooltip(radio, view_mode_tooltips[mode])

        def _render_person_buttons(
                select_window_view, copy_profile, save_profile, show_gallery=None):
            _clear_buttons()
            _render_view_selector(select_window_view)
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80, command=win.destroy
            ).pack(side="right", padx=8)
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_profile
            )
            copy_btn.pack(side="right", padx=(0, 8))
            Tooltip(copy_btn, get_tip_copy_profile())
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_profile
            )
            save_btn.pack(side="right", padx=(0, 8))
            Tooltip(save_btn, get_tip_save_profile())
            if show_gallery is not None:
                gallery_btn = ctk.CTkButton(
                    btn_frame, text=BTN_PROFILE_GALLERY, width=90,
                    command=show_gallery,
                )
                gallery_btn.pack(side="right", padx=(0, 8))
                Tooltip(gallery_btn, get_tip_profile_gallery())

        def _render_tree_buttons(
            select_window_view,
            copy_graph,
            save_graph,
            search_graph,
            jump_graph,
            save_debug=None,
        ):
            _clear_buttons()
            _render_view_selector(select_window_view)
            ctk.CTkButton(
                btn_frame, text=BTN_CLOSE, width=80, command=win.destroy
            ).pack(side="right", padx=8)
            copy_btn = ctk.CTkButton(
                btn_frame, text=BTN_COPY_GRAPH, width=80, command=copy_graph
            )
            copy_btn.pack(side="right", padx=(0, 8))
            Tooltip(copy_btn, get_tip_copy_graph())
            save_btn = ctk.CTkButton(
                btn_frame, text=BTN_SAVE_GRAPH, width=80, command=save_graph
            )
            save_btn.pack(side="right", padx=(0, 8))
            Tooltip(save_btn, get_tip_save_graph())
            jump_btn = ctk.CTkButton(
                btn_frame, text=BTN_JUMP_GRAPH, width=80, command=jump_graph
            )
            jump_btn.pack(side="right", padx=(0, 8))
            Tooltip(jump_btn, get_tip_jump_graph())
            search_btn = ctk.CTkButton(
                btn_frame, text=BTN_SEARCH_GRAPH, width=80, command=search_graph
            )
            search_btn.pack(side="right", padx=(0, 8))
            Tooltip(search_btn, get_tip_search_graph())
            if save_debug:
                debug_btn = ctk.CTkButton(
                    btn_frame, text=BTN_DEBUG_GRAPH, width=100, command=save_debug
                )
                debug_btn.pack(side="right", padx=(0, 8))
                Tooltip(debug_btn, TIP_DEBUG_GRAPH)

        back_seq = "<Command-Left>" if sys.platform == "darwin" else "<Alt-Left>"
        fwd_seq = "<Command-Right>" if sys.platform == "darwin" else "<Alt-Right>"

        def _go_back():
            if state["history"]:
                state["forward"].append(state["person_id"])
                state["person_id"] = state["history"].pop()
                _show_person_view()

        def _go_forward():
            if state["forward"]:
                state["history"].append(state["person_id"])
                state["person_id"] = state["forward"].pop()
                _show_person_view()

        def _select_window_view(new_mode):
            if new_mode == "person":
                if state["mode"] != "person":
                    _show_person_view(state["person_id"])
                return
            if state["mode"] == "tree" and new_mode == state["tree_view_mode"]:
                return
            _show_tree_view(state["person_id"], tree_mode=new_mode)

        def _show_person_view(iid=None):
            # Leaving tree mode: drop the tree automation hooks (see _show_tree_view).
            self._expand_open_descendant_tree = None
            self._set_open_tree_zoom = None
            self._frame_open_descendant_top = None
            if iid is not None:
                state["history"].append(state["person_id"])
                state["forward"].clear()
                state["person_id"] = iid
            current_id = state["person_id"]
            state["mode"] = "person"
            _clear_content()
            text = ctk.CTkTextbox(
                content_frame, font=(self._mono_family, self._mono_size), wrap="none"
            )
            text._textbox.configure(padx=8, pady=8)
            text.pack(fill="both", expand=True)

            def _apply_person_zoom(size):
                text.configure(font=(self._mono_family, size))
                text._textbox.tag_configure(
                    "bold",
                    font=scaled_tag_font(
                        text, self._mono_family, size, weight="bold"),
                )

            state["zoom_controller"] = TextZoomController(
                text, self._mono_size, _apply_person_zoom, targets=(text._textbox,)
            )
            _bind_text_navigation(text)
            win.bind(back_seq, lambda *_: _go_back() or "break")
            win.bind(fwd_seq, lambda *_: _go_forward() or "break")

            indi = self.individuals[current_id]
            win.title(WIN_GEDCOM_RECORD.format(name=indi["name"] or current_id))
            text.configure(state="normal")
            text.delete("1.0", "end")

            def _on_tag_click(tag_name):
                self.tag_keyword.set(tag_name)
                self.page_marker.set("")
                self.search_text.set("")
                self.filter_text.set("")
                self.show_flagged_only.set(True)
                win.destroy()

            self._insert_person_profile(
                text, current_id, _show_person_view, tag_callback=_on_tag_click
            )

            text.configure(state="disabled")

            def _profile_content():
                body = text.get("1.0", "end").rstrip()
                title = win.title().strip()
                return (title + "\n\n" + body) if title else body

            def _copy_profile(*_):
                content = _profile_content()
                if not content:
                    return "break"
                win.clipboard_clear()
                win.clipboard_append(content)
                return "break"

            def _save_profile(*_):
                content = _profile_content()
                if not content:
                    return "break"
                path = filedialog.asksaveasfilename(
                    parent=filedialog_parent(win),
                    title=DLG_SAVE_PROFILE,
                    defaultextension=".txt",
                    filetypes=[
                        ("Text files", "*.txt"),
                        ("All files", "*.*"),
                    ],
                )
                if not path:
                    return "break"
                try:
                    with open(path, "w", encoding="utf-8") as f:
                        f.write(content)
                        f.write("\n")
                except OSError as exc:
                    messagebox.showerror(
                        ERR_SAVE_GRAPH_TITLE,
                        ERR_SAVE_PROFILE_MSG.format(error=exc),
                        parent=win,
                    )
                return "break"

            win.bind(copy_shortcut, _copy_profile)
            win.bind(save_shortcut, _save_profile)
            show_gallery = None
            if self._profile_gallery_candidates(current_id):
                show_gallery = lambda iid=current_id: self._show_profile_image_gallery(
                    iid, parent=win)
            _render_person_buttons(
                _select_window_view,
                _copy_profile,
                _save_profile,
                show_gallery,
            )
            text.focus_set()

        def _tree_window_title(mode, name):
            if mode == "pedigree":
                return WIN_PEDIGREE_TREE.format(name=name)
            if mode == "descendant":
                return WIN_DESCENDANT_TREE.format(name=name)
            return WIN_FAMILY_TREE.format(name=name)

        def _tree_save_title(mode):
            if mode == "pedigree":
                return DLG_SAVE_PEDIGREE_TREE
            if mode == "descendant":
                return DLG_SAVE_DESCENDANT_TREE
            return DLG_SAVE_FAMILY_TREE

        def _show_tree_view(iid=None, tree_mode=None):
            was_tree = state["mode"] == "tree"
            center_changed = iid is not None and iid != state["person_id"]
            if iid is not None:
                state["person_id"] = iid
            if tree_mode is not None:
                state["tree_view_mode"] = tree_mode
            state["mode"] = "tree"
            if center_changed or not was_tree:
                state["tree_expanded"] = [
                    (state["person_id"], cat) for cat in INITIAL_TREE_CATEGORIES
                ]
                state["descendant_expanded"] = {state["person_id"]}
            _clear_content()
            indi = self.individuals[state["person_id"]]
            win.title(
                _tree_window_title(
                    state["tree_view_mode"], indi["name"] or state["person_id"]
                )
            )

            is_dark = ctk.get_appearance_mode() == "Dark"
            colors = self._path_graph_colors(
                is_dark, getattr(self, "_theme_pref", None)
            )

            canvas_frame = ctk.CTkFrame(content_frame, fg_color="transparent")
            canvas_frame.pack(fill="both", expand=True, padx=12, pady=(12, 0))
            canvas_frame.rowconfigure(0, weight=1)
            canvas_frame.columnconfigure(0, weight=1)

            canvas = tk.Canvas(canvas_frame, bg=colors["bg"], highlightthickness=0)
            canvas._highlighted_nodes = set()
            ybar = tk.Scrollbar(canvas_frame, orient="vertical", command=canvas.yview)
            xbar = tk.Scrollbar(canvas_frame, orient="horizontal", command=canvas.xview)
            canvas.configure(yscrollcommand=ybar.set, xscrollcommand=xbar.set)
            canvas.grid(row=0, column=0, sticky="nsew")
            ybar.grid(row=0, column=1, sticky="ns")
            xbar.grid(row=1, column=0, sticky="ew")

            graph_state = {
                "zoom": state["tree_zoom"],
                "canvas_w": 0,
                "canvas_h": 0,
                "debug_payload": None,
            }
            canvas.bind(
                "<Configure>",
                lambda *_: self._center_graph_canvas(
                    canvas, graph_state["canvas_w"], graph_state["canvas_h"]
                ),
                add="+",
            )

            def _redraw_tree(progress_callback=None):
                canvas.delete("all")
                mode = state["tree_view_mode"]
                render_kwargs = {}
                expanded = state["tree_expanded"]
                if mode == "pedigree":
                    graph = build_pedigree_tree_graph(
                        state["person_id"], self.individuals, self.families
                    )
                    expanded = []
                    render_kwargs.update(
                        {
                            "graph_builder": lambda graph=graph: graph,
                            "layout_builder": layout_pedigree_tree,
                            "expandable_categories": (),
                            "orientation": "horizontal",
                        }
                    )
                elif mode == "descendant":
                    graph = build_descendant_tree_graph(
                        state["person_id"],
                        state["descendant_expanded"],
                        self.individuals,
                        self.families,
                    )
                    branch_ids = {state["person_id"]}
                    changed = True
                    while changed:
                        changed = False
                        for source_id, target_id, category in graph[1]:
                            if (
                                category == "children"
                                and source_id in branch_ids
                                and target_id not in branch_ids
                            ):
                                branch_ids.add(target_id)
                                changed = True
                    expanded = descendant_tree_expanded_requests(
                        [indi_id for indi_id in graph[0] if indi_id in branch_ids],
                        state["descendant_expanded"],
                        self._family_tree_members_for,
                    )
                    render_kwargs.update(
                        {
                            "graph_builder": lambda graph=graph: graph,
                            "layout_builder": layout_descendant_tree,
                            "expandable_categories": ("children",),
                            "graph_type": "descendant_tree",
                            "expansion_options_lookup": (
                                lambda node_id, visible_set: (
                                    descendant_tree_expansion_options(
                                        node_id,
                                        visible_set,
                                        self._family_tree_members_for,
                                    )
                                    if node_id in branch_ids
                                    else {"children": []}
                                )
                            ),
                            "expanded_for_buttons": expanded,
                            "expand_all_categories_lookup": (
                                lambda node_id, visible_set: (
                                    ("children",)
                                    if (
                                        node_id in branch_ids
                                        and self._family_tree_members_for(node_id).get(
                                            "children"
                                        )
                                    )
                                    else ()
                                )
                            ),
                        }
                    )
                graph_state["canvas_w"], graph_state["canvas_h"] = (
                    self._render_family_tree_canvas(
                        canvas,
                        state["person_id"],
                        expanded,
                        colors,
                        win,
                        graph_state["zoom"],
                        _expand_tree,
                        _recenter_tree,
                        _show_profile_from_tree,
                        _find_matches_from_tree,
                        _find_paths_from_tree,
                        _expand_all_tree,
                        progress_callback=progress_callback,
                        **render_kwargs,
                    )
                )
                graph_state["debug_payload"] = getattr(
                    canvas, "_family_tree_debug_payload", None
                )

            canvas._redraw_fn = _redraw_tree

            def _center_tree_on_current():
                canvas.update_idletasks()
                center_x, center_y = getattr(
                    canvas,
                    "_family_tree_center",
                    (graph_state["canvas_w"] / 2, graph_state["canvas_h"] / 2),
                )
                view_w = max(canvas.winfo_width(), 1)
                view_h = max(canvas.winfo_height(), 1)
                canvas_w = max(graph_state["canvas_w"], 1)
                canvas_h = max(graph_state["canvas_h"], 1)
                max_x = max(0, 1 - (view_w / canvas_w))
                max_y = max(0, 1 - (view_h / canvas_h))
                x_pos = max(0, min(max_x, (center_x - view_w / 2) / canvas_w))
                y_pos = max(0, min(max_y, (center_y - view_h / 2) / canvas_h))
                canvas.xview_moveto(x_pos)
                canvas.yview_moveto(y_pos)

            def _set_tree_zoom(zoom):
                zoom = max(0.5, min(2.5, zoom))
                if abs(zoom - graph_state["zoom"]) < 0.001:
                    return
                x0, x1 = canvas.xview()
                y0, y1 = canvas.yview()
                center_x = (x0 + x1) / 2
                center_y = (y0 + y1) / 2
                span_x = x1 - x0
                span_y = y1 - y0
                graph_state["zoom"] = zoom
                state["tree_zoom"] = zoom
                _redraw_tree()
                canvas.update_idletasks()
                canvas.xview_moveto(max(0, min(1, center_x - span_x / 2)))
                canvas.yview_moveto(max(0, min(1, center_y - span_y / 2)))

            def _zoom_tree_in():
                _set_tree_zoom(graph_state["zoom"] * 1.1)

            def _zoom_tree_out():
                _set_tree_zoom(graph_state["zoom"] / 1.1)

            def _zoom_tree_reset():
                _set_tree_zoom(1.0)

            def _maybe_grow_tree_win():
                """Grow window to fit expanded content; skip if already maximized."""
                # Detect maximized state separately so a TclError from an
                # unsupported attribute (e.g. -zoomed on macOS Aqua) is treated
                # as "not maximized" rather than aborting the whole function.
                try:
                    is_max = (
                        win.state() == "zoomed"
                        if sys.platform == "win32"
                        else bool(win.attributes("-zoomed"))
                    )
                except tk.TclError:
                    is_max = False
                if is_max:
                    return
                try:
                    win.update_idletasks()
                    tsw = self.root.winfo_screenwidth()
                    tsh = self.root.winfo_screenheight()
                    tnw = int(graph_state["canvas_w"]) + 65
                    tnh = int(graph_state["canvas_h"]) + 105
                    if tnw > int(tsw * 0.9) or tnh > int(tsh * 0.9):
                        if sys.platform == "win32":
                            win.state("zoomed")
                        else:
                            win.attributes("-zoomed", True)
                    else:
                        cur_w = win.winfo_width()
                        cur_h = win.winfo_height()
                        new_w = max(cur_w, tnw)
                        new_h = max(cur_h, tnh)
                        if new_w > cur_w or new_h > cur_h:
                            cx, cy = win.winfo_x(), win.winfo_y()
                            win.geometry(
                                f"{int(new_w)}x{int(new_h)}"
                                f"+{max(0, min(cx, tsw - new_w))}"
                                f"+{max(0, min(cy, tsh - new_h))}"
                            )
                except tk.TclError:
                    pass

            def _expand_tree(expand_id, category):
                if state["tree_view_mode"] == "descendant":
                    if expand_id in state["descendant_expanded"]:
                        state["descendant_expanded"].remove(expand_id)
                    else:
                        state["descendant_expanded"].add(expand_id)
                    _redraw_tree()
                    _maybe_grow_tree_win()
                    return
                request = (expand_id, category)
                self._toggle_expansion_request(state["tree_expanded"], request)
                _redraw_tree()
                _maybe_grow_tree_win()

            def _recenter_tree(new_center_id):
                state["person_id"] = new_center_id
                state["tree_expanded"] = [
                    (new_center_id, cat) for cat in INITIAL_TREE_CATEGORIES
                ]
                state["descendant_expanded"] = {new_center_id}
                center = self.individuals[new_center_id]
                win.title(
                    _tree_window_title(
                        state["tree_view_mode"], center["name"] or new_center_id
                    )
                )
                _redraw_tree()
                _maybe_grow_tree_win()
                canvas.after_idle(_center_tree_on_current)

            def _show_profile_from_tree(indi_id):
                self._show_profile_from_tree_context(indi_id, _show_person_view)

            def _find_matches_from_tree(indi_id):
                self._select_person_in_main_tree(indi_id)
                _on_destroy_person_win()
                self.root.after_idle(self._find_matches)

            def _find_paths_from_tree(indi_id):
                center_id = state["person_id"]
                self._select_person_in_main_tree(center_id)
                _on_destroy_person_win()
                self.root.after_idle(lambda: self._run_path_search(center_id, indi_id))

            def _expand_all_tree(indi_id, categories):
                if state["tree_view_mode"] == "descendant":

                    def _collect_descendants(cancel_event):
                        to_expand = {indi_id}
                        stack = [indi_id]
                        while stack:
                            if cancel_event.is_set():
                                return None
                            source_id = stack.pop()
                            for child_id in self._family_tree_members_for(
                                source_id
                            ).get("children", ()):
                                if child_id in to_expand:
                                    continue
                                to_expand.add(child_id)
                                stack.append(child_id)
                        return to_expand

                    def _on_cancel():
                        self._hide_search_popup()

                    def _on_done(result, error):
                        if error:
                            self._hide_search_popup()
                            messagebox.showerror(ERR_PARSE_TITLE, str(error))
                            return
                        if not result:
                            self._hide_search_popup()
                            return

                        def _apply_expand_all():
                            before = set(state["descendant_expanded"])
                            state["descendant_expanded"].update(result)
                            if before != state["descendant_expanded"]:
                                _redraw_tree(self._pulse_search_popup_progress)
                                _maybe_grow_tree_win()
                            self._hide_search_popup()

                        if len(result) < 250:
                            _apply_expand_all()
                            return

                        apply_cancelled = {"value": False}

                        def _cancel_apply():
                            apply_cancelled["value"] = True
                            self._hide_search_popup()

                        self._hide_search_popup()
                        self._show_search_popup(
                            PROGRESS_EXPANDING_DESCENDANTS,
                            on_cancel=_cancel_apply,
                            owner=win,
                        )

                        def _apply_after_popup_maps():
                            if apply_cancelled["value"]:
                                return
                            _apply_expand_all()

                        win.after(100, _apply_after_popup_maps)

                    self._run_background_task(
                        _collect_descendants,
                        _on_done,
                        popup_message=PROGRESS_EXPANDING_DESCENDANTS,
                        cancelable=True,
                        on_cancel=_on_cancel,
                        popup_delay_ms=2000,
                        popup_owner=win,
                    )
                    return
                if self._expand_all_requests(
                    state["tree_expanded"], indi_id, categories
                ):
                    _redraw_tree()
                    _maybe_grow_tree_win()

            def _save_tree(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_canvas(
                        win,
                        canvas,
                        graph_state,
                        _tree_save_title(state["tree_view_mode"]),
                    )
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            def _copy_tree(*_):
                win.update_idletasks()
                try:
                    return self._copy_graph_canvas(win, canvas, graph_state)
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            def _search_tree_center(*_):
                self._search_tree_center_context(
                    lambda: self._pick_person(WIN_SELECT_PERSON, owner=win),
                    _recenter_tree,
                )
                return "break"

            def _jump_tree_center(*_):
                visible = set(getattr(canvas, "_family_tree_positions", {}).keys())
                indi_id = self._pick_person(
                    WIN_SELECT_PERSON,
                    owner=win,
                    filter_ids=visible if visible else None,
                )
                if not indi_id:
                    return "break"
                positions = getattr(canvas, "_family_tree_positions", {})
                if indi_id not in positions:
                    return "break"
                self._add_canvas_highlighted_node(canvas, indi_id)
                positions = getattr(canvas, "_family_tree_positions", {})
                if indi_id not in positions:
                    return "break"
                node_x, node_y = positions[indi_id]
                canvas.update_idletasks()
                view_w = max(canvas.winfo_width(), 1)
                view_h = max(canvas.winfo_height(), 1)
                canvas_w = max(graph_state["canvas_w"], 1)
                canvas_h = max(graph_state["canvas_h"], 1)
                max_x = max(0, 1 - (view_w / canvas_w))
                max_y = max(0, 1 - (view_h / canvas_h))
                x_pos = max(0, min(max_x, (node_x - view_w / 2) / canvas_w))
                y_pos = max(0, min(max_y, (node_y - view_h / 2) / canvas_h))
                canvas.xview_moveto(x_pos)
                canvas.yview_moveto(y_pos)
                return "break"

            def _save_tree_debug(*_):
                win.update_idletasks()
                try:
                    return self._save_graph_debug_payload(win, graph_state)
                finally:
                    btn_frame.pack(fill="x", pady=(4, 8))

            _redraw_tree()

            # Automation hooks for the App Store screenshot generator
            # (dev/generate-appstore-assets.py).  These let the generator drive
            # the open tree window synchronously — fully expanding a descendant
            # tree (the in-canvas "expand all" runs as a cancelable background
            # task with a progress popup, which is awkward to await) and setting
            # the zoom so a sprawling tree can be framed.  They are harmless in
            # normal use and are cleared when the window switches to a profile
            # view or closes.
            def _expand_all_descendants_now():
                if state["tree_view_mode"] != "descendant":
                    return False
                to_expand = {state["person_id"]}
                stack = [state["person_id"]]
                while stack:
                    source_id = stack.pop()
                    for child_id in self._family_tree_members_for(source_id).get(
                        "children", ()
                    ):
                        if child_id not in to_expand:
                            to_expand.add(child_id)
                            stack.append(child_id)
                if to_expand <= state["descendant_expanded"]:
                    return False
                state["descendant_expanded"].update(to_expand)
                _redraw_tree()
                _maybe_grow_tree_win()
                return True

            def _frame_descendants_from_top():
                # Scroll so the root sits at top-centre and the generations
                # cascade downward — the natural framing for a screenshot of a
                # tree too wide/deep to fit entirely on screen.
                canvas.update_idletasks()
                center_x, _ = getattr(
                    canvas,
                    "_family_tree_center",
                    (graph_state["canvas_w"] / 2, 0),
                )
                view_w = max(canvas.winfo_width(), 1)
                canvas_w = max(graph_state["canvas_w"], 1)
                max_x = max(0, 1 - (view_w / canvas_w))
                canvas.xview_moveto(
                    max(0, min(max_x, (center_x - view_w / 2) / canvas_w))
                )
                canvas.yview_moveto(0.0)

            self._expand_open_descendant_tree = _expand_all_descendants_now
            self._set_open_tree_zoom = _set_tree_zoom
            self._frame_open_descendant_top = _frame_descendants_from_top

            _bind_canvas_navigation(canvas)
            _bind_tree_mouse_navigation(canvas)
            bind_zoom_shortcuts(canvas, _zoom_tree_in, _zoom_tree_out, _zoom_tree_reset)
            win.bind(copy_shortcut, _copy_tree)
            win.bind(save_shortcut, _save_tree)
            win.bind(find_shortcut, _search_tree_center)
            canvas.bind(find_shortcut, _search_tree_center)
            win.bind(jump_shortcut, _jump_tree_center)
            canvas.bind(jump_shortcut, _jump_tree_center)
            graph_debug_enabled = debug_enabled()
            if graph_debug_enabled:
                win.bind("<Control-Shift-D>", _save_tree_debug)
                canvas.bind("<Control-Shift-D>", _save_tree_debug)
            _render_tree_buttons(
                _select_window_view,
                _copy_tree,
                _save_tree,
                _search_tree_center,
                _jump_tree_center,
                _save_tree_debug if graph_debug_enabled else None,
            )
            state["_tree_button_needed_w"] = self._button_bar_needed_width(btn_frame)
            canvas.focus_set()
            canvas.after_idle(_center_tree_on_current)

            # Compute needed window size from tree content plus fixed UI overhead.
            # Measured chrome at scale=1.0: padx×2 (24) + ybar (17) = 41 wide;
            # pady-top (12) + xbar (17) + btn-bar+pady (~40) = 69 tall.
            # Add a 24px horizontal and 36px vertical buffer above the measured
            # chrome so that minor geometry rounding never triggers scrollbars.
            # Use self.root (always mapped) for reliable screen dimensions.
            _tsw = self.root.winfo_screenwidth()
            _tsh = self.root.winfo_screenheight()
            _tmax_w = int(_tsw * 0.9)
            _tmax_h = int(_tsh * 0.9)
            _tnw = int(graph_state["canvas_w"]) + 65
            _tnh = int(graph_state["canvas_h"]) + 105
            _tnw = max(_tnw, state.get("_tree_button_needed_w", 0))
            _twants_max = _tnw > _tmax_w or _tnh > _tmax_h
            state["_tree_wants_max"] = _twants_max
            state["_tree_needed_w"] = min(_tnw, _tmax_w)
            state["_tree_needed_h"] = min(_tnh, _tmax_h)

            if win.winfo_viewable():
                if _twants_max:
                    if sys.platform == "win32":
                        win.state("zoomed")
                    else:
                        try:
                            win.attributes("-zoomed", True)
                        except tk.TclError:
                            win.geometry(
                                f"{state['_tree_needed_w']}"
                                f"x{state['_tree_needed_h']}+0+0"
                            )
                else:
                    _tcur_w = win.winfo_width()
                    _tcur_h = win.winfo_height()
                    _tnew_w = max(_tcur_w, state["_tree_needed_w"])
                    _tnew_h = max(_tcur_h, state["_tree_needed_h"])
                    if _tnew_w > _tcur_w or _tnew_h > _tcur_h:
                        _tcx = win.winfo_x()
                        _tcy = win.winfo_y()
                        win.geometry(
                            f"{int(_tnew_w)}x{int(_tnew_h)}"
                            f"+{max(0, min(_tcx, _tsw - _tnew_w))}"
                            f"+{max(0, min(_tcy, _tsh - _tnew_h))}"
                        )

        def _toggle_view(*_):
            cycle = ("tree", "pedigree", "descendant", "person")
            current = _current_window_view()
            next_mode = cycle[(cycle.index(current) + 1) % len(cycle)]
            _select_window_view(next_mode)
            return "break"

        win.bind(toggle_shortcut, _toggle_view)

        initial_view = self._resolve_initial_person_view(initial_view)
        if initial_view in self._TREE_VIEW_MODES:
            _show_tree_view(indi_id, tree_mode=initial_view)
        else:
            _show_person_view(indi_id)

        # Use self.root for screen info — win is still withdrawn so
        # win.winfo_screenwidth() returns 0 on Windows before first show.
        _sw = self.root.winfo_screenwidth()
        _sh = self.root.winfo_screenheight()
        _mw = max(400, int(_sw * 0.9) - 32)
        _mh = max(300, int(_sh * 0.9) - 32)
        _tnw = state.get("_tree_needed_w", 0)
        _tnh = state.get("_tree_needed_h", 0)
        _twm = state.get("_tree_wants_max", False)

        if self._show_person_geometry and self._show_person_opened_this_session:
            # Subsequent open: parse saved geometry and expand for tree if needed.
            try:
                _wh = self._show_person_geometry.split("+")[0].split("-")[0]
                _sgw, _sgh = (int(p) for p in _wh.split("x"))
                _rest = self._show_person_geometry[len(_wh) :]
                _pnums = [
                    int(n)
                    for n in _rest.replace("+", " +").replace("-", " -").split()
                    if n
                ]
                _sgx, _sgy = _pnums[0], _pnums[1]
            except (ValueError, IndexError, AttributeError):
                _sgw, _sgh = 700, 520
                _sgx, _sgy = (_sw - _sgw) // 2, (_sh - _sgh) // 2
            if _tnw and not _twm:
                # Size to tree content, not to saved size.  The saved geometry
                # may have been set when a large tree caused the window to grow
                # to near-maximum; reusing that size would make every subsequent
                # small tree open at full maximum width.  Use the saved position
                # so the window re-opens near where the user left it.
                _w = min(_tnw, _mw)
                _h = min(_tnh, _mh)
            else:
                _w, _h = min(_sgw, _mw), min(_sgh, _mh)
            _x = max(0, min(_sgx, _sw - _w))
            _y = max(0, min(_sgy, _sh - _h))
        else:
            # First open this session: size for content and center on display.
            if _twm:
                _w, _h = 700, 520  # will be maximized after deiconify
            elif _tnw:
                _w, _h = min(_tnw, _mw), min(_tnh, _mh)
            else:
                _w, _h = 700, 520
            _w, _h = max(400, _w), max(300, _h)
            _x = max(0, (_sw - _w) // 2)
            _y = max(0, (_sh - _h) // 2)

        self._show_person_opened_this_session = True
        win.bind("<Configure>", _on_win_configure)
        win.minsize(400, 300)
        if reuse_window:
            win.update_idletasks()
            self._raise_window(win)
            return

        win.update_idletasks()
        win.geometry(f"{int(_w)}x{int(_h)}+{int(_x)}+{int(_y)}")
        self._raise_window(win)
        if _twm:
            if sys.platform == "win32":
                win.state("zoomed")
            else:
                try:
                    win.attributes("-zoomed", True)
                except tk.TclError:
                    win.geometry(
                        f"{state.get('_tree_needed_w', _mw)}"
                        f"x{state.get('_tree_needed_h', _mh)}"
                        f"+{_x}+{_y}"
                    )

    @staticmethod
    def _reused_person_window_bindings():
        """Return Toplevel bindings that should not survive a view swap."""
        mod_key = "Command" if sys.platform == "darwin" else "Control"
        return (
            "<Escape>",
            "<Up>",
            "<Down>",
            "<Prior>",
            "<Next>",
            "<Home>",
            "<End>",
            f"<{mod_key}-c>",
            f"<{mod_key}-s>",
            f"<{mod_key}-t>",
            f"<{mod_key}-plus>",
            f"<{mod_key}-equal>",
            f"<{mod_key}-KP_Add>",
            f"<{mod_key}-minus>",
            f"<{mod_key}-KP_Subtract>",
            f"<{mod_key}-0>",
            f"<{mod_key}-KP_0>",
            f"<{mod_key}-MouseWheel>",
            f"<{mod_key}-Button-4>",
            f"<{mod_key}-Button-5>",
        )
