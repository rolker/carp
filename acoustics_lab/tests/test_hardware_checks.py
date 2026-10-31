"""The offset and schedule tests, and the command-line tool, on the fake device."""
import importlib.util
import io
import json
import os
import re

import numpy as np
import pytest

from acoustics_lab.hardware import checks, discovery, stream
from acoustics_lab.hardware.fake import FakeDevice

HERE = os.path.dirname(os.path.abspath(__file__))


def dongle(**kwargs):
    options = dict(in_latency=130.3, out_latency=400.45)
    options.update(kwargs)
    return FakeDevice(**options)


def test_a_ping_is_located_to_a_fraction_of_a_sample():
    template = checks.make_ping(48000)
    for shift in (0.0, 0.25, 0.5, 0.8):
        dev = dongle(in_latency=300.0 + shift, out_latency=400.0,
                     noise_rms=1.0)
        with dev:
            dev.schedule(template, 5000, gain=0.1)
            dev.wait_input(8000)
            found = checks.locate(dev.read_input(4000, 8000), template)
        assert found is not None
        assert 4000 + found[0] - 5000 == pytest.approx(700.0 + shift, abs=0.03)
        assert found[1] == pytest.approx(-26.0, abs=0.2)    # -20 dB ping, loopback gain 0.5


def test_noise_alone_is_not_a_ping():
    rng = np.random.default_rng(1)
    noise = rng.normal(0, 50, 8000)
    assert checks.locate(noise, checks.make_ping(48000)) is None


def test_offset_test_recovers_the_loopback_delay():
    with dongle(noise_rms=3.0) as dev:
        result = checks.run_offset_test(dev, 20)
    s = result.summary
    assert s["pings"] == 40 and s["found"] == 40 and s["used"] == 40
    assert s["offset_mean_samples"] == pytest.approx(530.75, abs=0.03)
    assert s["offset_std_samples"] < 0.03
    assert s["verdict_ok"]
    assert "Offset steady to +-" in result.verdict[0]
    assert "No dropouts" in " ".join(result.verdict)
    assert all(abs(r.offset - 530.75) < 0.1 for r in result.rows)


def test_offset_test_with_a_click():
    with dongle(loopback_gain=1.0) as dev:
        result = checks.run_offset_test(dev, 10, level_db=-6, ping="click")
    assert result.summary["offset_mean_samples"] == pytest.approx(530.75, abs=0.1)


def test_offset_test_sees_drift():
    with dongle(offset_drift=0.05) as dev:           # 3 samples a minute
        result = checks.run_offset_test(dev, 120)
    s = result.summary
    assert s["drift_samples_per_min"] == pytest.approx(3.0, abs=0.1)
    assert s["drift_ppm"] == pytest.approx(1e6 * 0.05 / 48000, rel=0.05)
    assert not s["verdict_ok"]
    assert any(line.startswith("Drift") for line in result.verdict)


def test_pings_in_an_xrun_are_left_out_and_reported():
    flags = stream.INPUT_OVERFLOW
    first = 25024                    # where the first ping goes after the start-up wait
    during = first + 24000 * 5 + 560           # as the 6th ping's copy arrives
    before = first + 24000 * 9 + 10            # just as the 10th is played
    with dongle(xruns=[(during, flags), (before, flags)]) as dev:
        result = checks.run_offset_test(dev, 15, settle=0.0)
    s = result.summary
    flagged = [r for r in result.rows if r.xrun]
    assert {r.k for r in flagged} >= {5, 9}
    assert len(flagged) <= 4
    assert s["used"] == s["pings"] - len(flagged)
    assert s["xruns"]["input overflow"] == 2
    assert any("Dropouts" in line for line in result.verdict)
    assert not s["verdict_ok"]
    # the pings that were kept are still right
    assert s["offset_max_dev_samples"] < 0.1


def test_no_loopback_gives_a_helpful_verdict():
    with dongle(loopback=False) as dev:
        result = checks.run_offset_test(dev, 6)
    assert result.summary["used"] == 0 and not result.summary["verdict_ok"]
    assert "loopback" in result.verdict[0]


def test_the_claimed_offset_is_reported_beside_the_measured_one():
    with dongle(pa_error=20.0) as dev:
        result = checks.run_offset_test(dev, 8)
    line = [l for l in result.verdict if l.startswith("PortAudio claimed")][0]
    claimed, measured = [float(x) for x in re.findall(r"\d+\.\d", line)[:2]]
    assert claimed == pytest.approx(550.8, abs=0.1)
    assert measured == pytest.approx(530.75, abs=0.1)


def test_schedule_test_lands_replies_exactly_n_samples_after_the_arrival():
    with dongle(in_latency=130.3, out_latency=400.62, noise_rms=3.0) as dev:
        result = checks.run_schedule_test(dev, 0.2, pulses=25)
    s = result.summary
    assert s["replies"] == 25 and s["late"] == 0 and s["lost"] == 0
    assert s["tat_samples"] == 9600
    for r in result.rows:
        assert r.scheduled == round(r.heard + 9600)
        assert abs(r.rounding) <= 0.5
        # through the loopback the reply is the turnaround plus the device
        # offset after the arrival that triggered it
        assert (r.arrival - r.heard) == pytest.approx(9600 + 530.92, abs=0.6)
        assert abs(r.error) <= 0.55
    assert s["error_max_abs_samples"] <= 0.55
    assert s["offset_mean_samples"] == pytest.approx(530.92, abs=0.03)
    assert s["verdict_ok"], result.verdict
    assert s["margin_min_ms"] > 100


def test_schedule_test_notices_a_turnaround_that_is_too_short():
    with dongle() as dev:
        result = checks.run_schedule_test(dev, 0.004, pulses=5)
    assert result.summary["late"] > 0
    assert not result.summary["verdict_ok"]


def test_schedule_test_flags_replies_that_overlap_a_dropout():
    with dongle(xruns=[(51344, stream.INPUT_OVERFLOW)]) as dev:
        result = checks.run_schedule_test(dev, 0.2, pulses=12, settle=0.0)
    assert result.summary["in_xrun"] >= 1
    assert not result.summary["verdict_ok"]


def test_results_are_saved_as_csv_and_json(tmp_path):
    with dongle() as dev:
        result = checks.run_offset_test(dev, 5)
    folder = checks.save(result, str(tmp_path), "donglea")
    assert os.path.basename(folder).endswith("_donglea_offset")
    lines = open(os.path.join(folder, "offset.csv")).read().splitlines()
    assert lines[0].startswith("k,scheduled_out_sample,arrival_in_sample")
    assert len(lines) == 11
    summary = json.load(open(os.path.join(folder, "summary.json")))
    assert summary["test"] == "offset" and summary["verdict_lines"]
    with dongle() as dev:
        reply = checks.run_schedule_test(dev, 0.2, pulses=4)
    folder2 = checks.save(reply, str(tmp_path), "donglea")
    assert os.path.exists(os.path.join(folder2, "schedule.csv"))


# -- the command-line tool -------------------------------------------------------

def load_tool():
    path = os.path.join(os.path.dirname(HERE), "tools", "duplex_check.py")
    spec = importlib.util.spec_from_file_location("duplex_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def run_tool(*argv):
    tool = load_tool()
    out = io.StringIO()
    code = tool.main(list(argv), out)
    return code, out.getvalue()


def test_tool_runs_the_offset_test_on_the_fake(tmp_path):
    code, text = run_tool("--fake", "--offset-test", "--minutes", "0.5",
                          "--runs", str(tmp_path))
    assert code == 0, text
    assert "Plan" in text and "-20 dBFS peak" in text and "simulated" in text
    assert "Offset steady to +-" in text and "Saved in" in text
    assert len(os.listdir(tmp_path)) == 1


def test_tool_runs_the_schedule_test_on_the_fake(tmp_path):
    code, text = run_tool("--fake", "--schedule-test", "--pulses", "6",
                          "--tat", "0.2", "--runs", str(tmp_path))
    assert code == 0, text
    assert "replies at a turnaround of 200 ms" in text


def test_tool_refuses_input_choice_on_the_fake():
    with pytest.raises(SystemExit):
        run_tool("--fake", "--offset-test", "--input", "right")


def test_tool_never_opens_anything_unless_a_device_is_named():
    code, text = run_tool("--offset-test")
    assert code == 2 and "Name a device" in text
    code, text = run_tool("--device", "1")
    assert code == 2 and "Nothing to do" in text


def test_tool_warns_about_loud_and_clipped_levels(tmp_path):
    code, text = run_tool("--fake", "--offset-test", "--level", "3",
                          "--minutes", "0.05", "--no-wait", "--runs", str(tmp_path))
    assert "WARNING" in text and "clipped" in text
    code, text = run_tool("--fake", "--offset-test", "--level", "-3",
                          "--minutes", "0.05", "--no-wait", "--runs", str(tmp_path))
    assert "WARNING" in text and "loud" in text


def test_tool_warns_about_a_card_that_is_not_usb(monkeypatch):
    tool = load_tool()
    builtin = discovery.Card(1, "PCH", "HDA-Intel", "HDA Intel PCH")
    monkeypatch.setattr(discovery, "list_cards", lambda *a, **k: [builtin])
    monkeypatch.setattr(discovery, "attach_portaudio",
                        lambda *a, **k: "no PortAudio device (test)")
    out = io.StringIO()
    tool.main(["--device", "PCH", "--offset-test"], out)
    assert "WARNING" in out.getvalue() and "not a USB card" in out.getvalue()


def test_tool_does_not_guess_which_card_is_meant(monkeypatch):
    tool = load_tool()
    usb = discovery.Card(2, "Device", "USB-Audio", "x", usb=True, usb_port="1-2")
    monkeypatch.setattr(discovery, "list_cards", lambda *a, **k: [usb])
    code, text = run_tool("--device", "3", "--offset-test")
    assert code == 2 and "no sound card matches '3'" in text


def test_tool_lists_cards_and_marks_usb(monkeypatch):
    usb = discovery.Card(2, "Device", "USB-Audio", "USB Audio Device", usb=True,
                         usb_id="1b3f:2008", usb_port="1-2.3")
    usb.portaudio = [discovery.PortAudioDevice(
        5, "USB Audio Device: - (hw:2,0)", 0, 1, 2, 48000.0,
        input_rates=[44100, 48000], output_rates=[44100, 48000])]
    builtin = discovery.Card(0, "PCH", "HDA-Intel", "HDA Intel PCH")
    monkeypatch.setattr(discovery, "list_cards", lambda *a, **k: [builtin, usb])
    monkeypatch.setattr(discovery, "attach_portaudio", lambda *a, **k: "")
    code, text = run_tool("--list")
    assert code == 0
    assert "[USB]     card 2 [Device]" in text
    assert "[not USB] card 0 [PCH]" in text
    assert "1b3f:2008 port 1-2.3" in text
    assert "no serial number" in text
    assert "in 44.1/48 kHz" in text and "--device 1-2.3" in text


def test_the_direct_sound_is_found_when_an_echo_is_stronger():
    # As on a laptop: the reflection off the screen beats the direct sound.
    with dongle(echoes=[(60.0, 2.0)], noise_rms=2.0) as dev:
        result = checks.run_offset_test(dev, 6)
    s = result.summary
    assert s["used"] >= 10
    assert s["offset_mean_samples"] == pytest.approx(530.75, abs=0.1)
    assert all(abs(r.offset - 530.75) < 0.3 for r in result.rows if r.valid)


def test_offsets_away_from_the_main_group_are_counted_not_averaged():
    rows = [checks.PingRow(k, 1000 + 24000 * k) for k in range(12)]
    for r in rows:
        r.arrival, r.level_dbfs, r.snr_db = r.scheduled + 500.0, -30.0, 40.0
        r.offset = 500.0
    rows[3].offset, rows[7].offset = 560.0, 4000.0      # an echo, a false hit
    with dongle() as dev:
        result = checks._offset_result(dev, rows, checks.make_ping(48000),
                                       -20.0, "left", 0.5, "chirp", 0, 6.0)
    s = result.summary
    assert s["used"] == 10 and s["outliers"] == 2
    assert s["offset_max_dev_samples"] == 0.0
    assert any("away from the main group" in line for line in result.verdict)


def test_input_check_warns_about_clipping_dc_and_noise():
    rng = np.random.default_rng(1)
    clipped = np.clip(rng.normal(-8000, 20000, 48000), -32768, 32767)
    check = checks.input_check(clipped)
    text = " ".join(check["warnings"])
    assert "clipping" in text and "DC offset" in text
    quiet = rng.normal(0, 3, 48000)
    assert checks.input_check(quiet)["warnings"] == []
    noisy = rng.normal(0, 2000, 48000)
    assert "noisy" in " ".join(checks.input_check(noisy)["warnings"])


def test_the_offset_test_waits_for_the_input_to_settle_first():
    with dongle() as dev:
        result = checks.run_offset_test(dev, 2, settle=2.0)
    assert result.rows[0].scheduled > 2.0 * 48000
    assert result.summary["input_check"]["warnings"] == []
