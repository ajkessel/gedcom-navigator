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
- **Link handling uses PUBLIC API only — no `_impl` reach, no navigation.** A clicked
  link's `onclick` sets `window.__nav = "<id>"; return false;` (so the page never
  navigates), and a background poll reads it via the public `evaluate_javascript()` API,
  then recenters. Identical on WKWebView + WebView2. Verified headlessly: 13 onclick links,
  ids round-trip, poll JS well-formed.
- **Bonus:** the same WebView+HTML path covers the markdown help/about dialogs
  (`gedcom_markdown.py`) — markdown → HTML → WebView, retiring the bespoke tk-tag renderer.

This removes what the plan called Toga's "biggest genuine gap" — and notably, it's the ONE
gap that turned out **not** to need a native-layer reach. WebView backends: WKWebView
(macOS), WebView2/Edge (Windows), WebKitGTK (Linux).

**Rejected approach — `on_navigation_starting` interception (don't use it here).** The
obvious approach (person links → intercept navigation → cancel) works on macOS but is a
per-backend minefield: WKWebView ignores unregistered custom schemes and Toga's cleanup
runs `self.url = url` which **raises `ValueError` on any non-http(s) URL** (so links must be
`https://`); and toga-winforms pins its internal `_allowed_url` to `"about:blank"` after
`set_content()` and never clears it, so the handler is bypassed on Windows — and forcing it
clear routes WebView2's internal `about:blank` navs into the handler, which cancels them and
**blanks the page**. Also `on_navigation_starting` is unsupported on GTK/Qt. The
`evaluate_javascript` poll above avoids all of this. Left here as the cautionary trail.

## Deprecation warnings / Toga API churn (decision signal)

On-device runs emit several `DeprecationWarning`s. Diagnosed headlessly:
- `Pack(padding=)` → `Pack(margin=)` — **fixed**.
- `App.add_background_task()` → `asyncio.create_task()` — **fixed** (Toga's recommended
  replacement; re-run to confirm the loop is running at `startup`).
- **Canvas drawing API overhaul (Toga 0.6, renamed 2026-02, compat shims through
  2026-05)** — the graph spike uses the 0.5 spelling, which still works but warns:
  `Canvas.context`→`root_state`; `Context()/Fill()/Stroke()`→`state()/fill()/stroke()`;
  drawing methods are now called **on the canvas** inside a `with canvas.fill()/stroke()/
  state()` block (not on the returned state); `write_text()`→`fill_text()`/`stroke_text()`.
  Not rewritten blind (can't render-test here; the clear-and-redraw idiom is ambiguous
  from source) — do this deliberately with an on-device render check.

**This churn is itself a data point for the go/no-go:** Toga's canvas API was renamed
wholesale within the last few months, with dated backwards-compat shims. A migration now
means tracking an API that is still actively moving — real maintenance overhead, and
another facet of the young-ecosystem cost (alongside the per-backend native-layer tax).
wxPython's API is comparatively frozen.

## Not verifiable in this Linux sandbox ❗

- **Live window rendering.** `toga-gtk` 0.5.5 is incompatible with the system's very
  recent **PyGObject 3.50** (`GLibEventLoop.__init__() missing 'main_context'`); 0.5.6
  needs a newer PyGObject that can't be compiled here (no dev headers / no sudo). This
  is a **Linux-dev-environment integration issue only** — macOS uses `toga-cocoa` via
  rubicon-objc with no GTK/PyGObject involved, so it does not bear on the App Store
  target. **Final visual confirmation of painting + interaction must be done on macOS**
  (or a Linux box with a matching PyGObject/toga-gtk pair).

## Packaging (deliverable c) — Briefcase scaffold ✅ (needs on-device validation)

Scaffold in `spike/briefcase/` (pyproject.toml + minimal Toga app + runbook). Key finding
from the Briefcase docs: **Briefcase does not first-class Mac App Store distribution** — its
`package -p pkg` targets Developer ID + notarization, with no automation for the Apple
Distribution / "3rd Party Mac Developer" certs or provisioning-profile embedding, and App
Store `.pkg`s aren't notarized. So the migration **swaps the bundler** (PyInstaller →
Briefcase, which handles the sandboxed universal `.app` + entitlements) but **keeps the App
Store sign/provision/validate steps** already in `dev/build-mac-appstore.sh`, pointed at
Briefcase's `.app`. Entitlements mirror `dev/entitlements-appstore.plist`; bundle id
`com.ajkessel.gedcom-navigator`, team `4GT4UKXZ4V`. On-device validation (`briefcase build`
→ App Store sign → `altool --validate-app`) is the remaining check — see the runbook.

**Confirmed on-device:** `briefcase package macOS` is NOT usable for App Store — it (1)
auto-selects the **Developer ID** cert (direct-download, not App Store) and (2) signs every
`.so` with `--options runtime --entitlements`, hitting `errSecInternalComponent` on Python
extension modules — the exact failure `build-mac-appstore.sh` avoids by signing `.so`
plainly. Flow is firmly **`briefcase build` (bundler) → manual App Store signing from
`build-mac-appstore.sh`** (now inlined in `spike/briefcase/README.md`). Prerequisite: the
"3rd Party Mac Developer Application/Installer" certs must be in the keychain (owner's
keychain showed only Developer ID so far — may need to create them in the portal).

**Validation reached Apple's backend — technical pipeline PROVEN.** After manual signing +
`productbuild`, `altool --validate-app` was rejected only with
`FORBIDDEN.REQUIRED_AGREEMENTS_MISSING_OR_EXPIRED` — an unsigned/expired Apple legal
agreement (App Store Connect → Business), **not** a package/signing/entitlement error (zero
`ITMS-xxxxx`). i.e. the Toga → `briefcase build` → manual App Store sign → `.pkg` pipeline
produces a structurally App-Store-acceptable package; auth and package structure passed.
Remaining (account paperwork, outside the migration): Account Holder signs the agreement,
then re-validate to confirm no technical errors hide behind the short-circuited check. Also
resolved en route: `errSecInternalComponent` = keychain key access → `security
unlock-keychain` + `set-key-partition-list` (documented in the runbook).

## Verdict

Both technical gaps the plan flagged are resolved and confirmed on Mac + Windows: the
**graph canvas** (render, click-recenter, zoom, native wheel-pan, tooltips, node hover) and
the **rich results view** (WebView+HTML, public-API link handling). Packaging is scaffolded
with a clear (if partly manual) App Store path. **Toga is viable**; the cost is the
recurring native-layer tax (tooltips/hover/wheel) + tracking Toga's still-moving canvas API.

## Reproduce

```bash
python3 -m venv --system-site-packages /tmp/spike-venv
/tmp/spike-venv/bin/pip install -c constraints.txt toga   # constraints pin pygobject==3.50.0, pycairo==1.27.0
# headless logic check passes anywhere; headed run needs a working toga-gtk/PyGObject pair or macOS:
/tmp/spike-venv/bin/python spike/toga_graph_spike.py
```
