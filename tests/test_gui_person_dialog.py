"""Tests for person dialog defensive behavior."""

from gedcom_gui_person_dialog import PersonDialogMixin
from gedcom_gui_results import ResultsMixin
from gedcom_strings import (
    BIO_SECTION,
    FAM_SECTION,
    FACTS_EVENTS_SECTION,
    GEDCOM_SECTION,
    PROFILE_IMAGE_NAV_STATUS,
    RESULT_PATH_SECTION,
    TAGS_SECTION,
)


class Var:
    def __init__(self, value):
        self.value = value

    def get(self):
        return self.value


class FakeText:
    def __init__(self):
        self._textbox = self
        self.parts = []
        self.inserted = []
        self.bindings = {}
        self.configured_tags = {}
        self.deleted_tags = []

    def insert(self, _index, text, _tags=None):
        self.parts.append(text)
        self.inserted.append((text, _tags))

    def tag_configure(self, *_args, **_kwargs):
        if _args:
            self.configured_tags[_args[0]] = _kwargs

    def tag_bind(self, tag, sequence, callback=None, **_kwargs):
        self.bindings[(tag, sequence)] = callback

    def tag_names(self, *_args):
        return list(self.configured_tags)

    def tag_delete(self, tag):
        self.deleted_tags.append(tag)


class Model:
    def find_common_ancestors(self, *_args):
        return []


def test_show_person_for_missing_id_warns_without_opening_window(monkeypatch):
    """Stale callbacks should not build a profile/tree window for missing IDs."""

    class App(PersonDialogMixin):
        pass

    app = App()
    app.individuals = {}
    warnings = []
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.messagebox.showwarning',
        lambda title, message: warnings.append((title, message)),
    )

    app._show_person_for('@OLD@', initial_view='tree')

    assert warnings
    assert not hasattr(app, '_secondary_win')


def test_tree_context_profile_stays_in_person_window():
    """Tree View Profile action navigates within the person detail window."""

    class App(PersonDialogMixin):
        def __init__(self):
            self.calls = []

        def _select_person_in_main_tree(self, indi_id):
            self.calls.append(('select', indi_id))

        def _set_display_mode(self, mode):
            self.calls.append(('display', mode))

    app = App()
    navigated = []

    app._show_profile_from_tree_context('@P1@', lambda iid: navigated.append(iid))

    assert navigated == ['@P1@']
    assert app.calls == []


def test_tree_initial_view_uses_configured_default_tree():
    """Opening Tree View starts with the configured tree subview."""

    class Config:
        def get_default_tree(self):
            return 'pedigree'

    class App(PersonDialogMixin):
        def __init__(self):
            self._config = Config()

    app = App()

    assert app._resolve_initial_person_view('tree') == 'pedigree'
    assert app._resolve_initial_person_view('descendant') == 'descendant'
    assert app._resolve_initial_person_view('profile') == 'profile'
    assert app._resolve_initial_person_view(None) == 'profile'


def test_button_bar_needed_width_includes_window_padding():
    """Tree View initial sizing accounts for the full button row."""

    class ButtonFrame:
        def __init__(self):
            self.updated = False

        def update_idletasks(self):
            self.updated = True

        def winfo_reqwidth(self):
            return 820

    frame = ButtonFrame()

    assert PersonDialogMixin._button_bar_needed_width(frame) == 844
    assert frame.updated is True


def test_profile_preview_window_dimensions_include_button_width():
    """Small images still produce a preview wide enough for all buttons."""

    win_w, win_h, min_w, min_h = (
        PersonDialogMixin._profile_preview_window_dimensions(
            image_w=72,
            image_h=48,
            max_w=800,
            max_h=600,
            button_w=330,
            button_h=54,
        )
    )

    assert win_w == 330
    assert win_h == 104
    assert min_w == 330
    assert min_h == 104


def test_tree_search_recenters_only_when_person_selected():
    """Tree search leaves the current center unchanged when the picker is cancelled."""

    class App(PersonDialogMixin):
        pass

    app = App()
    recentered = []

    selected = app._search_tree_center_context(lambda: '@P1@', recentered.append)
    cancelled = app._search_tree_center_context(lambda: None, recentered.append)

    assert selected == '@P1@'
    assert cancelled is None
    assert recentered == ['@P1@']


def test_add_canvas_highlighted_node_redraws_only_when_added():
    """Tree jump highlighting redraws when it marks a newly selected person."""

    class Canvas:
        def __init__(self):
            self._highlighted_nodes = {'@A@'}
            self.redraws = 0
            self._redraw_fn = self._redraw

        def _redraw(self):
            self.redraws += 1

    canvas = Canvas()

    added = PersonDialogMixin._add_canvas_highlighted_node(canvas, '@B@')
    unchanged = PersonDialogMixin._add_canvas_highlighted_node(canvas, '@B@')

    assert added is True
    assert unchanged is False
    assert canvas._highlighted_nodes == {'@A@', '@B@'}
    assert canvas.redraws == 1


def test_profile_thumbnail_size_is_larger_than_graph_thumbnail_and_clamped():
    class Root:
        def winfo_screenheight(self):
            return 1440

    class App(PersonDialogMixin):
        pass

    app = App()
    app.root = Root()
    app._mono_size = 14

    assert app._profile_thumbnail_size() == (173, 173)
    assert app._graph_thumbnail_size(lambda value, minimum=1: value) == (84, 84)

    app.root = type("SmallRoot", (), {"winfo_screenheight": lambda self: 720})()
    assert app._profile_thumbnail_size() == (112, 112)

    app.root = type("LargeRoot", (), {"winfo_screenheight": lambda self: 3000})()
    assert app._profile_thumbnail_size() == (176, 176)


def test_missing_profile_image_notice_shows_once_for_missing_file(monkeypatch):
    class App(PersonDialogMixin):
        pass

    class Media:
        @staticmethod
        def selected_media_file(_indi):
            return "missing/photo.jpg"

        @staticmethod
        def is_supported_path(_path):
            return True

        @staticmethod
        def resolve_media_path(_path, _gedcom_path, _media_dirs=None):
            return None

    class GedcomPath:
        @staticmethod
        def get():
            return "/tmp/tree.ged"

    class Config:
        def __init__(self):
            self.saved = []

        def get_media_parent_dir(self, _gedcom_path):
            return None

        def set_media_parent_dir(self, gedcom_path, directory):
            self.saved.append((gedcom_path, directory))

    app = App()
    app.gedcom_path = GedcomPath()
    app._config = Config()
    app.root = object()
    prompts = []
    monkeypatch.setattr(
        "gedcom_gui_person_dialog.messagebox.askyesno",
        lambda title, message, parent=None: prompts.append((title, message, parent)) or True,
    )
    monkeypatch.setattr(
        "gedcom_gui_person_dialog.filedialog.askdirectory",
        lambda **_kwargs: "/new/media",
    )

    app._maybe_show_missing_profile_image_notice({"name": "Alex"}, Media())
    app._maybe_show_missing_profile_image_notice({"name": "Alex"}, Media())

    assert len(prompts) == 1
    assert "missing/photo.jpg" in prompts[0][1]
    assert app._config.saved == [("/tmp/tree.ged", "/new/media")]
    assert app._profile_image_missing_notice_shown is True


def test_missing_profile_image_notice_skips_absent_or_resolved_file(monkeypatch):
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return "/tmp/tree.ged"

    class Media:
        def __init__(self, media_path, resolved):
            self.media_path = media_path
            self.resolved = resolved

        def selected_media_file(self, _indi):
            return self.media_path

        @staticmethod
        def is_supported_path(_path):
            return True

        def resolve_media_path(self, _path, _gedcom_path, _media_dirs=None):
            return self.resolved

    app = App()
    app.gedcom_path = GedcomPath()
    app._config = None
    notices = []
    monkeypatch.setattr(
        "gedcom_gui_person_dialog.messagebox.askyesno",
        lambda *_args, **_kwargs: notices.append(_args),
    )

    app._maybe_show_missing_profile_image_notice({}, Media("", None))
    app._maybe_show_missing_profile_image_notice({}, Media("found.jpg", "/tmp/found.jpg"))

    assert notices == []
    assert not getattr(app, "_profile_image_missing_notice_shown", False)


def test_initial_media_directory_prefers_saved_directory(tmp_path):
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return str(tmp_path / "tree.ged")

    saved = tmp_path / "saved"
    saved.mkdir()
    app = App()
    app.gedcom_path = GedcomPath()
    app._profile_media_dirs = lambda: [str(saved)]

    assert app._initial_media_directory() == str(saved)


def test_initial_media_directory_prefers_nearby_media_folder(tmp_path):
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return str(tmp_path / "tree.ged")

    media = tmp_path / "Photos"
    media.mkdir()
    app = App()
    app.gedcom_path = GedcomPath()
    app._profile_media_dirs = lambda: []

    assert app._initial_media_directory() == str(media)


def test_initial_media_directory_falls_back_to_gedcom_directory(tmp_path):
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return str(tmp_path / "tree.ged")

    app = App()
    app.gedcom_path = GedcomPath()
    app._profile_media_dirs = lambda: []

    assert app._initial_media_directory() == str(tmp_path)


def test_profile_gallery_candidates_exclude_profile_and_unsupported():
    class App(PersonDialogMixin):
        pass

    class Media:
        @staticmethod
        def is_supported_path(path):
            return path.endswith(".jpg")

    app = App()
    app.show_profile_image = Var(True)
    app._media_service = Media()
    app.individuals = {
        "@A@": {
            "media_candidates": [
                {"file": "profile.jpg", "title": "Profile"},
                {"file": "album.jpg", "title": "Album"},
                {"file": "notes.pdf", "title": "Document"},
                {"file": "album.jpg", "title": "Album"},
                {"file": "", "title": "Missing"},
            ],
        },
    }

    assert app._profile_gallery_candidates("@A@") == [
        {"file": "album.jpg", "title": "Album"},
    ]

    app.show_profile_image = Var(False)
    assert app._profile_gallery_candidates("@A@") == []


def test_pdf_profile_photo_bytes_uses_only_resolved_real_media():
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return "/tmp/tree.ged"

    class Media:
        @staticmethod
        def resolve_person_media(indi, gedcom_path, media_dirs=None):
            assert indi["name"] == "Alex"
            assert gedcom_path == "/tmp/tree.ged"
            assert media_dirs == ["/replacement"]
            return "/tmp/alex.jpg"

        @staticmethod
        def full_size_png_bytes(path, size):
            assert path == "/tmp/alex.jpg"
            assert size == (240, 240)
            return b"png-data"

    app = App()
    app.individuals = {"@A@": {"name": "Alex"}}
    app.gedcom_path = GedcomPath()
    app._media_service = Media()
    app._profile_media_dirs = lambda: ["/replacement"]

    assert app._pdf_profile_photo_bytes("@A@") == b"png-data"


def test_pdf_profile_photo_bytes_omits_missing_photo():
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return "/tmp/tree.ged"

    class Media:
        @staticmethod
        def resolve_person_media(*_args, **_kwargs):
            return None

    app = App()
    app.individuals = {"@A@": {"name": "Alex"}}
    app.gedcom_path = GedcomPath()
    app._media_service = Media()
    app._profile_media_dirs = lambda: []

    assert app._pdf_profile_photo_bytes("@A@") is None


def test_profile_gallery_items_prompt_for_missing_media_dir(monkeypatch):
    class App(PersonDialogMixin):
        pass

    class GedcomPath:
        @staticmethod
        def get():
            return "/tmp/tree.ged"

    class Config:
        def __init__(self):
            self.directory = None

        def get_media_parent_dir(self, _gedcom_path):
            return self.directory

        def set_media_parent_dir(self, _gedcom_path, directory):
            self.directory = directory

    class Media:
        @staticmethod
        def is_supported_path(path):
            return path.endswith(".jpg")

        @staticmethod
        def resolve_media_path(path, _gedcom_path, media_dirs=None):
            if media_dirs:
                return f"{media_dirs[0]}/{path}"
            return None

        @staticmethod
        def tk_thumbnail(_path, _size):
            return "thumbnail"

    app = App()
    app.show_profile_image = Var(True)
    app.gedcom_path = GedcomPath()
    app._config = Config()
    app._media_service = Media()
    app._initial_media_directory = lambda: "/tmp"
    app.root = object()
    app.individuals = {
        "@A@": {
            "media_candidates": [
                {"file": "profile.jpg", "title": "Profile"},
                {"file": "album.jpg", "title": "Album"},
            ],
        },
    }
    monkeypatch.setattr(
        "gedcom_gui_person_dialog.messagebox.askyesno",
        lambda *_args, **_kwargs: True,
    )
    monkeypatch.setattr(
        "gedcom_gui_person_dialog.filedialog.askdirectory",
        lambda **_kwargs: "/new/media",
    )

    items = app._profile_gallery_items("@A@", (120, 120), prompt_missing=True)

    assert items == [{
        "path": "/new/media/album.jpg",
        "image": "thumbnail",
        "title": "Album",
        "file": "album.jpg",
    }]
    assert app._config.directory == "/new/media"


def test_profile_image_navigation_state_requires_current_gallery_path():
    paths = ["/media/one.jpg", "/media/two.jpg", "/media/three.jpg"]

    assert PersonDialogMixin._profile_image_navigation_state(
        "/media/two.jpg", paths) == (paths, 1)
    assert PersonDialogMixin._profile_image_navigation_state(
        "/media/missing.jpg", paths) == ([], 0)
    assert PersonDialogMixin._profile_image_navigation_state(
        "/media/two.jpg", None) == ([], 0)


def test_profile_image_navigation_status_text_is_one_based():
    assert PROFILE_IMAGE_NAV_STATUS.format(current=2, total=5) == "2 of 5"


def test_profile_full_image_title_uses_filename_without_extension():
    assert PersonDialogMixin._profile_full_image_title(
        "/media/family/Adam J. Kessel.jpg") == "Adam J. Kessel"
    assert PersonDialogMixin._profile_full_image_title(
        r"C:\media\Family Photo.PNG") == "Family Photo"


def test_profile_thumbnail_is_parented_above_inner_text(monkeypatch):
    class Image:
        @staticmethod
        def width():
            return 100

        @staticmethod
        def height():
            return 120

    class Inner:
        def tag_delete(self, _tag):
            pass

        def update_idletasks(self):
            pass

        @staticmethod
        def winfo_x():
            return 10

        @staticmethod
        def winfo_y():
            return 5

        @staticmethod
        def winfo_width():
            return 300

        def bind(self, *_args, **_kwargs):
            pass

    class Text:
        def __init__(self):
            self._textbox = Inner()
            self.bindings = []

        def configure(self, **_kwargs):
            pass

        def bind(self, *args, **kwargs):
            self.bindings.append((args, kwargs))

        @staticmethod
        def winfo_toplevel():
            return None

    class Label:
        def __init__(self, master, **_kwargs):
            self.master = master
            self.placements = []
            self.lift_count = 0

        def bind(self, *_args, **_kwargs):
            pass

        def place(self, **kwargs):
            self.placements.append(kwargs)

        def lift(self):
            self.lift_count += 1

        def after_idle(self, callback):
            callback()

    class App(PersonDialogMixin):
        def _profile_media_payload(self, _indi_id, _size):
            return {'kind': 'real', 'path': '/media/photo.jpg', 'image': Image()}

        @staticmethod
        def _profile_thumbnail_size():
            return 100, 120

    monkeypatch.setattr('gedcom_gui_person_dialog.tk.Label', Label)
    text = Text()

    layout = App()._place_profile_thumbnail(text, '@A@')

    label = text._profile_image_label
    assert label.master is text
    assert label.placements[-1] == {'x': 302, 'y': 13, 'anchor': 'ne'}
    assert label.lift_count >= 1
    assert layout == {'width': 100, 'height': 120, 'pad': 8}


def test_full_profile_image_panning_binds_both_mouse_buttons():
    class Canvas:
        def __init__(self):
            self.bindings = {}
            self.calls = []

        def bind(self, sequence, callback):
            self.bindings[sequence] = callback

        def scan_mark(self, x, y):
            self.calls.append(('mark', x, y))

        def scan_dragto(self, x, y, gain):
            self.calls.append(('drag', x, y, gain))

        def configure(self, **kwargs):
            self.calls.append(('configure', kwargs))

    class Event:
        x = 12
        y = 34

    canvas = Canvas()
    PersonDialogMixin._bind_full_profile_image_panning(canvas)

    for button in (1, 3):
        assert canvas.bindings[f'<ButtonPress-{button}>'](Event()) == 'break'
        assert canvas.bindings[f'<B{button}-Motion>'](Event()) == 'break'
        assert canvas.bindings[f'<ButtonRelease-{button}>'](Event()) == 'break'

    assert canvas.calls == [
        ('mark', 12, 34),
        ('configure', {'cursor': 'fleur'}),
        ('drag', 12, 34, 1),
        ('configure', {'cursor': ''}),
    ] * 2


def test_clamped_toplevel_geometry_keeps_gallery_on_screen():
    class Parent:
        @staticmethod
        def update_idletasks():
            return None

        @staticmethod
        def winfo_screenwidth():
            return 800

        @staticmethod
        def winfo_screenheight():
            return 600

        @staticmethod
        def winfo_rootx():
            return 300

        @staticmethod
        def winfo_rooty():
            return 500

        @staticmethod
        def winfo_width():
            return 300

        @staticmethod
        def winfo_height():
            return 200

    geometry = PersonDialogMixin._clamped_toplevel_geometry(
        Parent(), 500, 260)

    assert geometry == "500x260+200+316"


def test_profile_sections_render_in_requested_order():
    """Profile sections render Biography, Family, Home Path, Facts, then Tags."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _get_family_members(self, _indi_id):
            return [], [], [], []

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@A@': {
            'name': 'Alex Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': ['DNA Match'],
            '_raw': [(0, '@A@', 'INDI', ''),
                     (1, None, 'BIRT', ''),
                     (2, None, 'DATE', '1900'),
                     (1, None, 'OCCU', 'Blacksmith')],
        },
        '@H@': {
            'name': 'Home Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [],
        },
    }
    app.families = {}
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(True)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()

    app._insert_person_profile(
        text,
        '@A@',
        lambda _indi_id: None,
        home_paths={
            'home_id': '@H@',
            'paths': [[('@A@', None), ('@H@', 'father')]],
        },
    )
    rendered = ''.join(text.parts)

    assert rendered.index(BIO_SECTION) < rendered.index(RESULT_PATH_SECTION)
    assert rendered.index(BIO_SECTION) < rendered.index(FAM_SECTION)
    assert rendered.index(FAM_SECTION) < rendered.index(RESULT_PATH_SECTION)
    assert rendered.index(RESULT_PATH_SECTION) < rendered.index(FACTS_EVENTS_SECTION)
    assert rendered.index(FACTS_EVENTS_SECTION) < rendered.index(TAGS_SECTION)
    assert rendered.index(TAGS_SECTION) < rendered.index(GEDCOM_SECTION)


def test_profile_facts_events_render_grouped_and_chronological():
    """Profile facts use fixed groups and chronological date-first entries."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _get_family_members(self, _indi_id):
            return [], [], [], []

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@A@': {
            'name': 'Alex Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [
                (0, '@A@', 'INDI', ''),
                (1, None, 'BIRT', ''),
                (2, None, 'DATE', '1900'),
                (1, None, 'OCCU', 'Blacksmith'),
                (2, None, 'DATE', '1910'),
                (2, None, 'PLAC', 'Boston, Massachusetts'),
                (1, None, 'RESI', ''),
                (2, None, 'DATE', '1930'),
                (2, None, 'PLAC', 'Chicago, Illinois'),
                (1, None, 'RESI', ''),
                (2, None, 'DATE', '1920'),
                (2, None, 'PLAC', 'New York, New York'),
                (1, None, 'EDUC', 'Princeton University'),
                (2, None, 'DATE', 'ABT 1905'),
                (1, None, 'GRAD', 'Engineering'),
                (2, None, 'DATE', '1908'),
                (1, None, 'EVEN', 'Eagle Scout'),
                (2, None, 'TYPE', 'Award'),
                (2, None, 'DATE', '1920'),
                (2, None, 'NOTE', 'earned '),
                (3, None, 'CONC', 'merit badges'),
                (3, None, 'CONT', 'over two lines'),
                (1, None, 'BURI', ''),
                (2, None, 'DATE', '1980'),
            ],
        },
    }
    app.families = {}
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(False)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()

    app._insert_person_profile(text, '@A@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert rendered.index(BIO_SECTION) < rendered.index(FAM_SECTION)
    assert rendered.index(FAM_SECTION) < rendered.index(FACTS_EVENTS_SECTION)
    residence = rendered.index('  Residence\n')
    education = rendered.index('  Education\n')
    occupation = rendered.index('  Occupation\n')
    other = rendered.index('  Other Facts & Events\n')
    assert residence < education < occupation < other
    assert rendered.index('    1920: New York, New York\n') < rendered.index(
        '    1930: Chicago, Illinois\n'
    )
    assert '    ABT 1905: Princeton University\n' in rendered
    assert '    1908: Graduation: Engineering\n' in rendered
    assert '    1910: Blacksmith, Boston, Massachusetts\n' in rendered
    assert '    1920: Award: Eagle Scout\n' in rendered
    assert '      Note: earned merit badges over two lines\n' in rendered
    assert 'Birth:' not in rendered
    assert 'Burial:' not in rendered


def test_profile_facts_events_put_unparseable_and_undated_entries_last():
    raw = [
        (1, None, 'OCCU', 'Undated role'),
        (1, None, 'OCCU', 'Dated role'),
        (2, None, 'DATE', '2000'),
        (1, None, 'OCCU', 'Text date role'),
        (2, None, 'DATE', 'UNKNOWN'),
        (1, None, 'OCCU', 'Same-year first'),
        (2, None, 'DATE', '2000'),
    ]

    groups = PersonDialogMixin._profile_fact_event_groups(raw)

    assert groups == [
        (
            'Occupation',
            [
                {
                    'date': '2000',
                    'primary': 'Dated role',
                    'supplemental': [],
                    'source_order': 1,
                },
                {
                    'date': '2000',
                    'primary': 'Same-year first',
                    'supplemental': [],
                    'source_order': 3,
                },
                {
                    'date': 'UNKNOWN',
                    'primary': 'Text date role',
                    'supplemental': [],
                    'source_order': 2,
                },
                {
                    'date': '',
                    'primary': 'Undated role',
                    'supplemental': [],
                    'source_order': 0,
                },
            ],
        )
    ]


def test_profile_facts_events_render_sources_and_clickable_urls(monkeypatch):
    """Facts & Events detail lines reuse Profile URL hyperlink rendering."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _get_family_members(self, _indi_id):
            return [], [], [], []

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@A@': {
            'name': 'Alex Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [
                (0, '@A@', 'INDI', ''),
                (1, None, 'RESI', ''),
                (2, None, 'DATE', '1930'),
                (2, None, 'PLAC', 'Chicago, Illinois'),
                (2, None, 'NOTE', 'See https://example.test/residence)'),
                (2, None, 'SOUR', '@S1@'),
                (
                    3,
                    None,
                    'PAGE',
                    'The Burlington Free Press; Publication Date: 17 Aug 1996; '
                    'Publication Place: Burlington, Vermont, USA; URL: '
                    'https://www.newspapers.com/image/202577571/?article=abc'
                    '&xid=4717 &terms=Adam_Kessel',
                ),
                (2, None, 'SOUR', '@S2@'),
                (3, None, 'PAGE', 'Ordinary source without a URL'),
            ],
        },
    }
    app.families = {}
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(False)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()
    opened = []
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.webbrowser.open', lambda url: opened.append(url)
    )

    app._insert_person_profile(text, '@A@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert (
        '  Residence\n'
        '    1930: Chicago, Illinois\n'
        '      Note: See https://example.test/residence)\n'
        '      Source: The Burlington Free Press; Publication Date: 17 Aug 1996; '
        'Publication Place: Burlington, Vermont, USA\n'
        '      Source: Ordinary source without a URL\n'
        in rendered
    )
    assert 'URL:' not in rendered
    assert 'https://www.newspapers.com/image/202577571/' not in rendered
    assert ('gedcom_url_link', 'gedcom_url_0') in [
        tags for part, tags in text.inserted
        if part == 'https://example.test/residence'
    ]
    assert ('gedcom_url_link', 'gedcom_url_1') in [
        tags for part, tags in text.inserted
        if part == (
            'Source: The Burlington Free Press; Publication Date: '
            '17 Aug 1996; Publication Place: Burlington, Vermont, USA'
        )
    ]
    assert ('      ', None) in text.inserted
    assert not any(
        part.startswith(' ')
        for part, tags in text.inserted
        if tags and 'gedcom_url_link' in tags
    )

    text.bindings[('gedcom_url_0', '<Button-1>')](None)
    text.bindings[('gedcom_url_1', '<Button-1>')](None)

    assert opened == [
        'https://example.test/residence',
        'https://www.newspapers.com/image/202577571/?article=abc'
        '&xid=4717&terms=Adam_Kessel',
    ]


def test_full_gedcom_https_urls_are_clickable(monkeypatch):
    """Full GEDCOM Record URLs are rendered as browser links."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _get_family_members(self, _indi_id):
            return [], [], [], []

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@A@': {
            'name': 'Alex Person',
            'sex': 'M',
            'famc': [],
            'fams': [],
            'tags': [],
            '_raw': [
                (0, '@A@', 'INDI', ''),
                (1, None, 'WWW', 'https://example.com/person?x=1.'),
                (1, None, 'NOTE', 'See https://example.org/a and https://b.test/z)'),
            ],
        },
    }
    app.families = {}
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(True)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()
    opened = []
    monkeypatch.setattr(
        'gedcom_gui_person_dialog.webbrowser.open', lambda url: opened.append(url)
    )

    app._insert_person_profile(text, '@A@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert '1 WWW https://example.com/person?x=1.' in rendered
    assert 'gedcom_url_link' not in text.deleted_tags
    assert ('gedcom_url_link', 'gedcom_url_0') in [
        tags for part, tags in text.inserted
        if part == 'https://example.com/person?x=1'
    ]
    assert ('gedcom_url_link', 'gedcom_url_1') in [
        tags for part, tags in text.inserted
        if part == 'https://example.org/a'
    ]
    assert ('gedcom_url_link', 'gedcom_url_2') in [
        tags for part, tags in text.inserted
        if part == 'https://b.test/z'
    ]

    text.bindings[('gedcom_url_0', '<Button-1>')](None)
    text.bindings[('gedcom_url_2', '<Button-1>')](None)

    assert opened == ['https://example.com/person?x=1', 'https://b.test/z']


def test_profile_labels_non_biological_and_half_relatives():
    """Profile family section qualifies only non-ordinary relatives."""

    class App(PersonDialogMixin, ResultsMixin):
        def _display_name(self, indi):
            return indi['name']

        def _show_path_graph(self, *_args):
            pass

    app = App()
    app.individuals = {
        '@ME@': {
            'id': '@ME@', 'name': 'Me Person', 'sex': 'M',
            'famc': ['@F1@'], 'fams': [], 'tags': [], '_raw': [],
        },
        '@DAD@': {
            'id': '@DAD@', 'name': 'Dad Person', 'sex': 'M',
            'famc': [], 'fams': ['@F1@', '@F2@'], 'tags': [], '_raw': [],
        },
        '@STEP@': {
            'id': '@STEP@', 'name': 'Step Parent', 'sex': 'F',
            'famc': [], 'fams': ['@F1@'], 'tags': [], '_raw': [],
        },
        '@HALF@': {
            'id': '@HALF@', 'name': 'Half Sibling', 'sex': 'F',
            'famc': ['@F2@'], 'fams': [], 'tags': [], '_raw': [],
        },
    }
    app.families = {
        '@F1@': {
            'id': '@F1@', 'husb': '@DAD@', 'wife': '@STEP@',
            'chil': ['@ME@'],
            'child_links': {'@ME@': {'father': 'birth', 'mother': 'step'}},
        },
        '@F2@': {
            'id': '@F2@', 'husb': '@DAD@', 'wife': None,
            'chil': ['@HALF@'], 'child_links': {},
        },
    }
    app.show_ids = Var(False)
    app.show_full_gedcom = Var(False)
    app._link_color = '#0000ee'
    app._mono_family = 'Courier'
    app._mono_size = 12
    app._model = Model()
    text = FakeText()

    app._insert_person_profile(text, '@ME@', lambda _indi_id: None)

    rendered = ''.join(text.parts)
    assert 'Father: Dad Person' in rendered
    assert 'Step-mother: Step Parent' in rendered
    assert 'Half-sister: Half Sibling' in rendered
    assert 'Biological' not in rendered
