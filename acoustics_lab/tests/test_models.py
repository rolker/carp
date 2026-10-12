"""Checks on the models, ported from carp/acoustic/test_ranging_dsp.py:
chirps, the matched filter, arrival times, and finding the events of a ping.
"""
import numpy as np

from acoustics_lab import wav_io
from acoustics_lab.models import detection as det
from acoustics_lab.models import media, signals
from acoustics_lab.models.signals import make_chirp

from helpers import RATE, event, recording, simulate_noise

SPEED = float(media.sound_speed_air(20.0))


def arrivals_for(delays, gains, noise=0.01, threshold=0.1):
    chirp = make_chirp(RATE, 2000, 20000, 0.02)
    e = event("c", 2000, 20000, 0.02, 0.0)
    rec = recording([(e, list(zip(delays, gains)))], noise=noise)
    return det.find_arrivals(det.matched_filter(rec, chirp), RATE, threshold)


def test_chirp_shape():
    chirp = make_chirp(RATE, 2000, 20000, 0.02)
    assert chirp.size == 960
    assert abs(float(np.max(np.abs(chirp))) - 1.0) < 0.05
    assert abs(float(chirp[0])) < 1e-6


def test_chirp_rejects_band_above_nyquist():
    try:
        make_chirp(RATE, 2000, 23000, 0.02)
    except ValueError:
        return
    raise AssertionError("expected ValueError")


def test_reverse_of_an_up_chirp_is_a_down_chirp_that_correlates_poorly():
    up = make_chirp(RATE, 14000, 16000, 0.05)
    down = signals.time_reverse(up)
    pad = np.zeros(up.size)
    own = det.matched_filter(np.concatenate([pad, up, pad]), up).max()
    cross = det.matched_filter(np.concatenate([pad, down, pad]), up).max()
    assert cross < 0.25 * own
    assert np.array_equal(signals.invert(up), -up)


def test_delay_is_recovered_to_a_fraction_of_a_sample():
    # 1.5 m in air: not a whole number of samples.
    delay = 1.5 / SPEED
    arrivals = arrivals_for([0.0, delay], [0.2, 0.05])
    assert len(arrivals) == 2
    measured = (arrivals[1].sample - arrivals[0].sample) / RATE
    assert abs(measured - delay) * RATE < 0.1, (measured, delay)


def test_weak_echo_is_found_and_ordered_by_time():
    arrivals = arrivals_for([0.0, 0.004, 0.0065], [0.3, 0.02, 0.05], threshold=0.03)
    assert len(arrivals) == 3
    delays = [(a.sample - arrivals[0].sample) / RATE for a in arrivals]
    assert abs(delays[1] - 0.004) < 1e-5 and abs(delays[2] - 0.0065) < 1e-5
    assert arrivals[1].level < arrivals[2].level < arrivals[0].level


def test_narrow_band_sidelobes_are_not_reported_as_arrivals():
    # 4-7 kHz is roughly what a piezo disc passes in air. With a lightly
    # tapered chirp, a -14 dB sidelobe ahead of the loopback copy was taken
    # as the first arrival.
    chirp = make_chirp(RATE, 4000, 7000, 0.01)
    e = event("c", 4000, 7000, 0.01, 0.0)
    delay = 1.0 / SPEED
    rec = recording([(e, [(0.0, 0.2), (delay, 0.05)])])
    arrivals = det.find_arrivals(det.matched_filter(rec, chirp), RATE)
    assert len(arrivals) == 2
    measured = (arrivals[1].sample - arrivals[0].sample) / RATE
    assert abs(measured - delay) * RATE < 0.5, (measured, delay)
    assert arrivals[0].level > arrivals[1].level


def test_sidelobes_are_well_below_the_default_threshold():
    chirp = make_chirp(RATE, 2000, 20000, 0.02)
    e = event("c", 2000, 20000, 0.02, 0.0)
    rec = recording([(e, [(0.0, 0.2)])], noise=0.0)
    envelope = det.matched_filter(rec, chirp)
    peak = int(np.argmax(envelope))
    guard = int(det.resolution(2000, 20000) * RATE) + 1
    outside = np.concatenate([envelope[:peak - guard], envelope[peak + guard:]])
    assert outside.max() < 0.01 * envelope[peak]


def test_noise_alone_gives_no_strong_arrival_pair():
    assert len(arrivals_for([0.0], [0.2])) == 1


def test_sound_speed_air():
    assert abs(media.sound_speed_air(20.0) - 343.2) < 0.3
    assert abs(media.sound_speed_air(0.0) - 331.3) < 0.01
    assert abs(media.wavelength(343.2, 20000) - 0.01716) < 1e-5


def test_processing_gain_is_duration_times_bandwidth():
    # 40 ms over 4 kHz: time-bandwidth product 160, 22 dB.
    assert abs(signals.processing_gain_db(16000, 20000, 0.04) - 22.04) < 0.01


def test_wav_round_trip(tmp_path):
    e = event("c", 2000, 20000, 0.02, 0.0)
    rec = recording([(e, [(0.0, 0.2), (0.003, 0.05)])])
    path = str(tmp_path / "t.wav")
    wav_io.write_wav(path, rec, RATE)
    loaded, rate = wav_io.read_wav(path)
    assert rate == RATE and loaded.size == rec.size
    assert float(np.max(np.abs(loaded - rec))) < 1e-4 + 1 / 32767


# ---- finding the events of a ping --------------------------------------

LEFT, RIGHT = [(1.5, 0.1), (2.6, 0.03)], [(1.9, 0.06), (3.3, 0.024)]


def heard(placed, noise=0.002):
    """Analyse a recording in which each (event, path list in metres and
    gain) is heard; returns (analysis, events)."""
    events = [e for e, _ in placed]
    sounds = [(e, [(m / SPEED, g) for m, g in paths]) for e, paths in placed]
    rec = recording(sounds, noise=noise)
    return det.analyse_events(rec, RATE, events), events


def default_pair():
    up_left = event("up", 2000, 20000, 0.02, 0.0)
    up_right = event("up", 2000, 20000, 0.02, 0.15)
    return up_left, up_right


def test_left_and_right_are_told_apart_by_the_gap():
    a, b = default_pair()
    analysis, _ = heard([(a, LEFT), (b, RIGHT)])
    assert analysis.detected() == [0, 1]
    extra = analysis.delay_ms(1) - analysis.delay_ms(0)
    assert abs(extra * SPEED / 1e3 - 0.4) < 0.01, extra


def test_a_weak_left_before_a_loud_right_is_found():
    # As heard from the TV on 2026-10-11: the left chirp 18 dB below the right.
    a, b = default_pair()
    analysis, _ = heard([(a, [(1.5, 0.006)]), (b, [(1.9, 0.05)])])
    assert analysis.detected() == [0, 1]
    assert analysis.results[1].level > 5 * analysis.results[0].level
    assert abs(analysis.delay_ms(0) * SPEED / 1e3 + 0.4) < 0.01


def test_three_on_one_channel_and_a_second_signal():
    up = [event("up", 2000, 20000, 0.02, t) for t in (0.0, 0.1, 0.3)]
    low = event("low", 3000, 8000, 0.03, 0.2)
    placed = [(up[0], LEFT), (up[1], LEFT), (low, RIGHT), (up[2], LEFT)]
    analysis, _ = heard(placed)
    assert analysis.detected() == [0, 1, 2, 3]
    assert max(abs(analysis.delay_ms(i) - analysis.delay_ms(0)) for i in (1, 3)) < 0.01
    assert abs((analysis.delay_ms(2) - analysis.delay_ms(0)) * SPEED / 1e3 - 0.4) < 0.02


def test_failures_are_reported_not_invented():
    a, b = default_pair()
    silent = det.analyse_events(np.zeros(40000), RATE, [a, b])
    assert not silent.detected() and "silent" in silent.warnings[0]
    noise = np.random.default_rng(0).normal(0, 0.01, 40000)
    assert not det.analyse_events(noise, RATE, [a, b]).detected()
    # Only the left chirp present: one event heard, with a warning.
    alone, _ = heard([(a, LEFT)])
    both = det.analyse_events(recording([(a, [(1.5 / SPEED, 0.1)])], noise=0.002),
                              RATE, [a, b])
    assert len(both.detected()) == 1 and both.warnings
    assert alone.detected() == [0]


def test_same_signal_at_the_same_time_is_flagged_as_one_sound():
    # Roland's design of 2026-10-11: left three times, right along with the third.
    ev = [event("s", 15000, 17000, 0.035, t) for t in (0.0, 0.1, 0.2, 0.2)]
    assert det.inseparable(ev) == [[2, 3]]
    analysis, _ = heard([(ev[0], LEFT), (ev[1], LEFT), (ev[2], LEFT), (ev[3], RIGHT)])
    assert any("cannot be told apart" in w for w in analysis.warnings)
    assert analysis.delay_ms(2) == analysis.delay_ms(3)
    assert det.inseparable(list(default_pair())) == []


def test_up_and_down_chirps_in_one_band_are_flagged_as_leaking():
    # Roland's design of 2026-10-11: 16-14 kHz on the left against 14-16 kHz
    # on the right, together. The left "arrived" 1.7 ms early: a leak.
    down = event("down", 16000, 14000, 0.02, 0.0)
    up = event("up", 14000, 16000, 0.02, 0.0)
    (i, j, isolation), = det.leaking([down, up], RATE)
    assert (i, j) == (0, 1) and -25 < isolation < -5, isolation
    analysis, _ = heard([(down, LEFT), (up, RIGHT)])
    assert any("leaks" in w for w in analysis.warnings)
    # Separate bands, or the same pair far apart in time, are fine.
    lo = event("lo", 2000, 9000, 0.03, 0.0)
    hi = event("hi", 11000, 20000, 0.03, 0.0)
    assert det.leaking([lo, hi], RATE) == []
    later = event("up", 14000, 16000, 0.02, 0.2)
    assert det.leaking([down, later], RATE) == []


def test_arrivals_after_the_first_are_kept():
    e = event("c", 2000, 20000, 0.02, 0.0)
    analysis, _ = heard([(e, [(1.5, 0.1), (2.6, 0.03)])])
    arrivals = analysis.results[0].arrivals
    assert len(arrivals) == 2
    assert abs((arrivals[1].sample - arrivals[0].sample) / RATE * SPEED - 1.1) < 0.01


def test_noise_spectrum_finds_a_tone_and_the_quiet_bands():
    noise = simulate_noise(RATE, 2.0)
    freqs, db = det.noise_spectrum(noise, RATE)
    above = freqs > 2000
    assert abs(freqs[above][np.argmax(db[above])] - 17000) < 100
    bands = {b["f0"]: b["level_db"] for b in det.band_levels(noise, RATE)}
    assert bands[17000.0] > bands[10000.0] + 3
    assert bands[0.0] > bands[10000.0] + 10         # the rumble
    # White noise of rms 0.003 over 24 kHz: -50.5 dBFS in all, 1/24 of it per band.
    assert abs(bands[10000.0] - (20 * np.log10(0.003) - 10 * np.log10(24))) < 1.5
