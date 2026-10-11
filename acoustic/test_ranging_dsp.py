#!/usr/bin/env python3
"""Checks for ranging_dsp.py, pinger.py and chirp_data.py on simulated recordings. Run: python3 test_ranging_dsp.py"""
import os
import tempfile

import numpy as np

import chirp_data
import pinger
import ranging_dsp as dsp
import wav_io

RATE = 48000


def arrivals_for(delays, gains, noise=0.01, threshold=0.1):
    chirp = dsp.make_chirp(RATE, 2000, 20000, 0.02)
    recording = dsp.simulate_recording(chirp, RATE, delays, gains, noise=noise)
    envelope = dsp.matched_filter(recording, chirp)
    return dsp.find_arrivals(envelope, RATE, threshold)


def test_chirp_shape():
    chirp = dsp.make_chirp(RATE, 2000, 20000, 0.02)
    assert chirp.size == 960
    assert abs(float(np.max(np.abs(chirp))) - 1.0) < 0.05
    assert abs(float(chirp[0])) < 1e-6


def test_chirp_rejects_band_above_nyquist():
    try:
        dsp.make_chirp(RATE, 2000, 23000, 0.02)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_delay_is_recovered_to_a_fraction_of_a_sample():
    # 1.5 m in air: not a whole number of samples.
    delay = 1.5 / dsp.sound_speed_air(20.0)
    arrivals = arrivals_for([0.0, delay], [0.2, 0.05])
    assert len(arrivals) == 2
    measured = (arrivals[1].sample - arrivals[0].sample) / RATE
    assert abs(measured - delay) * RATE < 0.1, (measured, delay)


def test_weak_echo_is_found_and_ordered_by_time():
    arrivals = arrivals_for([0.0, 0.004, 0.0065], [0.3, 0.02, 0.05],
                            threshold=0.03)
    assert len(arrivals) == 3
    delays = [(a.sample - arrivals[0].sample) / RATE for a in arrivals]
    assert abs(delays[1] - 0.004) < 1e-5 and abs(delays[2] - 0.0065) < 1e-5
    assert arrivals[1].level < arrivals[2].level < arrivals[0].level


def test_narrow_band_sidelobes_are_not_reported_as_arrivals():
    # 4-7 kHz is roughly what a piezo disc passes in air. With a lightly
    # tapered chirp, a -14 dB sidelobe ahead of the loopback copy was taken
    # as the first arrival.
    chirp = dsp.make_chirp(RATE, 4000, 7000, 0.01)
    delay = 1.0 / dsp.sound_speed_air(20.0)
    recording = dsp.simulate_recording(chirp, RATE, [0.0, delay], [0.2, 0.05])
    arrivals = dsp.find_arrivals(dsp.matched_filter(recording, chirp), RATE)
    assert len(arrivals) == 2
    measured = (arrivals[1].sample - arrivals[0].sample) / RATE
    assert abs(measured - delay) * RATE < 0.5, (measured, delay)
    assert arrivals[0].level > arrivals[1].level


def test_sidelobes_are_well_below_the_default_threshold():
    chirp = dsp.make_chirp(RATE, 2000, 20000, 0.02)
    recording = dsp.simulate_recording(chirp, RATE, [0.0], [0.2], noise=0.0)
    envelope = dsp.matched_filter(recording, chirp)
    peak = int(np.argmax(envelope))
    guard = int(dsp.resolution(2000, 20000) * RATE) + 1
    outside = np.concatenate([envelope[:peak - guard], envelope[peak + guard:]])
    assert outside.max() < 0.01 * envelope[peak]


def test_noise_alone_gives_no_strong_arrival_pair():
    chirp = dsp.make_chirp(RATE, 2000, 20000, 0.02)
    recording = dsp.simulate_recording(chirp, RATE, [0.0], [0.2])
    arrivals = dsp.find_arrivals(dsp.matched_filter(recording, chirp), RATE)
    assert len(arrivals) == 1


def test_sound_speed_air():
    assert abs(dsp.sound_speed_air(20.0) - 343.2) < 0.3
    assert abs(dsp.sound_speed_air(0.0) - 331.3) < 0.01


def test_wav_round_trip():
    chirp = dsp.make_chirp(RATE, 2000, 20000, 0.02)
    recording = dsp.simulate_recording(chirp, RATE, [0.0, 0.003], [0.2, 0.05])
    with tempfile.TemporaryDirectory() as folder:
        path = os.path.join(folder, "t.wav")
        wav_io.write_wav(path, recording, RATE)
        loaded, rate = wav_io.read_wav(path)
    assert rate == RATE and loaded.size == recording.size
    assert float(np.max(np.abs(loaded - recording))) < 1e-4 + 1 / 32767


SETUP = pinger.Setup()


def test_pinger_tells_left_from_right_by_the_gap():
    design = pinger.default_design()
    result = pinger.analyse(pinger.simulate(design, SETUP), design, SETUP)
    assert result.detected() == [0, 1]
    # Simulated paths: left 1.5 m, right 1.9 m.
    extra = result.delay_ms(1) - result.delay_ms(0)
    assert abs(extra * SETUP.sound_speed / 1e3 - 0.4) < 0.01, extra


def test_pinger_finds_a_weak_left_before_a_loud_right():
    # As heard from the TV on 2026-10-11: the left chirp 18 dB below the right.
    design = pinger.default_design()
    chirp, speed = design.signals[0].samples(RATE), SETUP.sound_speed
    recording = dsp.simulate_recording(
        chirp, RATE, [1.5 / speed, 0.15 + 1.9 / speed], [0.006, 0.05],
        noise=0.002)
    result = pinger.analyse(recording, design, SETUP)
    assert result.detected() == [0, 1]
    assert result.events[1].level > 5 * result.events[0].level
    assert abs(result.delay_ms(0) * speed / 1e3 + 0.4) < 0.01


def test_pinger_chain_of_three_on_one_channel_with_a_second_signal():
    design = pinger.Design(
        signals=[pinger.Signal("up", 2000, 20000), pinger.Signal("low", 3000, 8000, 0.03)],
        events=[pinger.Event("left", "up", 0.0), pinger.Event("left", "up", 0.1),
                pinger.Event("right", "low", 0.2), pinger.Event("left", "up", 0.3)])
    design.check(RATE)
    playback = pinger.build_playback(design, SETUP)
    assert np.count_nonzero(np.abs(playback[:, 0]) > 0.01) > 3 * 400
    result = pinger.analyse(pinger.simulate(design, SETUP), design, SETUP)
    assert result.detected() == [0, 1, 2, 3]
    # The three repeats on the left all took the same path.
    assert max(abs(result.delay_ms(i) - result.delay_ms(0)) for i in (1, 3)) < 0.01
    assert abs((result.delay_ms(2) - result.delay_ms(0)) * SETUP.sound_speed / 1e3 - 0.4) < 0.02


def test_pinger_failures_are_reported_not_invented():
    design = pinger.default_design()
    silent = pinger.analyse(np.zeros(40000, np.float32), design, SETUP)
    assert not silent.detected() and "silent" in silent.warnings[0]
    noise = np.random.default_rng(0).normal(0, 0.01, 40000).astype(np.float32)
    assert not pinger.analyse(noise, design, SETUP).detected()
    # Only the left chirp present: one event heard, with a warning.
    alone = pinger.Design(design.signals, design.events[:1])
    result = pinger.analyse(pinger.simulate(alone, SETUP), design, SETUP)
    assert len(result.detected()) == 1 and result.warnings


def test_same_signal_at_the_same_time_is_flagged_as_one_sound():
    # Roland's design of 2026-10-11: left three times, right along with the third.
    design = pinger.Design(
        signals=[pinger.Signal("s", 15000, 17000, 0.035)],
        events=[pinger.Event("left", "s", 0.0), pinger.Event("left", "s", 0.1),
                pinger.Event("left", "s", 0.2), pinger.Event("right", "s", 0.2)])
    assert design.inseparable() == [[2, 3]]
    result = pinger.analyse(pinger.simulate(design, SETUP), design, SETUP)
    rows = pinger.rows(result)
    assert rows[2]["combined_with"] == [4] and rows[3]["combined_with"] == [3]
    assert rows[0]["combined_with"] == []
    assert rows[2]["delay_ms"] == rows[3]["delay_ms"]
    assert any("cannot be told apart" in w for w in result.warnings)
    assert pinger.default_design().inseparable() == []


def test_up_and_down_chirps_in_one_band_are_flagged_as_leaking():
    # Roland's design of 2026-10-11: 16-14 kHz on the left against 14-16 kHz
    # on the right, together. The left "arrived" 1.7 ms early: a leak.
    design = pinger.Design(
        signals=[pinger.Signal("down", 16000, 14000), pinger.Signal("up", 14000, 16000)],
        events=[pinger.Event("left", "down", 0.0), pinger.Event("right", "up", 0.0)])
    (i, j, isolation), = design.leaking(RATE)
    assert (i, j) == (0, 1) and -25 < isolation < -5, isolation
    result = pinger.analyse(pinger.simulate(design, SETUP), design, SETUP)
    assert any("leaks" in w for w in result.warnings)
    # Separate bands, or the same pair far apart in time, are fine.
    split = pinger.Design(
        signals=[pinger.Signal("lo", 2000, 9000, 0.03), pinger.Signal("hi", 11000, 20000, 0.03)],
        events=[pinger.Event("left", "lo", 0.0), pinger.Event("right", "hi", 0.0)])
    assert split.leaking(RATE) == []
    design.events[1].time = 0.2
    assert design.leaking(RATE) == []


def test_design_check_and_json_round_trip():
    design = pinger.default_design()
    again = pinger.Design.from_dict(__import__("json").loads(design.to_json()))
    assert again == design
    for bad in (pinger.Design(design.signals, []),
                pinger.Design(design.signals, [pinger.Event("left", "nope")]),
                pinger.Design([pinger.Signal("hi", 2000, 30000)],
                              [pinger.Event("left", "hi")])):
        try:
            bad.check(RATE)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def _sweep_recording(gaps=None):
    design = pinger.sweep_design(2000, 20000, 1000)
    recording = pinger.simulate_sweep(design, SETUP)
    if gaps:    # splice silence in, as a sound path that does not keep time would
        pieces, last = [], 0
        for at, length in gaps:
            pieces += [recording[last:at], np.zeros(length, np.float32)]
            last = at
        recording = np.concatenate(pieces + [recording[last:]])
    return design, recording


def test_sweep_finds_the_band_a_system_passes():
    design, recording = _sweep_recording()
    assert len(design.signals) == 18 and design.events[1].time == pinger.SWEEP_GAP
    bands = pinger.analyse_sweep(recording, design, SETUP)
    best = max(b["peak"] for b in bands)
    level = {b["f0"]: 20 * np.log10(max(b["peak"], 1e-12) / best) for b in bands}
    # Simulated system passes 4.5-13 kHz.
    assert all(level[f] > -6 for f in (6000, 8000, 10000, 11000))
    assert all(level[f] < -20 for f in (2000, 17000, 19000))
    f0, f1 = pinger.suggest_band({"left": bands})
    assert 4000 <= f0 <= 6000 and 12000 <= f1 <= 14000, (f0, f1)


def test_sweep_does_not_depend_on_the_spacing_between_bands():
    design, recording = _sweep_recording()
    _, slipped = _sweep_recording(gaps=[(20000, 240), (33000, 480), (52000, 240)])
    plain = pinger.analyse_sweep(recording, design, SETUP)
    moved = pinger.analyse_sweep(slipped, design, SETUP)
    assert pinger.suggest_band({"x": plain}) == pinger.suggest_band({"x": moved})
    for a, b in zip(plain, moved):
        if a["heard"] and a["snr"] > 50:
            assert abs(20 * np.log10(b["peak"] / a["peak"])) < 1.0


def test_sweep_suggestion_needs_every_channel_and_handles_silence():
    design, recording = _sweep_recording()
    bands = pinger.analyse_sweep(recording, design, SETUP)
    narrow = [dict(b, heard=b["heard"] and b["f0"] >= 9000) for b in bands]
    f0, f1 = pinger.suggest_band({"left": bands, "right": narrow})
    assert f0 == 9000 and 12000 <= f1 <= 14000
    silent = pinger.analyse_sweep(np.zeros(60000, np.float32), design, SETUP)
    assert not any(b["heard"] for b in silent)
    assert pinger.suggest_band({"left": silent}) is None
    averaged = pinger.average_sweeps([bands, bands])
    assert abs(averaged[5]["peak"] - bands[5]["peak"]) < 1e-9
    for bad in ((2000, 2500, 1000), (5000, 2000, 1000)):
        try:
            pinger.sweep_design(*bad)
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


def test_noise_spectrum_finds_a_tone_and_the_quiet_bands():
    noise = dsp.simulate_noise(RATE, 2.0)
    freqs, db = dsp.noise_spectrum(noise, RATE)
    above = freqs > 2000
    assert abs(freqs[above][np.argmax(db[above])] - 17000) < 100
    bands = {b["f0"]: b["level_db"] for b in dsp.band_levels(noise, RATE)}
    assert bands[17000.0] > bands[10000.0] + 3
    assert bands[0.0] > bands[10000.0] + 10         # the rumble
    # White noise of rms 0.003 over 24 kHz: -50.5 dBFS in all, 1/24 of it per band.
    assert abs(bands[10000.0] - (20 * np.log10(0.003) - 10 * np.log10(24))) < 1.5


DATA = chirp_data.DataConfig()
MESSAGE = b"TAT 123456 us"


def _decode(recording, config=DATA):
    return chirp_data.demodulate(recording, config)


def test_data_round_trip_with_noise_and_echoes():
    samples = chirp_data.modulate(MESSAGE, DATA)
    assert abs(samples.size / RATE - DATA.message_time(len(MESSAGE))) < 0.001
    for kwargs in (dict(noise=0.001), dict(noise=0.3), dict(noise=0.95, index=3),
                   dict(echoes=((3.0, 1.5),)),
                   dict(echoes=((0.7, 0.8), (2.3, 0.9), (6.0, 0.6)))):
        result = _decode(chirp_data.simulate_channel(samples, RATE, **kwargs))
        assert result.ok and result.payload == MESSAGE, kwargs


def test_data_other_settings_and_sizes():
    for config in (chirp_data.DataConfig(spread=7, bits=7),
                   chirp_data.DataConfig(spread=6, bits=4),
                   chirp_data.DataConfig(f0=2000, f1=20000, spread=8, bits=6),
                   chirp_data.DataConfig(rate=96000, f0=25000, f1=40000, spread=8, bits=6)):
        for payload in (b"", b"A", bytes(range(200))):
            recording = chirp_data.simulate_channel(
                chirp_data.modulate(payload, config), config.rate, noise=0.02)
            result = _decode(recording, config)
            assert result.ok and result.payload == payload, (config, len(payload))


def test_data_failures_are_caught_not_invented():
    assert not _decode(np.zeros(90000, np.float32)).found
    noise = np.random.default_rng(1).normal(0, 0.05, 90000).astype(np.float32)
    assert not _decode(noise).found
    # A 5 ms gap part-way through, as the WSL sound bridge does: the CRC must fail.
    recording = chirp_data.simulate_channel(chirp_data.modulate(MESSAGE, DATA), RATE)
    cut = recording.size // 2
    slipped = np.concatenate([recording[:cut], np.zeros(240, np.float32), recording[cut:]])
    result = _decode(slipped)
    assert result.found and not result.ok
    errors, total = chirp_data.bit_errors(MESSAGE, result.payload)
    assert 0 < errors <= total
    # Cut off before the end.
    result = _decode(recording[:recording.size // 2])
    assert not result.ok and "ended" in result.message
    assert chirp_data.bit_errors(b"ab", b"ab") == (0, 16)
    assert chirp_data.bit_errors(b"ab", b"a") == (8, 16)
    for bad in (chirp_data.DataConfig(bits=9), chirp_data.DataConfig(f1=30000),
                chirp_data.DataConfig(f0=15000, f1=15100)):
        try:
            bad.check()
        except ValueError:
            continue
        raise AssertionError("expected ValueError")


if __name__ == "__main__":
    tests = [(n, f) for n, f in sorted(globals().items())
             if n.startswith("test_") and callable(f)]
    for name, test in tests:
        test()
        print("ok  ", name)
    print(f"{len(tests)} passed")
