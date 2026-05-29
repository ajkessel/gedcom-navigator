#!/usr/bin/env python3
"""
generate_icon.py

Generate a Windows icon file from a PNG image.
"""
from PIL import Image
from sys import argv
from pathlib import Path
import io
try:
    # Windows PIP fails to pull the cairo DLLs (C libraries), so this import may fail
    # fallback is to generate directly from the png
    # To install DLLs, install either GTK Runtime Environment or cairo from conda-forge
    import cairosvg
    svg = True
except:
    print("cairosvg library not found, skipping icon generation from scratch")
    svg = False

input_file = Path(argv[1])
output_file = input_file.with_suffix('.ico')
icon_sizes = [(16, 16), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
img_list = []

if input_file.stat().st_mtime <= output_file.stat().st_mtime:
    print("Newer icon file already exists. Skipping generation.")
    exit()

if str(input_file).lower().endswith('.svg'):
    if svg:
        png_file = input_file.with_suffix('.png')
        cairosvg.svg2png(url=str(input_file), write_to=str(png_file))
        for size in icon_sizes:
            png_data = cairosvg.svg2png(url=str(input_file), output_width=size[0], output_height=size[1])
            img = Image.open(io.BytesIO(png_data))
            img_list.append(img)
        img_list[0].save(output_file, format='ICO', append_images=img_list[1:], sizes=icon_sizes)
        exit()
    else:
        input_file = Path(argv[1].with_suffix('.png'))

try:
    img = Image.open(input_file)
    img.save(output_file, sizes=icon_sizes)
except Exception as e:
    print(f"Icon generation from PNG file failed: {e}")
