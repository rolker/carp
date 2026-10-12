"""The mixer through the control-API backend: set, verify, save, restore,
watch for changes, fall back to amixer. Fakes only, except one smoke test
that only reads the real first card."""
import os
import shutil
import time
import warnings

import pytest

from acoustics_lab.hardware import alsa_ctl, discovery, mixer
from fake_audio import FakeAlsaBackend

HERE = os.path.dirname(os.path.abspath(__file__))


def fixture(name):
    with open(os.path.join(HERE, "fixtures", name)) as handle:
        return handle.read()


@pytest.fixture
def backend():
    return FakeAlsaBackend(fixture("amixer_usb_dongle.txt"))


def test_set_control_goes_through_the_backend_and_is_verified(backend):
    result = mixer.set_control(1, "Speaker Playback Volume", "60%", backend)
    assert backend.writes == [(result.control.numid, [91, 91])]
    assert result.verified and result.before == [100, 100]
    off = mixer.set_control(1, "auto gain control", "off", backend)
    assert off.control.values == [0] and off.verified
    mixer.set_control(1, "Input Source", "Line In", backend)
    assert backend.controls[
        mixer.find_control(mixer.read_controls(1, backend), "Input Source").numid
    ].values == [1]
    mixer.set_control(1, "Speaker Playback Volume", "80,70", backend)
    assert backend.writes[-1][1] == [80, 70]


def test_dB_values_are_converted_here_not_by_a_program(backend):
    result = mixer.set_control(1, "Speaker Playback Volume", "-25dB", backend)
    assert result.verified, result.note
    assert abs(result.control.to_db(result.control.values[0]) + 25) < 1.0
    assert all(isinstance(v, int) for _, values in backend.writes for v in values)


def test_a_write_that_did_not_take_is_noticed(backend):
    numid = mixer.find_control(mixer.read_controls(1, backend), "Mic Capture Volume").numid
    backend.ignore.add(numid)
    result = mixer.set_control(1, "Mic Capture Volume", "3", backend)
    assert not result.verified and "read back 8" in result.note


def test_bad_values_are_refused_before_anything_is_written(backend):
    for name, value in (("Speaker Playback Volume", "loud"),
                        ("Input Source", "Banana"),
                        ("Speaker Playback Volume", "1,2,3"),
                        ("Auto Gain Control", "-3dB")):
        with pytest.raises(mixer.MixerError):
            mixer.set_control(1, name, value, backend)
    assert backend.writes == []


def test_snapshot_restore_and_differences(backend):
    saved = mixer.snapshot(1, backend)
    assert all(values for _, _, values in saved.values())
    assert mixer.differences(1, saved, backend) == []
    mixer.set_control(1, "Speaker Playback Volume", "60%", backend)
    mixer.set_control(1, "auto gain control", "off", backend)
    different = mixer.differences(1, saved, backend)
    assert {d.name for d in different} == {"Speaker Playback Volume",
                                           "Auto Gain Control"}
    agc = next(d for d in different if d.name == "Auto Gain Control")
    assert (agc.saved, agc.now, agc.setting) == ("on", "off", "on")
    restored, failed = mixer.restore(1, saved, backend)
    assert not failed and len(restored) == 2
    assert mixer.differences(1, saved, backend) == []
    assert mixer.restore(1, saved, backend) == ([], [])


def test_restore_reports_a_control_that_refuses(backend):
    saved = mixer.snapshot(1, backend)
    mixer.set_control(1, "auto gain control", "off", backend)
    backend.refuse.add(mixer.find_control(mixer.read_controls(1, backend),
                                          "Auto Gain Control").numid)
    restored, failed = mixer.restore(1, saved, backend)
    assert restored == [] and "busy" in failed[0][1]


def test_amixer_headers_with_a_device_number_are_parsed():
    text = ("numid=25,iface=PCM,name='ELD',device=3\n"
            "  ; type=BYTES,access=r-------,values=0\n"
            "numid=18,iface=PCM,name='Playback Channel Map'\n"
            "  ; type=INTEGER,access=r----R--,values=2,min=0,max=36,step=0\n"
            "  : values=0,0\n")
    controls = mixer.parse_contents(text)
    assert [(c.numid, c.name) for c in controls] == [(25, "ELD"),
                                                     (18, "Playback Channel Map")]
    assert controls[1].values == [0, 0]


# -- events --------------------------------------------------------------------

def test_a_change_during_the_watch_is_reported_with_old_and_new(backend):
    watcher = mixer.Watcher(1, backend).start(thread=False)
    assert watcher.mode == "events"
    assert watcher.poll() == []
    backend.touch("Speaker Playback Volume", [140, 140])
    backend.touch("Auto Gain Control", [0])
    found = watcher.poll()
    assert [c.name for c in found] == ["Speaker Playback Volume", "Auto Gain Control"] \
        or {c.name for c in found} == {"Speaker Playback Volume", "Auto Gain Control"}
    volume = next(c for c in found if c.name == "Speaker Playback Volume")
    assert volume.old.startswith("100") and volume.new.startswith("140")
    assert "Speaker Playback Volume:" in volume.text() and "->" in volume.text()
    # A second change is relative to the one before it.
    backend.touch("Speaker Playback Volume", [141, 141])
    again = watcher.poll()
    assert again[0].old.startswith("140") and again[0].new.startswith("141")
    assert [c.new for c in watcher.seen()][-1] == again[0].new
    watcher.stop()
    assert backend.queues == []          # the event source was closed


def test_the_watcher_thread_collects_changes(backend):
    watcher = mixer.Watcher(1, backend).start()
    backend.touch("Mic Capture Volume", [2])
    deadline = time.time() + 5
    while not watcher.seen() and time.time() < deadline:
        time.sleep(0.01)
    changes = watcher.stop()
    assert [c.name for c in changes] == ["Mic Capture Volume"]
    assert changes[0].seconds >= 0


def test_writes_by_this_program_are_events_too_so_stop_before_restoring(backend):
    saved = mixer.snapshot(1, backend)
    watcher = mixer.Watcher(1, backend).start(thread=False)
    mixer.set_control(1, "auto gain control", "off", backend)
    assert [c.name for c in watcher.poll()] == ["Auto Gain Control"]
    watcher.stop()
    mixer.restore(1, saved, backend)       # after stop: not reported


def test_without_events_the_mixer_is_polled():
    backend = FakeAlsaBackend(fixture("amixer_usb_dongle.txt"), events=False)
    watcher = mixer.Watcher(1, backend, interval=0.01).start(thread=False)
    assert watcher.mode == "polling"
    assert watcher.poll() == []
    backend.touch("Auto Gain Control", [0])
    assert [c.name for c in watcher.poll()] == ["Auto Gain Control"]


def test_amixer_backend_has_no_events_and_the_watcher_polls():
    from test_hardware_discovery_mixer import FakeAmixer
    runner = FakeAmixer(fixture("amixer_usb_dongle.txt"))
    watcher = mixer.Watcher(1, runner).start(thread=False)
    assert watcher.mode == "polling"
    mixer.set_control(1, "auto gain control", "off", runner)
    assert [c.name for c in watcher.poll()] == ["Auto Gain Control"]


# -- fallback ------------------------------------------------------------------

def test_without_libasound_the_amixer_backend_is_used_with_a_warning(monkeypatch):
    def broken():
        raise alsa_ctl.AlsaError("libasound.so.2 not found (apt: libasound2t64)")
    monkeypatch.setattr(alsa_ctl, "load", broken)
    monkeypatch.setattr(mixer, "_fallback_reason", [])
    with pytest.warns(RuntimeWarning, match="amixer"):
        chosen = mixer.default_backend()
    assert isinstance(chosen, mixer.AmixerBackend)
    assert "libasound" in mixer.fallback_reason()
    with warnings.catch_warnings():            # said once
        warnings.simplefilter("error")
        assert isinstance(mixer.default_backend(), mixer.AmixerBackend)


def test_with_libasound_the_default_backend_is_the_api_one(monkeypatch):
    monkeypatch.setattr(alsa_ctl, "load", lambda: object())
    assert isinstance(mixer.default_backend(), mixer.AlsaBackend)


# -- the real library, read only ----------------------------------------------------

def _first_card():
    cards = discovery.list_cards()
    return cards[0].number if cards else None


@pytest.mark.skipif(not alsa_ctl.available() or _first_card() is None,
                    reason="no libasound or no sound card")
def test_libasound_reads_the_real_card_like_amixer_does():
    """Reads only: lists the controls and their values and compares what
    does not change with `amixer contents`. Writes nothing."""
    card = _first_card()
    controls = mixer.AlsaBackend().read_controls(card)
    assert controls
    for c in controls:
        assert c.type and c.iface
        if c.type == "INTEGER" and c.db_table:
            assert len(c.db_table) == c.maximum - c.minimum + 1
    if shutil.which("amixer"):
        try:
            text = mixer.AmixerBackend().read_controls(card)
        except mixer.MixerError:
            text = []
        by_id = {c.numid: c for c in text}
        for c in controls:
            other = by_id.get(c.numid)
            if other is None:
                continue
            assert (c.name, c.type, c.count, c.minimum, c.maximum, c.items) == \
                (other.name, other.type, other.count, other.minimum,
                 other.maximum, other.items)
    events = mixer.AlsaBackend().open_events(card)       # subscribes, writes nothing
    try:
        assert isinstance(events.wait(0), list)
    finally:
        events.close()
