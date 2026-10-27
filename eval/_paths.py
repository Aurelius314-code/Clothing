"""Lets the evaluation scripts in this folder import the app's own modules (measure.py, watcher.py).

Data files and results live in this folder; the .env file is the app's, one level up.
"""
import sys
from pathlib import Path

EVAL_DIR = Path(__file__).resolve().parent
ROOT = EVAL_DIR.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))
