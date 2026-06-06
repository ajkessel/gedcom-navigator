#!/usr/bin/env python3
"""
Generate Mac App Store screenshots and animated preview assets.

Run from the project root on MacOS:
    python dev/generate-appstore-assets.py                # full pipeline
    python dev/generate-appstore-assets.py --only pedigree  # one screenshot
    python dev/generate-appstore-assets.py --only tree pedigree  # a subset

With no --only the full pipeline runs (all screenshots + video).  --only
regenerates just the named screenshot(s) and skips video compilation; the
mandatory setup (GEDCOM load, home person, Maya selection) always runs.

Produces in docs/screenshots/appstore/:
  screenshot_01_main.png          – person list, Maya selected, path-to-home visible
  screenshot_02_matches.png       – DNA match results + path to home person
  screenshot_03_paths.png         – paths mode: Maya → Brianna Logan Vaughn
  screenshot_04_with_graph.png    – main + relationship graph (Maya → Brianna)
  screenshot_04_graph_only.png    – relationship graph alone (2560×1600)
  screenshot_05_tree.png          – family tree view, Daniel Hart (2560×1600)
  screenshot_06_pedigree.png      – pedigree (ancestor) tree, Maya Hart (2560×1600)
  screenshot_07_descendant.png    – descendant tree, Arthur Hart (2560×1600)
  screen_recording.gif            – animated GIF (for README / web)
  app_preview.mp4                 – H.264 App Preview (for Mac App Store, ~17 s)

No Screen Recording permission required: window pixels are read directly
via AppKit's NSThemeFrame (called via performSelectorOnMainThread so that
the AppKit call never runs inside a Tkinter callback, avoiding the
PyObjC/GIL crash in Python 3.13 + PyObjC 12.1).

App Store requirements satisfied
---------------------------------
* Screenshots: 2560×1600 @2x Retina (accepted Mac App Store size).
* App Preview: H.264, ~17 s (within 15–30 s requirement).
"""

import os
import subprocess
import sys
import threading
import time
import queue
from pathlib import Path

if sys.platform != 'darwin':
    print("Error: this script requires a MacOS environment", file=sys.stderr)
    sys.exit(1)

# Detect if the script is running inside a virtual environment
if sys.prefix == sys.base_prefix:
    venv_python = Path(__file__).parent.parent / ".venv" / "bin" / "python"
    if venv_python.exists():
        os.execl(str(venv_python), str(venv_python), *sys.argv)
    else:
        print("Error: Virtual environment ('venv') not found.", file=sys.stderr)
        sys.exit(1)

# ---------------------------------------------------------------------------
# Project paths
# ---------------------------------------------------------------------------
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_DIR = SCRIPT_DIR.parent
sys.path.insert(0, str(PROJECT_DIR / "src"))
os.chdir(PROJECT_DIR)

GEDCOM_FILE = str(PROJECT_DIR / "samples" / "fictional_genealogy.ged")
OUTPUT_DIR = PROJECT_DIR / "docs" / "screenshots" / "appstore"
FRAMES_DIR = OUTPUT_DIR / "frames"

WIN_W = 1280
WIN_CONTENT_H = 772  # +28 px title bar → 800 px total
WIN_X, WIN_Y = 60, 60

# Home person for the DNA results demo: Maya's paternal grandfather.
# Sets up a 2-hop "path to home" (Maya → Daniel → Arthur) visible in results.
HOME_PERSON_ID = "@I6@"

# Start person for all searches (Maya Lynn Hart).
START_PERSON_ID = "@I1@"

# Paths / relationship-graph demo target: a non-obvious multi-hop relationship
# from Maya.  @I367@ Brianna Logan Vaughn is Maya's "second cousin-in-law" via a
# 7-node path: mother → father → sibling → child → child → spouse.
PATHS_TARGET_ID = "@I367@"

# Tree-view subjects, chosen so each of the three views is visually full and
# the set spans three generations of the same family:
#   family tree  – Daniel Hart: 2 parents, 5 siblings, 2 spouses, 10 children
#   pedigree     – Maya Hart:   8 ancestors across 3 generations (youngest)
#   descendant   – Arthur Hart: 148 descendants across 3 generations (eldest)
TREE_PERSON_ID = "@I2@"
PEDIGREE_PERSON_ID = "@I1@"
DESCENDANT_PERSON_ID = "@I6@"

# Window-title fragments used as capture keys for each tree view.
TREE_TITLES = {
    "tree": "Family Tree",
    "pedigree": "Pedigree Tree",
    "descendant": "Descendant Tree",
}

# Selective regeneration keys — each maps to one logical screenshot step.  Pass
# one or more with `--only KEY [KEY ...]` to regenerate just those screenshots;
# with no `--only` the full pipeline runs (every screenshot plus the GIF/MP4).
# "graph" covers both the combined (screenshot_04_with_graph) and graph-only
# (screenshot_04_graph_only) captures, which share the same setup.
SCREENSHOT_KEYS = (
    "main",        # screenshot_01_main.png
    "matches",     # screenshot_02_matches.png
    "paths",       # screenshot_03_paths.png
    "graph",       # screenshot_04_with_graph.png + screenshot_04_graph_only.png
    "tree",        # screenshot_05_tree.png
    "pedigree",    # screenshot_06_pedigree.png
    "descendant",  # screenshot_07_descendant.png
)


def _relationship_for_path(app, start_id, path):
    """Plain-English relationship label for *path*, matching the results panel.

    The DNA results pane computes the label with the start person's ancestor and
    descendant depth maps plus the family table; replicate that here so the graph
    caption is identical to what the user sees in the list.  describe_relationship
    takes ``ancestors``/``descendants``/``families`` as keyword args — passing the
    family table positionally would bind it to ``ancestors`` and mislabel the path.
    """
    try:
        from gedcom_relationship import (  # noqa: PLC0415
            describe_relationship,
            get_ancestor_depths,
            get_descendant_depths,
        )

        ancestors = get_ancestor_depths(start_id, app.individuals, app.families)
        descendants = get_descendant_depths(start_id, app.individuals, app.families)
        return describe_relationship(
            path,
            app.individuals,
            ancestors=ancestors,
            descendants=descendants,
            families=app.families,
        )
    except Exception:  # pylint: disable=broad-exception-caught
        return "relationship"

# ---------------------------------------------------------------------------
# AppKit capture — via performSelectorOnMainThread to bypass Tkinter's
# callback dispatch (which causes a GIL crash in Python 3.13 + PyObjC 12.1)
# ---------------------------------------------------------------------------
import AppKit  # noqa: E402  (pyobjc-framework-Cocoa)
import objc  # noqa: E402
from Foundation import NSObject, NSNumber  # noqa: E402


class _AppKitCapturer(NSObject):
    """NSObject whose doCapture_ selector is invoked on the Cocoa main thread."""

    _pending_title: str = ""
    _pending_path: str = ""
    _pending_ok: bool = False

    def doCapture_(self, _ignored: object) -> None:
        title = _AppKitCapturer._pending_title
        out_path = Path(_AppKitCapturer._pending_path)
        ns_app = AppKit.NSApplication.sharedApplication()
        win = None
        for w in ns_app.windows():
            if title in str(w.title()):
                win = w
                break
        if win is None:
            print(f"  WARNING: window '{title}' not found")
            _AppKitCapturer._pending_ok = False
            return
        theme_frame = win.contentView().superview()
        bounds = theme_frame.bounds()
        rep = theme_frame.bitmapImageRepForCachingDisplayInRect_(bounds)
        theme_frame.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
        data = rep.representationUsingType_properties_(
            AppKit.NSBitmapImageFileTypePNG, None
        )
        out_path.parent.mkdir(parents=True, exist_ok=True)
        data.writeToFile_atomically_(str(out_path), True)
        _AppKitCapturer._pending_ok = True


_capturer: _AppKitCapturer | None = None


def _init_capturer() -> None:
    global _capturer
    _capturer = _AppKitCapturer.alloc().init()


def _capture(title_fragment: str, out_path: Path) -> bool:
    """
    Capture the window from any thread via NSRunLoop (not Tkinter callback).
    """
    _AppKitCapturer._pending_title = title_fragment
    _AppKitCapturer._pending_path = str(out_path)
    _AppKitCapturer._pending_ok = False
    _capturer.performSelectorOnMainThread_withObject_waitUntilDone_(
        "doCapture:", NSNumber.numberWithInt_(0), True
    )
    return _AppKitCapturer._pending_ok


# ---------------------------------------------------------------------------
# Cross-thread UI helper — Tkinter operations only (no AppKit here)
# ---------------------------------------------------------------------------
_root_ref = None  # set before mainloop starts


def _ui(fn, *args, timeout: float = 30.0):
    """
    Schedule *fn* on the Tk main thread, block until done, return result.
    Safe to call from any thread.
    """
    result_q: queue.Queue = queue.Queue(maxsize=1)

    def _call():
        try:
            result_q.put(("ok", fn(*args)))
        except Exception as exc:  # pylint: disable=broad-exception-caught
            result_q.put(("err", exc))

    _root_ref.after(0, _call)
    kind, val = result_q.get(timeout=timeout)
    if kind == "err":
        raise val
    return val


# ---------------------------------------------------------------------------
# Video compilation helpers
# ---------------------------------------------------------------------------
from PIL import Image  # noqa: E402


def build_gif(frame_dir: Path, out_path: Path, fps: int = 5):
    frames = sorted(frame_dir.glob("frame_*.png"))
    if not frames:
        print("  No frames – skipping GIF.")
        return
    images = []
    for f in frames:
        img = Image.open(f).resize((WIN_W, 800), Image.LANCZOS)
        images.append(img.convert("P", palette=Image.ADAPTIVE, colors=256))
    duration = 1000 // fps
    images[0].save(
        out_path,
        save_all=True,
        append_images=images[1:],
        loop=0,
        duration=duration,
        optimize=True,
    )
    size_mb = out_path.stat().st_size / 1_048_576
    print(
        f"  GIF: {out_path.name}  ({len(images)} frames @ {fps} fps, {size_mb:.1f} MB)"
    )


def build_mp4(frame_dir: Path, out_path: Path, fps: int = 5):
    # App Preview requirement: 1920×1080 (16:9).
    # Source frames are 2560×1600 (16:10 Retina capture), so scale to
    # 1920×1200 first, then crop 60 px from top and bottom to reach 1080.
    pattern = str(frame_dir / "frame_%05d.png")
    cmd = [
        "ffmpeg",
        "-y",
        "-framerate",
        str(fps),
        "-i",
        pattern,
        "-f",
        "lavfi",
        "-i",
        "anullsrc",
        "-vf",
        "scale=1920:1200:flags=lanczos,crop=1920:1080:0:60",
        "-r",
        "30",  # output at 30 fps (App Store minimum); frames are duped
        "-c:v",
        "libx264",
        "-preset",
        "slow",
        "-crf",
        "18",
        "-c:a",
        "aac",
        "-pix_fmt",
        "yuv420p",
        "-movflags",
        "+faststart",
        "-shortest",  # stop audio when video stream ends
        str(out_path),
    ]
    result = subprocess.run(cmd, capture_output=True, text=True)
    if result.returncode != 0:
        print("  ffmpeg error:", result.stderr[-400:])
    else:
        size_mb = out_path.stat().st_size / 1_048_576
        dur = len(sorted(frame_dir.glob("frame_*.png"))) / fps
        print(f"  MP4: {out_path.name}  ({size_mb:.1f} MB, {dur:.1f} s)")


# ---------------------------------------------------------------------------
# Automation helpers
# ---------------------------------------------------------------------------

frame_idx = 0


def _snap(label: str = "", title: str = "GEDCOM"):
    """Capture a numbered video frame (always from the main GEDCOM window)."""
    global frame_idx
    path = FRAMES_DIR / f"frame_{frame_idx:05d}.png"
    if label:
        print(f"    frame {frame_idx:04d}: {label}")
    _capture(title, path)
    frame_idx += 1


def _screenshot(out_path: Path, title: str = "GEDCOM"):
    """Save a named screenshot."""
    _capture(title, out_path)
    print(f"  Saved: {out_path.name}")


def _snaps(n: int, label: str = "", pause: float = 0.5, title: str = "GEDCOM"):
    """Capture *n* frames with *pause* seconds between them."""
    for _ in range(n):
        _snap(label, title)
        time.sleep(pause)


def _wait_tree_populated(app, timeout: float = 30.0) -> bool:
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        count = _ui(lambda: len(app.tree.get_children()))
        if count > 0:
            return True
        time.sleep(0.4)
    return False


def _wait_not_busy(app, timeout: float = 60.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if not _ui(lambda: getattr(app, "_busy", False)):
            return
        time.sleep(0.2)


def _best_path_to(app, start_id, target_id):
    """
    Return the best (shortest) relationship path from *start_id* to *target_id*
    as a list of (id, edge) tuples, or None if unreachable.  Uses the same
    model search the GUI's paths mode runs, with the GUI's configured limits.
    """
    top_n, max_depth = _ui(
        lambda: (int(app.top_n.get()), int(app.max_depth.get()))
    )
    paths, _truncated = app._model.find_all_paths(
        start_id, target_id, top_n, max_depth
    )
    return list(paths[0]) if paths else None


def _open_tree_view(app, indi_id, mode) -> bool:
    """
    Open a tree window centred on *indi_id* in the given *mode*:
      "tree"       – family tree (parents, siblings, spouses, children)
      "pedigree"   – ancestor (pedigree) chart
      "descendant" – descendant chart

    Reuses the existing secondary window if one is already open (e.g. the
    relationship graph, or a previously opened tree view), replacing its
    contents — this is the same window the app reuses for all detail views.
    """
    if mode == "tree":
        # initial_view="tree" resolves to the user's configured default tree
        # mode, which could be pedigree or descendant.  Force the family-tree
        # view so the window title is reliably "Family Tree: …" (the capture
        # key).  The pedigree/descendant modes are passed through directly and
        # are unaffected by this setting.
        app._default_tree_view_mode = lambda: "tree"

    _ui(lambda: app._show_person_for(indi_id, initial_view=mode))

    # Wait for the secondary window to become visible.
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        win = getattr(app, "_secondary_win", None)
        if win is not None:
            try:
                if _ui(lambda: win.winfo_viewable()):
                    break
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        time.sleep(0.3)

    # Allow the tree to render and potentially auto-maximise.
    time.sleep(1.5)
    return getattr(app, "_secondary_win", None) is not None


def _capture_tree_view(
    app, indi_id, mode, out_name, expand_all=False, zoom=None, fit=False
) -> None:
    """Open a tree *mode* for *indi_id*, size it for Retina, and screenshot.

    expand_all – fully expand a descendant tree (every generation) first.
    zoom       – zoom factor applied after expansion (clamped 0.5–2.5 by the
                 app); use a small value to frame a large, sprawling tree.
    fit        – after the final resize, zoom so the whole tree fits the
                 viewport and center it.  The default family tree already
                 carries a full ring of relatives (parents, siblings, spouses,
                 children), so fitting shows them all at once rather than the
                 zoomed-in default framing that clipped the outer nodes.
    """
    title_key = TREE_TITLES[mode]
    _open_tree_view(app, indi_id, mode)

    if expand_all:
        hook = getattr(app, "_expand_open_descendant_tree", None)
        if hook is not None:
            _ui(hook)
            time.sleep(2.0)  # let the much larger canvas finish rendering
        else:
            print("  WARNING: expand-all hook unavailable – tree not expanded.")

    if zoom is not None:
        set_zoom = getattr(app, "_set_open_tree_zoom", None)
        if set_zoom is not None:
            _ui(lambda: set_zoom(zoom))
            time.sleep(1.0)

    # Resize to 1280×772 so the Retina capture is exactly 2560×1600.  This also
    # reins in any auto-maximise the render may have triggered for a large tree.
    tree_win = getattr(app, "_secondary_win", None)
    if tree_win is not None:
        try:
            if _ui(lambda: tree_win.winfo_exists()):
                _ui(
                    lambda: tree_win.geometry(
                        f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y + 60}"
                    )
                )
                time.sleep(0.8)
        except Exception:  # pylint: disable=broad-exception-caught
            pass

    # Fit the (now larger) family tree into the final viewport and center it.
    # Must run after the resize so it measures the real capture size.
    if fit:
        fit_tree = getattr(app, "_fit_open_tree", None)
        if fit_tree is not None:
            _ui(fit_tree)
            time.sleep(0.6)
        else:
            print("  WARNING: family-tree fit hook unavailable.")

    # For a fully expanded (large) descendant tree, frame the root at the top
    # so the generations cascade downward in view.  Must run after the final
    # resize, since the scroll position depends on the viewport size.
    if expand_all:
        frame = getattr(app, "_frame_open_descendant_top", None)
        if frame is not None:
            _ui(frame)
            time.sleep(0.6)

    # Video frames come from the main window (always 1280×772) so every frame
    # fed to ffmpeg is the same size; the tree window is captured only for its
    # dedicated screenshot.
    _snaps(5, f"{mode} tree view", pause=0.4)
    _screenshot(OUTPUT_DIR / out_name, title=title_key)


# ---------------------------------------------------------------------------
# Automation worker thread
# ---------------------------------------------------------------------------


def automation(app, done_event: threading.Event, selected=None):
    """Screenshot automation — runs in the worker thread.

    *selected* – optional set of screenshot keys (see SCREENSHOT_KEYS) to
    regenerate.  When None, the full pipeline runs (every screenshot plus the
    GIF/MP4 video assets).  When a subset is given, the mandatory setup (GEDCOM
    load, home person, Maya selection) still runs, then only the requested
    screenshots are captured; the video assets are skipped because they need
    the complete frame sequence.
    """

    def want(name: str) -> bool:
        return selected is None or name in selected

    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        for f in FRAMES_DIR.glob("frame_*.png"):
            f.unlink()

        # ---------------------------------------------------------------
        # 1. Wait for fictional_genealogy.ged to load
        # ---------------------------------------------------------------
        print("\n[1/9] Waiting for GEDCOM to load …")

        _snaps(5, "loading", pause=0.8)

        ok = _wait_tree_populated(app, timeout=40)
        if not ok:
            print("  WARNING: tree empty after 40 s — aborting.")
            return

        time.sleep(1.0)
        n_people = _ui(lambda: len(app.tree.get_children()))
        print(f"  Loaded: {n_people} people in tree")

        # ---------------------------------------------------------------
        # 2. Set home person (@I6@ Arthur Hart) + select Maya (@I1@)
        # ---------------------------------------------------------------
        print("\n[2/9] Setting home person and selecting Maya Hart …")

        def _setup():
            # Set Arthur Hart (@I6@, Maya's paternal grandfather) as home.
            # The DNA results will show a 2-hop "path to home":
            # Maya Lynn Hart → Daniel Joseph Hart → Arthur Miles Hart.
            app._home_person_id = HOME_PERSON_ID
            app._clear_home_path_cache()
            app._save_home_person(GEDCOM_FILE, HOME_PERSON_ID)
            # Select Maya (@I1@) in the main tree.
            target = "@I1@" if app.tree.exists("@I1@") else app.tree.get_children()[0]
            app.tree.selection_set(target)
            app.tree.see(target)
            app.tree.focus(target)
            return target, app.tree.item(target)["values"][0]

        sel_id, sel_name = _ui(_setup)
        print(f"  Home person: {HOME_PERSON_ID} (Arthur Miles Hart)")
        print(f"  Selected:    {sel_id} = {sel_name}")

        # Wait for the profile view to compute the home-path asynchronously.
        time.sleep(2.5)

        _snaps(20, "main window loaded", pause=0.4)
        if want("main"):
            _screenshot(OUTPUT_DIR / "screenshot_01_main.png")

        if want("matches"):
            # -----------------------------------------------------------
            # 3. Run DNA match search for Maya
            # -----------------------------------------------------------
            print("\n[3/9] Running DNA match search …")
            _ui(
                lambda: (
                    app.tree.selection_set(sel_id),
                    setattr(app, "_active_id", sel_id),
                )
            )
            _ui(app._find_matches)

            _snaps(6, "searching", pause=0.6)
            _wait_not_busy(app, timeout=60)
            time.sleep(0.4)

            # -----------------------------------------------------------
            # 4. Screenshot DNA results — scroll to show path-to-home section
            # -----------------------------------------------------------
            print("\n[4/9] Screenshot – DNA results with path to home person …")
            _snaps(25, "results", pause=0.4)

            # Scroll the results panel to the bottom so the "Path to Home
            # Person" section (showing Maya → Daniel → Arthur) is visible.
            def _scroll_results_bottom():
                try:
                    app.results.yview_moveto(1.0)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            _ui(_scroll_results_bottom)
            time.sleep(0.5)
            _screenshot(OUTPUT_DIR / "screenshot_02_matches.png")

        # ---------------------------------------------------------------
        # 5. Paths mode: Maya → Brianna Logan Vaughn (second cousin-in-law)
        # ---------------------------------------------------------------
        # The path/relationship are reused by both the paths screenshot and the
        # relationship-graph screenshot, so compute them whenever either is
        # requested.
        _paths_path = None
        _paths_rel = "relationship"
        if want("paths") or want("graph"):
            # Compute the path up front so the relationship-graph screenshot in
            # step 6 can reuse it — running the path search overwrites
            # app._last_result with type='path' and no path list.
            _paths_path = _best_path_to(app, START_PERSON_ID, PATHS_TARGET_ID)
            _paths_rel = (
                _relationship_for_path(app, START_PERSON_ID, _paths_path)
                if _paths_path
                else "relationship"
            )

        if want("paths"):
            print(
                "\n[5/9] Screenshot – paths mode (Maya → Brianna Logan Vaughn) …"
            )
            if _paths_path:
                _ui(lambda: app._run_path_search(START_PERSON_ID, PATHS_TARGET_ID))
                _wait_not_busy(app, timeout=30)
                time.sleep(0.5)
                _snaps(8, "paths mode", pause=0.4)
                _screenshot(OUTPUT_DIR / "screenshot_03_paths.png")
            else:
                print(
                    f"  No path {START_PERSON_ID} → {PATHS_TARGET_ID} – skipping."
                )

        # ---------------------------------------------------------------
        # 6. Relationship graph for the Maya → Brianna path
        # ---------------------------------------------------------------
        if want("graph"):
            print(
                "\n[6/9] Opening relationship graph (Maya → Brianna Logan Vaughn) …"
            )
            if _paths_path:
                _ui(lambda: app._show_path_graph(_paths_path, _paths_rel))
                print(f"  Graph opened ({_paths_rel}).")
            else:
                print("  No graph data – skipping.")

            time.sleep(1.2)

            # Position graph window offset from the main window.
            graph_win = getattr(app, "_path_graph_win", None) or getattr(
                app, "_secondary_win", None
            )
            if graph_win is not None:
                try:
                    if _ui(lambda: graph_win.winfo_exists()):
                        _ui(
                            lambda: graph_win.geometry(
                                f"+{WIN_X + 160}+{WIN_Y + 80}"
                            )
                        )
                        time.sleep(0.5)
                except Exception:  # pylint: disable=broad-exception-caught
                    pass

            _snaps(30, "graph open", pause=0.4)
            _screenshot(OUTPUT_DIR / "screenshot_04_with_graph.png")

            # Graph-only screenshot — resize to 1280×772 for 2560×1600 Retina.
            graph_win = getattr(app, "_path_graph_win", None) or getattr(
                app, "_secondary_win", None
            )
            if graph_win is not None:
                try:
                    if _ui(lambda: graph_win.winfo_exists()):
                        _ui(
                            lambda: graph_win.geometry(
                                f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X + 160}+{WIN_Y + 80}"
                            )
                        )
                        time.sleep(0.6)
                        # With images enabled the nodes are tall enough that a
                        # multi-row path overflows the fixed 1280×772 window and
                        # the bottom rows clip.  Shrink the graph to fit the (now
                        # final) viewport so the whole relationship path is
                        # visible while the captured asset stays exactly
                        # 2560×1600.
                        fit_graph = getattr(app, "_fit_open_graph", None)
                        if fit_graph is not None:
                            _ui(fit_graph)
                            time.sleep(0.5)
                        else:
                            print("  WARNING: graph fit hook unavailable.")
                except Exception:  # pylint: disable=broad-exception-caught
                    pass
            _screenshot(
                OUTPUT_DIR / "screenshot_04_graph_only.png", title="Relationship Gr"
            )

        # ---------------------------------------------------------------
        # 7. Family tree view: Daniel Hart — 19 relatives around the centre
        # ---------------------------------------------------------------
        if want("tree"):
            print("\n[7/9] Opening family tree view (Daniel Hart, 19 relatives) …")
            _capture_tree_view(
                app, TREE_PERSON_ID, "tree", "screenshot_05_tree.png", fit=True
            )

        # ---------------------------------------------------------------
        # 8. Pedigree (ancestor) tree: Maya Hart — 8 ancestors, 3 generations
        # ---------------------------------------------------------------
        if want("pedigree"):
            print("\n[8/9] Opening pedigree tree (Maya Hart, 8 ancestors) …")
            _capture_tree_view(
                app,
                PEDIGREE_PERSON_ID,
                "pedigree",
                "screenshot_06_pedigree.png",
                fit=True,
            )

        # ---------------------------------------------------------------
        # 9. Descendant tree: Arthur Hart — 148 descendants, 3 generations
        # ---------------------------------------------------------------
        if want("descendant"):
            print(
                "\n[9/9] Opening descendant tree (Arthur Hart, 148 descendants) …"
            )
            _capture_tree_view(
                app,
                DESCENDANT_PERSON_ID,
                "descendant",
                "screenshot_07_descendant.png",
                expand_all=True,
                zoom=0.5,
            )

        # ---------------------------------------------------------------
        # Compile video assets — only for a full run; a selective run does not
        # capture the complete frame sequence the GIF/MP4 require.
        # ---------------------------------------------------------------
        import shutil

        if selected is None:
            total = frame_idx
            print(f"\nCompiling video assets ({total} frames) …")
            build_gif(FRAMES_DIR, OUTPUT_DIR / "screen_recording.gif", fps=5)
            build_mp4(FRAMES_DIR, OUTPUT_DIR / "app_preview.mp4", fps=5)
        else:
            print("\nSelective run — skipping GIF/MP4 video compilation.")

        shutil.rmtree(FRAMES_DIR, ignore_errors=True)

        print(f"\nAll assets written to: {OUTPUT_DIR}")
        for p in sorted(OUTPUT_DIR.iterdir()):
            if p.is_file():
                mb = p.stat().st_size / 1_048_576
                print(f"  {p.name:<50} {mb:6.1f} MB")

    except Exception:  # pylint: disable=broad-exception-caught
        import traceback

        traceback.print_exc()
    finally:
        done_event.set()
        _root_ref.after(0, _root_ref.quit)


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


def _parse_args(argv):
    """Parse command-line arguments.

    With no arguments the full pipeline runs (all screenshots + video).  Pass
    `--only KEY [KEY ...]` to regenerate just those screenshots; see
    SCREENSHOT_KEYS for the valid keys.
    """
    import argparse  # noqa: PLC0415

    parser = argparse.ArgumentParser(
        description=(
            "Generate Mac App Store screenshots and preview video.  With no "
            "options the full pipeline runs; use --only to regenerate a subset."
        ),
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=(
            "screenshot keys (for --only):\n"
            "  main        screenshot_01_main.png\n"
            "  matches     screenshot_02_matches.png\n"
            "  paths       screenshot_03_paths.png\n"
            "  graph       screenshot_04_with_graph.png + screenshot_04_graph_only.png\n"
            "  tree        screenshot_05_tree.png\n"
            "  pedigree    screenshot_06_pedigree.png\n"
            "  descendant  screenshot_07_descendant.png\n"
            "\n"
            "examples:\n"
            "  python dev/generate-appstore-assets.py\n"
            "  python dev/generate-appstore-assets.py --only pedigree\n"
            "  python dev/generate-appstore-assets.py --only tree pedigree descendant"
        ),
    )
    parser.add_argument(
        "--only",
        nargs="+",
        choices=SCREENSHOT_KEYS,
        metavar="KEY",
        help=(
            "regenerate only these screenshot(s); video assets are skipped. "
            "choices: " + ", ".join(SCREENSHOT_KEYS)
        ),
    )
    return parser.parse_args(argv)


def main(argv=None):
    global _root_ref

    args = _parse_args(sys.argv[1:] if argv is None else argv)
    selected = set(args.only) if args.only else None
    if selected is not None:
        print(f"Selective regeneration: {', '.join(sorted(selected))}")

    import customtkinter as ctk  # noqa: PLC0415
    import tkinter as tk
    from gedcom_navigator_gui import GedcomNavigatorApp  # noqa: PLC0415

    # Force light mode so screenshots are never rendered in dark mode,
    # regardless of the user's system preference or saved settings.
    ctk.set_appearance_mode("light")

    _init_capturer()

    root = tk.Tk()
    _root_ref = root
    root.geometry(f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y}")

    app = GedcomNavigatorApp(root)
    # Prevent the app from overriding the forced light mode with a saved dark theme.
    app._theme_pref = "Light"
    app._apply_theme("Light")

    # Redirect the auto-load to use our fictional sample.
    # Must happen before root.mainloop() fires the queued callback.
    app.gedcom_path.set(GEDCOM_FILE)
    app._recent_files = []

    # Explicitly trigger the load.  The app only auto-loads when the user has a
    # recent file on disk, so we cannot rely on that callback being queued.
    root.after(0, app._load_file)

    root.geometry(f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y}")
    root.deiconify()

    done = threading.Event()
    t = threading.Thread(
        target=automation, args=(app, done, selected), daemon=True
    )
    t.start()

    root.mainloop()
    t.join(timeout=5)
    print("Done.")


if __name__ == "__main__":
    main()
