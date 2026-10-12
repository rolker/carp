"""Detection designs: the settings, the workspace kind, the threading through
the detection code and the hardware checks, the migration of designs/, and
analysing a saved test again. No sound device is opened."""
import importlib.util
import io
import json
import os

import numpy as np
import pytest

from acoustics_lab.hardware import checks
from acoustics_lab.hardware.fake import FakeDevice
from acoustics_lab.models import detection as det
from acoustics_lab.models import detection_design as dd
from acoustics_lab.objects import detections, schema as s, starter
from acoustics_lab.objects.schema import InUseError, WorkspaceError
from acoustics_lab.workspace import Workspace
from helpers import RATE, event, recording

HERE = os.path.dirname(os.path.abspath(__file__))
SPEED = 343.2


def dongle(**kwargs):
    options = dict(in_latency=130.3, out_latency=400.45)
    options.update(kwargs)
    return FakeDevice(**options)


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    return w


# ---- the settings --------------------------------------------------------

def test_every_setting_has_a_default_a_unit_and_a_sentence():
    fields = {f.name for f in dd.DetectionDesign.__dataclass_fields__.values()}
    for setting in dd.SETTINGS:
        assert setting.key in fields and setting.text and setting.label
        assert getattr(dd.DEFAULT, setting.key) == setting.default
    assert {s_.key for s_ in dd.SETTINGS} <= fields


def test_the_defaults_are_what_the_code_used_to_hard_wire():
    d = dd.DEFAULT
    assert (d.detect_snr, d.search_s, d.first_fraction, d.listed_fraction) == (8.0, 0.03, 0.3, 0.05)
    assert (d.hit_snr, d.group_samples, d.settle_s) == (10.0, 5.0, 2.0)
    assert (checks.FIRST_FRACTION, checks.GROUP_SAMPLES, checks.SETTLE_S) == (0.3, 5.0, 2.0)
    assert (det.SEARCH, det.DETECT) == (0.03, 8.0)
    assert (d.upsample, d.refine_half, d.margin_samples) == (16, 48, 64)


def test_designs_round_trip_and_unknown_keys_are_ignored():
    data = dict(dd.DEFAULT.to_dict(), first_fraction=0.5, future_setting=3)
    design = dd.from_dict(data)
    assert design.first_fraction == 0.5 and "future_setting" not in design.to_dict()
    assert dd.from_dict({"name": "bare"}).detect_snr == 8.0       # missing: the default
    assert design.differences() == {"first_fraction": (0.5, 0.3)}
    assert "first_fraction 0.5" in design.summary()


@pytest.mark.parametrize("bad, message", [
    (dict(first_fraction=0), "First-arrival fraction must be between"),
    (dict(method="magic"), "method must be one of"),
    (dict(detect_snr="high"), "needs a number"),
    (dict(kind="nonsense"), "kind must be one of"),
    (dict(search_s=-1), "Search window"),
])
def test_values_out_of_range_are_refused_with_a_reason(bad, message):
    with pytest.raises(ValueError, match=message):
        dd.from_dict(bad)


# ---- the workspace kind ----------------------------------------------------

def test_a_new_workspace_has_the_default_detection_design_and_designs_name_it(ws):
    assert ws.ids("detection_designs") == [starter.DEFAULT_DETECTION]
    data = ws.get("detection_designs", starter.DEFAULT_DETECTION)
    assert dd.from_dict(data) == dd.DEFAULT.changed(name=data["name"],
                                                    description=data["description"])
    assert ws.get("ping_designs", "left_then_right")["detection_design"] == starter.DEFAULT_DETECTION
    assert (ws.path / "ping_designs" / "left_then_right.json").exists()
    assert (ws.path / "detection_designs" / "default_arrival_detection.json").exists()
    assert not (ws.path / "designs").exists()


def test_detection_designs_are_edited_with_undo_and_checked(ws):
    new = ws.create("detection_designs", "strict", s.new_detection_design("", first_fraction=0.9))
    assert dd.from_dict(ws.get("detection_designs", new)).first_fraction == 0.9
    ws.update("detection_designs", new, hit_snr=20.0)
    ws.undo_stack.undo()
    assert ws.get("detection_designs", new)["hit_snr"] == 10.0
    ws.undo_stack.redo()
    assert ws.get("detection_designs", new)["hit_snr"] == 20.0
    with pytest.raises(WorkspaceError, match="Search window"):
        ws.update("detection_designs", new, search_s=0)
    ws.undo_stack.undo()
    ws.undo_stack.undo()
    assert not ws.exists("detection_designs", new)


def test_a_detection_design_a_ping_design_names_cannot_be_deleted(ws):
    with pytest.raises(InUseError) as error:
        ws.delete("detection_designs", starter.DEFAULT_DETECTION)
    assert ("ping_designs", "left_then_right") in error.value.users
    assert "detection design" in str(error.value)
    other = ws.create("detection_designs", "other", s.new_detection_design(""))
    ws.update("ping_designs", "left_then_right", detection_design=other)
    for did in ws.ids("ping_designs"):
        ws.update("ping_designs", did, detection_design=other)
    ws.delete("detection_designs", starter.DEFAULT_DETECTION)       # now nobody names it
    with pytest.raises(WorkspaceError, match="no detection design with ID 'gone'"):
        ws.update("ping_designs", "left_then_right", detection_design="gone")


def test_the_design_in_force_comes_from_the_page_then_the_ping_design(ws):
    strict = ws.create("detection_designs", "strict", s.new_detection_design("", hit_snr=50.0))
    own = detections.of_ping_design(ws, "left_then_right")
    assert own == starter.DEFAULT_DETECTION
    assert detections.resolve(ws, None, own)[0] == starter.DEFAULT_DETECTION
    chosen_id, chosen = detections.resolve(ws, strict, own)
    assert chosen_id == strict and chosen.hit_snr == 50.0
    assert detections.resolve(ws, "gone", None)[0] == starter.DEFAULT_DETECTION
    assert detections.record(strict, chosen)["id"] == strict
    assert detections.record(strict, chosen)["hit_snr"] == 50.0


# ---- the old designs/ folder -----------------------------------------------

def old_workspace(path, names=("a", "b")):
    (path / "designs").mkdir(parents=True)
    (path / "signals").mkdir()
    (path / "workspace.json").write_text(json.dumps(dict(name="old", version=1)))
    for n in names:
        (path / "designs" / f"{n}.json").write_text(json.dumps(
            dict(name=n, events=[], receivers=[], listen=0.3, roles=["bench"])))


def test_opening_a_step_1_workspace_moves_designs_to_ping_designs(tmp_path):
    old_workspace(tmp_path)
    ws = Workspace(tmp_path)
    assert not (tmp_path / "designs").exists()
    assert ws.ids("ping_designs") == ["a", "b"]
    assert (tmp_path / "ping_designs" / "a.json").exists()
    assert any("Moved 2 ping design file(s)" in n for n in ws.notices)
    assert "detection_designs" in ws.new_kinds          # the app will give it the default
    again = Workspace(tmp_path)
    assert again.notices == [] and again.ids("ping_designs") == ["a", "b"]


def test_migration_leaves_a_file_whose_name_is_taken_and_says_so(tmp_path):
    old_workspace(tmp_path)
    (tmp_path / "ping_designs").mkdir()
    (tmp_path / "ping_designs" / "a.json").write_text(json.dumps(
        dict(name="new a", events=[], receivers=[], listen=0.3)))
    ws = Workspace(tmp_path)
    assert ws.get("ping_designs", "a")["name"] == "new a"          # not overwritten
    assert (tmp_path / "designs" / "a.json").exists()
    assert not (tmp_path / "designs" / "b.json").exists()
    assert any("Left in designs/" in n and "a.json" in n for n in ws.notices)


def test_an_old_workspace_gets_the_default_detection_design_from_the_application(tmp_path):
    old_workspace(tmp_path)
    ws = Workspace(tmp_path)
    assert ws.ids("detection_designs") == []
    assert starter.ensure_default_detection(ws) == starter.DEFAULT_DETECTION
    assert starter.ensure_default_detection(ws) is None            # only if there are none


# ---- the detection code takes its choices from the design --------------------

def two_arrivals(weak=0.3, strong=0.8, gap=0.002):
    e = event("c", 2000, 20000, 0.01, 0.0)
    rec = recording([(e, [(0.004, weak), (0.004 + gap, strong)])], noise=0.002)
    return rec, [e]


def test_the_first_arrival_fraction_decides_which_peak_is_first():
    rec, events = two_arrivals()                      # first is 0.375 of the stronger
    default = det.analyse_events(rec, RATE, events)
    strict = det.analyse_events(rec, RATE, events, design=dd.DEFAULT.changed(first_fraction=0.5))
    assert default.results[0].first < strict.results[0].first
    assert strict.results[0].first - default.results[0].first == pytest.approx(0.002 * RATE, abs=1)
    assert strict.design.first_fraction == 0.5 and default.design == dd.DEFAULT


def test_the_event_threshold_and_listed_fraction_come_from_the_design():
    rec, events = two_arrivals(weak=0.03, strong=0.8)
    assert len(det.analyse_events(rec, RATE, events).results[0].arrivals) == 1
    low = dd.DEFAULT.changed(listed_fraction=0.02, first_fraction=0.02)
    result = det.analyse_events(rec, RATE, events, design=low).results[0]
    assert len(result.arrivals) == 2
    deaf = dd.DEFAULT.changed(detect_snr=1e5)
    assert not det.analyse_events(rec, RATE, events, design=deaf).detected()


def test_the_envelope_method_finds_a_ping_without_a_template():
    rec, events = two_arrivals(weak=0.0, strong=0.5, gap=0.0)
    matched = det.analyse_events(rec, RATE, events)
    envelope = det.analyse_events(rec, RATE, events, design=dd.DEFAULT.changed(method="envelope"))
    assert matched.detected() == envelope.detected() == [0]
    # coarser: within a signal length, not a few samples
    assert abs(envelope.results[0].first - matched.results[0].first) < 0.01 * RATE
    assert envelope.design.method == "envelope"
    # with no filter there is nothing to leak into
    up, down = event("u", 2000, 20000, 0.02, 0.0), event("d", 20000, 2000, 0.02, 0.0)
    assert det.leaking([up, down], RATE) != []
    assert det.leaking([up, down], RATE, dd.DEFAULT.changed(method="envelope")) == []


def test_the_search_window_decides_which_events_are_inseparable():
    a, b = event("u", 2000, 20000, 0.02, 0.0), event("u", 2000, 20000, 0.1, 0.1)
    assert det.inseparable([a, b]) == []
    assert det.inseparable([a, b], dd.DEFAULT.changed(search_s=0.06)) == [[0, 1]]


def test_the_input_check_limits_come_from_the_design():
    rng = np.random.default_rng(1)
    noisy = rng.normal(0, 800, 48000)                # about -32 dBFS
    assert checks.input_check(noisy)["warnings"] == []
    strict = dd.DEFAULT.changed(noise_dbfs=-40.0)
    assert "noisy" in " ".join(checks.input_check(noisy, strict)["warnings"])
    offset = rng.normal(0, 3, 48000) + 400           # 1.2 % of full scale
    assert checks.input_check(offset)["warnings"] == []
    assert "DC offset" in " ".join(
        checks.input_check(offset, dd.DEFAULT.changed(dc_fraction=0.01))["warnings"])
    float_unit = checks.detection.input_check(offset / 32768.0, strict, unit=1.0)
    assert float_unit["dc_fraction"] == pytest.approx(400 / 32768, rel=0.01)


def test_the_live_detector_uses_the_design(tmp_path):
    template = checks.make_ping(48000)
    with dongle(noise_rms=2.0) as dev:
        dev.schedule(template, 5000, gain=0.1)
        dev.wait_input(20000)
        loud = checks.ArrivalDetector(dev, template, start=0)
        assert len(loud.poll()) == 1
        deaf = checks.ArrivalDetector(dev, template, start=0,
                                      design=dd.DEFAULT.changed(hit_snr=1e5))
        assert deaf.poll() == []
        wide = checks.ArrivalDetector(dev, template, start=0,
                                      design=dd.DEFAULT.changed(final_lengths=40.0))
        assert wide.poll() == []                      # waits for 40 lengths of input first


def test_the_grouping_tolerance_is_the_designs():
    rows = [checks.PingRow(k, 1000 + 24000 * k) for k in range(12)]
    for r in rows:
        r.arrival, r.level_dbfs, r.snr_db, r.offset = r.scheduled + 500.0, -30.0, 40.0, 500.0
    rows[3].offset = 560.0
    with dongle() as dev:
        template = checks.make_ping(48000)
        default = checks._offset_result(dev, rows, template, -20.0, "left", 0.5, "chirp", 0, 6.0)
        wide = checks._offset_result(dev, rows, template, -20.0, "left", 0.5, "chirp", 0, 6.0,
                                     design=dd.DEFAULT.changed(group_samples=100.0))
    assert default.summary["outliers"] == 1 and wide.summary["outliers"] == 0
    assert wide.summary["detection_design"]["group_samples"] == 100.0
    assert default.summary["detection_design"] == dd.DEFAULT.to_dict()


# ---- the raw input of a test, and analysing it again --------------------------

def test_a_test_keeps_its_raw_input_and_saves_it(tmp_path):
    with dongle(noise_rms=3.0) as dev:
        result = checks.run_offset_test(dev, 10)
    raw = result.raw
    assert raw.samples.dtype == np.int16 and raw.start == 0
    assert len(raw.samples) >= result.rows[-1].scheduled
    assert raw.meta["plan"] == [r.scheduled for r in result.rows]
    folder = checks.save(result, str(tmp_path), "fake")
    assert set(os.listdir(folder)) >= {"input.wav", "input.wav.json", "offset.csv", "summary.json"}
    loaded = checks.load_run(folder)
    assert np.array_equal(loaded.samples, raw.samples)           # exactly, not rescaled
    assert loaded.meta["detection_design"] == dd.DEFAULT.to_dict()
    assert json.load(open(os.path.join(folder, "summary.json")))["detection_design"] == dd.DEFAULT.to_dict()


def test_analysing_a_saved_run_with_the_same_design_gives_the_same_offsets(tmp_path):
    with dongle(noise_rms=3.0, echoes=[(60.0, 2.0)]) as dev:
        live = checks.run_offset_test(dev, 12)
    again = checks.reanalyse_offset(checks.load_run(checks.save(live, str(tmp_path), "f")))
    assert again.summary["reanalysis"] and again.raw is None
    for a, b in zip(live.rows, again.rows):
        assert b.offset == pytest.approx(a.offset, abs=0.05)
    assert again.summary["used"] == live.summary["used"]
    assert again.summary["offset_mean_samples"] == pytest.approx(
        live.summary["offset_mean_samples"], abs=0.05)


def test_another_design_changes_what_the_same_recording_says(tmp_path):
    # An echo 60 samples later and twice as strong as the direct sound.
    with dongle(noise_rms=2.0, echoes=[(60.0, 2.0)]) as dev:
        live = checks.run_offset_test(dev, 12)
    raw = checks.load_run(checks.save(live, str(tmp_path), "f"))
    direct = live.summary["offset_mean_samples"]
    # direct sound is 0.5 of the echo: only a first-arrival fraction above that skips it
    echo = checks.reanalyse_offset(raw, dd.DEFAULT.changed(first_fraction=0.9))
    assert echo.summary["offset_mean_samples"] == pytest.approx(direct + 60.0, abs=0.5)
    assert echo.summary["detection_design"]["first_fraction"] == 0.9
    deaf = checks.reanalyse_offset(raw, dd.DEFAULT.changed(hit_snr=1e6))
    assert deaf.summary["found"] == 0 and not deaf.summary["verdict_ok"]
    clipped = checks.reanalyse_offset(raw, dd.DEFAULT.changed(noise_dbfs=-140.0))
    assert "Before the test" in clipped.verdict[0]                # the input check, redone
    with pytest.raises(ValueError, match="only an offset test"):
        raw.meta["kind"] = "schedule"
        checks.reanalyse_offset(raw)


def test_a_folder_without_raw_input_says_so(tmp_path):
    with pytest.raises(ValueError, match="no input.wav"):
        checks.load_run(str(tmp_path))


def test_the_schedule_test_keeps_its_raw_input_too(tmp_path):
    with dongle(out_latency=400.62) as dev:
        result = checks.run_schedule_test(dev, 0.2, pulses=4)
    folder = checks.save(result, str(tmp_path), "f")
    assert os.path.exists(os.path.join(folder, "input.wav"))
    assert checks.load_run(folder).meta["kind"] == "schedule"
    with pytest.raises(ValueError, match="only an offset test"):
        checks.reanalyse_offset(checks.load_run(folder))


# ---- the command-line tool ---------------------------------------------------

def run_tool(*argv):
    path = os.path.join(os.path.dirname(HERE), "tools", "duplex_check.py")
    spec = importlib.util.spec_from_file_location("duplex_check", path)
    tool = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(tool)
    out = io.StringIO()
    code = tool.main(list(argv), out)
    return code, out.getvalue()


def test_tool_saves_the_raw_input_and_reanalyses_it_with_another_design(tmp_path):
    code, text = run_tool("--fake", "--offset-test", "--minutes", "0.5",
                          "--runs", str(tmp_path), "--detect", "first_fraction=0.4")
    assert code == 0, text
    folder = tmp_path / os.listdir(tmp_path)[0]
    assert (folder / "input.wav").exists()
    assert json.load(open(folder / "summary.json"))["detection_design"]["first_fraction"] == 0.4
    code, text = run_tool("--reanalyse", str(folder), "--detect", "first_fraction=0.9",
                          "--detect", "group_samples=50")
    assert code == 0, text
    assert "made with:" in text and "first_fraction 0.9 (was 0.4)" in text
    assert "group_samples 50 (was 5)" in text and "Offset steady" in text
    saved = [p for p in folder.iterdir() if p.is_dir()]
    assert len(saved) == 1 and (saved[0] / "offset.csv").exists()
    assert json.load(open(saved[0] / "summary.json"))["detection_design"]["group_samples"] == 50.0


def test_tool_takes_a_design_file_and_complains_clearly(tmp_path):
    strict = tmp_path / "strict.json"
    strict.write_text(json.dumps(dict(dd.DEFAULT.to_dict(), name="strict", hit_snr=1e6)))
    code, text = run_tool("--fake", "--offset-test", "--minutes", "0.1", "--no-wait",
                          "--runs", str(tmp_path / "r"), "--detection", str(strict))
    assert code == 1 and "were not found" in text or "usable" in text
    code, text = run_tool("--reanalyse", str(tmp_path), "--detect", "nonsense=1")
    assert code == 2 and ("no input.wav" in text or "no detection setting" in text)
    code, text = run_tool("--fake", "--offset-test", "--detect", "first_fraction=9")
    assert code == 2 and "First-arrival fraction must be between" in text
    code, text = run_tool("--fake", "--offset-test", "--detect", "first_fraction")
    assert code == 2 and "KEY=VALUE" in text
