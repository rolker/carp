"""The desktop's own volumes for a card (save, restore, verify) and how
duplex_check.py uses them with the mixer and the borrowed card. Fakes only:
no sound server is asked and no card is touched."""
import importlib.util
import io
import json
import os
import shutil
import sys
import types

import pytest

from acoustics_lab.hardware import (checks, desktop, discovery, fake,
                                    mixer, reserve)
from fake_audio import FakeAlsaBackend, FakeClock, FakeDesktop, node

HERE = os.path.dirname(os.path.abspath(__file__))
CARD = 7
SINK = "alsa_output.pci-0000_00_1f.3.analog-stereo"
SOURCE = "alsa_input.pci-0000_00_1f.3.analog-stereo"


def speaker(volume=0.13, name=SINK, card=CARD, mute=False):
    return node(desktop.SINK, name, card, [volume, volume], mute,
                "Built-in Audio Analog Stereo")


def microphone(volume=0.70, name=SOURCE, card=CARD):
    return node(desktop.SOURCE, name, card, [volume, volume], False,
                "Built-in Audio Analog Stereo")


def hdmi():
    return node(desktop.SINK, "alsa_output.hdmi", 0, [0.63, 0.63])


def run_restore(saved, server, **options):
    clock = FakeClock()
    return desktop.restore(saved, server, sleep=clock.sleep, clock=clock, **options)


# -- save -----------------------------------------------------------------------

def test_save_keeps_only_the_cards_own_sinks_and_sources():
    server = FakeDesktop([speaker(), microphone(), hdmi()], "default-sink", "default-source")
    saved = desktop.save(CARD, server)
    assert [n.name for n in saved.nodes] == [SINK, SOURCE]
    assert saved.default_sink == "default-sink"
    text = " ".join(saved.lines())
    assert "0.13" in text and "0.70" in text and "card 7" in text
    assert "no sink or source" in desktop.save(3, server).lines()[0]


def test_card_is_read_from_either_alsa_property():
    assert desktop.card_of({"alsa.card": "1"}) == 1
    assert desktop.card_of({"api.alsa.card": "2"}) == 2
    assert desktop.card_of({"alsa.card": "x"}) is None and desktop.card_of({}) is None


def test_volume_text():
    assert desktop.volume_text([0.13, 0.13]) == "0.13"
    assert desktop.volume_text([0.13, 0.2], True) == "0.13/0.20, muted"


# -- restore --------------------------------------------------------------------

def test_waits_for_the_sink_to_reappear_then_puts_the_volume_back():
    server = FakeDesktop([speaker(), microphone()])
    saved = desktop.save(CARD, server)
    server.current = []                                    # the card is borrowed

    def returns():                                          # WirePlumber is back,
        server.current = [speaker(0.56, SINK + ".14"),      # with new names and
                          microphone(0.15, SOURCE + ".14")]  # what it saw
    server.script[6] = returns
    result = run_restore(saved, server)
    assert result.ok and result.waited >= 1.0
    assert [e.status for e in result.entries] == [desktop.RESTORED, desktop.RESTORED]
    assert [n.volumes for n in server.current] == [[0.13, 0.13], [0.70, 0.70]]
    assert "put back to 0.13 (was 0.56)" in result.lines()[0]
    assert "put back to 0.70 (was 0.15)" in result.lines()[1]
    assert result.fix_commands() == []


def test_a_server_that_changes_it_again_is_corrected_again():
    server = FakeDesktop([speaker(0.13)])
    saved = desktop.save(CARD, server)
    server.current = [speaker(0.56)]
    again = []

    def meddle(target):                 # the first set is overridden once
        if not again:
            again.append(1)
            target.volumes = [0.40, 0.40]
    server.meddle = meddle
    result = run_restore(saved, server)
    assert result.ok and len(server.sets) == 2
    assert server.current[0].volumes == [0.13, 0.13]


def test_a_volume_that_never_stays_is_reported_with_the_command():
    server = FakeDesktop([speaker(0.13)])
    saved = desktop.save(CARD, server)
    server.current = [speaker(0.56)]
    server.meddle = lambda target: setattr(target, "volumes", [0.56, 0.56])
    result = run_restore(saved, server, rounds=3)
    assert not result.ok and result.entries[0].status == desktop.DIFFERS
    assert "should be 0.13 but is 0.56" in result.lines()[0]
    command = result.fix_commands()[0]
    assert command == f"pactl set-sink-volume {SINK} 8520 8520"
    assert f"pactl set-sink-mute {SINK} 0" in result.fix_commands()


def test_a_sink_that_does_not_come_back_is_reported_after_the_timeout():
    server = FakeDesktop([speaker(), microphone()])
    saved = desktop.save(CARD, server)
    server.current = [microphone(0.15)]                    # the speaker never returns
    result = run_restore(saved, server, timeout=3.0)
    assert not result.ok
    assert [e.status for e in result.entries] == [desktop.MISSING, desktop.RESTORED]
    assert result.waited >= 3.0
    assert "has not made it again" in result.lines()[0]


def test_nothing_to_do_when_it_is_as_it_was_and_mute_is_restored():
    server = FakeDesktop([speaker(0.13), microphone()])
    saved = desktop.save(CARD, server)
    result = run_restore(saved, server)
    assert result.ok and server.sets == []
    assert all(e.status == desktop.UNCHANGED for e in result.entries)
    server.current[0].mute = True
    server.current[1].volumes = [0.7, 0.2]
    result = run_restore(saved, server)
    assert result.ok
    assert ("mute", SINK, False) in server.sets
    assert server.current[1].volumes == [0.70, 0.70]


def test_a_card_with_no_desktop_nodes_restores_nothing():
    saved = desktop.save(CARD, FakeDesktop([hdmi()]))
    result = run_restore(saved, FakeDesktop([]))
    assert result.ok and result.entries == []


def test_a_server_error_is_a_result_not_an_exception():
    server = FakeDesktop([speaker()])
    saved = desktop.save(CARD, server)
    server.fail = "cannot reach the sound server"
    result = run_restore(saved, server)
    assert not result.ok and "cannot reach" in result.lines()[0]


def test_a_changed_default_is_mentioned_not_changed():
    server = FakeDesktop([speaker()], "sink-a", "source-a")
    saved = desktop.save(CARD, server)
    server.sink_default = "sink-b"
    result = run_restore(saved, server)
    assert result.ok
    assert any("pactl set-default-sink sink-a" in line for line in result.lines())


def test_matching_survives_a_renamed_node():
    saved = [speaker(name="alsa_output.x.analog-stereo.14"), microphone(name="in.1")]
    now = [microphone(name="in.2"), speaker(name="alsa_output.x.analog-stereo.15")]
    found = desktop.match(saved, now)
    assert found[0].name.endswith(".15") and found[1].name == "in.2"


# -- backends -------------------------------------------------------------------

SINKS_JSON = json.dumps([{
    "index": 5, "name": SINK, "description": "Built-in Audio Analog Stereo",
    "mute": False, "monitor_source": SINK + ".monitor",
    "volume": {"front-left": {"value": 8520, "value_percent": "13%"},
               "front-right": {"value": 8520, "value_percent": "13%"}},
    "properties": {"alsa.card": "7"}}])
SOURCES_JSON = json.dumps([
    {"index": 6, "name": SINK + ".monitor", "description": "Monitor", "mute": False,
     "monitor_of_sink": 5, "volume": {"mono": {"value": 65536}},
     "properties": {"alsa.card": "7"}},
    {"index": 7, "name": SOURCE, "description": "Built-in Audio Analog Stereo",
     "mute": True, "monitor_of_sink": None,
     "volume": {"front-left": {"value": 45875}, "front-right": {"value": 45875}},
     "properties": {"api.alsa.card": "7"}}])


class FakePactl:
    def __init__(self):
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        if args[:2] == ["--format=json", "list"]:
            return SINKS_JSON if args[2] == "sinks" else SOURCES_JSON
        if args[0] == "get-default-sink":
            return SINK + "\n"
        if args[0] == "get-default-source":
            return SOURCE + "\n"
        return ""


def test_pactl_backend_reads_json_skips_monitors_and_sets_raw_volumes():
    runner = FakePactl()
    backend = desktop.PactlBackend(runner)
    saved = desktop.save(CARD, backend)
    assert [(n.kind, n.name, n.mute) for n in saved.nodes] == [
        (desktop.SINK, SINK, False), (desktop.SOURCE, SOURCE, True)]
    assert saved.nodes[0].volumes == [pytest.approx(0.13, abs=1e-4)] * 2
    assert saved.default_sink == SINK
    backend.set_volume(saved.nodes[0], [0.13, 0.13])
    backend.set_mute(saved.nodes[1], False)
    assert ["set-sink-volume", SINK, "8520", "8520"] in runner.calls
    assert ["set-source-mute", SOURCE, "0"] in runner.calls


def fake_pulsectl(monkeypatch):
    """A stand-in for the pulsectl module with a tiny in-memory server."""
    state = {"sinks": [types.SimpleNamespace(
        name=SINK, index=5, description="Built-in", mute=0,
        volume=types.SimpleNamespace(values=[0.13, 0.13]),
        proplist={"alsa.card": "7"}, monitor_of_sink=None)],
        "sources": [types.SimpleNamespace(
            name=SINK + ".monitor", index=6, description="Monitor", mute=0,
            volume=types.SimpleNamespace(values=[1.0, 1.0]),
            proplist={"alsa.card": "7"}, monitor_of_sink=5),
            types.SimpleNamespace(
            name=SOURCE, index=7, description="Mic", mute=0,
            volume=types.SimpleNamespace(values=[0.7, 0.7]),
            proplist={"alsa.card": "7"}, monitor_of_sink=0xFFFFFFFF)]}

    class PulseError(Exception):
        pass

    class Pulse:
        def __init__(self, client):
            pass

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def sink_list(self):
            return state["sinks"]

        def source_list(self):
            return state["sources"]

        def volume_set(self, item, info):
            item.volume.values = list(info.values)

        def mute(self, item, mute):
            item.mute = int(mute)

        def server_info(self):
            return types.SimpleNamespace(default_sink_name=SINK,
                                         default_source_name=SOURCE)

    module = types.ModuleType("pulsectl")
    module.Pulse, module.PulseError = Pulse, PulseError
    module.PulseVolumeInfo = lambda values: types.SimpleNamespace(values=values)
    monkeypatch.setitem(sys.modules, "pulsectl", module)
    return state


def test_pulsectl_backend_lists_and_sets(monkeypatch):
    state = fake_pulsectl(monkeypatch)
    backend = desktop.PulsectlBackend()
    saved = desktop.save(CARD, backend)
    assert [n.name for n in saved.nodes] == [SINK, SOURCE]       # no monitor
    assert saved.backend == "pulsectl" and saved.default_source == SOURCE
    backend.set_volume(saved.nodes[0], [0.5, 0.5])
    backend.set_mute(saved.nodes[1], True)
    assert state["sinks"][0].volume.values == [0.5, 0.5]
    assert state["sources"][1].mute == 1
    with pytest.raises(desktop.DesktopError, match="gone"):
        backend.set_volume(desktop.Node(desktop.SINK, "nope"), [1.0])


def test_default_backend_prefers_pulsectl_then_pactl_then_nothing(monkeypatch):
    fake_pulsectl(monkeypatch)
    backend, note = desktop.default_backend()
    assert backend.name == "pulsectl" and note == ""
    monkeypatch.setitem(sys.modules, "pulsectl", None)          # import fails
    monkeypatch.setattr(shutil, "which", lambda name: "/usr/bin/pactl")
    backend, note = desktop.default_backend()
    assert backend.name == "pactl" and "python3-pulsectl" in note
    monkeypatch.setattr(shutil, "which", lambda name: None)
    backend, note = desktop.default_backend()
    assert backend is None and "cannot be saved" in note


@pytest.mark.skipif(not shutil.which("pactl"), reason="no pactl")
def test_the_real_sound_server_can_be_read():
    """Reads only: lists the server's sinks and sources. Sets nothing."""
    try:
        nodes = desktop.PactlBackend().nodes()
    except desktop.DesktopError:
        pytest.skip("no sound server")
    assert all(n.volumes for n in nodes)
    assert all(not n.name.endswith(".monitor") for n in nodes if n.kind == desktop.SOURCE)


# -- duplex_check.py ---------------------------------------------------------------

MIXER_TEXT = """\
numid=4,iface=MIXER,name='Speaker Playback Switch'
  ; type=BOOLEAN,access=rw------,values=2
  : values=off,off
numid=5,iface=MIXER,name='Master Playback Volume'
  ; type=INTEGER,access=rw---R--,values=1,min=0,max=87,step=0
  : values=17
  | dBscale-min=-65.25dB,step=0.75dB,mute=0
numid=6,iface=MIXER,name='Capture Source'
  ; type=ENUMERATED,access=rw------,values=1,items=3
  ; Item #0 'Internal Mic'
  ; Item #1 'Headset Mic'
  ; Item #2 'Headphone Mic'
  : values=1
"""


class FakeReservation:
    """Records when the card is given back, and lets the test play
    WirePlumber taking it back."""
    log = None
    on_release = None

    def __init__(self, card, **options):
        self.card = card
        self.ok = True

    def acquire(self):
        self.log.append("borrow")

    def describe(self):
        return [f"Borrowed card {self.card} from FakeHolder."]

    def release(self):
        self.log.append("release")
        if self.on_release:
            self.on_release()

    def describe_release(self):
        return [f"Released card {self.card}."]


class World:
    """Everything duplex_check touches, faked."""

    def __init__(self, monkeypatch, tmp_path):
        self.log = []
        self.mixer = FakeAlsaBackend(MIXER_TEXT)
        self.mixer.log = self.log
        self.server = FakeDesktop([speaker(0.13), microphone(0.70)], SINK, SOURCE)
        self.server.log = self.log
        self.test_hook = None
        self.tmp = tmp_path
        card = discovery.Card(CARD, "PCH", "HDA-Intel", "HDA Intel PCH")
        monkeypatch.setattr(discovery, "list_cards", lambda *a, **k: [card])
        monkeypatch.setattr(mixer, "default_backend", lambda: self.mixer)
        monkeypatch.setattr(desktop, "default_backend", lambda: (self.server, ""))
        monkeypatch.setattr(desktop, "SETTLE_S", 0.0)
        monkeypatch.setattr(desktop, "TIMEOUT_S", 0.5)
        monkeypatch.setattr(desktop, "POLL_S", 0.01)
        FakeReservation.log = self.log
        FakeReservation.on_release = self.card_returns
        monkeypatch.setattr(reserve, "Reservation", FakeReservation)
        path = os.path.join(os.path.dirname(HERE), "tools", "duplex_check.py")
        spec = importlib.util.spec_from_file_location("duplex_check", path)
        self.module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(self.module)
        self.module.make_real = self.make_real
        monkeypatch.setattr(checks, "run_offset_test", self.offset_test)
        self.card = card
        self.after_return = lambda: None

    def make_real(self, args, out, holds):
        holds.append(self.module.borrow_card(self.card, args, out))
        self.server.current = []              # the desktop lets go of the card
        return fake.FakeDevice(), self.card

    def card_returns(self):
        """WirePlumber takes the card back and applies what it saw: its own
        idea of the volumes."""
        self.server.current = [speaker(0.56, SINK + ".2"), microphone(0.15, SOURCE + ".2")]
        self.after_return()

    def offset_test(self, device, *args, **kwargs):
        self.log.append("test")
        if self.test_hook:
            self.test_hook()
        return checks.TestResult("offset", [], {"verdict_ok": True}, ["verdict line"])

    def run(self, *argv):
        out = io.StringIO()
        code = self.module.main(["--device", str(CARD), "--offset-test", "--no-wait",
                                 "--runs", str(self.tmp / "runs")] + list(argv), out)
        return code, out.getvalue()


@pytest.fixture
def world(monkeypatch, tmp_path):
    return World(monkeypatch, tmp_path)


def test_everything_is_saved_first_and_put_back_in_order(world):
    code, text = world.run("--set", "Speaker Playback Switch=on")
    assert code == 0, text
    log = world.log
    # saved before the first mixer write; mixer put back before the card goes back;
    # desktop volumes put back after it.
    assert log.index("desktop read") < log.index("mixer write Speaker Playback Switch")
    assert log.index("borrow") < log.index("test") < log.index("release")
    writes = [i for i, entry in enumerate(log) if entry.startswith("mixer write")]
    assert writes[0] < log.index("borrow") and writes[-1] < log.index("release")
    sets = [i for i, entry in enumerate(log) if entry.startswith("desktop set")]
    assert sets and min(sets) > log.index("release")
    assert "Desktop volumes saved for card 7" in text
    assert "Mixer of card 7 put back as before the test: Speaker Playback Switch = off" in text
    assert text.index("put back as before the test") < text.index("Released card 7")
    assert text.index("Released card 7") < text.index("Desktop volumes of card 7 are as before")
    assert "put back to 0.13 (was 0.56)" in text and "put back to 0.70 (was 0.15)" in text
    assert text.rindex("Mixer of card 7 is as before the test.") > text.index("Desktop volumes of card 7")
    assert "NOT as before" not in text and "Could not" not in text
    assert [n.volumes for n in world.server.current] == [[0.13, 0.13], [0.70, 0.70]]


def test_a_mixer_change_during_the_test_is_reported_and_saved(world):
    world.test_hook = lambda: (world.mixer.touch("Master Playback Volume", [50]),
                               __import__("time").sleep(0.5))
    code, text = world.run()
    assert "Something changed the mixer of" in text
    assert "Master Playback Volume: 17" in text and "-> 50" in text
    summaries = [os.path.join(d, "summary.json") for d, _, files
                 in os.walk(world.tmp / "runs") if "summary.json" in files]
    summary = json.load(open(summaries[0]))
    assert summary["mixer_changes"] and "Master Playback Volume" in summary["mixer_changes"][0]
    # The restore at the end is not reported as a second change.
    assert text.count("Master Playback Volume: 17 (") <= 2
    assert "Mixer of card 7 put back as before the test: Master Playback Volume" in text


def test_no_change_is_said_too(world):
    code, text = world.run()
    assert "Nothing changed the mixer of card 7 during the test" in text


def test_desktop_volumes_that_do_not_stay_are_a_prominent_warning_with_commands(world):
    world.server.meddle = lambda target: setattr(target, "volumes", [0.56, 0.56])
    code, text = world.run()
    assert "are NOT as before the test" in text and "!!!!!" in text
    assert f"pactl set-sink-volume {SINK}.2 8520 8520" in text


def test_a_mixer_the_desktop_changed_on_its_return_is_a_warning(world):
    world.after_return = lambda: world.mixer.touch("Capture Source", [0])
    code, text = world.run("--set", "Capture Source=Headphone Mic")
    assert "The mixer of" in text and "is NOT as before the test" in text
    assert "Capture Source: was Headset Mic, is Internal Mic" in text
    assert "duplex_check.py --device 7 --mixer --set 'Capture Source=Headset Mic'" in text


def test_no_desktop_binding_is_a_warning_and_the_test_goes_on(world, monkeypatch):
    monkeypatch.setattr(desktop, "default_backend",
                        lambda: (None, "neither python3-pulsectl nor pactl is available"))
    code, text = world.run()
    assert code == 0 and "WARNING: neither python3-pulsectl nor pactl" in text
    assert "Mixer of card 7 is as before the test." in text


def test_keep_mixer_and_no_borrow_leave_the_desktop_alone(world):
    code, text = world.run("--keep-mixer")
    assert "Desktop volumes saved" not in text and world.server.sets == []
    world.log.clear()
    code, text = world.run("--no-borrow")
    assert "Desktop volumes saved" not in text and "borrow" not in world.log
