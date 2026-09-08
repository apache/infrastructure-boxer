"""Test bootstrap: put the checkout root on sys.path so orgscanner resolves."""
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import orgscanner  # noqa: E402,F401
