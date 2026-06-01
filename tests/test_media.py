"""Tests for profile media resolution and thumbnail caching."""

import os
import time

import pytest

from gedcom_media import Image, ProfileMediaService


def test_resolve_media_path_prefers_gedcom_relative_path(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    photo = tmp_path / "media" / "alice.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"not a real image")

    service = ProfileMediaService(tmp_path / "cache")

    assert service.resolve_media_path("media/alice.jpg", str(ged)) == str(photo.resolve())


def test_resolve_media_path_searches_nearby_media_folder_by_basename(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    photo = tmp_path / "Photos" / "alice.jpg"
    photo.parent.mkdir()
    photo.write_bytes(b"not a real image")

    service = ProfileMediaService(tmp_path / "cache")

    assert service.resolve_media_path(r"C:\old\path\alice.jpg", str(ged)) == str(photo.resolve())


def test_resolve_media_path_uses_replacement_media_directory(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    media_dir = tmp_path / "new-media"
    photo = media_dir / "nested" / "alice.jpg"
    photo.parent.mkdir(parents=True)
    photo.write_bytes(b"not a real image")
    service = ProfileMediaService(tmp_path / "cache")

    assert service.resolve_media_path(
        r"C:\old\media\alice.jpg", str(ged), [str(media_dir)]
    ) == str(photo.resolve())


def test_resolve_person_media_uses_only_selected_candidate(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    photo = tmp_path / "alice.png"
    photo.write_bytes(b"not a real image")
    service = ProfileMediaService(tmp_path / "cache")
    indi = {
        "media_candidates": [
            {"file": "notes.txt"},
            {"file": "alice.png"},
        ]
    }

    assert service.resolve_person_media(indi, str(ged)) is None
    assert service.selected_media_file(indi) == "notes.txt"


def test_resolve_person_media_resolves_selected_candidate(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    photo = tmp_path / "alice.png"
    photo.write_bytes(b"not a real image")
    service = ProfileMediaService(tmp_path / "cache")
    indi = {
        "media_candidates": [
            {"file": "notes.txt"},
            {"file": "alice.png"},
        ]
    }

    assert service.resolve_person_media(indi, str(ged)) is None

    indi["media_candidates"] = [{"file": "alice.png"}]
    assert service.resolve_person_media(indi, str(ged)) == str(photo.resolve())


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
def test_thumbnail_cache_reuses_and_invalidates_on_mtime_change(tmp_path):
    ged = tmp_path / "tree.ged"
    ged.write_text("0 HEAD\n0 TRLR\n", encoding="utf-8")
    photo = tmp_path / "alice.png"
    Image.new("RGB", (24, 24), "red").save(photo)
    service = ProfileMediaService(tmp_path / "cache")

    first = service.ensure_thumbnail_cache(str(photo), (16, 16))
    cache_files = list((tmp_path / "cache" / "thumbnails").glob("*.png"))
    assert first is not None
    assert len(cache_files) == 1

    second = service.ensure_thumbnail_cache(str(photo), (16, 16))
    assert second is not None
    assert len(list((tmp_path / "cache" / "thumbnails").glob("*.png"))) == 1

    time.sleep(0.01)
    os.utime(photo, None)
    third = service.ensure_thumbnail_cache(str(photo), (16, 16))
    assert third is not None
    assert len(list((tmp_path / "cache" / "thumbnails").glob("*.png"))) == 2


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
def test_thumbnail_generation_contains_without_cropping(tmp_path):
    photo = tmp_path / "portrait.png"
    Image.new("RGB", (40, 120), "red").save(photo)
    service = ProfileMediaService(tmp_path / "cache")

    cached = service.ensure_thumbnail_cache(str(photo), (80, 80))

    with Image.open(cached) as thumb:
        assert thumb.size == (80, 80)
        assert thumb.getpixel((40, 5))[:3] == (255, 0, 0)
        assert thumb.getpixel((5, 40))[:3] == (243, 244, 246)


def test_generic_key_uses_sex_when_available(tmp_path):
    service = ProfileMediaService(tmp_path / "cache")

    assert service.generic_key_for_person({"sex": "M"}) == "male"
    assert service.generic_key_for_person({"sex": "F"}) == "female"
    assert service.generic_key_for_person({"sex": ""}) == "unknown"


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
def test_display_size_for_photo_preserves_small_images_and_fits_large(tmp_path):
    small = tmp_path / "small.png"
    large = tmp_path / "large.png"
    Image.new("RGB", (80, 60), "red").save(small)
    Image.new("RGB", (4000, 2000), "blue").save(large)

    assert ProfileMediaService.display_size_for_photo(str(small), (800, 600)) == (
        80,
        60,
    )
    assert ProfileMediaService.display_size_for_photo(str(large), (800, 600)) == (
        800,
        400,
    )


def test_zoomed_display_size_scales_from_preview_base():
    assert ProfileMediaService.zoomed_display_size(
        (800, 400), 1.0) == (800, 400)
    assert ProfileMediaService.zoomed_display_size(
        (800, 400), 1.1) == (880, 440)
    assert ProfileMediaService.zoomed_display_size(
        (800, 400), 0.5) == (400, 200)
    assert ProfileMediaService.zoomed_display_size((12, 6), 0.1) == (48, 24)


@pytest.mark.skipif(Image is None, reason="Pillow not installed")
def test_full_size_png_bytes_match_display_size(tmp_path):
    photo = tmp_path / "large.png"
    Image.new("RGB", (4000, 2000), "blue").save(photo)
    service = ProfileMediaService(tmp_path / "cache")

    png_bytes = service.full_size_png_bytes(str(photo), (800, 600))

    assert png_bytes is not None
    from io import BytesIO
    with Image.open(BytesIO(png_bytes)) as copied:
        assert copied.size == (800, 400)
