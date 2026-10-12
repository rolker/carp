"""The duplex stream core, driven through the fake device (no hardware)."""
import ctypes

import numpy as np
import pytest

from acoustics_lab.hardware import stream
from acoustics_lab.hardware.discovery import PortAudioDevice
from acoustics_lab.hardware.fake import FakeDevice
from acoustics_lab.hardware.stream import (DeviceError, LateError,
                                           LostDataError)


def exact(**kwargs):
    """A fake whose loopback is a clean whole-sample delay of 700 samples."""
    options = dict(in_latency=300.0, out_latency=400.0, loopback_gain=1.0,
                   noise_rms=0.0)
    options.update(kwargs)
    return FakeDevice(**options)


def impulse(value=1000):
    return np.array([value], dtype=np.int16)


def test_scheduled_sample_comes_back_at_the_loopback_delay():
    with exact() as dev:
        for start in (5000, 5001, 5255, 5256, 7777):
            dev.schedule(impulse(), start)
        dev.wait_input(9000)
        heard = dev.read_input(0, 9000)
        assert sorted(np.flatnonzero(heard)) == [5700, 5701, 5955, 5956, 8477]
        assert set(heard[np.flatnonzero(heard)]) == {1000}


def test_a_fractional_delay_is_interpolated():
    with exact(in_latency=300.25) as dev:
        dev.schedule(np.array([0, 0, 1000, 0, 0], dtype=np.int16), 5000)
        dev.wait_input(6000)
        heard = dev.read_input(5600, 5900).astype(float)
        centre = np.sum(np.arange(5600, 5900) * heard) / heard.sum()
        assert centre == pytest.approx(5000 + 2 + 700.25, abs=0.05)


def test_items_are_mixed_and_clipped():
    with exact() as dev:
        dev.schedule(impulse(20000), 4000)
        dev.schedule(impulse(15000), 4000)
        dev.schedule(impulse(500), 4001)
        dev.schedule(np.array([100, 100, 100], dtype=np.int16), 4000)
        dev.wait_input(5000)
        heard = dev.read_input(4700, 4704)
        assert list(heard) == [32767, 600, 100, 0]


def test_float_samples_are_full_scale_and_gain_is_linear():
    with exact() as dev:
        dev.schedule(np.array([0.5]), 4000, gain=0.5)
        dev.wait_input(5000)
        assert dev.read_input(4700, 4701)[0] == round(0.25 * 32767)


def test_channels_are_separate():
    with exact() as dev:               # the loopback is wired to the left output
        dev.schedule(impulse(), 4000, channel="right")
        dev.schedule(impulse(), 4100, channel="left")
        dev.schedule(impulse(), 4200, channel="both")
        dev.wait_input(5000)
        assert sorted(np.flatnonzero(dev.read_input(0, 5000))) == [4800, 4900]
        with pytest.raises(ValueError):
            dev.schedule(impulse(), 4300, channel=5)


def test_a_late_item_is_rejected_or_played_in_part():
    with exact() as dev:
        dev.wait_input(3000)
        now = dev.out_position
        with pytest.raises(LateError) as caught:
            dev.schedule(impulse(), now - 10)
        assert caught.value.late_by == 10
        assert dev.pending() == []
        item = dev.schedule(np.full(40, 300, dtype=np.int16), now - 10,
                            late="play")
        assert item.skipped == 10
        dev.wait_input(now + 2000)
        played = dev.read_input(now + 690, now + 760)
        assert np.count_nonzero(played) == 30


def test_an_item_on_time_reports_nothing_lost():
    with exact() as dev:
        dev.wait_input(3000)
        start = dev.out_position + 100
        item = dev.schedule(np.full(500, 100, dtype=np.int16), start)
        dev.wait_input(start + 1000)
        assert item.started and item.skipped == 0


def test_cancel_only_works_before_it_starts():
    with exact() as dev:
        dev.wait_input(3000)
        far = dev.schedule(impulse(), dev.out_position + 10000)
        assert dev.cancel(far) and dev.pending() == []
        near = dev.schedule(impulse(), dev.out_position + 1)
        assert not dev.cancel(near)


def test_scheduling_needs_a_running_stream():
    dev = exact()
    with pytest.raises(DeviceError):
        dev.schedule(impulse(), 100)
    dev.start()
    dev.stop()
    dev.stop()                       # harmless twice
    with pytest.raises(DeviceError):
        dev.wait_input(10)


def test_counter_restarts_with_the_stream():
    dev = exact()
    dev.start()
    dev.wait_input(5000)
    dev.stop()
    dev.start()
    assert dev.in_position == 0 and dev.out_position == 0
    dev.stop()


def test_the_ring_wraps_and_reads_stay_correct():
    with exact(ring_seconds=0.5) as dev:          # 24000 samples
        assert dev.capacity == 24000
        marks = [10_000 + 7000 * k for k in range(8)]
        for m in marks:
            dev.schedule(impulse(m // 100), m)
        dev.wait_input(marks[-1] + 2000)
        end = dev.in_position
        assert end > 2 * dev.capacity
        for start in (end - 24000, end - 23000, end - 5001):
            heard = dev.read_input(start, end)
            where = np.flatnonzero(heard) + start
            expected = [m + 700 for m in marks if start <= m + 700 < end]
            assert list(where) == expected
        with pytest.raises(LostDataError, match="overwritten"):
            dev.read_input(end - 24001, end)
        with pytest.raises(LostDataError, match="not been captured"):
            dev.read_input(end - 10, end + 1)
        assert len(dev.read_input(end - 10, end - 10)) == 0


def test_a_read_across_the_wrap_point_is_continuous():
    with exact(ring_seconds=0.5, frames_per_buffer=256, in_latency=400,
               out_latency=400) as dev:
        ramp = (np.arange(30000) % 20000).astype(np.int16)
        dev.schedule(ramp, 1000, gain=1.0)
        dev.wait_input(40000)
        got = dev.read_input(24000, 40000)       # wraps inside the ring
        assert got.dtype == np.int16
        want = np.zeros(16000, dtype=np.int16)
        for i, n in enumerate(range(24000, 40000)):
            k = n - 1000 - 800
            if 0 <= k < 30000:
                want[i] = k % 20000
        assert np.array_equal(got, want)


def test_xruns_are_counted_logged_and_cover_their_block():
    flags = stream.INPUT_OVERFLOW | stream.OUTPUT_UNDERFLOW
    with exact(xruns=[(10_000, stream.INPUT_OVERFLOW), (20_000, flags)]) as dev:
        dev.wait_input(30_000)
        assert dev.xrun_count == 2
        events = dev.xruns()
        assert events[0].kinds == ["input overflow"]
        assert events[1].kinds == ["input overflow", "output underflow"]
        for event, sample in zip(events, (10_000, 20_000)):
            assert event.sample <= sample < event.sample + event.frames
            assert event.sample % 256 == 0           # at a block start
        assert dev.xrun_counts()["input overflow"] == 2
        assert dev.xrun_counts()["output underflow"] == 1
        assert dev.xruns_between(0, 9000) == []
        assert len(dev.xruns_between(9000, 10_001)) == 1
        assert dev.xruns_between(10_000 + 256, 19_000) == []
        assert len(dev.xruns_between(0, 30_000)) == 2


def test_an_output_underflow_loses_the_audio_of_that_block():
    with exact(xruns=[(5000, stream.OUTPUT_UNDERFLOW)]) as dev:
        dev.schedule(impulse(), 5000)      # in the flagged block: lost
        dev.schedule(impulse(), 6000)
        dev.wait_input(8000)
        assert list(np.flatnonzero(dev.read_input(0, 8000))) == [6700]


def test_an_input_overflow_loses_the_input_of_that_block():
    with exact(xruns=[(5700, stream.INPUT_OVERFLOW)]) as dev:
        dev.schedule(impulse(), 5000)
        dev.schedule(impulse(), 6000)
        dev.wait_input(8000)
        heard = dev.read_input(0, 8000)
        assert np.flatnonzero(heard).tolist() == [6700]
        assert dev.xruns_between(5700, 5701)


def test_portaudio_time_stamps_are_kept_but_can_be_wrong():
    with exact(pa_error=12.0, clock_ppm=250.0) as dev:
        dev.wait_input(3 * 48000)
        timing = dev.timing()
        assert timing["claimed_offset_samples"] == pytest.approx(712.0, abs=0.01)
        assert timing["clock_ratio"] == pytest.approx(1.00025, abs=1e-6)
        assert dev.loopback_delay() == 700.0     # the truth differs from the claim


def test_the_loopback_delay_can_drift():
    with exact(offset_drift=0.5) as dev:         # half a sample per second
        dev.schedule(impulse(), 5000)
        dev.schedule(impulse(), 5000 + 4 * 48000)
        dev.wait_input(5000 + 4 * 48000 + 2000)
        heard = np.abs(dev.read_input(0, 5000 + 4 * 48000 + 2000).astype(float))
        first = int(np.argmax(heard[:100_000]))
        second = 100_000 + int(np.argmax(heard[100_000:]))
        assert first == 5700
        assert second - (5000 + 4 * 48000) == 702      # 700 + 0.5 * 4 s


def test_a_realtime_fake_runs_on_its_own_clock():
    with exact(realtime=True, speed=40.0) as dev:
        dev.schedule(impulse(), 20_000)
        assert dev.wait_input(30_000, timeout=5)
        assert list(np.flatnonzero(dev.read_input(0, 30_000))) == [20_700]
        assert not dev.wait_input(10**9, timeout=0.05)


def test_the_fake_refuses_a_loopback_shorter_than_a_block():
    with pytest.raises(ValueError, match="at least"):
        FakeDevice(in_latency=10, out_latency=10)


# -- the real device's callback, called by hand ------------------------------------

def portaudio_stand_in(**kwargs):
    info = PortAudioDevice(index=3, name="USB Audio (hw:1,0)", pcm=0,
                           inputs=1, outputs=2, default_rate=48000.0)
    dev = stream.PortAudioDuplex(info, frames_per_buffer=64, **kwargs)
    dev._running = True            # without opening anything
    return dev


def call(dev, incoming, flags=0):
    """Run the C callback the way PortAudio would; returns the output array."""
    n = len(incoming) // dev.in_channels
    inbuf = (ctypes.c_int16 * len(incoming))(*incoming)
    outbuf = (ctypes.c_int16 * (n * dev.out_channels))()
    info = stream._TimeInfo(10.0, 10.5, 10.75)
    code = dev._pa_callback(ctypes.addressof(inbuf), ctypes.addressof(outbuf), n,
                            ctypes.pointer(info), flags, None)
    assert code == stream.PA_CONTINUE
    return np.frombuffer(outbuf, dtype=np.int16).reshape(n, dev.out_channels).copy()


def test_the_c_callback_fills_the_ring_and_the_output():
    dev = portaudio_stand_in()
    assert (dev.in_channels, dev.out_channels, dev.rate) == (1, 2, 48000.0)
    dev.schedule(np.arange(1, 101, dtype=np.int16), 64 + 10, channel="right")
    first = call(dev, list(range(64)))
    second = call(dev, list(range(64, 128)))
    assert not first.any()
    assert not second[:, 0].any()
    assert list(second[10:54, 1]) == list(range(1, 45))
    assert list(dev.read_input(0, 128)) == list(range(128))
    third = call(dev, [0] * 64)
    assert list(third[:46, 1]) == list(range(55, 101))
    assert not third[46:].any()
    assert dev.out_position == 192
    assert dev.timing()["blocks"] == 3


def test_the_c_callback_logs_xrun_flags_and_ignores_priming():
    dev = portaudio_stand_in()
    call(dev, [0] * 64, flags=stream.PRIMING_OUTPUT)
    assert dev.xrun_count == 0
    call(dev, [0] * 64, flags=stream.INPUT_OVERFLOW | stream.PRIMING_OUTPUT)
    call(dev, [0] * 64, flags=stream.OUTPUT_UNDERFLOW)
    assert dev.xrun_count == 2
    assert [e.sample for e in dev.xruns()] == [64, 128]


def test_a_failing_callback_aborts_instead_of_raising_into_portaudio():
    dev = portaudio_stand_in()
    code = dev._pa_callback(None, None, 64, None, 0, None)
    assert code == stream.PA_ABORT and dev._error is not None
    with pytest.raises(DeviceError, match="failed"):
        dev.wait_input(10)


def test_a_dongle_with_a_stereo_mic_or_too_many_channels():
    info = PortAudioDevice(3, "x (hw:1,0)", 0, 2, 2, 48000.0)
    dev = stream.PortAudioDuplex(info, in_channels=2, input_channel=1)
    assert dev.in_channels == 2 and dev.input_channel == 1
    with pytest.raises(DeviceError):
        stream.PortAudioDuplex(info, in_channels=3)
