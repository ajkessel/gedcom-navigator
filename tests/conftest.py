"""pytest configuration: put src/ on sys.path so tests can import gedcom modules."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent / "src"))
