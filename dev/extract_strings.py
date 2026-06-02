import os
import subprocess
import sys
from pathlib import Path

def generate_pot():
    """Extract strings from src/*.py and generate gedcom_navigator.pot using Babel."""
    root_dir = Path(__file__).parent.parent
    src_dir = root_dir / 'src'
    locales_dir = root_dir / 'locales'
    pot_file = locales_dir / 'gedcom_navigator.pot'

    if not locales_dir.exists():
        locales_dir.mkdir(parents=True)

    print(f"Extracting strings from {src_dir}...")
    
    try:
        # Check if babel is installed
        subprocess.run(["pybabel", "--version"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL, check=True)
        
        # Run pybabel extract
        # -o: output file
        # src/: input directory
        cmd = [
            "pybabel", "extract", 
            "-o", str(pot_file), 
            "--project=GEDCOM Navigator",
            "--charset=utf-8",
            str(src_dir)
        ]
        
        print(f"Running: {' '.join(cmd)}")
        subprocess.run(cmd, check=True)
        print(f"Successfully generated {pot_file} using Babel.")
        
    except (subprocess.CalledProcessError, FileNotFoundError):
        print("\nERROR: 'pybabel' not found.")
        print("To use this script, please install Babel in your development environment:")
        print("\n    pip install Babel\n")
        print("Babel is only needed for development to update translation templates.")

if __name__ == "__main__":
    generate_pot()
