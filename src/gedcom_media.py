#!/usr/bin/env python3
"""
gedcom_media.py

Local GEDCOM media resolution and thumbnail helpers for GUI profile images.
"""

import hashlib
import io
import os
from pathlib import Path
import tkinter as tk

try:
    from PIL import Image, ImageDraw, ImageOps, ImageTk
except Exception:  # pylint: disable=broad-exception-caught
    Image = None
    ImageDraw = None
    ImageOps = None
    ImageTk = None


THUMBNAIL_CACHE_VERSION = 2
SUPPORTED_IMAGE_EXTENSIONS = {
    '.bmp', '.gif', '.jpeg', '.jpg', '.png', '.tif', '.tiff', '.webp'
}
NEARBY_MEDIA_DIRS = (
    'media', 'Media', 'photos', 'Photos', 'images', 'Images', 'pictures', 'Pictures'
)


class ProfileMediaService:
    """Resolve local profile media and create Tk thumbnails lazily."""

    def __init__(self, cache_dir):
        self.cache_dir = Path(cache_dir) / 'thumbnails'
        self._tk_refs = []

    @staticmethod
    def is_supported_path(path):
        return Path(path or '').suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS

    @staticmethod
    def generic_key_for_person(indi):
        sex = (indi or {}).get('sex', '').strip().upper()
        if sex == 'M':
            return 'male'
        if sex == 'F':
            return 'female'
        return 'unknown'

    def profile_image_for_person(self, indi, gedcom_path, size, media_dirs=None):
        """Return metadata and a Tk image for a person's profile thumbnail."""
        resolved = self.resolve_person_media(indi, gedcom_path, media_dirs)
        if resolved:
            image = self.tk_thumbnail(resolved, size)
            if image is not None:
                return {
                    'kind': 'real',
                    'path': resolved,
                    'image': image,
                }
        return {
            'kind': 'generic',
            'path': None,
            'image': self.generic_tk_thumbnail(
                self.generic_key_for_person(indi), size),
        }

    @staticmethod
    def selected_media_file(indi):
        """Return the selected GEDCOM media FILE value for indi, if present."""
        candidates = (indi or {}).get('media_candidates') or []
        if not candidates:
            return ''
        return (candidates[0].get('file') or '').strip()

    def resolve_person_media(self, indi, gedcom_path, media_dirs=None):
        """Return the selected local image path for indi, or None."""
        media_path = self.selected_media_file(indi)
        if not media_path or not self.is_supported_path(media_path):
            return None
        return self.resolve_media_path(media_path, gedcom_path, media_dirs)

    def resolve_media_path(self, media_path, gedcom_path, media_dirs=None):
        """Resolve a GEDCOM FILE value to a conservative local filesystem path."""
        if not media_path:
            return None
        raw = media_path.strip().strip('"')
        if not raw:
            return None
        variants = {raw, raw.replace('\\', os.sep), raw.replace('/', os.sep)}
        ged_dir = Path(gedcom_path).expanduser().resolve().parent
        candidates = []
        override_dirs = [
            Path(directory).expanduser()
            for directory in (media_dirs or [])
            if directory
        ]
        for variant in variants:
            p = Path(variant).expanduser()
            candidates.append(p)
            if not p.is_absolute():
                candidates.append(ged_dir / p)
                for folder in NEARBY_MEDIA_DIRS:
                    candidates.append(ged_dir / folder / p.name)
            for directory in override_dirs:
                candidates.append(directory / p.name)
                if not p.is_absolute():
                    candidates.append(directory / p)
        for candidate in candidates:
            try:
                if candidate.is_file():
                    return str(self._case_preserving_resolve(candidate))
            except OSError:
                continue

        basename = Path(raw.replace('\\', '/')).name
        if basename:
            for directory in override_dirs:
                try:
                    for root, _dirs, files in os.walk(directory):
                        if basename in files:
                            found = Path(root) / basename
                            if self.is_supported_path(found):
                                return str(self._case_preserving_resolve(found))
                except OSError:
                    continue
            try:
                for root, _dirs, files in os.walk(ged_dir):
                    if basename in files:
                        found = Path(root) / basename
                        if self.is_supported_path(found):
                            return str(self._case_preserving_resolve(found))
            except OSError:
                return None
        return None

    @staticmethod
    def _case_preserving_resolve(path):
        """Resolve path while preserving actual directory-entry casing."""
        resolved = Path(path).resolve()
        if os.name == 'nt':
            return resolved
        parts = resolved.parts
        if not parts:
            return resolved
        current = Path(parts[0])
        for part in parts[1:]:
            try:
                entries = os.listdir(current)
            except OSError:
                current = current / part
                continue
            match = next((entry for entry in entries if entry == part), None)
            if match is None:
                part_l = part.lower()
                match = next(
                    (entry for entry in entries if entry.lower() == part_l),
                    part,
                )
            current = current / match
        return current

    def _thumbnail_cache_path(self, source_path, size):
        stat = os.stat(source_path)
        key = '|'.join([
            str(THUMBNAIL_CACHE_VERSION),
            str(Path(source_path).resolve()),
            str(stat.st_mtime_ns),
            str(stat.st_size),
            f'{int(size[0])}x{int(size[1])}',
            'contain',
        ])
        digest = hashlib.sha256(key.encode('utf-8')).hexdigest()
        return self.cache_dir / f'{digest}.png'

    def tk_thumbnail(self, source_path, size):
        """Return a Tk PhotoImage thumbnail for source_path, using disk cache."""
        if Image is None or ImageTk is None:
            return None
        try:
            cached = self.ensure_thumbnail_cache(source_path, size)
            image = ImageTk.PhotoImage(file=str(cached))
            self._tk_refs.append(image)
            return image
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def ensure_thumbnail_cache(self, source_path, size):
        """Create and return the cached thumbnail path for source_path."""
        if Image is None:
            return None
        self.cache_dir.mkdir(parents=True, exist_ok=True)
        cached = self._thumbnail_cache_path(source_path, size)
        if not cached.exists():
            with Image.open(source_path) as img:
                img = ImageOps.exif_transpose(img).convert('RGBA')
                self._fit_contained_thumbnail(img, size).save(cached, 'PNG')
        return cached

    @staticmethod
    def _fit_contained_thumbnail(img, size):
        """Fit img inside size without cropping, centered on a neutral background."""
        width, height = int(size[0]), int(size[1])
        thumb = img.copy()
        thumb.thumbnail((width, height), Image.Resampling.LANCZOS)

        # Use a slightly warm neutral background so transparent or letterboxed
        # areas read as intentional card space rather than missing image data.
        canvas = Image.new('RGBA', (width, height), '#f3f4f6')
        x = (width - thumb.width) // 2
        y = (height - thumb.height) // 2
        canvas.alpha_composite(thumb, (x, y))
        return canvas

    def generic_tk_thumbnail(self, key, size):
        """Return a generated sex-based fallback PhotoImage."""
        width, height = int(size[0]), int(size[1])
        if Image is not None and ImageDraw is not None and ImageTk is not None:
            colors = {
                'male': ('#d8e8f7', '#4079a8'),
                'female': ('#f3dce7', '#a84b78'),
                'unknown': ('#e3e5e8', '#6b7280'),
            }
            bg, fg = colors.get(key, colors['unknown'])
            img = Image.new('RGBA', (width, height), bg)
            draw = ImageDraw.Draw(img)
            cx = width / 2
            head_r = min(width, height) * 0.18
            draw.ellipse(
                (cx - head_r, height * 0.20, cx + head_r, height * 0.20 + head_r * 2),
                fill=fg,
            )
            body_w = width * 0.56
            draw.rounded_rectangle(
                (cx - body_w / 2, height * 0.54, cx + body_w / 2, height * 0.94),
                radius=max(4, int(width * 0.08)),
                fill=fg,
            )
            image = ImageTk.PhotoImage(img)
        else:
            image = tk.PhotoImage(width=width, height=height)
            image.put('#e3e5e8', to=(0, 0, width, height))
        self._tk_refs.append(image)
        return image

    def full_size_photo(self, source_path, max_size):
        """Return a Tk image scaled to fit max_size without upscaling."""
        if Image is None or ImageTk is None:
            return None
        try:
            with Image.open(source_path) as img:
                img = ImageOps.exif_transpose(img).convert('RGBA')
                img.thumbnail(self.display_size_for_photo(source_path, max_size),
                              Image.Resampling.LANCZOS)
                image = ImageTk.PhotoImage(img)
                self._tk_refs.append(image)
                return image
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def photo_at_size(self, source_path, size):
        """Return a Tk image resized to exact display size."""
        if Image is None or ImageTk is None:
            return None
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        try:
            with Image.open(source_path) as img:
                img = ImageOps.exif_transpose(img).convert('RGBA')
                if img.size != (width, height):
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                image = ImageTk.PhotoImage(img)
                self._tk_refs.append(image)
                return image
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def full_size_png_bytes(self, source_path, max_size):
        """Return PNG bytes for source_path scaled like full_size_photo."""
        if Image is None:
            return None
        try:
            with Image.open(source_path) as img:
                img = ImageOps.exif_transpose(img).convert('RGBA')
                img.thumbnail(self.display_size_for_photo(source_path, max_size),
                              Image.Resampling.LANCZOS)
                out = io.BytesIO()
                img.save(out, format='PNG')
                return out.getvalue()
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    def png_bytes_at_size(self, source_path, size):
        """Return PNG bytes for source_path resized to exact display size."""
        if Image is None:
            return None
        width, height = max(1, int(size[0])), max(1, int(size[1]))
        try:
            with Image.open(source_path) as img:
                img = ImageOps.exif_transpose(img).convert('RGBA')
                if img.size != (width, height):
                    img = img.resize((width, height), Image.Resampling.LANCZOS)
                out = io.BytesIO()
                img.save(out, format='PNG')
                return out.getvalue()
        except Exception:  # pylint: disable=broad-exception-caught
            return None

    @staticmethod
    def display_size_for_photo(source_path, max_size):
        """Return original-or-fitted image dimensions without upscaling."""
        if Image is None:
            return int(max_size[0]), int(max_size[1])
        with Image.open(source_path) as img:
            img = ImageOps.exif_transpose(img)
            width, height = img.size
        max_w, max_h = max(1, int(max_size[0])), max(1, int(max_size[1]))
        scale = min(1.0, max_w / max(width, 1), max_h / max(height, 1))
        return max(1, int(round(width * scale))), max(1, int(round(height * scale)))

    @staticmethod
    def zoomed_display_size(base_size, zoom, *, min_size=24, max_size=8192):
        """Return dimensions for a zoomed preview image."""
        width, height = max(1, int(base_size[0])), max(1, int(base_size[1]))
        zoom = max(0.1, min(8.0, float(zoom)))
        scaled_w = width * zoom
        scaled_h = height * zoom
        if min(scaled_w, scaled_h) < min_size:
            factor = min_size / max(min(scaled_w, scaled_h), 0.001)
            scaled_w *= factor
            scaled_h *= factor
        if scaled_w > max_size or scaled_h > max_size:
            factor = min(max_size / scaled_w, max_size / scaled_h)
            scaled_w *= factor
            scaled_h *= factor
        return max(1, int(round(scaled_w))), max(1, int(round(scaled_h)))
