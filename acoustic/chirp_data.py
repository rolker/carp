"""Sending a few bytes as sound, the way LoRa sends them by radio.

Chirp spread spectrum: every symbol is one chirp that sweeps the whole band
from bottom to top. The data is in where the sweep starts. A symbol with
value s starts s steps up the band, runs to the top, wraps to the bottom and
finishes where it began. The receiver multiplies each symbol by a chirp
running the other way, which turns it into a steady tone, and the tone's
pitch says where the sweep started.

Why this suits the ranging work: a chirp is what the matched filter already
handles well, it survives narrow and uneven bands, and a late echo only
shifts the tone by a bin or two instead of destroying the symbol.

A message on the air:
  preamble   6 plain up-chirps (symbol 0), then 2 down-chirps
  frame      length byte, payload, CRC-16

The two down-chirps mark where the frame starts. The up-chirp just before
them is used to measure how far the tones are shifted (by the echo the
receiver locked on to, or a small timing error), and that shift is taken
out of every symbol.

No audio hardware here: modulate() makes samples, demodulate() reads a
recording.
"""
from dataclasses import dataclass, field

import numpy as np
from scipy import signal

import ranging_dsp as dsp

PREAMBLE_UPS = 6
SYNC_DOWNS = 2
RAMP = 0.005        # fade at each end of a message, s
DETECT = 8.0        # the sync must stand this far above the noise


@dataclass
class DataConfig:
    rate: int = 48000
    f0: float = 13000.0         # bottom of the band, Hz
    f1: float = 17000.0         # top of the band, Hz (adjusted, see symbol_samples)
    spread: int = 7             # 2**spread steps across the band, per symbol
    bits: int = 5               # bits carried per symbol, at most `spread`
    amplitude: float = 0.3

    def check(self):
        if not 4 <= self.spread <= 10:
            raise ValueError("spread must be between 4 and 10")
        if not 1 <= self.bits <= self.spread:
            raise ValueError("bits per symbol must be between 1 and the spread")
        if self.f0 <= 0 or self.f1 - self.f0 < 500:
            raise ValueError("the band must be at least 500 Hz wide")
        if self.f1 > 0.45 * self.rate:
            raise ValueError(
                f"{self.f1:.0f} Hz is too high for a {self.rate} Hz sample rate")

    @property
    def steps(self):
        return 2 ** self.spread

    @property
    def symbol_samples(self):
        """Samples per symbol. The bandwidth is nudged so this is a whole
        number, which keeps every tone exactly on a bin."""
        return int(round(self.steps * self.rate / (self.f1 - self.f0)))

    @property
    def bandwidth(self):
        return self.steps * self.rate / self.symbol_samples

    @property
    def symbol_time(self):
        return self.symbol_samples / self.rate

    @property
    def bit_rate(self):
        return self.bits / self.symbol_time

    def message_time(self, payload_bytes):
        symbols = -(-8 * (payload_bytes + 3) // self.bits)
        return (PREAMBLE_UPS + SYNC_DOWNS + symbols) * self.symbol_time


def _phase(config, start_step, down=False):
    """Phase of one symbol, sample by sample."""
    n = config.symbol_samples
    position = (start_step / config.steps + np.arange(n) / n) % 1.0
    if down:
        position = 1.0 - position
    frequency = config.f0 + position * config.bandwidth
    return 2 * np.pi * np.cumsum(frequency) / config.rate


def _gray(value):
    return value ^ (value >> 1)


def _ungray(value):
    out = 0
    while value:
        out ^= value
        value >>= 1
    return out


def crc16(data):
    """CRC-16/CCITT-FALSE."""
    crc = 0xFFFF
    for byte in data:
        crc ^= byte << 8
        for _ in range(8):
            crc = ((crc << 1) ^ 0x1021 if crc & 0x8000 else crc << 1) & 0xFFFF
    return crc


def frame_symbols(payload, config):
    """Payload bytes -> symbol values (0 .. 2**bits - 1)."""
    if len(payload) > 255:
        raise ValueError("at most 255 bytes per message")
    frame = bytes([len(payload)]) + bytes(payload)
    frame += crc16(frame).to_bytes(2, "big")
    bits = np.unpackbits(np.frombuffer(frame, dtype=np.uint8))
    bits = np.concatenate([bits, np.zeros(-bits.size % config.bits, np.uint8)])
    weights = 1 << np.arange(config.bits - 1, -1, -1)
    return [int(v) for v in bits.reshape(-1, config.bits) @ weights]


def modulate(payload, config):
    """Payload bytes -> float32 samples of the whole message."""
    config.check()
    spacing = config.steps >> config.bits       # steps between used start points
    parts = [np.cos(_phase(config, 0)) for _ in range(PREAMBLE_UPS)]
    parts += [np.cos(_phase(config, 0, down=True)) for _ in range(SYNC_DOWNS)]
    parts += [np.cos(_phase(config, _gray(v) * spacing))
              for v in frame_symbols(payload, config)]
    samples = np.concatenate(parts)
    ramp = int(RAMP * config.rate)
    window = np.ones(samples.size)
    window[:ramp] = np.sin(np.linspace(0, np.pi / 2, ramp)) ** 2
    window[-ramp:] = window[:ramp][::-1]
    return (config.amplitude * samples * window).astype(np.float32)


@dataclass
class DataResult:
    found: bool = False             # was a preamble found at all
    ok: bool = False                # did the CRC check out
    payload: bytes = b""
    sync_snr: float = 0.0           # sync peak over the typical noise level
    shift: int = 0                  # tone shift taken out, in steps
    symbol_snr: list = field(default_factory=list)   # per symbol, dB
    tones: np.ndarray = None        # symbols x steps, power, for display
    picked: list = field(default_factory=list)       # chosen step per symbol
    message: str = ""


def _tone_powers(analytic, start, config, reference):
    """Power at each of the 2**spread start points for the symbol at `start`."""
    n, steps = config.symbol_samples, config.steps
    if start < 0 or start + n > analytic.size:
        return None
    spectrum = np.abs(np.fft.fft(analytic[start:start + n] * reference)) ** 2
    # Before the wrap the tone is at +s bins, after it at s - steps.
    return spectrum[:steps] + spectrum[np.arange(steps) - steps]


def demodulate(recording, config):
    """Find one message in a recording and decode it."""
    config.check()
    result = DataResult()
    n, steps = config.symbol_samples, config.steps
    recording = np.asarray(recording, dtype=np.float64)
    if recording.size < (PREAMBLE_UPS + SYNC_DOWNS + 2) * n:
        result.message = "recording too short"
        return result
    if np.max(np.abs(recording)) < 10 ** (-70 / 20):
        result.message = "recording is silent"
        return result

    sync = np.concatenate([np.cos(_phase(config, 0, down=True))] * SYNC_DOWNS)
    envelope = dsp.matched_filter(recording, sync)
    peak = int(np.argmax(envelope))
    result.sync_snr = float(envelope[peak] / (np.median(envelope) or 1e-12))
    if result.sync_snr < DETECT:
        result.message = "no message found"
        return result
    result.found = True

    analytic = signal.hilbert(recording - recording.mean())
    reference = np.exp(-1j * _phase(config, 0))
    # The last plain up-chirp before the sync should give tone 0. Whatever
    # it gives instead is the shift to take out of every symbol.
    calibration = _tone_powers(analytic, peak - n, config, reference)
    if calibration is not None:
        shift = int(np.argmax(calibration))
        result.shift = shift - steps if shift > steps // 2 else shift

    spacing = steps >> config.bits
    start = peak + SYNC_DOWNS * n
    values, rows = [], []
    needed = -(-8 // config.bits)      # symbols that hold the length byte
    total = None
    while total is None or len(values) < total:
        powers = _tone_powers(analytic, start + len(values) * n, config, reference)
        if powers is None:
            result.message = "the recording ended before the message did"
            break
        powers = np.roll(powers, -result.shift)
        step = int(np.argmax(powers))
        rows.append(powers)
        result.picked.append(step)
        result.symbol_snr.append(float(10 * np.log10(
            powers[step] / (np.median(powers) or 1e-12))))
        values.append(_ungray(((step + spacing // 2) // spacing) % (1 << config.bits)))
        if total is None and len(values) >= needed:
            length = _bits_to_bytes(values, config)[0]
            total = -(-8 * (length + 3) // config.bits)
    result.tones = np.array(rows) if rows else None
    if total is None or len(values) < total:
        return result
    frame = _bits_to_bytes(values, config)[:1 + frame_length(values, config) + 2]
    body, received = frame[:-2], int.from_bytes(frame[-2:], "big")
    result.payload = bytes(body[1:])
    result.ok = crc16(bytes(body)) == received
    result.message = "received" if result.ok else "received with errors (CRC failed)"
    return result


def frame_length(values, config):
    return _bits_to_bytes(values, config)[0]


def _bits_to_bytes(values, config):
    bits = np.array([(v >> i) & 1 for v in values
                     for i in range(config.bits - 1, -1, -1)], dtype=np.uint8)
    return np.packbits(bits[:bits.size - bits.size % 8]).tobytes()


def bit_errors(sent, received):
    """Number of differing bits between two byte strings of any lengths
    (a missing byte counts as 8 errors), and the bits compared."""
    longest = max(len(sent), len(received))
    a = np.unpackbits(np.frombuffer(bytes(sent).ljust(longest, b"\0"), np.uint8))
    b = np.unpackbits(np.frombuffer(bytes(received).ljust(longest, b"\0"), np.uint8))
    missing = 8 * abs(len(sent) - len(received))
    shortest = 8 * min(len(sent), len(received))
    return int(np.count_nonzero(a[:shortest] != b[:shortest])) + missing, 8 * longest


def simulate_channel(samples, rate, index=0, noise=0.01, echoes=((2.0, 0.5),),
                     lead_in=0.25, tail=0.2):
    """What a microphone might record: the message, late copies of it
    (delay in ms, gain) and noise."""
    rng = np.random.default_rng(index)
    longest = max([0.0] + [ms for ms, _ in echoes]) / 1e3
    total = int((lead_in + longest + tail) * rate) + samples.size
    recording = rng.normal(0.0, noise, total)
    for delay_ms, gain in ((0.0, 1.0),) + tuple(echoes):
        at = int(round((lead_in + delay_ms / 1e3) * rate))
        recording[at:at + samples.size] += gain * samples
    return recording.astype(np.float32)
