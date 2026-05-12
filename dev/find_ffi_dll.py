import sys
import glob
import os
import shutil
from pathlib import Path

if not Path('./venv').is_dir():
    print("venv directory not found. Please create a virtual environment in the current directory "
          "named 'venv' and install the required packages before running this script.")
    exit(1)

_dlls = []
if sys.platform == 'win32':
    _base = os.path.dirname(sys.executable)
    _conda_base = sys.base_prefix
    for _pat in [
        os.path.join(_base, 'libffi*.dll'),
        os.path.join(_base, 'ffi*.dll'),
        os.path.join(_base, 'DLLs', 'libffi*.dll'),
        os.path.join(_base, 'DLLs', 'ffi*.dll'),
        os.path.join(_base, 'Library', 'bin', 'libffi*.dll'),
        os.path.join(_base, 'Library', 'bin', 'ffi*.dll'),
        os.path.join(_conda_base, 'libffi*.dll'),
        os.path.join(_conda_base, 'ffi*.dll'),
        os.path.join(_conda_base, 'DLLs', 'libffi*.dll'),
        os.path.join(_conda_base, 'DLLs', 'ffi*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'libffi*.dll'),
        os.path.join(_conda_base, 'Library', 'bin', 'ffi*.dll'),
    ]:
        _dlls += [p for p in glob.glob(_pat)]

for dll in _dlls:
    shutil.copy(dll, "./venv/Scripts")
