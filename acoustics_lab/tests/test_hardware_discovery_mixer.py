"""Card discovery from /proc and sysfs text, and mixer parsing, from samples."""
import os
import re

import pytest

from acoustics_lab.hardware import discovery, mixer

HERE = os.path.dirname(os.path.abspath(__file__))

CARDS = """\
 0 [PCH            ]: HDA-Intel - HDA Intel PCH
                      HDA Intel PCH at 0x6064118000 irq 203
 1 [Device         ]: USB-Audio - USB Audio Device
                      GeneralPlus USB Audio Device at usb-0000:00:14.0-2.3, full speed
 2 [Device_1       ]: USB-Audio - USB Audio Device
                      GeneralPlus USB Audio Device at usb-0000:00:14.0-2.4, full speed
"""


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name)) as handle:
        return handle.read()


@pytest.fixture
def tree(tmp_path):
    """A /proc/asound and /sys with a built-in card and two identical
    USB dongles on ports 1-2.3 and 1-2.4."""
    proc = tmp_path / "proc"
    sysfs = tmp_path / "sys"
    proc.mkdir()
    (proc / "cards").write_text(CARDS)
    pci = sysfs / "devices" / "pci0000:00" / "0000:00:1f.3"
    pci.mkdir(parents=True)
    (sysfs / "class" / "sound" / "card0").mkdir(parents=True)
    os.symlink(pci, sysfs / "class" / "sound" / "card0" / "device")
    for number, port in ((1, "1-2.3"), (2, "1-2.4")):
        device = sysfs / "devices" / "pci0000:00" / "0000:00:14.0" / "usb1" / "1-2" / port
        interface = device / f"{port}:1.0"
        interface.mkdir(parents=True)
        (device / "idVendor").write_text("1b3f\n")
        (device / "idProduct").write_text("2008\n")
        (device / "product").write_text("USB Audio Device\n")
        (sysfs / "class" / "sound" / f"card{number}").mkdir(parents=True)
        os.symlink(interface, sysfs / "class" / "sound" / f"card{number}" / "device")
        (proc / f"card{number}").mkdir()
        (proc / f"card{number}" / "usbid").write_text("1b3f:2008\n")
    return str(proc), str(sysfs)


def test_cards_text_is_parsed():
    cards = discovery.parse_cards(CARDS)
    assert cards[0] == (0, "PCH", "HDA-Intel", "HDA Intel PCH")
    assert cards[2][:2] == (2, "Device_1")


def test_usb_cards_are_told_from_built_in(tree):
    cards = discovery.list_cards(*tree)
    assert [c.usb for c in cards] == [False, True, True]
    first = cards[1]
    assert first.usb_id == "1b3f:2008"
    assert first.usb_port == "1-2.3"
    assert first.usb_interface == "1-2.3:1.0"
    assert first.usb_serial == ""
    assert cards[2].usb_port == "1-2.4"


def test_find_card_by_number_id_or_port(tree):
    cards = discovery.list_cards(*tree)
    assert discovery.find_card(cards, "1") is cards[1]
    assert discovery.find_card(cards, "hw:2") is cards[2]
    assert discovery.find_card(cards, "Device_1") is cards[2]
    assert discovery.find_card(cards, "1-2.3") is cards[1]
    assert discovery.find_card(cards, "usb:1-2.4") is cards[2]


def test_find_card_refuses_unknown_names(tree):
    cards = discovery.list_cards(*tree)
    with pytest.raises(LookupError, match="no sound card"):
        discovery.find_card(cards, "default")
    with pytest.raises(LookupError):
        discovery.find_card(cards, "")


def test_missing_proc_gives_no_cards(tmp_path):
    assert discovery.list_cards(str(tmp_path), str(tmp_path)) == []


def test_pa_device_prefers_one_with_both_directions():
    card = discovery.Card(1, "x", "USB-Audio", "x")
    out_only = discovery.PortAudioDevice(3, "a (hw:1,1)", 1, 0, 2, 48000.0)
    duplex = discovery.PortAudioDevice(4, "a (hw:1,0)", 0, 1, 2, 48000.0)
    card.portaudio = [out_only, duplex]
    assert card.pa_device() is duplex


# -- mixer ---------------------------------------------------------------------

def test_dongle_mixer_controls_are_parsed():
    controls = mixer.parse_contents(fixture("amixer_usb_dongle.txt"))
    by_name = {c.name: c for c in controls}
    volume = by_name["Speaker Playback Volume"]
    assert (volume.type, volume.count, volume.minimum, volume.maximum) == \
        ("INTEGER", 2, 0, 151)
    assert volume.values == [100, 100]
    assert (volume.db_min, volume.db_max) == (-95.0, 0.0)
    assert volume.to_db(151) == pytest.approx(0.0)
    assert volume.to_db(100) == pytest.approx(-95 + 95 * 100 / 151)
    mic = by_name["Mic Capture Volume"]
    assert mic.db_step == 1.0 and mic.to_db(8) == pytest.approx(8.0)
    assert by_name["Auto Gain Control"].values == [1]
    choice = by_name["Input Source"]
    assert choice.items == ["Mic", "Line In"] and choice.value_text() == "Mic"
    assert not by_name["Capture Channel Map"].writable


def test_important_controls_are_flagged():
    controls = mixer.parse_contents(fixture("amixer_usb_dongle.txt"))
    roles = {c.name: c.role for c in controls}
    assert roles["Speaker Playback Volume"] == mixer.PLAYBACK_VOLUME
    assert roles["Mic Capture Volume"] == mixer.CAPTURE_VOLUME
    assert roles["Auto Gain Control"] == mixer.AUTO_GAIN
    assert roles["Mic Playback Switch"] == mixer.MIC_MONITOR
    assert roles["Mic Playback Volume"] == mixer.MIC_MONITOR
    assert roles["Input Source"] == ""
    flagged = [c.name for c, _ in mixer.important(controls)]
    assert "Auto Gain Control" in flagged and "Input Source" not in flagged


def test_hda_mixer_with_a_dbrange_block():
    controls = mixer.parse_contents(fixture("amixer_hda_intel.txt"))
    by_name = {c.name: c for c in controls}
    master = by_name["Master Playback Volume"]
    assert master.to_db(87) == pytest.approx(0.0)
    assert by_name["Capture Switch"].values == [1, 1]
    boost = by_name["Mic Boost Volume"]
    assert boost.db_min is None and boost.to_db(2) is None
    assert boost.value_text() == "0, 0"
    assert by_name["Headphone Jack"].writable is False


class FakeAmixer:
    """Stands in for `amixer`: keeps the control values, answers `contents`
    and applies `cset numid=N VALUE`."""

    def __init__(self, text):
        self.text = text
        self.calls = []

    def __call__(self, args):
        self.calls.append(args)
        assert args[:2] == ["-c", "1"]
        if args[2] == "contents":
            return self.text
        assert args[2] == "cset"
        numid = int(args[3].split("=")[1])
        control = {c.numid: c for c in mixer.parse_contents(self.text)}[numid]
        value = args[4]
        if value.endswith("%"):
            span = control.maximum - control.minimum
            raw = round(control.minimum + float(value[:-1]) / 100 * span)
            values = [raw] * control.count
        elif value in ("on", "off"):
            values = [int(value == "on")] * control.count
        else:
            values = [int(v) for v in value.split(",")]
        head = re.compile(rf"(numid={numid},.*?\n(?:  [;|:].*\n)*?  : values=)[^\n]*")
        shown = ["on" if v else "off" for v in values] \
            if control.type == "BOOLEAN" else [str(v) for v in values]
        self.text = head.sub(lambda m: m.group(1) + ",".join(shown), self.text,
                             count=1)
        return ""


def test_set_control_reads_back_and_verifies():
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    result = mixer.set_control(1, "Speaker Playback Volume", "60%", runner)
    assert result.before == [100, 100]
    assert result.control.values == [91, 91]
    assert result.verified, result.note
    off = mixer.set_control(1, "auto gain control", "off", runner)
    assert off.control.values == [0] and off.verified
    raw = mixer.set_control(1, "Mic Capture Volume", "5", runner)
    assert raw.control.values == [5] and raw.verified


def test_set_control_notices_a_value_that_did_not_take():
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    original = runner.__call__

    def ignoring(args):
        return "" if args[2] == "cset" else original(args)
    result = mixer.set_control(1, "Mic Capture Volume", "3", ignoring)
    assert not result.verified and "read back 8" in result.note


def test_set_control_errors():
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    with pytest.raises(mixer.MixerError, match="no mixer control"):
        mixer.set_control(1, "Banana", "1", runner)
    with pytest.raises(mixer.MixerError, match="several"):
        mixer.set_control(1, "Playback Switch", "off", runner)
    with pytest.raises(mixer.MixerError, match="read-only"):
        mixer.set_control(1, "Capture Channel Map", "1", runner)


def test_snapshot_and_restore_put_changed_controls_back():
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    saved = mixer.snapshot(1, runner)
    mixer.set_control(1, "Speaker Playback Volume", "60%", runner)
    mixer.set_control(1, "auto gain control", "off", runner)
    restored, failed = mixer.restore(1, saved, runner)
    assert not failed
    assert {name for name, _ in restored} == {"Speaker Playback Volume",
                                             "Auto Gain Control"}
    after = {c.numid: list(c.values) for c in mixer.read_controls(1, runner)}
    assert all(after[numid] == values for numid, (_, _, values) in saved.items())
    # Nothing changed since: nothing to put back.
    assert mixer.restore(1, saved, runner) == ([], [])


def test_restore_reports_a_control_it_cannot_set():
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    saved = mixer.snapshot(1, runner)
    mixer.set_control(1, "auto gain control", "off", runner)
    original = runner.__call__

    def refusing(args):
        if args[2] == "cset":
            raise mixer.MixerError("amixer: Control busy")
        return original(args)
    restored, failed = mixer.restore(1, saved, refusing)
    assert restored == [] and failed and "busy" in failed[0][1]
