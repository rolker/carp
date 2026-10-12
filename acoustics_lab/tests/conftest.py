import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The package is acoustics_lab/acoustics_lab; make it importable from anywhere.
sys.path.insert(0, os.path.dirname(HERE))
sys.path.insert(0, HERE)

# Never open a window on the real display from a test.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
