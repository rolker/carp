"""Rigs and the hardware backend, on a faked machine: no card is borrowed, no
mixer written, no stream opened, no sound made."""
import numpy as np
import pytest

from acoustics_lab.backends.base import Cancelled
from acoustics_lab.backends.hardware import HardwareBackend
from acoustics_lab.experiments import ranging
from acoustics_lab.hardware.fake import FakeDevice
from acoustics_lab.hardware.stream import DeviceError
from acoustics_lab.models import detection_design as dd
from acoustics_lab.objects import rigs, schema as s, starter
from acoustics_lab.objects.schema import InUseError, WorkspaceError
from acoustics_lab.workspace import Workspace
from fake_hardware import World, environment, speaker, microphone

DIRECT = 3195          # samples from the output to the input, through the air (fake)


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    rigs.laptop_template(w)
    return w


def backend_for(ws, world, rig_id=rigs.LAPTOP_RIG, **env):
    messages = []
    backend = HardwareBackend.from_workspace(
        ws, rig_id, environment=environment(world, **env),
        on_message=lambda level, text: messages.append((level, text)))
    backend.messages = messages
    return backend


def ping_of(ws, backend, listen=None, **meta):
    ping = ranging.build_ping(ws, rigs.LAPTOP_DESIGN, backend.transducers())
    ping.meta.update(meta)
    if listen is not None:
        ping.listen = listen
    return ping


# ---- rigs as workspace objects --------------------------------------------------

def test_the_laptop_template_makes_a_rig_its_as_built_scene_and_a_demo(ws):
    ids = rigs.laptop_template(ws)
    rig = ws.get("rigs", ids["rig"])
    assert rig["layout"] == "laptop" and rig["as_built"] == ids["as_built"]
    assert ws.get("rigs", ids["rig"])["devices"][0]["access"] == "exclusive"
    built = ws.get("scenes", ids["as_built"])
    assert built["layout"] == "laptop" and built["devices"][0]["transducers"] == ["left", "right", "mic"]
    assert not built["movers"] and not built["reflectors"]
    demo = ws.get("scenes", ids["demo"])
    assert demo["movers"][0]["name"] == "person" and demo["planes"] and demo["reflectors"]
    assert ws.get("ping_designs", ids["design"])["detection_design"] == starter.DEFAULT_DETECTION
    assert rigs.laptop_template(ws) == ids                     # safe to repeat
    near = rigs.near_pairs(ws.get("layouts", "laptop"))
    assert [(a, b) for a, b, _ in near] == [("left", "mic"), ("right", "mic")]
    assert near[0][2] == pytest.approx(0.3064, abs=1e-3)
    assert rigs.near_pairs(ws.get("layouts", "stereo_dongle")) == []


def test_the_as_built_scene_follows_the_rig_and_keeps_the_benchs_own_surfaces(ws):
    built_id = ws.get("rigs", rigs.LAPTOP_RIG)["as_built"]
    ws.update("scenes", built_id, planes=[dict(name="wall", point=[0, 2, 0],
                                              normal=[0, -1, 0], reflection=0.3)])
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["rate"] = 44100
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)
    scene = ws.get("scenes", built_id)
    assert scene["devices"][0]["rate"] == 44100 and scene["planes"][0]["name"] == "wall"
    ws.undo_stack.undo()                      # one undo step undoes both
    assert ws.get("scenes", built_id)["devices"][0]["rate"] == 48000
    assert ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["rate"] == 48000
    assert rigs.is_as_built(ws, built_id) == rigs.LAPTOP_RIG
    assert rigs.is_as_built(ws, "dongle_bench") is None


def test_a_rig_is_checked_and_what_it_uses_cannot_be_deleted(ws):
    rig = ws.get("rigs", rigs.LAPTOP_RIG)
    with pytest.raises(InUseError):
        ws.delete("scenes", rig["as_built"])
    with pytest.raises(InUseError):
        ws.delete("layouts", "laptop")
    bad = dict(rig, transducers=[dict(id="left", device="nowhere", channel="left")])
    with pytest.raises(WorkspaceError, match="no device 'nowhere'"):
        ws.replace("rigs", rigs.LAPTOP_RIG, bad)
    twice = dict(rig, devices=rig["devices"] * 2)
    with pytest.raises(WorkspaceError, match="device IDs"):
        ws.replace("rigs", rigs.LAPTOP_RIG, twice)
    loop = dict(rig, devices=rig["devices"] + [s.device_config("b")],
                transducers=rig["transducers"][:1] + [dict(id="mic", device="b", channel=0)],
                loopbacks=[dict(receiver="mic", emitter="left")])
    with pytest.raises(WorkspaceError, match="same device"):
        ws.replace("rigs", rigs.LAPTOP_RIG, loop)
    assert rigs.problems(dict(rig, transducers=rig["transducers"][:1]), ws.get("layouts", "laptop"))
    rigs.delete_rig(ws, rigs.LAPTOP_RIG)
    assert not ws.exists("rigs", rigs.LAPTOP_RIG) and not ws.exists("scenes", rig["as_built"])
    ws.undo_stack.undo()
    assert ws.exists("rigs", rigs.LAPTOP_RIG) and ws.exists("scenes", rig["as_built"])


# ---- exclusive access: the whole sequence ------------------------------------

def test_a_ping_borrows_the_card_sets_the_mixer_and_close_puts_everything_back(ws, world):
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["mixer"] = {"Master Playback Volume": "50", "Capture Volume": "10"}
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)
    backend = backend_for(ws, world)
    capture = backend.open_stream(ping_of(ws, backend)).fire()
    log = world.log
    # saved first, then set, then borrowed, then opened
    assert log.index("desktop read") < log.index("mixer write Master Playback Volume")
    assert log.index("mixer write Capture Volume") < log.index("borrow") < log.index("open laptop hw")
    assert log.count("borrow") == 1
    info = capture.meta["devices"]["laptop"]
    assert info["access"] == "exclusive" and info["mixer_applied"] == {
        "Master Playback Volume": "50", "Capture Volume": "10"}
    assert info["card"].startswith("card 1 [PCH]")
    assert info["desktop_volumes_saved"] and info["input_check"]["warnings"] == []
    assert capture.meta["backend"] == "Hardware" and capture.meta["rig_id"] == rigs.LAPTOP_RIG
    assert capture.meta["layout"]["transducers"][0]["id"] == "left"
    assert "release" not in log                      # kept open between pings
    backend.close()
    assert log.index("release") > log.index("mixer write Master Playback Volume")
    # the desktop's own volumes came back as saved, the mixer too
    assert [n.volumes for n in world.server.current] == [[0.13, 0.13], [0.70, 0.70]]
    assert [c.values for c in world.mixer.controls.values()
            if c.name in ("Master Playback Volume", "Capture Volume")] == [[17], [40]]
    assert any("as before the test" in text for _, text in backend.messages)
    backend.close()                                  # twice is harmless
    assert log.count("release") == 1


def test_the_laptop_template_carries_what_worked_on_the_real_card(ws, world):
    mixer_settings = ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["mixer"]
    assert mixer_settings == {"Master Playback Volume": "-15dB", "Capture Volume": "5dB",
                              "Internal Mic Boost Volume": "0dB"}
    backend = backend_for(ws, world)
    backend.fire(ping_of(ws, backend))
    changed = {c.name: c.values for c in world.mixer.controls.values()}
    assert changed["Master Playback Volume"] != [17] and changed["Capture Volume"] != [40]
    assert changed["Internal Mic Boost Volume"] == [0]          # was +20 dB
    backend.close()
    assert {c.name: c.values for c in world.mixer.controls.values()}["Internal Mic Boost Volume"] == [2]


def test_a_mixer_control_the_card_does_not_have_is_a_warning_and_the_rest_are_still_set(ws, world):
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["mixer"] = {"No Such Control": "50", "Capture Volume": "10"}
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)
    backend = backend_for(ws, world)
    capture = backend.fire(ping_of(ws, backend))
    assert any(lv == "warning" and "cannot set 'No Such Control'" in t for lv, t in backend.messages)
    assert "mixer write Capture Volume" in world.log
    assert capture.meta["devices"]["laptop"]["mixer_applied"]["Capture Volume"] == "10"
    backend.close()


def test_pings_keep_the_streams_open_and_a_capture_has_the_structure_of_hardware(ws, world):
    backend = backend_for(ws, world)
    stream = backend.open_stream(ping_of(ws, backend))
    first, second = stream.fire(), stream.fire()
    assert world.log.count("borrow") == 1 and world.log.count("open laptop hw") == 1
    stream.close()
    assert backend.is_open()                          # the stream closing does not close devices
    rec = first.recordings["mic"]
    assert rec.clock == "laptop" and rec.rate == 48000 and rec.loopback_of == []
    assert rec.samples.dtype == np.float64 and np.max(np.abs(rec.samples)) < 1.0
    assert second.recordings["mic"].started > rec.started          # the same clock, later
    assert first.emitted["left"] == pytest.approx(
        first.meta["devices"]["laptop"]["started_output_sample"] / 48000)
    assert first.truth is None and first.meta["ping_index"] == 0 and second.meta["ping_index"] == 1
    assert first.ping.emissions[0].transducer == "left"
    # long enough for the sound, the listening time and the latency allowance
    assert len(rec.samples) >= (0.01 + 0.04 + 0.15) * 48000
    backend.close()


def test_a_hardware_capture_saves_with_what_made_it_and_replays(ws, world, tmp_path):
    import json
    from acoustics_lab import capture_io
    from acoustics_lab.experiments import room
    backend = backend_for(ws, world)
    capture = backend.fire(ping_of(ws, backend))
    backend.close()
    path = capture_io.save_capture(tmp_path, 1, capture, "mic")
    side = json.load(open(path + ".json"))["acoustics_lab"]
    assert side["backend"] == "Hardware" and side["rig"]["name"] == "Laptop speaker and mic"
    assert side["devices"]["laptop"]["access"] == "exclusive"
    assert side["devices"]["laptop"]["mixer_applied"]["Capture Volume"] == "5dB"
    assert side["layout"]["transducers"][0]["id"] == "left"
    assert side["ping"]["design_id"] == rigs.LAPTOP_DESIGN
    loaded = capture_io.load_capture(path)
    assert loaded.meta["sound_speed"] == pytest.approx(capture.meta["sound_speed"])
    assert loaded.ping.meta["design_id"] == rigs.LAPTOP_DESIGN
    result = room.analyse(loaded, "left", "mic")
    assert result.heard and result.baseline_m == pytest.approx(0.3064, abs=1e-3)
    assert result.direct_sample == pytest.approx(DIRECT, abs=1.0)    # 16-bit rounding of the WAV


def test_the_output_to_input_offset_is_measured_from_the_recording(ws, world):
    backend = backend_for(ws, world)
    capture = backend.fire(ping_of(ws, backend))
    result = ranging.analyse_capture(capture, "mic")
    assert result.analysis.detected() == [0]
    # the recording starts when the output is scheduled to start
    assert result.analysis.results[0].first == pytest.approx(DIRECT, abs=0.6)
    assert result.warnings == []
    backend.close()


def test_the_detection_design_in_the_ping_sets_how_long_the_input_settles(ws, world):
    backend = backend_for(ws, world)
    quick = dd.DEFAULT.changed(settle_s=0.0)
    backend.fire(ping_of(ws, backend, detection_settings=quick.to_dict()))
    stream = backend.env.made[0]
    assert stream.in_position < 2.0 * 48000 + 9000        # not the 2 s default settle
    backend.close()


def test_a_quiet_input_with_a_loud_offset_is_warned_about_not_refused(ws, world):
    noisy = FakeDevice(rate=48000, in_latency=2000.0, out_latency=1195.0,
                       noise_rms=9000.0, name="laptop")
    backend = backend_for(ws, world, streams=dict(laptop=noisy))
    capture = backend.fire(ping_of(ws, backend))
    warnings = [text for level, text in backend.messages if level == "warning"]
    assert any("noisy" in text or "clipping" in text for text in warnings)
    assert capture.meta["devices"]["laptop"]["input_check"]["warnings"]
    backend.close()


def test_a_loud_ping_is_a_warning_and_a_ping_above_full_scale_is_clipped_not_refused(ws, world):
    ws.update("signals", rigs.LAPTOP_SIGNAL, amplitude=0.9)
    backend = backend_for(ws, world)
    backend.fire(ping_of(ws, backend))
    assert any(level == "warning" and "loud" in text for level, text in backend.messages)
    ping = ping_of(ws, backend)
    ping.emissions[0].samples = ping.emissions[0].samples * 3.0       # peak 2.7
    backend.fire(ping)
    assert any("clipped flat" in text for _, text in backend.messages)
    backend.close()


def test_the_non_usb_card_is_a_prominent_warning(ws, world):
    backend = backend_for(ws, world)
    backend.fire(ping_of(ws, backend))
    texts = [t for lv, t in backend.messages if lv == "warning"]
    assert any("the desktop's own sound" in t and "borrowed" in t for t in texts)
    backend.close()


def test_a_card_that_will_not_be_given_up_is_a_warning_and_the_open_is_still_tried(ws, world):
    from fake_hardware import FakeReservation
    FakeReservation.refuse = True
    backend = backend_for(ws, world)
    backend.fire(ping_of(ws, backend))
    assert any("refused" in t for lv, t in backend.messages if lv == "warning")
    backend.close()


def test_a_missing_card_says_what_is_missing_and_leaves_nothing_taken(ws, world):
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["card"] = "9"
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)
    backend = backend_for(ws, world)
    with pytest.raises(DeviceError) as error:
        backend.fire(ping_of(ws, backend))
    assert "no sound card matches '9'" in str(error.value) and "moved" in str(error.value)
    assert "borrow" not in world.log and not backend.is_open()


def test_a_failing_open_still_puts_everything_back(ws, world):
    class Broken(FakeDevice):
        def _start_transport(self):
            raise DeviceError("cannot open the stream (test)")
    backend = backend_for(ws, world, streams=dict(laptop=Broken(name="laptop")))
    with pytest.raises(DeviceError, match="cannot open"):
        backend.fire(ping_of(ws, backend))
    assert world.log.count("borrow") == 1 and world.log.count("release") == 1
    assert [n.volumes for n in world.server.current] == [[0.13, 0.13], [0.70, 0.70]]
    assert not backend.is_open()


def test_cancel_stops_before_anything_is_played(ws, world):
    backend = backend_for(ws, world)
    with pytest.raises(Cancelled):
        backend.fire(ping_of(ws, backend), cancel=lambda: True)
    assert "borrow" not in world.log


def test_transducers_a_rig_cannot_use_are_explained(ws, world):
    backend = backend_for(ws, world)
    ping = ping_of(ws, backend)
    ping.emissions[0].transducer = "mic"
    with pytest.raises(ValueError, match="'mic' cannot send"):
        backend.fire(ping)
    ping = ping_of(ws, backend)
    ping.receivers = ["left"]
    with pytest.raises(ValueError, match="'left' cannot receive"):
        backend.fire(ping)
    assert [(t.id, t.can_send, t.can_receive, t.rate) for t in backend.transducers()] == [
        ("left", True, False, 48000.0), ("right", True, False, 48000.0),
        ("mic", False, True, 48000.0)]


# ---- shared access ------------------------------------------------------------

def shared_rig(ws):
    devices = ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["access"] = "shared"
    devices[0]["server_device"] = "pipewire"
    rigs.update_rig(ws, rigs.LAPTOP_RIG, devices=devices)


def test_shared_access_borrows_nothing_writes_nothing_and_records_the_server_volume(ws, world):
    shared_rig(ws)
    backend = backend_for(ws, world)
    capture = backend.fire(ping_of(ws, backend))
    assert world.log == ["open laptop pipewire"] and not world.mixer.writes
    info = capture.meta["devices"]["laptop"]
    assert info["access"] == "shared" and info["server_volumes"]["sink_volume"] == 1.0
    assert "other sounds can mix in" in info["note"]
    assert [t for lv, t in backend.messages if lv == "warning"] == []
    backend.close()
    assert world.log == ["open laptop pipewire"]            # nothing to give back


def test_shared_access_warns_when_the_server_volume_is_not_100_percent(ws, world):
    from acoustics_lab.hardware import shared
    from fake_audio import FakeDesktop, node
    from acoustics_lab.hardware import desktop
    shared_rig(ws)
    server = FakeDesktop([node(desktop.SINK, "sink", None, [0.35, 0.35], False, "Speakers"),
                          node(desktop.SOURCE, "source", None, [1.0, 1.0], True, "Mic")],
                         "sink", "source")
    backend = backend_for(ws, world, volumes=shared.read_volumes(server))
    capture = backend.fire(ping_of(ws, backend))
    warnings = " ".join(t for lv, t in backend.messages if lv == "warning")
    assert "35 %, not 100 %" in warnings and "muted" in warnings
    assert capture.meta["devices"]["laptop"]["server_volumes"]["sink_volume"] == pytest.approx(0.35)
    backend.close()


# ---- two devices, two clocks ------------------------------------------------------

def test_a_sender_and_a_receiver_on_different_devices_are_two_clock_domains(ws, world):
    layout = ws.get("layouts", "stereo_dongle")
    rig_id = rigs.create_rig(
        ws, "Two cards", "stereo_dongle",
        devices=[s.device_config("out", card="1"), s.device_config("in", card="1", access="shared")],
        transducers=[dict(id="left", device="out", channel="left"),
                     dict(id="right", device="out", channel="right"),
                     dict(id="mic", device="in", channel=0)])
    backend = backend_for(ws, world, rig_id=rig_id)
    ping = ranging.build_ping(ws, "left_then_right", backend.transducers())
    capture = backend.fire(ping)
    assert capture.recordings["mic"].clock == "in"
    assert set(capture.meta["devices"]) == {"out", "in"}
    assert capture.meta["devices"]["in"]["input_window"][0] <= capture.meta["devices"]["in"]["input_window"][1]
    assert capture.emitted["left"] == pytest.approx(
        capture.meta["devices"]["out"]["started_output_sample"] / 48000)
    # the receiver is not the sender, so its window covers the lead as well
    assert len(capture.recordings["mic"].samples) > 0.15 * 48000
    backend.close()
    assert world.log.count("borrow") == 1                       # only the exclusive one


def test_loopbacks_are_part_of_the_recording_structure(ws, world):
    rig_id = rigs.create_rig(
        ws, "Dongle", "stereo_dongle", devices=[s.device_config("dongle")],
        transducers=[dict(id="left", device="dongle", channel="left"),
                     dict(id="right", device="dongle", channel="right"),
                     dict(id="mic", device="dongle", channel=0)],
        loopbacks=[dict(receiver="mic", emitter="left"), dict(receiver="mic", emitter="right")])
    streams = dict(dongle=FakeDevice(in_latency=130.3, out_latency=400.45, noise_rms=2.0))
    backend = backend_for(ws, world, rig_id=rig_id, streams=streams)
    capture = backend.fire(ranging.build_ping(ws, "left_then_right", backend.transducers()))
    assert capture.recordings["mic"].loopback_of == ["left", "right"]
    result = ranging.analyse_capture(capture, "mic")
    assert result.analysis.detected() == [0]            # the fake loops only the left channel back
    backend.close()


# ---- Identify -------------------------------------------------------------------

def test_identify_plays_a_short_tone_on_one_transducer_and_gives_the_card_back(ws, world):
    backend = backend_for(ws, world)
    sentence = backend.identify("left", seconds=0.3)
    assert "1000 Hz tone" in sentence and "Left speaker" in sentence
    stream = backend.env.made[0]
    assert stream.out_position > 0.3 * 48000
    assert world.log.count("borrow") == 1 and world.log.count("release") == 1
    assert not backend.is_open()
    with pytest.raises(ValueError, match="not an output"):
        backend.identify("mic")
    # a device already open for pings stays open
    backend.fire(ping_of(ws, backend))
    backend.identify("left", seconds=0.2)
    assert backend.is_open()
    backend.close()


def test_identify_tone_is_quiet_and_on_the_chosen_channel(ws, world):
    rig_id = rigs.create_rig(
        ws, "Dongle", "stereo_dongle", devices=[s.device_config("dongle")],
        transducers=[dict(id="left", device="dongle", channel="left"),
                     dict(id="right", device="dongle", channel="right"),
                     dict(id="mic", device="dongle", channel=0)])
    dev = FakeDevice(in_latency=130.3, out_latency=400.45, noise_rms=2.0)
    played = []
    original = dev.schedule

    def spy(samples, start=None, channel="left", gain=1.0, late="raise"):
        played.append((float(np.max(np.abs(samples))), channel))
        return original(samples, start, channel, gain, late)
    dev.schedule = spy
    backend = backend_for(ws, world, rig_id=rig_id, streams=dict(dongle=dev))
    backend.identify("right", level_db=-20.0, seconds=0.2)
    assert played == [(pytest.approx(0.1, abs=0.001), "right")]
