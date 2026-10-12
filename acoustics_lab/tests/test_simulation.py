"""The simulation against its own truth: arrival times recovered to a small
fraction of a sample, near the end of the buffer, with clock drift, and no
wrap-around; levels as spreading and reflection say."""
import numpy as np
import pytest

from acoustics_lab.backends.base import Cancelled, Emission, Ping
from acoustics_lab.backends.simulation import SimulationBackend, noise_samples
from acoustics_lab.models import channel, detection
from acoustics_lab.models.signals import make_chirp
from acoustics_lab.objects import schema as s

RATE = 48000
CHIRP = make_chirp(RATE, 2000, 20000, 0.02)


def peak_sample(recording, template=CHIRP):
    """Sub-sample position of the strongest matched-filter peak."""
    envelope = detection.matched_filter(recording, template)
    return detection.find_arrivals(envelope, RATE, 0.5)[0].sample


# ---- the renderer ------------------------------------------------------

def test_fractional_delays_are_exact():
    n = 20000
    for delay_samples in (1000.0, 1000.25, 1000.5, 1000.9137, 7000.3):
        out = channel.render_paths(CHIRP, RATE, [(delay_samples / RATE, 1.0, 0.0)], n)
        assert abs(peak_sample(out) - delay_samples) < 0.02, delay_samples


def test_delay_near_the_end_of_the_buffer_does_not_wrap():
    n = 20000
    # The chirp ends 40 samples before the buffer does, at a fractional time.
    delay = n - CHIRP.size - 40 + 0.37
    out = channel.render_paths(CHIRP, RATE, [(delay / RATE, 1.0, 0.0)], n)
    assert abs(peak_sample(out) - delay) < 0.02
    assert np.max(np.abs(out[:int(delay) - 500])) < 1e-6          # nothing at the start


def test_an_impulse_delayed_by_a_fraction_leaves_nothing_at_the_other_end():
    n = 4096
    impulse = np.zeros(8)
    impulse[0] = 1.0
    # Late in the buffer: the sinc tails must not come round to the start.
    out = channel.render_paths(impulse, RATE, [((n - 12 + 0.4) / RATE, 1.0, 0.0)], n)
    assert np.max(np.abs(out[:1500])) < 1e-3
    assert abs(np.argmax(np.abs(out)) - (n - 12)) <= 1
    # Early: the pre-ringing before time zero must not appear at the end.
    out = channel.render_paths(impulse, RATE, [(0.4 / RATE, 1.0, 0.0)], n)
    assert np.max(np.abs(out[-1500:])) < 1e-3


def test_nyquist_component_of_a_delay_is_cosine_of_the_phase():
    # A long burst at half the sample rate, delayed by half a sample, is
    # zero in the middle: cos(pi / 2). By a whole sample it only moves.
    n = 4096
    nyquist = np.tile([1.0, -1.0], 256)
    whole = channel.render_paths(nyquist, RATE, [(100.0 / RATE, 1.0, 0.0)], n)
    half = channel.render_paths(nyquist, RATE, [(100.5 / RATE, 1.0, 0.0)], n)
    assert np.all(np.isfinite(half)) and half.dtype == np.float64
    middle = slice(100 + 200, 100 + 300)
    assert np.max(np.abs(whole[middle])) > 0.99
    assert np.max(np.abs(half[middle])) < 0.2     # the burst's ends leak a little


def test_gain_polarity_and_absorption():
    n = 8000
    base = channel.render_paths(CHIRP, RATE, [(0.01, 1.0, 0.0)], n)
    flipped = channel.render_paths(CHIRP, RATE, [(0.01, -0.5, 0.0)], n)
    assert np.allclose(flipped, -0.5 * base, atol=1e-9)
    # 1 dB per kHz^2 at 10 kHz is 100 dB: the 2-20 kHz chirp loses most of its energy.
    lossy = channel.render_paths(CHIRP, RATE, [(0.01, 1.0, 1.0)], n)
    assert np.std(lossy) < 0.2 * np.std(base)
    with pytest.raises(ValueError):
        channel.render_paths(CHIRP, RATE, [(-0.1, 1.0, 0.0)], n)


def test_image_source_geometry():
    image = channel.image_source([0, 0, 0], [0, 1, 0], [0, -1, 0])
    assert np.allclose(image, [0, 2, 0])
    assert channel.image_source([0, 2, 0], [0, 1, 0], [0, -1, 0]) is None
    assert abs(channel.path_length(image, [1.5, 0, 0]) - 2.5) < 1e-12


# ---- the backend -------------------------------------------------------

def scene(distance=1.5, planes=(), loopback=False, drift_rx=0.0, drift_tx=0.0,
          noise=0.0, same_device=True, absorption=0.0):
    layout = s.new_layout("t", [
        s.transducer("tx", "TX", (0, 0, 0), can_send=True),
        s.transducer("rx", "RX", (distance, 0, 0), can_receive=True)])
    if same_device:
        devices = [s.device("d", ["tx", "rx"], clock_drift_ppm=drift_rx)]
    else:
        devices = [s.device("a", ["tx"], clock_drift_ppm=drift_tx),
                   s.device("b", ["rx"], clock_drift_ppm=drift_rx, clock_offset=12.5)]
    loops = [dict(receiver="rx", emitter="tx", gain=0.2)] if loopback else []
    sc = s.new_scene("t", "l", devices, loopbacks=loops, planes=planes,
                     noise_rms=noise)
    sc["medium"]["absorption_db_per_m_per_khz2"] = absorption
    return SimulationBackend(sc, layout)


def ping(listen=0.1, start=0.0, samples=CHIRP):
    return Ping([Emission("tx", samples, start, RATE, "c")], ["rx"], listen)


def test_arrival_is_recovered_from_the_truth():
    for distance in (0.3, 1.0, 1.5, 2.3333, 5.0, 12.7):
        backend = scene(distance)
        capture = backend.fire(ping())
        truth, = [p for p in capture.truth["paths"] if p["route"] == "direct"]
        assert abs(truth["length_m"] - distance) < 1e-12
        found = peak_sample(capture.recordings["rx"].samples)
        assert abs(found - truth["arrival_sample"]) < 0.05, (distance, found)
        # And the truth is what the distance and the sound speed say.
        c = backend.sound_speed()
        lead = capture.truth["lead_in"]
        assert abs(truth["arrival_s"] - (lead + distance / c)) < 1e-12


def test_arrival_near_the_end_of_the_recording():
    # Ask for just enough listening time that the echo ends 30 samples
    # before the buffer does.
    backend = scene(3.0)
    c = backend.sound_speed()
    listen = 3.0 / c + 30 / RATE
    capture = backend.fire(ping(listen=listen))
    samples = capture.recordings["rx"].samples
    truth, = capture.truth["paths"]
    assert 20 < samples.size - (truth["arrival_sample"] + CHIRP.size) < 40
    assert abs(peak_sample(samples) - truth["arrival_sample"]) < 0.05
    # Nothing came round from the end to the start.
    assert np.max(np.abs(samples[:int(0.9 * truth["arrival_sample"])])) < 1e-6


def test_a_path_longer_than_the_recording_leaves_it_silent():
    capture = scene(30.0).fire(ping(listen=0.01))
    assert np.max(np.abs(capture.recordings["rx"].samples)) < 1e-6


def test_loopback_and_echoes_give_the_time_of_flight():
    wall = dict(name="wall", point=[0, 1, 0], normal=[0, -1, 0], reflection=0.3)
    backend = scene(1.5, planes=[wall], loopback=True)
    capture = backend.fire(ping(listen=0.05))
    rec = capture.recordings["rx"]
    assert rec.loopback_of == ["tx"]
    routes = {p["route"]: p for p in capture.truth["paths"]}
    assert set(routes) == {"direct", "plane:wall", "loopback"}
    assert abs(routes["plane:wall"]["length_m"] - 2.5) < 1e-9
    assert routes["plane:wall"]["reflections"] == ["wall"]
    envelope = detection.matched_filter(rec.samples, CHIRP)
    found = detection.find_arrivals(envelope, RATE, 0.05)
    assert len(found) == 3
    for arrival, name in zip(found, ("loopback", "direct", "plane:wall")):
        assert abs(arrival.sample - routes[name]["arrival_sample"]) < 0.05, name
    # Levels: the loopback gain, then link gain / length, times the reflection.
    levels = [a.level for a in found]
    ratio = levels[2] / levels[1]
    assert abs(ratio - (0.3 * 1.5 / 2.5)) < 0.02, ratio
    assert abs(levels[1] / levels[0] - (0.15 / 1.5) / 0.2) < 0.02


def test_receiver_behind_a_plane_gets_no_reflection_from_it():
    wall = dict(name="wall", point=[0, -1, 0], normal=[0, -1, 0], reflection=0.3)
    capture = scene(1.5, planes=[wall]).fire(ping())
    assert [p["route"] for p in capture.truth["paths"]] == ["direct"]


def test_clock_drift_moves_arrivals_and_truth_follows():
    plain = scene(2.0, loopback=True).fire(ping(listen=0.1))
    drifting = scene(2.0, loopback=True, drift_rx=100.0).fire(ping(listen=0.1))
    for capture in (plain, drifting):
        rec = capture.recordings["rx"].samples
        envelope = detection.matched_filter(rec, CHIRP)
        found = detection.find_arrivals(envelope, RATE, 0.05)
        by_route = {p["route"]: p for p in capture.truth["paths"]}
        assert abs(found[0].sample - by_route["loopback"]["arrival_sample"]) < 0.05
        assert abs(found[1].sample - by_route["direct"]["arrival_sample"]) < 0.05
    # Sender and receiver share the drifting clock, so only the flight
    # time stretches: a 100 ppm fast clock sees the 2 m flight 100 ppm longer.
    a = {p["route"]: p for p in plain.truth["paths"]}["direct"]["arrival_sample"]
    b = {p["route"]: p for p in drifting.truth["paths"]}["direct"]["arrival_sample"]
    flight = 2.0 / plain.truth["sound_speed"] * RATE
    assert abs((b - a) - flight * 100e-6) < 1e-6
    assert drifting.truth["unmodelled_stretch_s"][0] == 0.0     # one shared clock


def test_two_devices_keep_their_own_clocks():
    backend = scene(1.5, same_device=False, drift_tx=-30.0, drift_rx=80.0)
    capture = backend.fire(ping())
    rec = capture.recordings["rx"]
    assert rec.clock == "b" and rec.started == 12.5
    truth, = capture.truth["paths"]
    assert abs(peak_sample(rec.samples) - truth["arrival_sample"]) < 0.05
    # The stretch the model leaves out is stated, not hidden: 110 ppm of 20 ms.
    assert capture.truth["unmodelled_stretch_s"][0] == pytest.approx(0.02 * 110e-6)
    with pytest.raises(ValueError):         # a loopback cannot cross devices
        scene(1.5, same_device=False, loopback=True)


def test_noise_has_the_requested_level_and_slope():
    rng = np.random.default_rng(1)
    white = noise_samples(rng, 2 ** 18, 0.01)
    assert abs(np.std(white) - 0.01) < 1e-4
    pink = noise_samples(rng, 2 ** 18, 0.01, -3.0)
    assert abs(np.std(pink) - 0.01) < 1e-4
    freqs, db = detection.noise_spectrum(pink, RATE)
    low = db[(freqs > 500) & (freqs < 1000)].mean()
    high = db[(freqs > 8000) & (freqs < 16000)].mean()
    assert 7 < low - high < 15              # about 3 dB per octave over ~4 octaves


def test_noise_differs_between_pings_but_repeats_for_the_same_seed():
    first = scene(1.5, noise=0.01)
    a, b = first.fire(ping()), first.fire(ping())
    assert not np.array_equal(a.recordings["rx"].samples, b.recordings["rx"].samples)
    again = scene(1.5, noise=0.01).fire(ping())
    assert np.array_equal(a.recordings["rx"].samples, again.recordings["rx"].samples)


def test_bad_pings_are_refused_with_a_reason():
    backend = scene(1.5)
    with pytest.raises(ValueError, match="cannot send"):
        backend.fire(Ping([Emission("rx", CHIRP, 0, RATE)], ["rx"], 0.1))
    with pytest.raises(ValueError, match="cannot receive"):
        backend.fire(Ping([Emission("tx", CHIRP, 0, RATE)], ["tx"], 0.1))
    with pytest.raises(ValueError, match="arrives before"):
        sc = scene(1.5, same_device=False)
        sc.scene["devices"][1]["start_delay"] = 1.0
        sc.fire(ping())


def test_cancel_stops_the_render():
    with pytest.raises(Cancelled):
        scene(1.5).fire(ping(), cancel=lambda: True)


def test_stream_fires_repeatedly():
    backend = scene(1.5)
    with backend.open_stream(ping()) as stream:
        a, b = stream.fire(), stream.fire()
    assert a.meta["ping_index"] == 0 and b.meta["ping_index"] == 1
    assert a.ping.emissions[0].transducer == "tx"
