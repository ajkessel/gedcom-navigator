"""
gedcom_update.py

Helpers for checking whether a newer GitHub release is available.
"""

from dataclasses import dataclass
import json
import re
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen


GITHUB_LATEST_RELEASE_API = (
    "https://api.github.com/repos/ajkessel/gedcom-dna-finder/releases/latest"
)
GITHUB_LATEST_RELEASE_PAGE = (
    "https://github.com/ajkessel/gedcom-dna-finder/releases/latest"
)

_SEMVER_RE = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")


@dataclass(frozen=True)
class UpdateCheckResult:
    """Result of a user-initiated update check."""

    current_version: str
    latest_version: str
    release_url: str
    update_available: bool
    error: str = ""


def parse_semver(version):
    """Return ``version`` as a comparable ``(major, minor, patch)`` tuple."""
    match = _SEMVER_RE.match(str(version).strip())
    if not match:
        raise ValueError(f"Invalid semantic version: {version}")
    return tuple(int(part) for part in match.groups())


def normalize_semver(version):
    """Return a semantic version string without a leading ``v`` prefix."""
    return ".".join(str(part) for part in parse_semver(version))


def is_newer_version(latest_version, current_version):
    """Return True when ``latest_version`` is newer than ``current_version``."""
    return parse_semver(latest_version) > parse_semver(current_version)


def check_for_updates(current_version, opener=urlopen, timeout=8):
    """Query GitHub for the latest release and compare it with this app."""
    release_url = GITHUB_LATEST_RELEASE_PAGE
    request = Request(
        GITHUB_LATEST_RELEASE_API,
        headers={
            "Accept": "application/vnd.github+json",
            "User-Agent": f"gedcom-dna-finder/{current_version}",
        },
    )
    try:
        with opener(request, timeout=timeout) as response:
            payload = json.loads(response.read().decode("utf-8"))
    except (HTTPError, URLError, OSError, TimeoutError) as error:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version="",
            release_url=release_url,
            update_available=False,
            error=str(error),
        )
    except (json.JSONDecodeError, UnicodeDecodeError) as error:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version="",
            release_url=release_url,
            update_available=False,
            error=f"GitHub returned an unreadable release response: {error}",
        )

    tag_name = str(payload.get("tag_name", "")).strip()
    release_url = str(payload.get("html_url") or release_url)
    try:
        latest_version = normalize_semver(tag_name)
        update_available = is_newer_version(latest_version, current_version)
    except ValueError as error:
        return UpdateCheckResult(
            current_version=current_version,
            latest_version="",
            release_url=release_url,
            update_available=False,
            error=str(error),
        )

    return UpdateCheckResult(
        current_version=current_version,
        latest_version=latest_version,
        release_url=release_url,
        update_available=update_available,
    )
