"""pytest setup for the evaluation tests: makes this folder and the app's modules importable."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import _paths  # noqa: E402,F401
