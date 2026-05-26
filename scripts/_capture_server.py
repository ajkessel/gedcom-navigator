#!/usr/bin/env python3
"""
Capture server — run as a subprocess.
Reads one-line JSON commands from stdin, writes "ok" or "err:<msg>" to stdout.

Protocol:
  request:  {"title": "<fragment>", "path": "<output_path>"}
  response: "ok"  or  "err:<message>"
"""
import json
import sys
from pathlib import Path

import AppKit


def capture(title_fragment: str, out_path: str) -> str:
    ns_app = AppKit.NSApplication.sharedApplication()
    win = None
    for w in ns_app.windows():
        if title_fragment in str(w.title()):
            win = w
            break
    if win is None:
        return f"err:window '{title_fragment}' not found"

    theme_frame = win.contentView().superview()
    bounds = theme_frame.bounds()
    rep = theme_frame.bitmapImageRepForCachingDisplayInRect_(bounds)
    theme_frame.cacheDisplayInRect_toBitmapImageRep_(bounds, rep)
    data = rep.representationUsingType_properties_(
        AppKit.NSBitmapImageFileTypePNG, None)
    p = Path(out_path)
    p.parent.mkdir(parents=True, exist_ok=True)
    data.writeToFile_atomically_(str(p), True)
    return "ok"


def main():
    for raw_line in sys.stdin:
        raw_line = raw_line.strip()
        if not raw_line:
            continue
        try:
            req = json.loads(raw_line)
            result = capture(req["title"], req["path"])
        except Exception as exc:  # pylint: disable=broad-exception-caught
            result = f"err:{exc}"
        print(result, flush=True)


if __name__ == "__main__":
    main()
