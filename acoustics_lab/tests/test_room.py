"""The room sonar's analysis, and the simulation's reflectors and movers it is
shown with. Simulation only: no device."""
import numpy as np
import pytest

from acoustics_lab.backends.base import Capture, Emission, Ping, Recording
from acoustics_lab.backends.simulation import SimulationBackend, mover_position
from acoustics_lab.experiments import ranging, room
from acoustics_lab.models import detection_design as dd
from acoustics_lab.objects import rigs, schema as s, starter
from acoustics_lab.workspace import Workspace

SPEED = 343.2


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    rigs.laptop_template(w)
    return w


def sim(ws, scene=rigs.LAPTOP_DEMO):
    backend = SimulationBackend.from_workspace(ws, scene)
    ping = room.build_ping(ws, rigs.LAPTOP_DESIGN, "speaker", "mic", backend.transducers(),
                           5.0, backend.sound_speed(), 0.2)
    return backend, ping


def peaks(result, floor_db=-45.0):
    """Local maxima of the return above a level: (range m, dB)."""
    db = result.level_db
    found = [(float(result.range_m[k]), float(db[k])) for k in range(1, len(db) - 1)
             if db[k] > db[k - 1] and db[k] >= db[k + 1] and db[k] > floor_db]
    return found


def near(found, wanted, tolerance=0.02):
    return any(abs(r - wanted) <= tolerance for r, _ in found)


# ---- the simulated room -------------------------------------------------------

def test_a_mover_walks_back_and_forth_at_its_speed():
    mover = dict(name="p", a=[0.0, 1.0, 0.0], b=[0.0, 3.0, 0.0], speed=0.5)
    assert np.allclose(mover_position(mover, 0.0), [0, 1, 0])
    assert np.allclose(mover_position(mover, 2.0), [0, 2, 0])
    assert np.allclose(mover_position(mover, 4.0), [0, 3, 0])
    assert np.allclose(mover_position(mover, 5.0), [0, 2.5, 0])       # on its way back
    assert np.allclose(mover_position(mover, 8.0), [0, 1, 0])
    assert np.allclose(mover_position(dict(mover, speed=0.0), 3.0), [0, 1, 0])


def test_the_scene_has_a_mover_reflectors_and_walls_and_truth_says_where(ws):
    backend, ping = sim(ws)
    ping.meta["period_s"] = 1.0
    first, second = backend.fire(ping), backend.fire(ping)
    routes = {p["route"] for p in first.truth["paths"]}
    assert {"direct", "reflector:cabinet", "reflector:chair", "mover:person",
            "plane:front wall", "plane:left wall"} <= routes
    a, b = first.truth["movers"]["person"], second.truth["movers"]["person"]
    assert np.linalg.norm(np.array(b) - np.array(a)) == pytest.approx(0.5, abs=1e-9)  # 0.5 m/s, 1 s
    assert second.truth["time_s"] == 1.0


def test_the_as_built_scene_has_nothing_that_moves_and_no_made_up_reflectors(ws):
    built = ws.get("scenes", ws.get("rigs", rigs.LAPTOP_RIG)["as_built"])
    assert built["movers"] == [] and built["reflectors"] == []
    backend, ping = sim(ws, built and ws.get("rigs", rigs.LAPTOP_RIG)["as_built"])
    routes = {p["route"] for p in backend.fire(ping).truth["paths"]}
    assert routes == {"direct"}


# ---- the analysis ---------------------------------------------------------------

def test_the_direct_sound_is_time_zero_and_echoes_come_out_at_their_true_ranges(ws):
    backend, ping = sim(ws)
    capture = backend.fire(ping)
    result = room.analyse(capture, "speaker", "mic", max_range_m=5.0)
    assert result.heard and not result.warnings
    assert result.baseline_m == pytest.approx(0.2)
    assert result.level_db[np.searchsorted(result.range_m, 0.1)] == pytest.approx(0.0, abs=0.6)
    found = peaks(result)
    assert near(found, 0.1, 0.01)                                # the direct sound: d / 2
    assert result.truth and len(result.truth) == 7
    for route, true_range in result.truth:
        assert near(found, true_range), (route, true_range, found[:12])
    assert result.range_m[1] - result.range_m[0] == pytest.approx(backend.sound_speed() / 2 / 48000)
    assert result.range_m[-1] == pytest.approx(5.0, abs=0.01)


def test_two_devices_with_different_clocks_and_rates_give_the_same_picture(ws):
    # The speaker on one card, the microphone on another: a different rate, a
    # clock offset and drift, and a start delay. Time zero is the direct sound.
    demo = ws.get("scenes", rigs.LAPTOP_DEMO)
    demo["devices"] = [s.device("out", ["speaker"], rate=48000, start_delay=0.013),
                       s.device("in", ["mic"], rate=44100, clock_offset=7.0,
                                clock_drift_ppm=30.0, start_delay=0.002)]
    ws.replace("scenes", rigs.LAPTOP_DEMO, demo)
    backend, ping = sim(ws)
    capture = backend.fire(ping)
    assert capture.recordings["mic"].rate == 44100 and capture.recordings["mic"].clock == "in"
    result = room.analyse(capture, "speaker", "mic", max_range_m=5.0)
    found = peaks(result, -40.0)
    strong = [(r, at) for r, at in result.truth if r != "plane:front wall"]   # that one is -46 dB
    assert len(strong) == 6
    for route, true_range in strong:
        assert near(found, true_range, 0.03), (route, true_range)


def test_a_chirp_in_the_recording_is_all_that_is_needed_not_the_ping_design(ws):
    # Hand-made capture: one echo 12 ms after the direct sound, noise, nothing else.
    rate = 48000
    ping_samples = ranging.signal_objects.samples(ws.get_signal, rigs.LAPTOP_SIGNAL, rate)
    n = int(0.12 * rate)
    rec = np.random.default_rng(3).normal(0, 0.002, n)
    for delay, gain in ((0.01, 0.5), (0.022, 0.05)):
        at = int(delay * rate)
        rec[at:at + ping_samples.size] += gain * ping_samples
    ping = Ping([Emission("spk", ping_samples, 0.0, rate, "chirp")], ["m"], 0.04,
                meta=dict(signals=dict(chirp=dict(name="c", f0=2000, f1=20000, duration=0.01,
                                                  amplitude=0.3))))
    capture = Capture({"m": Recording(rec, rate, "x", 0.0)}, {}, None,
                      dict(sound_speed=SPEED, backend="test"), ping)
    result = room.analyse(capture, "spk", "m", max_range_m=5.0)       # separation unknown: 0
    assert result.heard and result.baseline_m == 0.0
    echo = result.range_m[np.argmax(result.level * (result.range_m > 1.0))]
    assert echo == pytest.approx(SPEED * 0.012 / 2, abs=0.01)         # (c t + 0) / 2
    assert np.max(result.level[result.range_m > 1.0]) == pytest.approx(0.1, rel=0.1)


def test_a_stronger_echo_just_after_the_direct_sound_does_not_become_time_zero(ws):
    # As on a laptop: a reflection off the screen, stronger than the direct sound.
    rate = 48000
    chirp = ranging.signal_objects.samples(ws.get_signal, rigs.LAPTOP_SIGNAL, rate)
    rec = np.random.default_rng(0).normal(0, 0.001, int(0.1 * rate))
    for at, gain in ((3195, 0.3), (3195 + 60, 0.45)):
        rec[at:at + chirp.size] += gain * chirp
    ping = Ping([Emission("spk", chirp, 0.0, rate, "chirp")], ["m"], 0.04,
                meta=dict(signals=dict(chirp=dict(name="c", f0=2000, f1=20000, duration=0.01,
                                                  amplitude=0.3))))
    capture = Capture({"m": Recording(rec, rate, "x", 0.0)}, {}, None,
                      dict(sound_speed=SPEED, backend="test"), ping)
    result = room.analyse(capture, "spk", "m")
    assert result.direct_sample == pytest.approx(3195, abs=0.5)
    strict = room.analyse(capture, "spk", "m", dd.DEFAULT.changed(first_fraction=0.9))
    assert strict.direct_sample == pytest.approx(3255, abs=0.5)     # the detection design decides
    assert strict.design.first_fraction == 0.9 and result.design == dd.DEFAULT


def test_silence_and_a_missing_direct_sound_are_explained_not_invented(ws):
    rate = 48000
    chirp = ranging.signal_objects.samples(ws.get_signal, rigs.LAPTOP_SIGNAL, rate)
    quiet = np.random.default_rng(0).normal(0, 0.01, int(0.1 * rate))
    ping = Ping([Emission("spk", chirp, 0.0, rate, "chirp")], ["m"], 0.04,
                meta=dict(signals=dict(chirp=dict(name="c", f0=2000, f1=20000, duration=0.01,
                                                  amplitude=0.3))))
    capture = Capture({"m": Recording(quiet, rate, "x", 0.0)}, {}, None,
                      dict(sound_speed=SPEED, backend="test"), ping)
    result = room.analyse(capture, "spk", "m")
    assert not result.heard and "direct sound from the speaker was not found" in result.warnings[0]
    assert result.level.size == 0
    other = room.analyse(capture, "nobody", "m")
    assert not other.heard and "no signal from 'nobody'" in other.warnings[0]
    short = Capture({"m": Recording(np.zeros(100), rate, "x", 0.0)}, {}, None, {}, ping)
    assert "too short" in room.analyse(short, "spk", "m").warnings[0]


def test_clipping_and_a_loopback_in_the_recording_are_warned_about(ws):
    backend, ping = sim(ws)
    capture = backend.fire(ping)
    capture.recordings["mic"].samples = np.clip(capture.recordings["mic"].samples * 40, -1, 1)
    assert any("clipping" in w for w in room.analyse(capture, "speaker", "mic").warnings)
    capture = backend.fire(ping)
    capture.recordings["mic"].loopback_of = ["speaker"]
    assert any("electrical loopback" in w for w in room.analyse(capture, "speaker", "mic").warnings)


def test_the_range_asked_for_sets_the_listening_time_and_the_ping(ws):
    backend, _ = sim(ws)
    infos = backend.transducers()
    a = room.build_ping(ws, rigs.LAPTOP_DESIGN, "speaker", "mic", infos, 5.0, SPEED, 0.2)
    b = room.build_ping(ws, rigs.LAPTOP_DESIGN, "speaker", "mic", infos, 10.0, SPEED, 0.2)
    assert a.listen == pytest.approx((2 * 5.0 - 0.2) / SPEED + 0.002)
    assert b.listen > a.listen and a.meta["room"] and a.meta["max_range_m"] == 5.0
    assert len(a.emissions) == 1 and a.emissions[0].transducer == "speaker"
    assert a.receivers == ["mic"] and a.emissions[0].start == 0.0
    with pytest.raises(ValueError, match="'mic' cannot send"):
        room.build_ping(ws, rigs.LAPTOP_DESIGN, "mic", "mic", infos, 5.0, SPEED)
    with pytest.raises(ValueError, match="'speaker' cannot receive"):
        room.build_ping(ws, rigs.LAPTOP_DESIGN, "speaker", "speaker", infos, 5.0, SPEED)
    ws.update("ping_designs", rigs.LAPTOP_DESIGN, events=[])
    with pytest.raises(ValueError, match="has no events"):
        room.build_ping(ws, rigs.LAPTOP_DESIGN, "speaker", "mic", infos, 5.0, SPEED)


def test_the_numbers_come_from_the_signal_and_the_settings():
    spec = dict(f0=2000.0, f1=20000.0, duration=0.01)
    n = room.numbers(spec, SPEED, 48000.0, 0.2, 5.0, 0.2)
    assert n["resolution_s"] == pytest.approx(3.0 / 18000)
    assert n["resolution_m"] == pytest.approx(SPEED * 3.0 / 18000 / 2)          # 2.9 cm
    assert n["bin_m"] == pytest.approx(SPEED / 2 / 48000)                        # 3.6 mm
    assert n["listen_s"] == pytest.approx((10 - 0.2) / SPEED + 0.002)
    assert n["ambiguity_m"] == pytest.approx(SPEED * 0.2 / 2)
    assert n["pulse_m"] == pytest.approx(SPEED * 0.01 / 2)
    assert room.numbers(spec, SPEED, 48000.0, 0.0, 5.0, 0)["ambiguity_m"] is None
    tone = room.numbers(dict(f0=5000.0, f1=5000.0, duration=0.01), SPEED, 48000.0, 0, 5.0, 0)
    assert tone["resolution_s"] == 0.01          # no bandwidth: the whole tone


# ---- the background and what moves ----------------------------------------------

def test_the_steady_part_cancels_and_the_mover_stands_out(ws):
    backend, ping = sim(ws)
    ping.meta["period_s"] = 0.2
    history, last = [], None
    for _ in range(30):
        capture = backend.fire(ping)
        last = room.analyse(capture, "speaker", "mic", max_range_m=5.0)
        mean = room.background(history, 20)
        diff = room.difference(last.level, mean)
        history.append(last.level)
    truth = dict(last.truth)
    mover_at = truth["mover:person"]
    grid = last.range_m
    # skip the direct sound and what is close to it
    quiet = (grid > 0.4)
    top = np.argmax(np.where(quiet, diff, 0.0))
    assert grid[top] == pytest.approx(mover_at, abs=0.1)
    # the static reflectors are far below the mover in the changes
    for route, at in last.truth:
        if route.startswith("mover"):
            continue
        k = np.searchsorted(grid, at)
        assert diff[max(k - 3, 0):k + 4].max() < 0.2 * diff[top]
    # while in the plain return the static ones are as strong as the mover or stronger
    assert last.level[np.searchsorted(grid, truth["plane:front wall"])] > 0.0
    assert room.difference(last.level, None).max() == 0.0          # no background yet: nothing
    assert room.background([], 5) is None
    assert room.background([np.ones(3), np.zeros(3)], 1).tolist() == [0, 0, 0]
    assert room.background([np.ones(3), np.zeros(5)], 5).size == 5  # a different grid is left out
    assert room.to_db(np.array([1.0, 0.0]))[0] == 0.0 and room.to_db(np.array([0.0]))[0] == room.FLOOR_DB
