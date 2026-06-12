#!/usr/bin/env python3
"""update_version.py — helper to dynamically update version and release date in gedcom_navigator/__init__.py."""

import os
import sys
import re
import subprocess
from datetime import datetime

def run_git(args):
    try:
        result = subprocess.run(
            ["git"] + args,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            check=True
        )
        return result.stdout.strip()
    except Exception:
        return None

def main():
    # 1. Determine version
    version = os.environ.get("GEDCOM_NAVIGATOR_VERSION")
    if not version:
        version = os.environ.get("VERSION")
    if not version:
        ref_name = os.environ.get("GITHUB_REF_NAME")
        if ref_name and ref_name.startswith("v"):
            version = ref_name[1:]
            print(f"Using version from GITHUB_REF_NAME: {version}")
    
    # Fallback to git describe
    if not version:
        git_desc = run_git(["describe", "--tags", "--always"])
        if git_desc:
            if git_desc.startswith("v"):
                version = git_desc[1:]
            else:
                version = git_desc
            print(f"Using version from git describe: {version}")
            
    # 2. Determine release date
    release_date = os.environ.get("GEDCOM_NAVIGATOR_RELEASE_DATE")
    if not release_date:
        release_date = os.environ.get("RELEASE_DATE")
        
    if not release_date:
        # Try to get release date from git commit date
        git_date = run_git(["log", "-1", "--format=%cs"])
        if git_date:
            release_date = git_date
            print(f"Using release date from git log: {release_date}")
        else:
            release_date = datetime.now().strftime("%Y-%m-%d")
            print(f"Using release date from current date: {release_date}")

    # 3. Read/update __init__.py
    init_path = os.path.join(os.path.dirname(__file__), "..", "gedcom_navigator", "__init__.py")
    if not os.path.exists(init_path):
        print(f"Error: {init_path} does not exist", file=sys.stderr)
        sys.exit(1)
        
    with open(init_path, "r", encoding="utf-8") as f:
        content = f.read()

    # If we couldn't determine version/date, parse the current ones to keep them
    current_version_match = re.search(r'__version__\s*=\s*["\']([^"\']+)["\']', content)
    current_date_match = re.search(r'__release_date__\s*=\s*["\']([^"\']+)["\']', content)
    
    if not version:
        if current_version_match:
            version = current_version_match.group(1)
            print(f"Keeping existing version: {version}")
        else:
            version = "0.0.0-unknown"
            print(f"No version found, using fallback: {version}")
            
    if not release_date:
        if current_date_match:
            release_date = current_date_match.group(1)
            print(f"Keeping existing release date: {release_date}")
        else:
            release_date = datetime.now().strftime("%Y-%m-%d")
            print(f"No release date found, using fallback: {release_date}")

    # Replace the version and release date
    new_content = content
    if current_version_match:
        # Replace only the value inside quotes
        start, end = current_version_match.span(1)
        new_content = new_content[:start] + version + new_content[end:]
    else:
        # If not present, append it
        new_content += f'\n__version__ = "{version}"'
        
    # Re-search in case indices shifted
    current_date_match = re.search(r'__release_date__\s*=\s*["\']([^"\']+)["\']', new_content)
    if current_date_match:
        start, end = current_date_match.span(1)
        new_content = new_content[:start] + release_date + new_content[end:]
    else:
        new_content += f'\n__release_date__ = "{release_date}"'

    if content != new_content:
        with open(init_path, "w", encoding="utf-8") as f:
            f.write(new_content)
        print(f"Updated {init_path}: version={version}, release_date={release_date}")
    else:
        print(f"{init_path} is already up to date: version={version}, release_date={release_date}")

if __name__ == "__main__":
    main()
