"""What a backend is, as far as pages and experiments are concerned.

A page asks for "send these signals from these transducers, give me what the
receivers heard". Whether that is a sound card, a simulated scene or a saved
run is the backend's business. Nothing here imports Qt or the workspace.

Times are always on a named device clock, and in seconds. Sample values are
float in full-scale units.
"""
from dataclasses import dataclass, field
from typing import Callable, Optional

import numpy as np


class Cancelled(Exception):
    """Raised by a backend when `cancel()` said stop."""


@dataclass
class Emission:
    """One signal sent from one transducer."""
    transducer: str          # transducer ID
    samples: np.ndarray      # float, full-scale units, at the sending device's rate
    start: float             # s after the ping starts, on the sending device's clock
    rate: float = 48000.0    # the sending device's sample rate, Hz (added to the sketch)
    signal: str = ""         # signal ID or name, so analysis can tell signals apart


@dataclass
class Ping:
    """What to send and who listens."""
    emissions: list          # of Emission
    receivers: list          # transducer IDs
    listen: float            # s to keep recording after the last emission
    meta: dict = field(default_factory=dict)
    # ^ where it came from (design ID and name, the signals' settings); kept
    # in the capture's meta so a saved run says what made it


@dataclass
class Recording:
    """What one receiving transducer heard, from one device."""
    samples: np.ndarray      # float, full-scale units
    rate: float              # this device's sample rate, Hz
    clock: str               # clock domain
    started: float           # start time on that clock, s
    loopback_of: list = field(default_factory=list)
    # ^ IDs of emitters whose electrical copy is mixed into this input


@dataclass
class Capture:
    """What came back from a ping."""
    recordings: dict         # receiver transducer ID -> Recording
    emitted: dict            # emitter ID -> send time (s, sender's clock), where known
    truth: Optional[dict]    # simulation only: every path's delay, level, history
    meta: dict               # backend, devices, sound speed, scene or rig, wall time...
    ping: Optional[Ping] = None     # what was asked for (added to the sketch)


@dataclass
class TransducerInfo:
    id: str
    name: str
    can_send: bool
    can_receive: bool
    rate: float              # sample rate of its device, Hz


def never_cancel():
    return False


def no_progress(fraction, text=""):
    pass


class PingStream:
    """A backend kept ready for repeated pings of one design.

    Hardware backends keep their audio streams open between pings; the others
    just call fire. Use as a context manager, or call close().
    """

    def __init__(self, backend, ping):
        self.backend, self.ping = backend, ping

    def fire(self, progress: Callable = no_progress,
             cancel: Callable = never_cancel) -> Capture:
        return self.backend.fire(self.ping, progress, cancel)

    def close(self):
        pass

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()


class Backend:
    """Where pings are made. Subclasses fill in fire() and transducers()."""

    name = "backend"
    realtime = True          # False: may run faster than real time

    def transducers(self) -> list:
        """TransducerInfo for everything this backend can send or receive on."""
        raise NotImplementedError

    def fire(self, ping: Ping, progress: Callable = no_progress,
             cancel: Callable = never_cancel) -> Capture:
        """Send the ping and return what was heard. Called from a worker
        thread, never the GUI thread. progress(fraction, text) reports
        how far along it is; cancel() returns True to stop early, in which
        case Cancelled is raised."""
        raise NotImplementedError

    def open_stream(self, ping: Ping) -> PingStream:
        """A stream for repeated pings of this design."""
        return PingStream(self, ping)
