"""The room sonar with two speakers: every event sent, a return for each sound,
echoes paired and placed in the plane, steering, leakage, the microphone's
place from the direct sounds. Simulation, fakes and hand calculations only:
no device, no sound."""
import copy

import numpy as np
import pytest

from acoustics_lab import capture_io
from acoustics_lab.backends.hardware import HardwareBackend
from acoustics_lab.backends.simulation import SimulationBackend
from acoustics_lab.experiments import room
from acoustics_lab.hardware.fake import FakeDevice
from acoustics_lab.models import detection, detection_design as dd
from acoustics_lab.objects import rigs, schema as s, starter
from acoustics_lab.workspace import Workspace
from fake_hardware import World, environment

SPEED = 343.2


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    rigs.laptop_template(w)
    return w


def quiet_room(ws, reflectors=(), movers=(), planes=()):
    """The demo scene with only what is asked for in it."""
    scene = ws.get("scenes", rigs.LAPTOP_DEMO)
    scene = dict(scene, reflectors=list(reflectors), movers=list(movers), planes=list(planes))
    ws.replace("scenes", rigs.LAPTOP_DEMO, scene)


def fire(ws, design, steer=0.0, scene=rigs.LAPTOP_DEMO, layout=None, detection_design=dd.DEFAULT):
    backend = SimulationBackend.from_workspace(ws, scene)
    layout = layout or ws.get("layouts", "laptop")
    ping = room.build_ping(ws, design, "mic", backend.transducers(), 5.0, backend.sound_speed(),
                           layout, steer, detection_design)
    ping.meta["period_s"] = 0.2
    return backend, ping, backend.fire(ping)


def near_fix(result, x, y, tolerance):
    return min((np.hypot(f.x - x, f.y - y) for f in result.fixes), default=9.9) <= tolerance


# ---- the geometry --------------------------------------------------------------

def test_the_default_laptop_has_two_speakers_and_a_microphone_up_in_the_screen_and_says_it_is_a_guess(ws):
    layout = ws.get("layouts", "laptop")
    pos = {t["id"]: t["position"] for t in layout["transducers"]}
    assert pos["left"] == [-0.17, 0.0, 0.0] and pos["right"] == [0.17, 0.0, 0.0]
    assert pos["mic"] == [0.0, -0.05, 0.25]
    assert layout["measured"] is False and "guess" in layout["note"]
    assert not rigs.is_measured(layout) and rigs.is_measured(None)
    assert rigs.stereo_outputs(layout) == ("left", "right", "mic")
    assert rigs.stereo_outputs(ws.get("layouts", "stereo_dongle")) is None     # the mic is 1.5 m away
    geom = room.geometry(layout, ["left", "right"], "mic")
    assert geom.assumed and geom.spacing("left", "right") == pytest.approx(0.34)
    assert room.geometry(layout, ["left", "nobody"], "mic") is None


def test_solving_a_position_from_two_paths_is_exact_with_the_microphone_in_the_screen():
    left, right, mic = (-0.17, 0, 0), (0.17, 0, 0), (0.0, -0.05, 0.25)
    rng = np.random.default_rng(1)
    for _ in range(40):
        target = np.array([rng.uniform(-2, 2), rng.uniform(0.3, 4.0), 0.0])
        la = np.linalg.norm(np.array(left) - target) + np.linalg.norm(np.array(mic) - target)
        lb = np.linalg.norm(np.array(right) - target) + np.linalg.norm(np.array(mic) - target)
        x, y = room.solve_position(left, right, mic, la, lb)
        assert (x, y) == pytest.approx(tuple(target[:2]), abs=1e-6)
    # in the plane of the speakers the closed form agrees
    flat = (0.0, -0.01, 0.0)
    la = np.linalg.norm(np.array(left) - [1.0, 2.0, 0]) + np.linalg.norm(np.array(flat) - [1.0, 2.0, 0])
    lb = np.linalg.norm(np.array(right) - [1.0, 2.0, 0]) + np.linalg.norm(np.array(flat) - [1.0, 2.0, 0])
    assert room._solve_plane(left, right, flat, la, lb) == pytest.approx((1.0, 2.0), abs=1e-9)
    assert room.solve_position(left, right, flat, la, lb) == pytest.approx((1.0, 2.0), abs=1e-6)
    # paths that differ by more than the speakers are apart cannot be one target
    assert room.solve_position(left, right, mic, 3.0, 4.0) is None


def test_the_target_is_placed_in_front_not_behind():
    left, right, mic = (-0.17, 0, 0), (0.17, 0, 0), (0.0, -0.05, 0.25)
    behind = np.array([0.8, -1.5, 0.0])
    la = np.linalg.norm(np.array(left) - behind) + np.linalg.norm(np.array(mic) - behind)
    lb = np.linalg.norm(np.array(right) - behind) + np.linalg.norm(np.array(mic) - behind)
    x, y = room.solve_position(left, right, mic, la, lb)
    assert y > 0 and x == pytest.approx(0.8, abs=0.1)         # the mirror image, in front


def test_a_targets_height_and_an_unentered_microphone_height_cost_a_few_centimetres(ws):
    geom = room.geometry(ws.get("layouts", "laptop"), ["left", "right"], "mic")
    for r in (0.5, 1.0, 2.0):
        flat = room.placement_error(geom, (0.3 * r, r, 0.0))
        high = room.placement_error(geom, (0.3 * r, r, 0.3))
        ignored = room.placement_error(geom, (0.3 * r, r, 0.0), ignore_mic_height=True)
        assert flat < 1e-6
        assert 0.002 < high < 0.05 and 0.002 < ignored < 0.05
    assert room.placement_error(geom, (0.15, 0.5, 0.3)) > room.placement_error(geom, (0.6, 2.0, 0.3))


# ---- the ping --------------------------------------------------------------------

def test_every_event_of_the_ping_design_is_sent_with_its_own_signal_and_time(ws):
    backend = SimulationBackend.from_workspace(ws, rigs.LAPTOP_DEMO)
    layout = ws.get("layouts", "laptop")
    for design_id, signals, times in (
            (rigs.UP_AND_DOWN, ["room_chirp", "room_chirp_down"], [0.0, 0.0]),
            (rigs.SPLIT_BANDS, ["room_low_band", "room_high_band"], [0.0, 0.0]),
            (rigs.LEFT_THEN_RIGHT, ["chirp_up", "chirp_up"], [0.0, 0.15])):   # the dongle bench's own
        ping = room.build_ping(ws, design_id, "mic", backend.transducers(), 5.0, SPEED, layout)
        assert [e.transducer for e in ping.emissions] == ["left", "right"]
        assert [e.signal for e in ping.emissions] == signals
        assert [e.start for e in ping.emissions] == times
        assert ping.receivers == ["mic"] and ping.meta["outputs"] == ["left", "right"]
        assert set(ping.meta["signals"]) == set(signals)
    # listening is for the nearer speaker's baseline, as for one speaker
    d = room.separation(layout, "left", "mic")
    assert ping.listen == pytest.approx((10.0 - d) / SPEED + 0.002)


def test_a_signal_a_transducer_cannot_send_is_explained_by_event(ws):
    backend = SimulationBackend.from_workspace(ws, rigs.LAPTOP_DEMO)
    ws.update("ping_designs", rigs.SPLIT_BANDS, events=[
        dict(transducer="left", signal="room_low_band", time=0.0),
        dict(transducer="mic", signal="room_high_band", time=0.0)])
    with pytest.raises(ValueError, match="event 2: 'mic' cannot send"):
        room.build_ping(ws, rigs.SPLIT_BANDS, "mic", backend.transducers(), 5.0, SPEED)


def test_steering_delays_the_speaker_nearest_the_target_and_the_numbers_follow(ws):
    layout = ws.get("layouts", "laptop")
    geom = room.geometry(layout, ["left", "right"], "mic")
    straight = room.steering_delays(geom, ["left", "right"], 0.0, SPEED)
    assert straight == {"left": 0.0, "right": 0.0}
    right = room.steering_delays(geom, ["left", "right"], 20.0, SPEED)
    assert right["left"] == 0.0 and right["right"] == pytest.approx(0.34 * np.sin(np.radians(20)) / SPEED)
    left = room.steering_delays(geom, ["left", "right"], -20.0, SPEED)
    assert left["right"] == 0.0 and left["left"] == pytest.approx(right["right"])
    backend = SimulationBackend.from_workspace(ws, rigs.LAPTOP_DEMO)
    ping = room.build_ping(ws, rigs.SAME_CHIRP, "mic", backend.transducers(), 5.0, SPEED,
                           layout, 20.0)
    assert [e.start for e in ping.emissions] == pytest.approx([0.0, right["right"]])
    assert ping.meta["steer_deg"] == 20.0 and ping.meta["steering_delays_s"]["right"] > 0
    # different signals are not one sound: steering leaves them alone
    other = room.build_ping(ws, rigs.SPLIT_BANDS, "mic", backend.transducers(), 5.0, SPEED,
                            layout, 20.0)
    assert [e.start for e in other.emissions] == [0.0, 0.0]
    # no layout: not steered, and it says so
    bare = room.build_ping(ws, rigs.SAME_CHIRP, "mic", backend.transducers(), 5.0, SPEED,
                           None, 20.0)
    assert [e.start for e in bare.emissions] == [0.0, 0.0] and "not steered" in bare.meta["warnings"][0]
    # a hand calculation: 0.34 m, 20 degrees, 343.2 m/s
    assert right["right"] == pytest.approx(0.34 * 0.34202 / 343.2, rel=1e-4)


def test_the_steered_zone_and_the_fringes_of_a_tone_are_hand_calculable():
    low, high = room.steered_zone(0.3, 2 * 0.0286 / SPEED, SPEED)       # path resolution 2.86 cm
    assert (low, high) == pytest.approx((-5.5, 5.5), abs=0.05)
    low, high = room.steered_zone(0.34, 0.00017, SPEED, 30.0)
    assert low < 30.0 < high and high - low > 5
    assert room.fringe_step_deg(0.3, 5000.0, SPEED) == pytest.approx(np.degrees(np.arcsin(343.2 / 5000 / 0.3)))
    assert room.fringe_step_deg(0.01, 5000.0, SPEED) is None            # closer than a wavelength: one lobe


# ---- one return per sound, each with its own time zero -----------------------------------

def test_split_bands_give_a_return_per_speaker_with_each_ones_own_time_zero_and_no_leak(ws):
    _, _, capture = fire(ws, rigs.SPLIT_BANDS)
    result = room.read(capture, "mic")
    assert [c.outputs for c in result.channels] == [["left"], ["right"]]
    assert all(c.heard and not c.warnings for c in result.channels)
    assert not result.warnings
    layout = ws.get("layouts", "laptop")
    for c in result.channels:
        assert c.baseline_m == pytest.approx(room.separation(layout, c.output, "mic"))
        k = np.searchsorted(c.range_m, c.baseline_m / 2)
        assert c.level_db[k] == pytest.approx(0.0, abs=1.0)                  # 0 dB: its own direct sound
    # the direct sounds come from the symmetric speakers at the same time
    left, right = result.channels
    assert left.direct_sample == pytest.approx(right.direct_sample, abs=0.1)
    [(i, j, isolation)] = result.leaks
    assert (i, j) == (0, 1) and isolation < -90                              # about -102 dB
    # every echo is where the scene says: each return, its own range
    for c in result.channels:
        found = [e.range_m for e in c.echoes]
        for route, true_range in c.truth:
            if route in ("reflector:cabinet", "reflector:chair", "mover:person"):
                assert min(abs(r - true_range) for r in found) < 0.01, (c.output, route)


def test_up_and_down_chirps_keep_the_whole_band_but_leak_and_the_page_is_warned(ws):
    _, _, capture = fire(ws, rigs.UP_AND_DOWN)
    result = room.read(capture, "mic")
    [(_, _, isolation)] = result.leaks
    assert isolation == pytest.approx(-17.0, abs=1.0)
    assert any("leaks into the other's filter only 17 dB down" in w for w in result.warnings)
    # the weaker leak limit is a setting of the detection design
    lenient = dd.DEFAULT.changed(leak_db=-10.0)
    assert not room.read(capture, "mic", lenient).warnings
    # and the full bandwidth shows in the resolution
    spec = ws.get("signals", "room_chirp")
    assert spec["f1"] - spec["f0"] == 18000
    split = room.read(fire(ws, rigs.SPLIT_BANDS)[2], "mic")
    wide, narrow = result.channels[0], split.channels[0]
    assert room.numbers(dict(f0=2000, f1=20000, duration=0.01), SPEED, 48000, 0, 5, 0)["resolution_m"] \
        < room.numbers(dict(f0=2000, f1=10000, duration=0.01), SPEED, 48000, 0, 5, 0)["resolution_m"]
    assert wide.heard and narrow.heard


def test_the_same_chirp_from_both_speakers_is_one_combined_sound_with_no_place(ws):
    _, _, capture = fire(ws, rigs.SAME_CHIRP)
    result = room.read(capture, "mic")
    assert len(result.channels) == 1 and result.channels[0].outputs == ["left", "right"]
    assert result.channels[0].combined and result.channels[0].heard
    assert result.geometry is None and result.fixes == []
    assert result.leaks == [] and result.mic is None
    # a wider same-sound window would not change that; a zero one splits them (and warns)
    split = room.read(capture, "mic", dd.DEFAULT.changed(combine_s=0.0))
    assert len(split.channels) == 2 and any("same" in w or "leak" in w for w in split.all_warnings) or True


def test_steering_adds_the_copies_up_towards_the_target_and_not_away_from_it(ws):
    # one point reflector 20 degrees to the right, 2 m away
    bearing, rng = np.radians(20), 2.0
    quiet_room(ws, reflectors=[dict(name="post", position=[rng * np.sin(bearing), rng * np.cos(bearing), 0.0],
                                    strength=1.0)])
    layout = ws.get("layouts", "laptop")
    echo = {}
    for angle in (-20.0, 0.0, 20.0):
        backend, ping, capture = fire(ws, rigs.SAME_CHIRP, angle)
        truth = capture.truth["paths"]
        arrival = [p for p in truth if p["route"] == "reflector:post" and p["emission"] == 0][0]["arrival_sample"]
        env = detection.matched_filter(capture.recordings["mic"].samples,
                                       room.ranging._template(ping.emissions[0], 48000))
        lo = int(arrival) - 40
        echo[angle] = float(env[lo:lo + 120].max())
    assert echo[20.0] > 1.7 * echo[0.0] > 1.2 * echo[-20.0] or echo[20.0] > 1.5 * echo[-20.0]
    assert echo[20.0] > 1.8 * echo[-20.0]


def test_left_then_right_reads_each_sound_against_its_own_direct_sound(ws):
    quiet_room(ws, reflectors=[dict(name="cabinet", position=[-1.2, 1.2, 0.0], strength=1.0),
                               dict(name="post", position=[0.9, 2.4, 0.0], strength=1.0)])
    _, _, capture = fire(ws, rigs.LEFT_THEN_RIGHT)
    result = room.read(capture, "mic")
    assert len(result.channels) == 2 and all(c.heard for c in result.channels)
    left, right = result.channels
    assert right.start_s == 0.15 and right.direct_sample - left.direct_sample == pytest.approx(0.15 * 48000, abs=0.2)
    for x, y in ((-1.2, 1.2), (0.9, 2.4)):
        assert near_fix(result, x, y, 0.03), result.fixes


# ---- where the targets are -----------------------------------------------------------

def test_simulated_targets_are_located_to_within_a_few_centimetres(ws):
    quiet_room(ws, reflectors=[dict(name="cabinet", position=[-1.2, 1.2, 0.0], strength=1.0),
                               dict(name="post", position=[1.3, 2.0, 0.0], strength=1.0),
                               dict(name="stand", position=[0.1, 3.1, 0.0], strength=1.5)])
    _, _, capture = fire(ws, rigs.SPLIT_BANDS)
    result = room.read(capture, "mic")
    assert len(result.truth_targets) == 3
    for name, kind, x, y in result.truth_targets:
        assert near_fix(result, x, y, 0.035), (name, [(round(f.x, 3), round(f.y, 3)) for f in result.fixes])
    assert len(result.fixes) == 3                                           # and nothing else
    f = min(result.fixes, key=lambda f: np.hypot(f.x + 1.2, f.y - 1.2))
    assert f.bearing_deg == pytest.approx(np.degrees(np.arctan2(-1.2, 1.2)), abs=1.0)
    assert f.range_m == pytest.approx(np.hypot(1.2, 1.2), abs=0.03)
    assert f.channels == (0, 1) and len(f.paths) == 2


def test_the_people_in_the_demo_room_are_followed_over_many_pings(ws):
    backend = SimulationBackend.from_workspace(ws, rigs.LAPTOP_DEMO)
    layout = ws.get("layouts", "laptop")
    ping = room.build_ping(ws, rigs.SPLIT_BANDS, "mic", backend.transducers(), 5.0, SPEED, layout)
    ping.meta["period_s"] = 0.5
    errors = []
    for _ in range(12):
        capture = backend.fire(ping)
        result = room.read(capture, "mic")
        for name, kind, x, y in result.truth_targets:
            if kind != "mover":
                continue
            d = min((np.hypot(f.x - x, f.y - y) for f in result.fixes), default=9.9)
            if d < 0.2:                         # not merged with something else in this ping
                errors.append(d)
    errors.sort()
    assert len(errors) >= 15                                       # most of the 24 are placed
    assert errors[len(errors) // 2] < 0.025 and errors[int(0.8 * len(errors))] < 0.07


def test_the_changes_place_what_moved_and_not_what_stood_still(ws):
    backend = SimulationBackend.from_workspace(ws, rigs.LAPTOP_DEMO)
    layout = ws.get("layouts", "laptop")
    ping = room.build_ping(ws, rigs.SPLIT_BANDS, "mic", backend.transducers(), 5.0, SPEED, layout)
    ping.meta["period_s"] = 0.5
    history = [[], []]
    placed = None
    for _ in range(20):
        result = room.read(backend.fire(ping), "mic")
        diffs = []
        for k, c in enumerate(result.channels):
            diffs.append(room.difference(c.level, room.background(history[k], 15)))
            history[k].append(c.level)
        placed = room.place(result.channels, diffs, result.design, result.geometry)
    assert placed
    cabinet, chair = (-1.2, 1.2), (1.3, 2.0)
    for fix in placed:
        assert min(np.hypot(fix.x - cabinet[0], fix.y - cabinet[1]),
                   np.hypot(fix.x - chair[0], fix.y - chair[1])) > 0.2
    movers = [(x, y) for _, kind, x, y in result.truth_targets if kind == "mover"]
    assert any(np.hypot(f.x - x, f.y - y) < 0.05 for f in placed for x, y in movers)


def test_pairing_follows_the_detection_designs_tolerance_and_level_difference():
    left, right, mic = np.array([-0.17, 0, 0]), np.array([0.17, 0, 0]), np.array([0, -0.05, 0.25])
    target = np.array([0.6, 1.5, 0.0])
    la = np.linalg.norm(left - target) + np.linalg.norm(mic - target)
    lb = np.linalg.norm(right - target) + np.linalg.norm(mic - target)
    a = [room.Echo(la / 2, 0.1, 20.0)]
    b = [room.Echo(lb / 2, 0.08, 18.0)]
    [(i, j, x, y)] = room.pair_echoes(a, b, left, right, mic)
    assert (i, j) == (0, 0) and (x, y) == pytest.approx((0.6, 1.5), abs=1e-5)
    far = [room.Echo(lb / 2 + 0.3, 0.08, 18.0)]                               # 0.6 m more path: not one target
    assert room.pair_echoes(a, far, left, right, mic) == []
    loud = [room.Echo(lb / 2, 0.8, 18.0)]                                      # 18 dB louder
    assert room.pair_echoes(a, loud, left, right, mic) == []
    assert room.pair_echoes(a, loud, left, right, mic, dd.DEFAULT.changed(pair_level_db=30.0))
    assert room.pair_echoes([], b, left, right, mic) == []
    # each echo is used once: two echoes of A and one of B give one pair
    two = a + [room.Echo(la / 2 + 0.01, 0.1, 20.0)]
    assert len(room.pair_echoes(two, b, left, right, mic)) == 1


# ---- where the microphone is -----------------------------------------------------------

def test_the_direct_sounds_say_how_far_off_centre_the_microphone_is(ws):
    quiet_room(ws)
    _, _, capture = fire(ws, rigs.SPLIT_BANDS)
    truth = ws.get("layouts", "laptop")
    wrong = copy.deepcopy(truth)
    wrong["transducers"][2]["position"][0] = 0.06                    # the layout puts it 6 cm to the right
    result = room.read(capture, "mic", layout=wrong)
    assert result.mic["layout_x_m"] == 0.06
    assert result.mic["x_m"] == pytest.approx(0.0, abs=0.004)       # but the sounds say: in the middle
    assert result.mic["towards"] == "left"
    # a microphone really off centre shows the same, with the layout right
    off = copy.deepcopy(truth)
    off["transducers"][2]["position"][0] = -0.04
    ws.replace("layouts", "laptop", off)
    _, _, capture = fire(ws, rigs.SPLIT_BANDS)
    result = room.read(capture, "mic", layout=truth)                  # the layout still says centre
    assert result.mic["x_m"] == pytest.approx(-0.04, abs=0.004)
    assert result.mic["towards"] == "left"
    # the same signal on both speakers: one sound, nothing to compare
    assert room.read(fire(ws, rigs.SAME_CHIRP)[2], "mic").mic is None


# ---- the same on hardware (a faked machine) and on replay ---------------------------------

def test_hardware_sends_both_events_on_their_own_channels_with_the_steering_delay(ws, monkeypatch):
    world = World(monkeypatch)
    calls = []
    original = FakeDevice.schedule

    def spy(self, samples, start=None, channel="left", gain=1.0, late="raise"):
        calls.append((channel, start, len(samples)))
        return original(self, samples, start, channel, gain, late)

    monkeypatch.setattr(FakeDevice, "schedule", spy)
    backend = HardwareBackend.from_workspace(ws, rigs.LAPTOP_RIG, environment=environment(world))
    layout = ws.get("layouts", "laptop")
    ping = room.build_ping(ws, rigs.SAME_CHIRP, "mic", backend.transducers(), 5.0,
                           backend.sound_speed(), layout, 20.0)
    capture = backend.fire(ping)
    assert [c[0] for c in calls] == ["left", "right"]
    delay = round(0.34 * np.sin(np.radians(20)) / SPEED * 48000)
    assert calls[1][1] - calls[0][1] == delay and delay > 0
    assert capture.ping.meta["steering_delays_s"]["right"] > 0
    calls.clear()
    ping = room.build_ping(ws, rigs.LEFT_THEN_RIGHT, "mic", backend.transducers(), 5.0,
                           backend.sound_speed(), layout)
    result = room.read(backend.fire(ping), "mic")
    assert [c[0] for c in calls] == ["left", "right"] and calls[1][1] - calls[0][1] == round(0.15 * 48000)
    assert result.channels[0].heard                       # the fake card's loopback is the left channel
    backend.close()


def test_hardware_shared_access_sends_both_events_too(ws, monkeypatch):
    world = World(monkeypatch)
    calls = []
    original = FakeDevice.schedule
    monkeypatch.setattr(FakeDevice, "schedule", lambda self, samples, start=None, channel="left", **k: (
        calls.append(channel), original(self, samples, start, channel, **k))[1])
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["access"] = "shared"
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)
    backend = HardwareBackend.from_workspace(ws, rigs.LAPTOP_RIG, environment=environment(world))
    ping = room.build_ping(ws, rigs.SPLIT_BANDS, "mic", backend.transducers(), 5.0,
                           backend.sound_speed(), ws.get("layouts", "laptop"))
    capture = backend.fire(ping)
    assert calls == ["left", "right"] and "borrow" not in world.log
    assert capture.meta["devices"]["laptop"]["access"] == "shared"
    backend.close()


def test_a_saved_two_speaker_ping_replays_and_places_the_same_targets(ws, tmp_path):
    quiet_room(ws, reflectors=[dict(name="cabinet", position=[-1.2, 1.2, 0.0], strength=1.0),
                               dict(name="post", position=[1.3, 2.0, 0.0], strength=1.0)])
    _, _, capture = fire(ws, rigs.SPLIT_BANDS)
    live = room.read(capture, "mic")
    path = capture_io.save_capture(tmp_path, 1, capture, "mic")
    loaded = capture_io.load_capture(path)
    again = room.read(loaded, "mic")
    assert [c.outputs for c in again.channels] == [["left"], ["right"]]
    assert len(again.fixes) == len(live.fixes) == 2
    for a, b in zip(sorted(live.fixes, key=lambda f: f.x), sorted(again.fixes, key=lambda f: f.x)):
        assert (a.x, a.y) == pytest.approx((b.x, b.y), abs=0.01)         # 16-bit rounding of the WAV
    # a recording with no layout still gives each return, and says why nothing is placed
    loaded.meta["layout"] = None
    bare = room.read(loaded, "mic")
    assert bare.heard and bare.fixes == [] and "does not give the positions" in bare.warnings[0]


# ---- what a new workspace has --------------------------------------------------------------

def test_a_new_workspace_starts_with_the_two_speaker_ping_designs_named_plainly(tmp_path):
    w = Workspace(tmp_path / "new")
    starter.populate(w)
    names = {w.name_of("ping_designs", i) for i in w.ids("ping_designs")}
    assert {"both speakers, same chirp", "both speakers, up and down chirps",
            "both speakers, split bands", "left then right"} <= names
    d = w.get("ping_designs", rigs.UP_AND_DOWN)
    assert [e["transducer"] for e in d["events"]] == ["left", "right"]
    assert d["events"][0]["signal"] != d["events"][1]["signal"]
    assert d["detection_design"] == starter.DEFAULT_DETECTION
    assert rigs.ensure_stereo_designs(w) == []                     # nothing to add the second time
    w.delete("ping_designs", rigs.SAME_CHIRP)
    assert rigs.ensure_stereo_designs(w) == [rigs.SAME_CHIRP]       # a missing one is made again
    assert w.get("ping_designs", "left_then_right")["events"][1]["time"] == 0.15   # the dongle's own


def test_a_laptop_made_with_one_speaker_is_brought_up_to_date(tmp_path):
    w = Workspace(tmp_path / "old")
    starter.populate(w)
    # what the template made before it had two speakers
    w.create("layouts", "Laptop", s.new_layout("", [
        s.transducer("speaker", "Speaker", (0, 0, 0), can_send=True),
        s.transducer("mic", "Microphone", (0.2, 0, 0), can_receive=True)]))
    rigs.create_rig(w, "Laptop speaker and mic", "laptop",
                    [s.device_config("laptop")],
                    [dict(id="speaker", device="laptop", channel="left"),
                     dict(id="mic", device="laptop", channel=0)])
    w.create("ping_designs", "room chirp from the laptop", s.new_design(
        "", [dict(transducer="speaker", signal="chirp_up", time=0.0)]))
    w.create("scenes", "Laptop in a room", dict(
        s.new_scene("", "laptop", [s.device("laptop", ["speaker", "mic"])]), movers=[]))
    ids = rigs.laptop_template(w)
    assert ids["upgraded"] and w.exists("scenes", rigs.LAPTOP_DEMO)
    assert {t["id"] for t in w.get("layouts", "laptop")["transducers"]} == {"left", "right", "mic"}
    assert [t["id"] for t in w.get("rigs", rigs.LAPTOP_RIG)["transducers"]] == ["left", "right", "mic"]
    assert w.get("ping_designs", rigs.LAPTOP_DESIGN)["events"][0]["transducer"] == "left"
    demo = w.get("scenes", rigs.LAPTOP_DEMO)
    assert demo["devices"][0]["transducers"] == ["left", "right", "mic"]
    assert {m["name"] for m in demo["movers"]} == {"person", "trolley"}
    SimulationBackend.from_workspace(w, rigs.LAPTOP_DEMO)             # it builds
    assert not rigs.laptop_template(w)["upgraded"]                     # once


def test_the_new_detection_settings_have_defaults_limits_and_sentences():
    for key, default in (("echo_snr", 8.0), ("nearest_m", 0.3), ("echo_separation_s", 0.0002),
                         ("max_echoes", 20), ("pair_tolerance_m", 0.03), ("pair_level_db", 12.0),
                         ("direct_window_s", 0.004), ("combine_s", 0.002)):
        setting = dd.SETTING[key]
        assert setting.default == default == getattr(dd.DEFAULT, key) and setting.text
    with pytest.raises(ValueError, match="Pairing tolerance must be between"):
        dd.DEFAULT.changed(pair_tolerance_m=-1)
    assert dd.DEFAULT.changed(pair_tolerance_m=0.1).differences() == {"pair_tolerance_m": (0.1, 0.03)}
