"""One always-running full-duplex stream per sound device.

`DuplexDevice` is the interface and everything that does not touch
hardware: a running sample counter, an output scheduler, an input ring
buffer and an xrun log. `PortAudioDuplex` adds the real stream. `fake.FakeDevice`
adds a simulated one. Both call `DuplexDevice._process` once per block, so
what is tested with the fake is what runs on hardware.

**Sample numbers.** There is one counter per device, on the device's own
clock. At the start of a block, input sample `n` is the first frame handed
in and output sample `n` is the first frame the callback must produce. They
count the same blocks, so both are the same number at that moment. That
does not mean output sample `n` is heard at input sample `n`: the output
goes through DAC and USB buffers, and the input through ADC buffers. The
delay from an output sample to the input sample where its loopback copy
shows up (the "offset") is measured with a pulse, not computed. PortAudio's
own claim for it (from the callback time stamps) is kept in `timing()` for
comparison, but never used.

**The callback does minimal work.** It copies the input into the ring,
mixes the pending output items into the output block, and logs xruns. All
allocation, conversion and searching happens in the caller's thread
(`schedule` converts to int16 before the callback ever sees the data;
`read_input` copies out of the ring).

Samples are int16 on the wire. `schedule` takes float in full-scale units
(1.0 is the largest output value) or int16.
"""
import ctypes
import threading
import time
from collections import deque
from dataclasses import dataclass, field

import numpy as np

from .discovery import quiet

# PortAudio's PaStreamCallbackFlags
INPUT_UNDERFLOW = 0x01
INPUT_OVERFLOW = 0x02
OUTPUT_UNDERFLOW = 0x04
OUTPUT_OVERFLOW = 0x08
PRIMING_OUTPUT = 0x10       # first callbacks while the output primes; not a fault
XRUN_MASK = INPUT_UNDERFLOW | INPUT_OVERFLOW | OUTPUT_UNDERFLOW | OUTPUT_OVERFLOW

_FLAG_NAMES = ((INPUT_UNDERFLOW, "input underflow"),
               (INPUT_OVERFLOW, "input overflow"),
               (OUTPUT_UNDERFLOW, "output underflow"),
               (OUTPUT_OVERFLOW, "output overflow"))

MAX_LOGGED_XRUNS = 5000


class DeviceError(Exception):
    """The device could not be opened or the stream failed."""


class LateError(ValueError):
    """An output item was scheduled for a sample that has already gone."""

    def __init__(self, start, now, late_by):
        super().__init__(f"output sample {start} is already past "
                         f"(the next one to be produced is {now}, "
                         f"{late_by} samples late)")
        self.start = start
        self.now = now
        self.late_by = late_by


class LostDataError(ValueError):
    """Input samples asked for are no longer in the ring (or not yet in it)."""


@dataclass
class PlayItem:
    """One scheduled piece of output. Also the handle `schedule` returns."""
    start: int               # output sample number of its first sample
    data: np.ndarray         # int16, mono
    channels: tuple          # output channel indices it is added to
    skipped: int = 0         # samples at the start that were too late to play
    started: bool = False    # the callback has begun playing it

    @property
    def length(self):
        return len(self.data)

    @property
    def end(self):
        return self.start + len(self.data)


@dataclass
class XrunEvent:
    """A callback that PortAudio flagged."""
    sample: int              # sample number at the start of that block
    frames: int              # block length, so the event covers sample..sample+frames
    flags: int
    wall: float              # time.monotonic() when the callback ran

    @property
    def kinds(self):
        return [name for bit, name in _FLAG_NAMES if self.flags & bit]


def to_int16(samples, gain=1.0):
    """Float full-scale samples times `gain`, as clipped int16 (copy)."""
    samples = np.asarray(samples)
    if samples.dtype == np.int16 and gain == 1.0:
        return samples.copy()
    scaled = np.rint(samples.astype(np.float64) * gain *
                     (32767.0 if samples.dtype.kind == "f" else 1.0))
    return np.clip(scaled, -32768, 32767).astype(np.int16)


class DuplexDevice:
    """Sample counter, output scheduler, input ring and xrun log.

    Subclasses provide `_open`, `_start_transport`, `_stop_transport` and
    call `_process` for each block. Public methods are safe to call from any
    thread except where stated.
    """

    def __init__(self, name, rate, frames_per_buffer, in_channels,
                 out_channels, input_channel=0, ring_seconds=30.0):
        if not 0 <= input_channel < max(in_channels, 1):
            raise ValueError("input_channel is outside the input channels")
        self.name = name
        self.rate = float(rate)
        self.frames_per_buffer = int(frames_per_buffer)
        self.in_channels = int(in_channels)
        self.out_channels = int(out_channels)
        self.input_channel = int(input_channel)
        self.capacity = int(ring_seconds * rate)
        self._ring = np.zeros(self.capacity, dtype=np.int16)
        self._in_pos = 0           # input frames received
        self._out_pos = 0          # output frames produced
        self._items = ()           # replaced, never changed in place
        self._write_lock = threading.Lock()
        self._work = np.zeros((self.frames_per_buffer, self.out_channels),
                              dtype=np.int32)
        self._out16 = np.zeros((self.frames_per_buffer, self.out_channels),
                               dtype=np.int16)
        self._xruns = []
        self._xrun_counts = {name: 0 for _, name in _FLAG_NAMES}
        self._xrun_total = 0
        self._blocks = 0
        self._time_first = None    # (sample, PortAudio current time)
        self._time_last = None
        self._ahead = deque(maxlen=256)   # dac time - adc time, s, per block
        self._error = None
        self._running = False

    # -- the callback ------------------------------------------------------

    def _process(self, indata, status, adc_time, dac_time, current_time):
        """One block. `indata` is int16 (frames, in_channels). Returns the
        int16 (frames, out_channels) output block, valid until the next call.
        Runs in the audio thread (or the fake's pump)."""
        n = indata.shape[0]
        start = self._out_pos
        if n > self._work.shape[0]:
            self._work = np.zeros((n, self.out_channels), dtype=np.int32)
            self._out16 = np.zeros((n, self.out_channels), dtype=np.int16)
        flags = status & XRUN_MASK
        if flags:
            self._note_xrun(start, n, flags)
        if self._time_first is None:
            self._time_first = (start, current_time)
        self._time_last = (start, current_time)
        self._blocks += 1
        self._ahead.append(dac_time - adc_time)
        # input into the ring
        if self.in_channels:
            column = indata[:, self.input_channel]
            at = start % self.capacity
            first = min(n, self.capacity - at)
            self._ring[at:at + first] = column[:first]
            if first < n:
                self._ring[:n - first] = column[first:]
        self._in_pos = start + n
        # scheduled items into the output
        out = self._out16[:n]
        work = self._work[:n]
        end = start + n
        mixed = False
        for item in self._items:
            a = item.start if item.start > start else start
            b = item.end if item.end < end else end
            if b <= a:
                continue
            if not mixed:
                work[:] = 0
                mixed = True
            if not item.started:
                item.started = True
                if item.start < start:
                    item.skipped = max(item.skipped, start - item.start)
            piece = item.data[a - item.start:b - item.start]
            for channel in item.channels:
                work[a - start:b - start, channel] += piece
        if mixed:
            np.clip(work, -32768, 32767, out=work)
            out[:] = work
        else:
            out[:] = 0
        self._out_pos = end
        return out

    def _note_xrun(self, sample, frames, flags):
        self._xrun_total += 1
        for bit, kind in _FLAG_NAMES:
            if flags & bit:
                self._xrun_counts[kind] += 1
        if len(self._xruns) < MAX_LOGGED_XRUNS:
            self._xruns.append(XrunEvent(sample, frames, flags, time.monotonic()))

    # -- positions -----------------------------------------------------------

    @property
    def in_position(self):
        """Input samples captured so far; input sample numbers below this
        can be read."""
        return self._in_pos

    @property
    def out_position(self):
        """The next output sample number that has not been produced yet; an
        item scheduled to start at or after it is on time."""
        return self._out_pos

    @property
    def lead_samples(self):
        """A safe distance ahead of `out_position` to schedule, in samples:
        two blocks."""
        return 2 * self.frames_per_buffer

    # -- output scheduling -----------------------------------------------

    def schedule(self, samples, start=None, channel="left", gain=1.0,
                 late="raise"):
        """Play `samples` starting at output sample `start`.

        samples: 1-D float (full-scale units) or int16 array, mixed (added,
        then clipped) with whatever else is pending. start: output sample
        number; None means `lead_samples` from now. channel: "left",
        "right", "both" or a channel index. gain: linear factor. late: what
        to do if `start` has already gone: "raise" (LateError, nothing is
        scheduled) or "play" (play what is left; the handle's `skipped` says
        how many samples were lost).

        An item can also be caught by the block being produced right now; the
        callback then plays it from where it can and sets `skipped` on the
        returned handle, so check `handle.skipped` after it has played.
        Returns the PlayItem.
        """
        if not self._running:
            raise DeviceError("the stream is not running")
        data = to_int16(np.asarray(samples).reshape(-1), gain)
        channels = self._channels(channel)
        now = self._out_pos
        if start is None:
            start = now + self.lead_samples
        start = int(start)
        skipped = 0
        if start < now:
            if late != "play":
                raise LateError(start, now, now - start)
            skipped = now - start
        item = PlayItem(start, data, channels, skipped=skipped)
        with self._write_lock:
            self._items = tuple(i for i in self._items if i.end > now) + (item,)
        return item

    def _channels(self, channel):
        if channel == "both":
            return tuple(range(self.out_channels))
        if channel == "left":
            index = 0
        elif channel == "right":
            index = 1
        else:
            index = int(channel)
        if not 0 <= index < self.out_channels:
            raise ValueError(f"output channel {channel!r} does not exist on "
                             f"a {self.out_channels}-channel output")
        return (index,)

    def pending(self):
        """Items that have not finished playing."""
        return [i for i in self._items if i.end > self._out_pos]

    def cancel(self, item):
        """Withdraw an item that has not started playing. Returns True if it
        was removed in time."""
        with self._write_lock:
            if item.started or item.start < self._out_pos + self.frames_per_buffer:
                return False
            self._items = tuple(i for i in self._items if i is not item)
        return True

    # -- input ring ------------------------------------------------------

    def read_input(self, start, stop):
        """Copy of input samples `start` up to (not including) `stop`, int16.

        Raises LostDataError if `stop` has not been captured yet, or if the
        ring has already overwritten `start`.
        """
        start, stop = int(start), int(stop)
        if stop < start:
            raise ValueError("stop is before start")
        if stop > self._in_pos:
            raise LostDataError(f"input sample {stop} has not been captured "
                                f"yet (captured {self._in_pos})")
        if start < self._in_pos - self.capacity:
            raise LostDataError(f"input sample {start} was overwritten "
                                f"(the ring holds {self.capacity} samples)")
        count = stop - start
        out = np.empty(count, dtype=np.int16)
        at = start % self.capacity
        first = min(count, self.capacity - at)
        out[:first] = self._ring[at:at + first]
        if first < count:
            out[first:] = self._ring[:count - first]
        if start < self._in_pos - self.capacity:      # written over while copying
            raise LostDataError(f"input sample {start} was overwritten "
                                "while it was being read")
        return out

    def wait_input(self, stop, timeout=None):
        """Block until input sample `stop` has been captured. True when it
        has, False on timeout (seconds). Raises DeviceError if the stream
        failed."""
        deadline = None if timeout is None else time.monotonic() + timeout
        return self._wait(lambda: self._in_pos >= stop, deadline)

    def _wait(self, done, deadline):
        while not done():
            if self._error is not None:
                raise DeviceError(f"the stream failed: {self._error}")
            if not self._running:
                raise DeviceError("the stream is not running")
            if deadline is not None and time.monotonic() >= deadline:
                return False
            time.sleep(0.001)
        return True

    # -- xruns -----------------------------------------------------------

    @property
    def xrun_count(self):
        """Callbacks flagged so far."""
        return self._xrun_total

    def xruns(self):
        """Logged xrun events, oldest first (a copy)."""
        return list(self._xruns)

    def xruns_between(self, start, stop):
        """Xrun events whose block overlaps samples start..stop. A capture
        in that range may have lost or repeated samples; discard it."""
        return [e for e in self._xruns
                if e.sample < stop and e.sample + e.frames > start]

    def xrun_counts(self):
        """Count per kind of fault: dict of name -> number."""
        return dict(self._xrun_counts)

    # -- timing ----------------------------------------------------------

    def timing(self):
        """What PortAudio reports about timing. Kept, not trusted.

        claimed_offset_samples: PortAudio's idea of the delay from an output
        sample to the input sample where a loopback copy of it appears
        (median of dac time minus adc time, in samples). None before enough
        blocks have run. clock_ratio: device samples per PortAudio-clock
        second divided by the nominal rate (1.0001 means this device's
        clock runs 100 ppm fast against the system's), None before about a
        second of data.
        """
        ahead = sorted(self._ahead)
        claimed = ahead[len(ahead) // 2] * self.rate if len(ahead) >= 8 else None
        ratio = None
        first, last = self._time_first, self._time_last
        if first and last and last[1] - first[1] >= 1.0:
            ratio = (last[0] - first[0]) / (last[1] - first[1]) / self.rate
        return {"claimed_offset_samples": claimed, "clock_ratio": ratio,
                "blocks": self._blocks}

    # -- life cycle ------------------------------------------------------

    def start(self):
        """Open and start the stream. The sample counter starts at 0."""
        if self._running:
            return
        self._error = None
        self._start_transport()
        self._running = True

    def stop(self):
        """Stop and close the stream. Pending items are dropped."""
        if not self._running:
            return
        self._running = False
        self._stop_transport()
        self._items = ()

    close = stop

    def __enter__(self):
        self.start()
        return self

    def __exit__(self, *exc):
        self.stop()

    def _start_transport(self):
        raise NotImplementedError

    def _stop_transport(self):
        raise NotImplementedError

    def describe(self):
        """Plain facts about the open stream, for logs and run summaries."""
        return {"name": self.name, "rate": self.rate,
                "frames_per_buffer": self.frames_per_buffer,
                "in_channels": self.in_channels,
                "out_channels": self.out_channels,
                "input_channel": self.input_channel}


# ---------------------------------------------------------------------------
# PortAudio through ctypes
#
# PyAudio can only open a duplex stream with the same channel count each way,
# and a cheap dongle is stereo out and mono in. libportaudio is already
# loaded by PyAudio, so its C interface is used directly for the stream.

class _StreamParameters(ctypes.Structure):
    _fields_ = [("device", ctypes.c_int),
                ("channelCount", ctypes.c_int),
                ("sampleFormat", ctypes.c_ulong),
                ("suggestedLatency", ctypes.c_double),
                ("hostApiSpecificStreamInfo", ctypes.c_void_p)]


class _TimeInfo(ctypes.Structure):
    _fields_ = [("inputBufferAdcTime", ctypes.c_double),
                ("currentTime", ctypes.c_double),
                ("outputBufferDacTime", ctypes.c_double)]


class _StreamInfo(ctypes.Structure):
    _fields_ = [("structVersion", ctypes.c_int),
                ("inputLatency", ctypes.c_double),
                ("outputLatency", ctypes.c_double),
                ("sampleRate", ctypes.c_double)]


class _HostErrorInfo(ctypes.Structure):
    _fields_ = [("hostApiType", ctypes.c_int),
                ("errorCode", ctypes.c_long),
                ("errorText", ctypes.c_char_p)]


_CALLBACK = ctypes.CFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_void_p,
                             ctypes.c_ulong, ctypes.POINTER(_TimeInfo),
                             ctypes.c_ulong, ctypes.c_void_p)

PA_INT16 = 0x00000008
PA_CONTINUE = 0
PA_ABORT = 2
PA_HOST_ERROR = -9999


def _load_portaudio():
    try:
        lib = ctypes.CDLL("libportaudio.so.2")
    except OSError as error:
        raise DeviceError(f"cannot load libportaudio.so.2 ({error})") from error
    lib.Pa_Initialize.restype = ctypes.c_int
    lib.Pa_Terminate.restype = ctypes.c_int
    lib.Pa_GetErrorText.restype = ctypes.c_char_p
    lib.Pa_GetErrorText.argtypes = [ctypes.c_int]
    lib.Pa_GetLastHostErrorInfo.restype = ctypes.POINTER(_HostErrorInfo)
    lib.Pa_OpenStream.restype = ctypes.c_int
    lib.Pa_OpenStream.argtypes = [
        ctypes.POINTER(ctypes.c_void_p), ctypes.POINTER(_StreamParameters),
        ctypes.POINTER(_StreamParameters), ctypes.c_double, ctypes.c_ulong,
        ctypes.c_ulong, _CALLBACK, ctypes.c_void_p]
    for call in ("Pa_StartStream", "Pa_StopStream", "Pa_CloseStream"):
        function = getattr(lib, call)
        function.restype = ctypes.c_int
        function.argtypes = [ctypes.c_void_p]
    lib.Pa_GetStreamInfo.restype = ctypes.POINTER(_StreamInfo)
    lib.Pa_GetStreamInfo.argtypes = [ctypes.c_void_p]
    return lib


class PortAudioDuplex(DuplexDevice):
    """A real device: one PortAudio callback stream, input and output together.

    `device` is a `discovery.PortAudioDevice` (an "hw:" device). The stream
    runs int16 at `rate` (default: the device's native rate) with
    `in_channels` in (default: 1 if the device has a mic, as on a dongle) and
    `out_channels` out (default 2). `latency` is the suggested latency in
    seconds each way; None uses the device's "high" default, which suits a
    Python callback. Nothing is opened until `start()`.
    """

    def __init__(self, device, rate=None, frames_per_buffer=512,
                 in_channels=None, out_channels=None, input_channel=0,
                 latency=None, ring_seconds=30.0, name=""):
        if in_channels is None:
            in_channels = min(device.inputs, 1)
        if out_channels is None:
            out_channels = min(device.outputs, 2)
        if in_channels > device.inputs or out_channels > device.outputs:
            raise DeviceError(
                f"{device.name} has {device.inputs} in / {device.outputs} out "
                f"channels; {in_channels} / {out_channels} were asked for")
        rate = float(rate or device.default_rate)
        super().__init__(name or device.name, rate, frames_per_buffer,
                         in_channels, out_channels, input_channel, ring_seconds)
        self.device = device
        self.latency = latency
        self.actual = {}               # latencies and rate PortAudio settled on
        self._lib = None
        self._stream = ctypes.c_void_p()
        self._callback = _CALLBACK(self._pa_callback)

    @classmethod
    def from_card(cls, card, **kwargs):
        """Stream for an ALSA card from `discovery`."""
        device = card.pa_device()
        if device is None:
            raise DeviceError(f"PortAudio lists no hw: device for {card.label()}")
        kwargs.setdefault("name", card.id)
        return cls(device, **kwargs)

    def _check(self, code, what):
        if code >= 0:
            return
        text = self._lib.Pa_GetErrorText(code)
        text = text.decode(errors="replace") if text else str(code)
        if code == PA_HOST_ERROR:
            info = self._lib.Pa_GetLastHostErrorInfo()
            if info and info.contents.errorText:
                text += ": " + info.contents.errorText.decode(errors="replace")
        raise DeviceError(f"{what}: {text} ({self.device.name}, "
                          f"{self.rate:g} Hz, {self.in_channels} in / "
                          f"{self.out_channels} out)")

    def _start_transport(self):
        self._lib = _load_portaudio()
        with quiet():
            self._check(self._lib.Pa_Initialize(), "PortAudio would not start")
        try:
            low_in = self.latency or self.device.high_input_latency
            low_out = self.latency or self.device.high_output_latency
            params_in = _StreamParameters(
                self.device.index, self.in_channels, PA_INT16, low_in, None)
            params_out = _StreamParameters(
                self.device.index, self.out_channels, PA_INT16, low_out, None)
            self._in_pos = self._out_pos = 0
            self._time_first = self._time_last = None
            with quiet():
                self._check(self._lib.Pa_OpenStream(
                    ctypes.byref(self._stream),
                    ctypes.byref(params_in) if self.in_channels else None,
                    ctypes.byref(params_out) if self.out_channels else None,
                    self.rate, self.frames_per_buffer, 0, self._callback, None),
                    "cannot open the stream")
            try:
                info = self._lib.Pa_GetStreamInfo(self._stream).contents
                self.actual = {"input_latency_s": info.inputLatency,
                               "output_latency_s": info.outputLatency,
                               "rate": info.sampleRate}
                with quiet():
                    self._check(self._lib.Pa_StartStream(self._stream),
                                "cannot start the stream")
            except BaseException:
                self._lib.Pa_CloseStream(self._stream)
                raise
        except BaseException:
            self._lib.Pa_Terminate()
            raise

    def _stop_transport(self):
        with quiet():
            self._lib.Pa_StopStream(self._stream)      # waits for the callback
            self._lib.Pa_CloseStream(self._stream)
            self._lib.Pa_Terminate()
        self._stream = ctypes.c_void_p()

    def _pa_callback(self, inp, outp, frames, time_info, flags, user):
        try:
            n = int(frames)
            if inp and self.in_channels:
                count = n * self.in_channels
                raw = (ctypes.c_int16 * count).from_address(inp)
                indata = np.frombuffer(raw, dtype=np.int16).reshape(
                    n, self.in_channels)
            else:
                indata = np.zeros((n, max(self.in_channels, 1)), dtype=np.int16)
            ti = time_info.contents
            out = self._process(indata, int(flags), ti.inputBufferAdcTime,
                                ti.outputBufferDacTime, ti.currentTime)
            if outp and self.out_channels:
                ctypes.memmove(outp, out.ctypes.data, n * self.out_channels * 2)
            return PA_CONTINUE
        except BaseException as error:        # never let it reach PortAudio
            self._error = error
            return PA_ABORT

    def describe(self):
        info = super().describe()
        info.update(portaudio_index=self.device.index,
                    portaudio_name=self.device.name, actual=dict(self.actual))
        return info
