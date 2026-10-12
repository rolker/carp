"""The workspace: IDs, atomic files, refusals, cycles, undo, outside changes,
imports, and the whole ping path from a design to a table of arrivals."""
import json
from pathlib import Path

import numpy as np
import pytest

from acoustics_lab import capture_io, importers
from acoustics_lab.backends.replay import ReplayBackend
from acoustics_lab.backends.simulation import SimulationBackend
from acoustics_lab.experiments import ranging
from acoustics_lab.objects import schema as s
from acoustics_lab.objects import signals as signal_objects
from acoustics_lab.objects import starter
from acoustics_lab.objects.schema import InUseError, WorkspaceError
from acoustics_lab.workspace import Workspace

OLD_DESIGNS = Path(__file__).resolve().parents[2] / "acoustic" / "designs"


@pytest.fixture
def ws(tmp_path):
    return Workspace(tmp_path / "w")


@pytest.fixture
def started(tmp_path):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    return w


def files(ws, kind):
    return sorted(p.name for p in (ws.path / kind).glob("*.json"))


# ---- IDs and files -----------------------------------------------------

def test_new_workspace_has_the_folders_and_a_gitignore(ws):
    for kind in ("signals", "designs", "layouts", "scenes"):
        assert (ws.path / kind).is_dir()
    assert (ws.path / ".gitignore").read_text() == "runs/\n"
    assert json.loads((ws.path / "workspace.json").read_text())["name"] == "w"
    assert ws.is_new


def test_ids_are_short_readable_and_never_change(ws):
    a = ws.create("signals", "Chirp up 2-20k", s.new_chirp(""))
    b = ws.create("signals", "Chirp up 2-20k", s.new_chirp(""))
    assert (a, b) == ("chirp_up_2_20k", "chirp_up_2_20k_2")
    ws.update("signals", a, name="Something else entirely")
    assert ws.get("signals", a)["name"] == "Something else entirely"
    assert files(ws, "signals") == ["chirp_up_2_20k.json", "chirp_up_2_20k_2.json"]
    assert ws.name_of("signals", a) == "Something else entirely"


def test_files_are_stable_indented_json_written_atomically(ws):
    a = ws.create("signals", "up", s.new_chirp(""))
    text = (ws.path / "signals" / f"{a}.json").read_text()
    assert text.endswith("}\n") and text.index('"amplitude"') < text.index('"duration"')
    assert not list((ws.path / "signals").glob(".*"))      # no temporary file left


def test_reopening_reads_everything_back(started):
    again = Workspace(started.path)
    assert not again.is_new
    for kind in ("signals", "designs", "layouts", "scenes"):
        assert again.ids(kind) == started.ids(kind)
    assert again.get("scenes", "dongle_bench") == started.get("scenes", "dongle_bench")


def test_bad_values_are_refused(ws):
    with pytest.raises(WorkspaceError, match="length"):
        ws.create("signals", "x", s.new_chirp("", duration=0))
    with pytest.raises(WorkspaceError, match="level"):
        ws.create("signals", "x", s.new_chirp("", amplitude=2))
    with pytest.raises(WorkspaceError, match="no signal"):
        ws.create("designs", "d", s.new_design("", [dict(transducer="a", signal="nope", time=0)]))
    assert files(ws, "signals") == [] and files(ws, "designs") == []


# ---- references --------------------------------------------------------

def test_deleting_something_in_use_is_refused_and_says_who_uses_it(ws):
    up = ws.create("signals", "up", s.new_chirp(""))
    rev = ws.create("signals", "rev", s.new_derived("", "time_reverse", up))
    d = ws.create("designs", "d", s.new_design("", [dict(transducer="a", signal=rev, time=0)]))
    with pytest.raises(InUseError) as error:
        ws.delete("signals", up)
    assert error.value.users == [("signals", rev)]
    assert "signal 'rev'" in str(error.value)
    with pytest.raises(InUseError) as error:
        ws.delete("signals", rev)
    assert error.value.users == [("designs", d)]
    assert ws.exists("signals", up) and ws.exists("signals", rev)
    ws.delete("designs", d)             # now the chain can be taken apart
    ws.delete("signals", rev)
    ws.delete("signals", up)
    assert files(ws, "signals") == []


def test_derived_signals_cannot_form_a_loop(ws):
    a = ws.create("signals", "a", s.new_chirp(""))
    b = ws.create("signals", "b", s.new_derived("", "time_reverse", a))
    c = ws.create("signals", "c", s.new_derived("", "invert", b))
    with pytest.raises(WorkspaceError, match="derived from itself"):
        ws.replace("signals", a, s.new_derived("a", "invert", c))
    with pytest.raises(WorkspaceError, match="derived from itself"):
        ws.update("signals", b, source=c)
    with pytest.raises(WorkspaceError, match="derived from itself"):
        ws.update("signals", b, source=b)
    assert ws.get("signals", a)["type"] == "chirp" and ws.get("signals", b)["source"] == a


def test_derived_samples_follow_their_source(ws):
    up = ws.create("signals", "up", s.new_chirp("", 14000, 16000, 0.05, 0.4))
    rev = ws.create("signals", "rev", s.new_derived("", "time_reverse", up))
    x = signal_objects.samples(ws.get_signal, up, 48000)
    y = signal_objects.samples(ws.get_signal, rev, 48000)
    assert np.array_equal(y, x[::-1]) and abs(np.max(np.abs(x)) - 0.4) < 0.02
    assert signal_objects.band(ws.get_signal, rev) == (16000, 14000, 0.05)
    ws.update("signals", up, f1=18000.0)
    assert signal_objects.band(ws.get_signal, rev) == (18000.0, 14000, 0.05)
    worth = signal_objects.worth(ws.get_signal, up)
    assert abs(worth["bandwidth_hz"] - 4000) < 1e-9
    assert abs(worth["resolution_ms"] - 0.75) < 1e-9


# ---- undo --------------------------------------------------------------

def test_undo_and_redo_rewrite_the_files(ws):
    changes = []
    ws.changed.connect(lambda kind, i: changes.append((kind, i)))
    a = ws.create("signals", "up", s.new_chirp("", 2000, 20000))
    path = ws.path / "signals" / f"{a}.json"
    ws.update("signals", a, f1=15000.0)
    ws.update("signals", a, f1=12000.0)
    assert json.loads(path.read_text())["f1"] == 12000.0
    ws.undo_stack.undo()
    assert json.loads(path.read_text())["f1"] == 15000.0
    ws.undo_stack.undo()
    assert json.loads(path.read_text())["f1"] == 20000.0
    ws.undo_stack.undo()
    assert not path.exists() and not ws.exists("signals", a)
    ws.undo_stack.redo()
    ws.undo_stack.redo()
    assert json.loads(path.read_text())["f1"] == 15000.0
    assert changes[-1] == ("signals", a)
    # An edit that changes nothing is not an undo step.
    count = ws.undo_stack.count()
    ws.update("signals", a, f1=15000.0)
    assert ws.undo_stack.count() == count


def test_undoing_a_delete_brings_the_file_back(ws):
    a = ws.create("signals", "up", s.new_chirp(""))
    ws.delete("signals", a)
    assert files(ws, "signals") == []
    ws.undo_stack.undo()
    assert files(ws, "signals") == [f"{a}.json"]


def test_a_macro_is_one_undo_step(ws):
    with ws.macro("two signals"):
        ws.create("signals", "a", s.new_chirp(""))
        ws.create("signals", "b", s.new_chirp(""))
    assert ws.undo_stack.count() == 1
    ws.undo_stack.undo()
    assert files(ws, "signals") == []


# ---- changes from outside ----------------------------------------------

def test_outside_changes_are_reloaded_and_clear_the_undo_history(ws):
    a = ws.create("signals", "up", s.new_chirp("", 2000, 20000))
    messages = []
    ws.reloaded.connect(messages.append)
    assert ws.rescan() is False                 # our own writes are not news
    path = ws.path / "signals" / f"{a}.json"
    data = json.loads(path.read_text())
    data["f1"] = 9000.0
    path.write_text(json.dumps(data))
    assert ws.rescan() is True
    assert ws.get("signals", a)["f1"] == 9000.0
    assert ws.undo_stack.count() == 0
    assert "outside" in messages[0]
    (ws.path / "signals" / "new_one.json").write_text(
        json.dumps(s.new_chirp("Added by git")))
    path.unlink()
    assert ws.rescan() is True and ws.ids("signals") == ["new_one"]


def test_the_watcher_sees_a_file_change(ws, qtbot=None):
    from acoustics_lab.qtcompat import QtCore, QtWidgets
    app = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])
    a = ws.create("signals", "up", s.new_chirp("", 2000, 20000))
    ws.start_watching(delay_ms=20)
    got = []
    ws.reloaded.connect(got.append)
    path = ws.path / "signals" / f"{a}.json"
    data = json.loads(path.read_text())
    data["f1"] = 7000.0
    path.write_text(json.dumps(data))
    loop = QtCore.QEventLoop()
    QtCore.QTimer.singleShot(1500, loop.quit)
    ws.reloaded.connect(lambda _: loop.quit())
    loop.exec()
    assert got and ws.get("signals", a)["f1"] == 7000.0
    ws.stop_watching()
    del app


# ---- imports -----------------------------------------------------------

def test_old_designs_import_as_signals_and_ping_designs(ws):
    messages = importers.import_designs(ws, OLD_DESIGNS)
    assert len(messages) == len(list(OLD_DESIGNS.glob("*.json")))
    assert all("imported" in m for m in messages), messages
    assert ws.exists("layouts", "stereo_dongle") and ws.exists("scenes", "dongle_bench")
    # split-bands: low band on the left, high band on the right, together.
    d = ws.get("designs", "split_bands")
    low, high = d["events"]
    assert (low["transducer"], high["transducer"]) == ("left", "right")
    assert low["time"] == high["time"] == 0.0
    assert ws.get("signals", low["signal"])["f0"] == 2000.0
    assert ws.get("signals", high["signal"])["f1"] == 20000.0
    assert d["receivers"] == ["mic"]
    # Signals of the same name and settings are shared between designs.
    assert ws.name_of("signals", "chirp_up") == "chirp up"
    assert len([i for i in ws.ids("signals") if ws.get("signals", i)["name"] == "chirp up"]) == 1
    # All of it as one undo step; and a second import adds nothing.
    assert ws.undo_stack.count() == 1
    before = {k: ws.ids(k) for k in ("signals", "designs")}
    again = importers.import_designs(ws, OLD_DESIGNS)
    assert all("already imported" in m for m in again), again
    assert {k: ws.ids(k) for k in before} == before


def test_every_imported_design_can_be_built_into_a_ping(ws):
    importers.import_designs(ws, OLD_DESIGNS)
    infos = SimulationBackend.from_workspace(ws, "dongle_bench").transducers()
    for design_id in ws.ids("designs"):
        ping = ranging.build_ping(ws, design_id, infos)
        assert ping.receivers == ["mic"] and ping.emissions


def test_a_signal_with_the_same_name_but_other_settings_gets_its_own_id(ws, tmp_path):
    importers.import_designs(ws, OLD_DESIGNS)
    folder = tmp_path / "old"
    folder.mkdir()
    (folder / "mine.json").write_text(json.dumps(dict(
        signals=[dict(name="chirp up", f0=3000.0, f1=4000.0, duration=0.01, amplitude=0.5)],
        events=[dict(channel="left", signal="chirp up", time=0.0)])))
    importers.import_designs(ws, folder)
    mine = ws.get("designs", "mine")["events"][0]["signal"]
    assert mine != "chirp_up" and ws.get("signals", mine)["f0"] == 3000.0
    assert ws.get("signals", "chirp_up")["f0"] == 2000.0


# ---- the whole ping path -----------------------------------------------

def test_a_ping_from_a_design_gives_a_table_checked_against_the_truth(started):
    backend = SimulationBackend.from_workspace(started, "dongle_bench_loopback")
    ping = ranging.build_ping(started, "left_then_right", backend.transducers())
    assert [e.transducer for e in ping.emissions] == ["left", "right"]
    assert ping.meta["signals"]["chirp_up"]["f1"] == 20000.0
    capture = backend.fire(ping)
    result = ranging.analyse_capture(capture, "mic")
    assert result.loopback == ["left", "right"] and not result.warnings
    left, right = result.rows
    # Time of flight from the loopback: left 1.5 m, right 1.9 m, to 1 mm.
    assert left["mode"] == "loopback"
    assert abs(left["path_m"] - 1.5) < 0.001 and abs(right["path_m"] - 1.9) < 0.001
    assert abs(left["error_mm"]) < 1 and abs(right["error_mm"]) < 1
    assert left["true_path_m"] == pytest.approx(1.5)
    marks = dict(ranging.truth_marks_ms(result, 0))
    assert set(marks) == {"loopback", "direct", "plane:wall"}
    assert abs(marks["direct"] - marks["loopback"] - left["delay_ms"]) < 0.005


def test_without_a_loopback_arrivals_are_timed_against_the_loudest(started):
    backend = SimulationBackend.from_workspace(started, "dongle_bench")
    ping = ranging.build_ping(started, "left_then_right", backend.transducers())
    result = ranging.analyse_capture(backend.fire(ping), "mic")
    assert all(r["mode"] == "first arrival" for r in result.rows)
    # The right output is 0.4 m further from the mic than the left.
    extra = (result.rows[1]["path_m"] - result.rows[0]["path_m"])
    assert abs(extra - 0.4) < 0.005 or abs(extra + 0.4) < 0.005
    assert 0.9 < result.rows[1]["true_path_m"] / 1.9 < 1.1


def test_designs_that_cannot_be_played_say_why(started):
    infos = SimulationBackend.from_workspace(started, "dongle_bench").transducers()
    started.update("designs", "left_then_right", events=[
        dict(transducer="mic", signal="chirp_up", time=0.0)])
    with pytest.raises(ValueError, match="'mic' cannot send"):
        ranging.build_ping(started, "left_then_right", infos)
    started.update("designs", "left_then_right", events=[])
    with pytest.raises(ValueError, match="no events"):
        ranging.build_ping(started, "left_then_right", infos)
    started.update("signals", "chirp_up", f1=30000.0)
    started.update("designs", "left_then_right", events=[
        dict(transducer="left", signal="chirp_up", time=0.0)])
    with pytest.raises(ValueError, match="too high"):
        ranging.build_ping(started, "left_then_right", infos)


# ---- saved runs and replay ---------------------------------------------

def test_a_saved_capture_replays_to_the_same_arrivals(started, tmp_path):
    backend = SimulationBackend.from_workspace(started, "dongle_bench_loopback")
    ping = ranging.build_ping(started, "left_then_right", backend.transducers())
    run = tmp_path / "runs" / "one"
    results = []
    for n in range(1, 4):
        capture = backend.fire(ping)
        capture_io.save_capture(run, n, capture)
        results.append(ranging.analyse_capture(capture, "mic"))
    sidecar = json.loads((run / "p_0001.wav.json").read_text())
    assert sidecar["acoustics_lab"]["scene"]["name"] == "Dongle bench loopback"
    assert sidecar["design"]["events"][1]["time"] == 0.15
    replay = ReplayBackend(run)
    assert len(replay) == 3 and {t.id for t in replay.transducers()} == {"left", "right", "mic"}
    for before in results:
        capture = replay.fire()
        assert capture.truth is None
        after = ranging.analyse_capture(capture, "mic")
        assert after.loopback == ["left", "right"]
        for b, a in zip(before.rows, after.rows):
            assert abs(a["path_m"] - b["path_m"]) < 0.002       # 16-bit WAV
    assert replay.fire().meta["index"] == 0                      # and round again


def old_run(folder, name="p_0001.wav"):
    """A recording as ping_gui.save_ping writes it, made with the old code's recipe."""
    from acoustics_lab import wav_io
    from acoustics_lab.models import channel
    from acoustics_lab.models.signals import make_chirp
    rate, speed = 48000, 343.2
    chirp = 0.5 * make_chirp(rate, 2000, 20000, 0.02)
    n = int(0.9 * rate)
    paths = [(0.25 + e / 1e3 + m / speed, g, 0.0) for e in (0, 150) for m, g in ((1.5, 0.1),)]
    out = np.zeros(n)
    out += channel.render_paths(chirp, rate, paths[:1], n)
    out += channel.render_paths(chirp, rate, [(0.4 + 1.9 / speed, 0.06, 0.0)], n)
    wav_io.write_wav(str(folder / name), out, rate)
    wav_io.write_meta(str(folder / name), dict(
        time="2026-10-11T10:00:00+00:00",
        setup=dict(rate=rate, listen=0.3, first_threshold=0.3, sound_speed=speed,
                   input_device=None, output_device=None),
        design=dict(signals=[dict(name="chirp up", f0=2000.0, f1=20000.0,
                                  duration=0.02, amplitude=0.5)],
                    events=[dict(channel="left", signal="chirp up", time=0.0),
                            dict(channel="right", signal="chirp up", time=0.15)]),
        results=[], warnings=[]))


def test_old_ping_gui_runs_open_in_replay(tmp_path):
    old_run(tmp_path)
    capture = ReplayBackend(tmp_path).fire()
    result = ranging.analyse_capture(capture, "mic")
    assert result.analysis.detected() == [0, 1] and not result.loopback
    assert capture.meta["sound_speed"] == 343.2
    assert abs((result.rows[1]["path_m"] - result.rows[0]["path_m"]) - 0.4) < 0.01


def test_loopback_test_runs_open_with_the_first_arrival_as_loopback(tmp_path):
    from acoustics_lab import wav_io
    from acoustics_lab.models import channel
    from acoustics_lab.models.signals import make_chirp
    chirp = 0.5 * make_chirp(48000, 2000, 20000, 0.02)
    out = channel.render_paths(chirp, 48000, [(0.1, 0.2, 0.0), (0.1 + 1.5 / 343.2, 0.05, 0.0)], 20000)
    wav_io.write_wav(str(tmp_path / "run1.wav"), out, 48000)
    wav_io.write_meta(str(tmp_path / "run1.wav"), dict(
        rate=48000, f0=2000.0, f1=20000.0, duration=0.02, amplitude=0.5,
        channel="left", sound_speed=343.2, simulated=False))
    result = ranging.analyse_capture(ReplayBackend(tmp_path / "run1.wav").fire(), "mic")
    assert result.loopback == ["left"]
    assert abs(result.rows[0]["path_m"] - 1.5) < 0.005


def test_a_recording_without_its_json_is_refused_clearly(tmp_path):
    from acoustics_lab import wav_io
    wav_io.write_wav(str(tmp_path / "bare.wav"), np.zeros(1000), 48000)
    with pytest.raises(ValueError, match="no .json file"):
        ReplayBackend(tmp_path).fire()
    with pytest.raises(ValueError, match="no WAV files"):
        ReplayBackend(tmp_path / "nothing_here")
