"""Tests for GitHub release update checks."""

import json
from urllib.error import URLError

import pytest

from gedcom_update import (
    GITHUB_LATEST_RELEASE_PAGE,
    check_for_updates,
    is_newer_version,
    normalize_semver,
    parse_semver,
)


class _FakeResponse:
    def __init__(self, payload):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, traceback):
        return False

    def read(self):
        return json.dumps(self._payload).encode("utf-8")


def _opener(payload):
    def _open(request, timeout):
        assert request.headers["Accept"] == "application/vnd.github+json"
        assert request.headers["User-agent"] == "gedcom-dna-finder/1.2.3"
        assert timeout == 8
        return _FakeResponse(payload)

    return _open


@pytest.mark.parametrize(
    "value, expected",
    [
        ("1.2.3", (1, 2, 3)),
        ("v1.2.3", (1, 2, 3)),
        (" 1.2.3 ", (1, 2, 3)),
    ],
)
def test_parse_semver_accepts_simple_release_versions(value, expected):
    assert parse_semver(value) == expected


@pytest.mark.parametrize("value", ["1.2", "1.2.3.4", "1.2.beta", "latest"])
def test_parse_semver_rejects_non_semver_values(value):
    with pytest.raises(ValueError):
        parse_semver(value)


def test_normalize_semver_removes_leading_v():
    assert normalize_semver("v1.2.3") == "1.2.3"


@pytest.mark.parametrize(
    "latest, current, expected",
    [
        ("1.2.4", "1.2.3", True),
        ("1.3.0", "1.2.9", True),
        ("2.0.0", "1.9.9", True),
        ("1.2.3", "1.2.3", False),
        ("1.2.2", "1.2.3", False),
    ],
)
def test_is_newer_version(latest, current, expected):
    assert is_newer_version(latest, current) is expected


def test_check_for_updates_reports_new_release():
    result = check_for_updates(
        "1.2.3",
        opener=_opener({
            "tag_name": "v1.2.4",
            "html_url": "https://github.com/example/releases/tag/v1.2.4",
        }),
    )

    assert result.current_version == "1.2.3"
    assert result.latest_version == "1.2.4"
    assert result.release_url == "https://github.com/example/releases/tag/v1.2.4"
    assert result.update_available is True
    assert result.error == ""


def test_check_for_updates_reports_current_release():
    result = check_for_updates(
        "1.2.3",
        opener=_opener({"tag_name": "v1.2.3"}),
    )

    assert result.latest_version == "1.2.3"
    assert result.release_url == GITHUB_LATEST_RELEASE_PAGE
    assert result.update_available is False
    assert result.error == ""


def test_check_for_updates_reports_network_error():
    def _raise_url_error(request, timeout):
        raise URLError("offline")

    result = check_for_updates("1.2.3", opener=_raise_url_error)

    assert result.latest_version == ""
    assert result.update_available is False
    assert "offline" in result.error
