import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
# The package is camera_lab/camera_lab; make it importable from anywhere
# (from the repository root "camera_lab" alone would be the outer folder).
sys.path.insert(0, os.path.dirname(HERE))

# Never open a window on the real display from a test.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
