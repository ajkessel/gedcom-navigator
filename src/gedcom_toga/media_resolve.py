"""Pure GEDCOM media path resolution (Phase 5.5).

Lifted from gedcom_media.ProfileMediaService (which can't be imported here — it does a
top-level `import tkinter` for its Tk thumbnails). Only the on-disk path-resolution
logic is needed for the Toga graph, which draws images via `toga.Image` + Canvas
`draw_image`. Same ranking/resolution rules as the tkinter app: the top-ranked
`media_candidates` FILE value, resolved against the GEDCOM dir, common media subfolders,
configured override dirs, then a basename walk.
"""
import os
from pathlib import Path

SUPPORTED_IMAGE_EXTENSIONS = {
    ".bmp", ".gif", ".jpeg", ".jpg", ".png", ".tif", ".tiff", ".webp",
}
NEARBY_MEDIA_DIRS = (
    "media", "Media", "photos", "Photos", "images", "Images", "pictures", "Pictures",
)


def is_supported_path(path):
    return Path(path or "").suffix.lower() in SUPPORTED_IMAGE_EXTENSIONS


def selected_media_file(indi):
    """Return the top-ranked GEDCOM media FILE value for a person, if any."""
    candidates = (indi or {}).get("media_candidates") or []
    if not candidates:
        return ""
    return (candidates[0].get("file") or "").strip()


def resolve_person_media(indi, gedcom_path, media_dirs=None):
    """Return the selected local image path for a person, or None."""
    media_path = selected_media_file(indi)
    if not media_path or not is_supported_path(media_path):
        return None
    return resolve_media_path(media_path, gedcom_path, media_dirs)


def resolve_media_path(media_path, gedcom_path, media_dirs=None):
    """Resolve a GEDCOM FILE value to a conservative local filesystem path."""
    if not media_path or not gedcom_path:
        return None
    raw = media_path.strip().strip('"')
    if not raw:
        return None
    variants = {raw, raw.replace("\\", os.sep), raw.replace("/", os.sep)}
    ged_dir = Path(gedcom_path).expanduser().resolve().parent
    override_dirs = [Path(d).expanduser() for d in (media_dirs or []) if d]
    candidates = []
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
                return str(_case_preserving_resolve(candidate))
        except OSError:
            continue

    basename = Path(raw.replace("\\", "/")).name
    if basename:
        for directory in list(override_dirs) + [ged_dir]:
            try:
                for root, _dirs, files in os.walk(directory):
                    if basename in files:
                        found = Path(root) / basename
                        if is_supported_path(found):
                            return str(_case_preserving_resolve(found))
            except OSError:
                continue
    return None


def _case_preserving_resolve(path):
    resolved = Path(path).resolve()
    if os.name == "nt":
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
        match = next((e for e in entries if e == part), None)
        if match is None:
            part_l = part.lower()
            match = next((e for e in entries if e.lower() == part_l), part)
        current = current / match
    return current
