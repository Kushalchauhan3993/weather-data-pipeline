# tests/conftest.py — Pytest configuration
# This file is automatically loaded by pytest before running tests.

import sys
from pathlib import Path

# Add the src/ directory to Python's path so tests can import our modules
sys.path.insert(0, str(Path(__file__).parent.parent / "src"))

# This also ensures the config.py sets up directories before tests run
import config
