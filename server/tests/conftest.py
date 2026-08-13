import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# plugins.configuration, plugins.basetypes and plugins.database import each other in a cycle
# that only resolves when entered via plugins.basetypes; enter it there before any test does
import plugins.basetypes  # noqa: E402,F401
