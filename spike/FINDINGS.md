# Toga migration spike — findings (deliverable (a): canvas graph)

Throwaway spike validating the go/no-go from the migration plan. Code:
`spike/toga_graph_spike.py`. Run in an isolated venv (Toga 0.5.5) — does **not**
touch the project `.venv`.

## Proven ✅

- **The tkinter-free layout engine drives Toga directly.** `build_model` +
  `gedcom_family_tree.build_pedigree_tree_graph` + `layout_pedigree_tree` produce
  `generation`/`column` coordinates that map cleanly to pixel node boxes and edges —
  no changes to the domain/layout code. (13 nodes / 12 edges from the sample tree,
  0 dangling edges, 0 same-column overlaps.)
- **Toga Canvas covers every drawing primitive the tk renderer uses**, and adds two
  things that *simplify* the port:
  - `round_rect`, `rect`, `line_to`/`stroke`, `write_text`/`measure_text`,
    `draw_image`, `line_dash`, `arc`/`ellipse`, `fill_style`/`stroke_style` — 1:1 with
    the tk canvas items.
  - **Native affine transforms** (`translate`/`scale`/`save`/`restore`): zoom & pan are
    a context transform, not the tk app's re-multiply-every-coordinate + full re-layout.
  - `as_image()`: PNG export can use this instead of the ~600-line canvas-introspection
    exporter (`gedcom_graph_export.py`).
- **Hit-testing works and round-trips correctly.** `on_press`/`on_drag`/`on_release`
  deliver `(x, y)`; mapping screen→world through pan/zoom and testing rectangle
  containment returns the right node across zoom {0.5, 1.0, 2.0} × pan offsets.
  Click-to-recenter rebuilds the graph correctly.

## Gaps ⚠️ and workarounds

### Tooltips — Toga has NO tooltip API at all (verified 0.5.5 AND 0.5.6)
No `tooltip` on `Widget` base or any widget. The current app uses tooltips heavily
(~64 hint tooltips on controls across 12 files, 9 canvas-node-tooltip refs, 3 in results).
Two tiers:
- **Control hints (~64): recoverable via native layer.** `add_native_tooltip()` in the
  spike sets `widget._impl.native.toolTip` (Cocoa) / `.set_tooltip_text()` (GTK) — gives
  real OS tooltips (more native than customtkinter's custom-drawn ones). Cost: depends on
  private `_impl.native`, isolated to one helper.
- **Per-node graph hover: the hard one.** The canvas is one native widget with no
  sub-views and Toga has no mouse-move event, so hover-over-node tooltips can't be done
  in pure Toga. Options: degrade to **click-to-select + info panel** (implemented), or
  the native-layer route — **prototyped in `spike/native_canvas_hover.py`**: Cocoa's
  `addToolTipRect:owner:userData:` machinery (macOS) and WinForms `MouseMove` + a
  persistent `ToolTip` (Windows), each reaching into `canvas._impl.native`. NOTE:
  register **one rect per node**, not one canvas-sized rect — Cocoa only re-queries /
  hides at rect boundaries, so a single big rect leaves stale tooltips that never
  dismiss. Verify on-device (macOS: watch for Y-flip). GTK not implemented (`query-tooltip`).
  wxPython has `EVT_MOTION` built in on every platform — no native-layer reach needed.

**Per-backend native-layer tax (the recurring theme):** every tooltip/hover fix is
backend-specific — GTK `set_tooltip_text`, WinForms `ToolTip.SetToolTip` + `MouseMove`,
Cocoa `.toolTip` / `addToolTipRect`. `add_native_tooltip()` now covers all three for
control hints; canvas hover covers macOS + Windows. This 3× per-feature cost across
backends is the clearest argument for wxPython, which provides tooltips, `EVT_MOTION`,
and `EVT_MOUSEWHEEL` uniformly.

### Scroll wheel — native pan works; wheel-zoom doesn't
- **Wheel/trackpad PAN works natively** by wrapping the canvas in a `ScrollContainer`
  (has `on_scroll` + native scrolling) — implemented; the canvas is sized to content×zoom
  and the ScrollContainer pans it. This covers the common "navigate a big tree" case.
- **Wheel-SPIN-to-zoom is not exposed** (no wheel delta/modifier on the canvas). Zoom is
  **Cmd +/−/0 keyboard commands + on-screen buttons** (implemented via `toga.Command`).
  wxPython has `EVT_MOUSEWHEEL` for true wheel-zoom.

Net: core functionality is preservable, but tooltips (especially graph hover) and
wheel-zoom are where Toga's youth shows and where several fixes reach into `_impl.native`.
That accumulating native-layer tax is the central Toga-vs-wxPython tradeoff.

## Rich results view (deliverable b) — WebView + HTML ✅ (logic proven)

The current results pane is inline rich text (bold headers, indentation, clickable
person-name links in flowing paragraphs) via tk.Text `tag_bind` — no native Toga analog.
Solution proven in `spike/toga_richtext_spike.py`:
- Render results as styled **HTML** and load via `WebView.set_content(root_url, html)` —
  full fidelity for bold/indent/color/inline links (better than the tk.Text tags).
- Person names are `<a href="person:ID">`. **`WebView.on_navigation_starting` exists**
  and its docstring is "requesting permission to navigate" → returning **`False` cancels**
  the navigation. So a link click is intercepted, canceled, and handled in-app (recenter),
  exactly replacing the `person_link` tag_bind. Verified headlessly: 13 links generated,
  clicking returns `False` + recenters, real content loads return `True`.
- **Bonus:** the same WebView+HTML path covers the markdown help/about dialogs
  (`gedcom_markdown.py`) — markdown → HTML → WebView, retiring the bespoke tk-tag markdown
  renderer.

This removes what the plan called Toga's "biggest genuine gap." WebView backends:
WKWebView (macOS), WebView2/Edge (Windows), WebKitGTK (Linux).

On-device check needed: confirm `on_navigation_starting` **cancel** actually blocks the
load on WKWebView + WebView2 (the return-False contract). If a backend treats it as
advisory-only, fall back to a custom URL scheme handled at the native webview, or a JS
bridge via `evaluate_javascript` — either is an isolated per-backend reach.

## Not verifiable in this Linux sandbox ❗

- **Live window rendering.** `toga-gtk` 0.5.5 is incompatible with the system's very
  recent **PyGObject 3.50** (`GLibEventLoop.__init__() missing 'main_context'`); 0.5.6
  needs a newer PyGObject that can't be compiled here (no dev headers / no sudo). This
  is a **Linux-dev-environment integration issue only** — macOS uses `toga-cocoa` via
  rubicon-objc with no GTK/PyGObject involved, so it does not bear on the App Store
  target. **Final visual confirmation of painting + interaction must be done on macOS**
  (or a Linux box with a matching PyGObject/toga-gtk pair).

## Still outstanding for the full go/no-go

- (c) Briefcase → signed **Mac App Store `.pkg`** that passes `altool`/Transporter —
  requires the owner's Mac + Apple Developer account. Cannot run in this environment.

## Reproduce

```bash
python3 -m venv --system-site-packages /tmp/spike-venv
/tmp/spike-venv/bin/pip install -c constraints.txt toga   # constraints pin pygobject==3.50.0, pycairo==1.27.0
# headless logic check passes anywhere; headed run needs a working toga-gtk/PyGObject pair or macOS:
/tmp/spike-venv/bin/python spike/toga_graph_spike.py
```
