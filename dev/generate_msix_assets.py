#!/usr/bin/env python3
"""
generate_msix_assets.py

Generate the various PNG assets required for an MSIX package.
"""
import os
from PIL import Image, ImageOps
from sys import argv
from pathlib import Path

def generate_assets(source_path, output_dir):
    img = Image.open(source_path)
    if img.mode != 'RGBA':
        img = img.convert('RGBA')

    assets = {
        "StoreLogo.png": (50, 50),
        "Square44x44Logo.png": (44, 44),
        "Square150x150Logo.png": (150, 150),
        "Square310x310Logo.png": (310, 310),
        "Wide310x150Logo.png": (310, 150),
        "SplashScreen.png": (620, 300),
    }

    os.makedirs(output_dir, exist_ok=True)

    for name, size in assets.items():
        # For non-square images, we'll pad with transparency
        out_img = Image.new("RGBA", size, (0, 0, 0, 0))
        
        # Calculate aspect ratio preserving size
        ratio = min(size[0] / img.width, size[1] / img.height)
        # Use a bit of padding (80% of target size)
        ratio *= 0.8
        
        new_size = (int(img.width * ratio), int(img.height * ratio))
        resized = img.resize(new_size, Image.Resampling.LANCZOS)
        
        # Center the image
        offset = ((size[0] - resized.width) // 2, (size[1] - resized.height) // 2)
        out_img.paste(resized, offset, resized)
        
        out_img.save(os.path.join(output_dir, name))
        print(f"Generated {name} ({size[0]}x{size[1]})")

if __name__ == "__main__":
    if len(argv) < 3:
        print("Usage: python generate_msix_assets.py <source_png> <output_dir>")
    else:
        generate_assets(argv[1], argv[2])
