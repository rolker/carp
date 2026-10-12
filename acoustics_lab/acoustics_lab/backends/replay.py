"""The replay backend: saved captures, one per ping, in order.

Reprocessing old data with new settings is the main use. A ping asked of
this backend is answered with the next saved recording, and the ping that
was asked for is ignored: what was sent is what the recording's JSON file
says. The list starts again after the last one.
"""
from pathlib import Path

from .. import capture_io
from .base import Backend, Cancelled, TransducerInfo, never_cancel, no_progress


class ReplayBackend(Backend):
    name = "Replay"
    realtime = False

    def __init__(self, path):
        """path is a WAV file or a folder of them (searched below it too)."""
        self.path = Path(path)
        self.files = capture_io.find_recordings(self.path)
        if not self.files:
            raise ValueError(f"no WAV files at {self.path}")
        self.index = 0
        self._first = capture_io.load_capture(self.files[0])

    def __len__(self):
        return len(self.files)

    def transducers(self):
        ping, rate = self._first.ping, None
        out = []
        for rid, recording in self._first.recordings.items():
            out.append(TransducerInfo(rid, rid, False, True, recording.rate))
            rate = recording.rate
        for e in ping.emissions:
            if all(t.id != e.transducer for t in out):
                out.append(TransducerInfo(e.transducer, e.transducer, True, False, rate))
        return out

    def fire(self, ping=None, progress=no_progress, cancel=never_cancel):
        if cancel():
            raise Cancelled()
        file = self.files[self.index]
        capture = capture_io.load_capture(file)
        capture.meta["index"] = self.index
        capture.meta["count"] = len(self.files)
        self.index = (self.index + 1) % len(self.files)
        progress(1.0, file.name)
        return capture
