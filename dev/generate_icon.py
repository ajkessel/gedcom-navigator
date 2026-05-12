#!/usr/bin/env python3
"""
generate_icon.py

Generate a Windows icon file from a PNG image.
"""
from PIL import Image
from sys import argv
from pathlib import Path
p = Path(argv[1])
img = Image.open(p)
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img.save(p.with_suffix(".ico"), sizes=icon_sizes)
