"""A page that is planned but not built yet."""
from ..qtcompat import Qt, QtWidgets

# Where each page appears in docs/design.md, "Getting there from carp/acoustic".
PLANNED = {
    "Signals": ("5", "Chirps and tones, spectrum, processing gain and how strongly "
                     "signals correlate with each other. For now, signals are edited "
                     "on the Ranging page."),
    "Transducers": ("5", "Resonance from an equivalent circuit, bandwidth and ringing."),
    "Beam patterns": ("3", "Elements and arrays, steering, grating lobes; polar slices "
                           "and a 3D surface; rotate-and-measure."),
    "Sound speed": ("4", "Sound speed in air and water, profiles, refraction."),
    "Propagation": ("4", "Spreading, absorption, reflections, travel time."),
    "Echo sounding & backscatter": ("7", "Bottom detection, backscatter, water-column "
                                         "echograms."),
    "Doppler": ("8", "Shifts, Doppler-tolerant signals, velocity measurement."),
    "Noise": ("5", "Background spectrum, over time."),
    "Receiver chain": ("5", "Gain staging, clipping, ADC bits, time-varying gain."),
    "Comms": ("6", "Chirp spread spectrum link, error rates."),
    "Multibeam design": ("7", "Beam widths, footprints, coverage, sounding accuracy."),
    "Sonar equation": ("7", "Source level, transmission loss, noise, detection."),
}


class PlaceholderPage(QtWidgets.QWidget):
    supports_run = False

    def __init__(self, title, parent=None):
        super().__init__(parent)
        self.title = title
        step, text = PLANNED.get(title, ("?", ""))
        label = QtWidgets.QLabel(
            f"<h2>{title}</h2><p>Not built yet: planned for step {step} of "
            f"docs/design.md.</p><p>{text}</p>")
        label.setWordWrap(True)
        label.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)
        box = QtWidgets.QVBoxLayout(self)
        box.setContentsMargins(24, 24, 24, 24)
        box.addWidget(label)
        box.addStretch(1)

    def run_blocker(self):
        return "this page has no experiment yet"

    def shutdown(self):
        pass
