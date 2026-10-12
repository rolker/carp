"""A device with no hardware, behind the same interface as `PortAudioDuplex`.

It runs the same `DuplexDevice._process` for every block, so the scheduler,
ring and xrun log are the real ones. What it adds is the world around them:
a loopback from one output channel into the input with a delay, a gain and
noise, and optionally faults.

Two ways to run:

- `realtime=False` (default): no thread. Time only moves when the caller
  waits (`wait_input`) or calls `advance`, and then as fast as the computer
  can go. Fully deterministic, which is what the tests need. A five-minute
  run takes seconds.
- `realtime=True`: a thread produces blocks at the device's pace
  (`speed` times real time), like hardware.

Delays are in samples and may be fractional.
"""
import threading
import time

import numpy as np

from .stream import (DeviceError, DuplexDevice, INPUT_OVERFLOW,
                     INPUT_UNDERFLOW, OUTPUT_OVERFLOW, OUTPUT_UNDERFLOW)

KERNEL_HALF = 8             # taps either side of the point, fractional delay


class FakeDevice(DuplexDevice):
    """Simulated dongle: stereo out, mono in, loopback from one output.

    rate: Hz. in_latency, out_latency: samples (any real number); the
    loopback copy of output sample n appears at input sample
    n + in_latency + out_latency (+ drift). loopback: feed `loopback_channel`
    into the input through `loopback_gain` (linear). noise_rms: input noise
    in int16 steps. offset_drift: loopback delay change in samples per
    second. clock_ppm: how much faster than nominal this device's clock runs
    against the (pretend) system clock, parts per million; it shows in
    `timing()["clock_ratio"]` and in the pace when `realtime`. xruns: list of
    (sample, flags) to inject; the block holding that sample is flagged,
    and its input (overflow, underflow on input) or its output (underflow,
    overflow on output) is lost. pa_error: samples by which the
    PortAudio-style time stamps are wrong, so a test can show the claim is
    not trusted. seed: for the noise.
    """

    def __init__(self, rate=48000.0, frames_per_buffer=256, in_latency=120.0,
                 out_latency=240.0, loopback=True, loopback_channel=0,
                 loopback_gain=0.5, noise_rms=2.0, offset_drift=0.0,
                 clock_ppm=0.0, xruns=(), pa_error=0.0, realtime=False,
                 speed=1.0, in_channels=1, out_channels=2, ring_seconds=30.0,
                 seed=0, name="fake"):
        super().__init__(name, rate, frames_per_buffer, in_channels,
                         out_channels, 0, ring_seconds)
        self.in_latency = float(in_latency)
        self.out_latency = float(out_latency)
        self.loopback = loopback
        self.loopback_channel = loopback_channel
        self.loopback_gain = loopback_gain
        self.noise_rms = noise_rms
        self.offset_drift = offset_drift
        self.clock_ppm = clock_ppm
        self.pa_error = pa_error
        self.realtime = realtime
        self.speed = speed
        self._pending_xruns = sorted(xruns)
        self._rng = np.random.default_rng(seed)
        if loopback:
            need = frames_per_buffer + KERNEL_HALF + 2
            if self.in_latency + self.out_latency < need:
                raise ValueError(
                    f"in_latency + out_latency must be at least {need} "
                    "samples (a block plus the interpolation reach), as on "
                    "real hardware where a block is always in flight")
            if loopback_channel >= out_channels:
                raise ValueError("loopback_channel does not exist")
        self._history = np.zeros(int(ring_seconds * rate) + 4096)
        self._taps = np.arange(-KERNEL_HALF + 1, KERNEL_HALF + 1)
        self._thread = None
        self._stop = threading.Event()

    # -- the simulated world -------------------------------------------------

    def loopback_delay(self, sample=0):
        """True delay from an output sample to its loopback copy, in samples,
        for an output sample number `sample`."""
        return (self.in_latency + self.out_latency +
                self.offset_drift * sample / self.rate)

    def _clock_time(self, sample):
        return 1000.0 + sample / (self.rate * (1.0 + self.clock_ppm * 1e-6))

    def _loopback_block(self, start, n):
        """Loopback signal for input samples start..start+n, from the output
        history, with a windowed-sinc fractional delay."""
        positions = (start + np.arange(n)) - (
            self.in_latency + self.out_latency +
            self.offset_drift * (start + np.arange(n)) / self.rate)
        base = np.floor(positions).astype(np.int64)
        frac = positions - base
        index = base[:, None] + self._taps[None, :]
        x = self._taps[None, :] - frac[:, None]
        weights = np.sinc(x) * (0.5 * (1.0 + np.cos(np.pi * x / (KERNEL_HALF + 0.5))))
        valid = (index >= 0) & (index < start)
        history = self._history[np.where(valid, index % len(self._history), 0)]
        return np.sum(np.where(valid, history, 0.0) * weights, axis=1)

    def _pump_block(self):
        n = self.frames_per_buffer
        start = self._out_pos
        status = 0
        lose_in = lose_out = False
        while self._pending_xruns and self._pending_xruns[0][0] < start + n:
            sample, flags = self._pending_xruns.pop(0)
            if sample >= start:
                status |= flags
                lose_in |= bool(flags & (INPUT_UNDERFLOW | INPUT_OVERFLOW))
                lose_out |= bool(flags & (OUTPUT_UNDERFLOW | OUTPUT_OVERFLOW))
        indata = np.zeros((n, max(self.in_channels, 1)))
        if self.loopback:
            indata[:, 0] += self.loopback_gain * self._loopback_block(start, n)
        if self.noise_rms:
            indata += self._rng.normal(0.0, self.noise_rms, indata.shape)
        indata = np.clip(np.rint(indata), -32768, 32767).astype(np.int16)
        if lose_in:
            indata[:] = 0
        now = self._clock_time(start)
        out = self._process(
            indata, status, now - self.in_latency / self.rate,
            now + (self.out_latency + self.pa_error) / self.rate, now)
        if lose_out:
            out[:] = 0
        self._history[(start + np.arange(n)) % len(self._history)] = (
            out[:, self.loopback_channel])

    # -- driving it --------------------------------------------------------

    def advance(self, frames):
        """Run blocks until at least `frames` more samples have passed
        (non-realtime only)."""
        if self.realtime:
            raise DeviceError("a realtime fake advances by itself")
        if not self._running:
            raise DeviceError("the stream is not running")
        target = self._out_pos + frames
        while self._out_pos < target:
            self._pump_block()

    def _wait(self, done, deadline):
        if self.realtime:
            return super()._wait(done, deadline)
        if not self._running:
            raise DeviceError("the stream is not running")
        # Time is pretend: a timeout (monotonic) still bounds the loop in
        # case `done` can never become true, but is not otherwise used.
        guard = 0
        while not done():
            self._pump_block()
            guard += 1
            if guard > 50_000_000 // self.frames_per_buffer:
                return False
        return True

    def _start_transport(self):
        self._in_pos = self._out_pos = 0
        self._time_first = self._time_last = None
        self._history[:] = 0
        if self.realtime:
            self._stop.clear()
            self._thread = threading.Thread(target=self._run, daemon=True)
            self._thread.start()

    def _run(self):
        wall0 = time.monotonic()
        try:
            while not self._stop.is_set():
                self._pump_block()
                due = wall0 + (self._out_pos / self.rate) / self.speed / (
                    1.0 + self.clock_ppm * 1e-6)
                delay = due - time.monotonic()
                if delay > 0:
                    self._stop.wait(delay)
        except BaseException as error:
            self._error = error

    def _stop_transport(self):
        if self._thread is not None:
            self._stop.set()
            self._thread.join(2.0)
            self._thread = None
