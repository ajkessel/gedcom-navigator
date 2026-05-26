#!/usr/bin/env python3
"""
Generate Mac App Store screenshots and animated preview assets.

Run from the project root:
    python scripts/generate-appstore-assets.py

Produces in docs/screenshots/appstore/:
  screenshot_01_main.png          – person list, Maya selected, path-to-home visible
  screenshot_02_matches.png       – DNA match results + path to home person
  screenshot_03_paths.png         – paths mode: Maya → Julia Gray Hollis (8 hops)
  screenshot_04_with_graph.png    – main + complex relationship graph
  screenshot_04_graph_only.png    – relationship graph alone (2560×1600)
  screenshot_05_tree.png          – family tree view, Daniel Hart (2560×1600)
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
WIN_CONTENT_H = 772   # +28 px title bar → 800 px total
WIN_X, WIN_Y = 60, 60

# Home person for the DNA results demo: Maya's paternal grandfather.
# Sets up a 2-hop "path to home" (Maya → Daniel → Arthur) visible in results.
HOME_PERSON_ID = "@I6@"

# ---------------------------------------------------------------------------
# AppKit capture — via performSelectorOnMainThread to bypass Tkinter's
# callback dispatch (which causes a GIL crash in Python 3.13 + PyObjC 12.1)
# ---------------------------------------------------------------------------
import AppKit  # noqa: E402  (pyobjc-framework-Cocoa)
import objc    # noqa: E402
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
            AppKit.NSBitmapImageFileTypePNG, None)
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
_root_ref = None   # set before mainloop starts


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
    images[0].save(out_path, save_all=True, append_images=images[1:],
                   loop=0, duration=duration, optimize=True)
    size_mb = out_path.stat().st_size / 1_048_576
    print(f"  GIF: {out_path.name}  ({len(images)} frames @ {fps} fps, {size_mb:.1f} MB)")


def build_mp4(frame_dir: Path, out_path: Path, fps: int = 5):
    pattern = str(frame_dir / "frame_%05d.png")
    cmd = [
        "ffmpeg", "-y",
        "-framerate", str(fps),
        "-i", pattern,
        "-vf", f"scale={WIN_W}:800:flags=lanczos",
        "-c:v", "libx264", "-preset", "slow", "-crf", "18",
        "-pix_fmt", "yuv420p",
        "-movflags", "+faststart",
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


def _run_paths_for_complex_target(app) -> bool:
    """
    Switch to paths mode and find all routes from Maya (@I1@) to the most
    distant DNA match (Julia Gray Hollis @I810@, 8 hops through 5 generations).
    The results render in the main window's right panel — no secondary window.
    """
    last = getattr(app, "_last_result", None)
    if not last:
        return False
    results = last.get("results", [])
    if not results:
        return False
    _dist, path = results[-1]
    if not path:
        return False
    # path is a list of (id, edge) tuples; last element is the target
    target_id = path[-1][0] if isinstance(path[-1], tuple) else path[-1]
    _ui(lambda: app._run_path_search("@I1@", target_id))
    return True


def _open_graph_for_best_result(app) -> bool:
    """
    Open the relationship graph for the MOST COMPLEX DNA match result
    (longest path = most generations traversed, most visually interesting).
    """
    last = getattr(app, "_last_result", None)
    if not last:
        return False
    results = last.get("results", [])
    if not results:
        return False
    # Use the most distant match (last in the sorted list) for the most
    # complex multi-generation path.
    _dist, path = results[-1]
    path = list(path)
    if not path:
        return False
    try:
        from gedcom_relationship import describe_relationship  # noqa: PLC0415
        rel = describe_relationship(path, app.individuals, app.families)
    except Exception:  # pylint: disable=broad-exception-caught
        rel = "relationship"
    _ui(lambda: app._show_path_graph(path, rel))
    return True


def _open_tree_view(app) -> bool:
    """
    Open the family tree view centred on @I2@ (Daniel Joseph Hart) —
    the person with the most visible connections (20 nodes):
    2 parents, 5 siblings, 2 spouses, 10 children.
    """
    # If the graph window is currently open (in _secondary_win), opening the
    # tree view reuses that same window and replaces the graph content.
    _ui(lambda: app._show_person_for("@I2@", initial_view="tree"))

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


# ---------------------------------------------------------------------------
# Automation worker thread
# ---------------------------------------------------------------------------

def automation(app, done_event: threading.Event):
    """Screenshot automation — runs in the worker thread."""
    try:
        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        FRAMES_DIR.mkdir(parents=True, exist_ok=True)
        for f in FRAMES_DIR.glob("frame_*.png"):
            f.unlink()

        # ---------------------------------------------------------------
        # 1. Wait for fictional_genealogy.ged to load
        # ---------------------------------------------------------------
        print("\n[1/7] Waiting for GEDCOM to load …")

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
        print("\n[2/7] Setting home person and selecting Maya Hart …")

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
        _screenshot(OUTPUT_DIR / "screenshot_01_main.png")

        # ---------------------------------------------------------------
        # 3. Run DNA match search for Maya
        # ---------------------------------------------------------------
        print("\n[3/7] Running DNA match search …")
        _ui(lambda: (app.tree.selection_set(sel_id),
                     setattr(app, "_active_id", sel_id)))
        _ui(app._find_matches)

        _snaps(6, "searching", pause=0.6)
        _wait_not_busy(app, timeout=60)
        time.sleep(0.4)

        # ---------------------------------------------------------------
        # 4. Screenshot DNA results — scroll to show path-to-home section
        # ---------------------------------------------------------------
        print("\n[4/7] Screenshot – DNA results with path to home person …")
        _snaps(25, "results", pause=0.4)

        # Scroll the results panel to the bottom so the "Path to Home Person"
        # section (showing Maya → Daniel → Arthur) is visible.
        def _scroll_results_bottom():
            try:
                app.results.yview_moveto(1.0)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        _ui(_scroll_results_bottom)
        time.sleep(0.5)
        _screenshot(OUTPUT_DIR / "screenshot_02_matches.png")

        # ---------------------------------------------------------------
        # 5. Paths mode: Maya → Julia Gray Hollis (8 hops, 5 generations)
        # ---------------------------------------------------------------
        print("\n[5/7] Screenshot – paths mode (Maya to most distant match) …")

        # Cache the best DNA path BEFORE running paths mode, because
        # _run_paths_for_complex_target calls _run_path_search which
        # overwrites app._last_result with type='path' (no 'results' key).
        _cached_dna_path = None
        _cached_dna_rel = "relationship"
        last = getattr(app, "_last_result", None)
        if last and last.get("results"):
            _dist, _raw_path = last["results"][-1]
            _cached_dna_path = list(_raw_path)
            try:
                from gedcom_relationship import describe_relationship  # noqa: PLC0415
                _cached_dna_rel = describe_relationship(
                    _cached_dna_path, app.individuals, app.families)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        ok = _run_paths_for_complex_target(app)
        if ok:
            _wait_not_busy(app, timeout=30)
            time.sleep(0.5)
            _snaps(8, "paths mode", pause=0.4)
            _screenshot(OUTPUT_DIR / "screenshot_03_paths.png")
        else:
            print("  No paths data – skipping.")

        # ---------------------------------------------------------------
        # 6. Open relationship graph for the most complex match
        # ---------------------------------------------------------------
        print("\n[6/7] Opening relationship graph (most complex path) …")
        if _cached_dna_path:
            _ui(lambda: app._show_path_graph(_cached_dna_path, _cached_dna_rel))
            opened = True
        else:
            opened = _open_graph_for_best_result(app)
        if opened:
            print("  Graph opened (longest relationship path).")
        else:
            print("  No graph data – skipping.")

        time.sleep(1.2)

        # Position graph window offset from the main window.
        graph_win = getattr(app, "_path_graph_win", None) or \
                    getattr(app, "_secondary_win", None)
        if graph_win is not None:
            try:
                if _ui(lambda: graph_win.winfo_exists()):
                    _ui(lambda: graph_win.geometry(
                        f"+{WIN_X + 160}+{WIN_Y + 80}"))
                    time.sleep(0.5)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        _snaps(30, "graph open", pause=0.4)
        _screenshot(OUTPUT_DIR / "screenshot_04_with_graph.png")

        # Graph-only screenshot — resize to 1280×772 for 2560×1600 Retina.
        graph_win = (getattr(app, "_path_graph_win", None) or
                     getattr(app, "_secondary_win", None))
        if graph_win is not None:
            try:
                if _ui(lambda: graph_win.winfo_exists()):
                    _ui(lambda: graph_win.geometry(
                        f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X + 160}+{WIN_Y + 80}"))
                    time.sleep(0.6)
            except Exception:  # pylint: disable=broad-exception-caught
                pass
        _screenshot(OUTPUT_DIR / "screenshot_04_graph_only.png",
                    title="Relationship Gr")

        # ---------------------------------------------------------------
        # 7. Family tree view: Daniel Hart — 20 nodes
        # ---------------------------------------------------------------
        print("\n[7/7] Opening family tree view (Daniel Hart, 20 nodes) …")
        _open_tree_view(app)

        # Resize to 1280×772 so the Retina capture is exactly 2560×1600.
        tree_win = getattr(app, "_secondary_win", None)
        if tree_win is not None:
            try:
                if _ui(lambda: tree_win.winfo_exists()):
                    _ui(lambda: tree_win.geometry(
                        f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y + 60}"))
                    time.sleep(0.8)
            except Exception:  # pylint: disable=broad-exception-caught
                pass

        _snaps(5, "tree view", pause=0.4)
        _screenshot(OUTPUT_DIR / "screenshot_05_tree.png",
                    title="Family Tree")

        # ---------------------------------------------------------------
        # Compile video assets
        # ---------------------------------------------------------------
        total = frame_idx
        print(f"\nCompiling video assets ({total} frames) …")
        build_gif(FRAMES_DIR, OUTPUT_DIR / "screen_recording.gif", fps=5)
        build_mp4(FRAMES_DIR, OUTPUT_DIR / "app_preview.mp4", fps=5)

        import shutil
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

def main():
    global _root_ref

    import tkinter as tk
    from gedcom_navigator_gui import GedcomNavigatorApp  # noqa: PLC0415

    _init_capturer()

    root = tk.Tk()
    _root_ref = root
    root.geometry(f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y}")

    app = GedcomNavigatorApp(root)

    # Redirect the auto-load to use our fictional sample.
    # Must happen before root.mainloop() fires the queued callback.
    app.gedcom_path.set(GEDCOM_FILE)
    app._recent_files = []

    root.geometry(f"{WIN_W}x{WIN_CONTENT_H}+{WIN_X}+{WIN_Y}")
    root.deiconify()

    done = threading.Event()
    t = threading.Thread(target=automation, args=(app, done), daemon=True)
    t.start()

    root.mainloop()
    t.join(timeout=5)
    print("Done.")


if __name__ == "__main__":
    main()
