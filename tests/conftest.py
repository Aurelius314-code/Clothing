"""pytest setup for the app's tests: makes the app's modules importable however pytest is started."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
