# Linux Issues

This page collects Linux-specific notes for running GEDCOM Navigator from
source or from the Linux release archive.

## WSL or X server windows do not appear

If the application starts but no usable window appears under WSL, first verify
that Linux GUI applications work outside GEDCOM Navigator. For example:

```bash
echo "$DISPLAY"
xeyes
```

If simple X11 applications cannot connect to the display, restart WSL or repair
the local X server / WSLg setup before troubleshooting GEDCOM Navigator.

## CustomTkinter font warnings

On Linux, CustomTkinter may print warnings like:

```text
FontManager error: [Errno 30] Read-only file system: '/home/user/.fonts/Roboto-Regular.ttf'
customtkinter.windows.widgets.font warning: Preferred drawing method 'font_shapes' can not be used because the font file could not be loaded.
Using 'circle_shapes' instead. The rendering quality will be bad!
```

This is behavior inside CustomTkinter, not GEDCOM Navigator-specific code.
CustomTkinter 5.2.x loads its bundled Roboto fonts and shape font at import time.
On Linux, its font manager copies those files into `~/.fonts/`, which is a
historical per-user font directory. Some modern Linux systems prefer
`~/.local/share/fonts/`, but CustomTkinter currently uses `~/.fonts/`.

If `~/.fonts/` is missing or not writable, CustomTkinter falls back to a lower
quality drawing mode. The application can still run, but some widgets may look
rougher.

To avoid the warning when running from source, make sure `~/.fonts/` is writable:

```bash
mkdir -p ~/.fonts
chmod u+rwx ~/.fonts
```

Do not run the application with `sudo` just to work around this warning. That
can create root-owned configuration or cache files in your home directory.

For maintainers: this is best fixed upstream in CustomTkinter, ideally by
loading bundled fonts privately or by using an XDG-compliant user font/data
location. A GEDCOM Navigator launcher workaround would only mask the library
behavior.
