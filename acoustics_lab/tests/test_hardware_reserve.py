"""Device borrowing, on a private D-Bus bus started by the tests.

Nothing here touches the user's session bus or any sound card: a throwaway
`dbus-daemon` is the bus, and a small program (fake_holder.py) plays
WirePlumber. Skipped where dbus-daemon or python3-dbus is missing.
"""
import os
import shutil
import signal
import subprocess
import sys
import time

import pytest

from acoustics_lab.hardware import reserve

HERE = os.path.dirname(os.path.abspath(__file__))
HOLDER = os.path.join(HERE, "fake_holder.py")
CARD = 7

pytestmark = pytest.mark.skipif(
    shutil.which("dbus-daemon") is None or not reserve.AVAILABLE,
    reason="needs dbus-daemon and python3-gi")


@pytest.fixture(autouse=True)
def never_the_real_session_bus(monkeypatch):
    """Anything that forgets to name the private bus finds no bus at all."""
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nonexistent/bus")


@pytest.fixture
def bus(tmp_path):
    """A private session bus; yields its address."""
    daemon = subprocess.Popen(
        ["dbus-daemon", "--session", "--nofork", "--print-address=1"],
        stdout=subprocess.PIPE, text=True, cwd=tmp_path)
    address = daemon.stdout.readline().strip()
    assert address
    yield address
    daemon.terminate()
    daemon.wait(timeout=5)


@pytest.fixture
def spawn(bus):
    """Start programs on the private bus; they are killed afterwards."""
    children = []

    def start(args, wait_for="ready"):
        env = dict(os.environ, DBUS_SESSION_BUS_ADDRESS=bus)
        child = subprocess.Popen([sys.executable] + args, env=env,
                                 stdout=subprocess.PIPE, text=True)
        children.append(child)
        line = child.stdout.readline().strip()
        assert line == wait_for, line
        return child

    yield start
    for child in children:
        child.kill()
        child.wait()


@pytest.fixture
def holder(spawn):
    def start(policy, priority=-20):
        return spawn([HOLDER, str(CARD), str(priority), policy])
    return start


def client(bus):
    """A plain client connection to the private bus."""
    from gi.repository import Gio
    return Gio.DBusConnection.new_for_address_sync(
        bus, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
        | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)


def ask(connection, card, priority):
    """Call RequestRelease on whoever holds the card."""
    from gi.repository import GLib
    return reserve.call(
        connection, f"{reserve.SERVICE}.Audio{card}", f"{reserve.PATH}/Audio{card}",
        reserve.SERVICE, "RequestRelease", GLib.Variant("(i)", (priority,)), "(b)",
        3)[0]


def owner(bus, card=CARD):
    """The unique name that owns the card's reservation name, or None."""
    from gi.repository import GLib
    connection = client(bus)
    try:
        return reserve.call(
            connection, *reserve._BUS, "GetNameOwner",
            GLib.Variant("(s)", (f"{reserve.SERVICE}.Audio{card}",)), "(s)")[0]
    except GLib.Error:
        return None
    finally:
        connection.close_sync(None)


def wait_until(test, seconds=3.0):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        if test():
            return True
        time.sleep(0.02)
    return test()


def test_a_free_card_is_simply_ours(bus):
    with reserve.borrow(CARD, bus_address=bus) as card:
        assert card.status == reserve.FREE and card.ok and card.held
        assert card.previous is None
        assert owner(bus) is not None
        assert "nobody held it" in card.describe()[0]
    assert owner(bus) is None
    assert not card.held


def test_a_willing_holder_gives_the_card_up_and_gets_it_back_after(bus, holder):
    fake = holder("agree")
    with reserve.borrow(CARD, bus_address=bus) as card:
        assert card.status == reserve.TAKEN and card.held
        assert card.previous.application == "FakeHolder"
        assert card.previous.device == f"fake_card_{CARD}"
        assert card.previous.priority == -20
        assert "FakeHolder" in card.describe()[0] and "agreed" in card.describe()[0]
        assert fake.stdout.readline().strip() == "asked 100"
        assert fake.stdout.readline().strip() == "released"
    # Our name is gone. The fake holder does not reclaim it, as WirePlumber does.
    assert owner(bus) is None
    assert "has not taken it back" in card.describe_release()[0]


def test_a_holder_that_refuses_keeps_the_card(bus, holder):
    fake = holder("refuse")
    before = owner(bus)
    card = reserve.Reservation(CARD, bus_address=bus)
    assert card.acquire() == reserve.REFUSED
    assert not card.ok and not card.held
    assert owner(bus) == before
    assert "did not give it up" in card.describe()[0]
    card.release()                      # harmless
    assert owner(bus) == before
    assert fake.poll() is None


def test_a_holder_of_higher_priority_refuses_us(bus, holder):
    holder("priority", priority=500)
    card = reserve.Reservation(CARD, priority=100, bus_address=bus)
    assert card.acquire() == reserve.REFUSED
    card.release()
    # ... and a lower one gives way
    card2 = reserve.Reservation(CARD, priority=1000, bus_address=bus)
    assert card2.acquire() == reserve.TAKEN
    card2.release()


def test_release_runs_on_an_exception_inside_the_with_block(bus):
    with pytest.raises(RuntimeError):
        with reserve.borrow(CARD, bus_address=bus):
            assert owner(bus) is not None
            raise RuntimeError("test blew up")
    assert owner(bus) is None


def test_release_twice_and_without_acquire_is_harmless(bus):
    card = reserve.Reservation(CARD, bus_address=bus)
    card.release()
    card.acquire()
    card.release()
    card.release()
    assert owner(bus) is None


def test_require_raises_when_refused(bus, holder):
    holder("refuse")
    with pytest.raises(reserve.ReserveError):
        reserve.borrow(CARD, require=True, bus_address=bus)


def test_no_bus_is_a_warning_not_a_failure(monkeypatch, tmp_path):
    monkeypatch.delenv("DBUS_SESSION_BUS_ADDRESS", raising=False)
    monkeypatch.setattr(reserve, "session_bus_address", lambda: None)
    with reserve.borrow(CARD) as card:
        assert card.status == reserve.NO_BUS and card.ok and not card.held
        assert "no D-Bus session bus" in card.describe()[0]
    card = reserve.Reservation(CARD, bus_address="unix:path=" + str(tmp_path / "nothing"))
    assert card.acquire() == reserve.NO_BUS and card.ok


def test_requests_for_the_card_are_logged_and_refused_by_default(bus):
    from gi.repository import GLib
    with reserve.borrow(CARD, bus_address=bus) as card:
        asker = client(bus)
        assert not ask(asker, CARD, 5000)
        for prop, value in (("ApplicationName", "acoustics_lab"),
                            ("ApplicationDeviceName", f"hw:{CARD}"), ("Priority", 100)):
            got = reserve.call(
                asker, f"{reserve.SERVICE}.Audio{CARD}",
                f"{reserve.PATH}/Audio{CARD}", reserve.PROPERTIES, "Get",
                GLib.Variant("(ss)", (reserve.SERVICE, prop)), "(v)", 3)[0]
            assert got == value
        asker.close_sync(None)
        assert card.held and owner(bus) is not None
        assert [(r.priority, r.released) for r in card.requests] == [(5000, False)]
    assert card.describe_release() == [f"Released card {CARD}."]


def test_policy_release_gives_the_card_to_the_asker(bus):
    with reserve.borrow(CARD, bus_address=bus, release="release") as card:
        asker = client(bus)
        assert ask(asker, CARD, 1)
        assert wait_until(lambda: owner(bus) is None)
        assert card.lost and not card.held
        asker.close_sync(None)
    assert "taken from us" in card.describe_release()[0]


def test_policy_priority_and_function(bus):
    card = reserve.Reservation(CARD, priority=100, release="priority")
    assert card._agrees(101) and not card._agrees(100) and not card._agrees(5)
    card = reserve.Reservation(CARD, release=lambda p: p == 42)
    assert card._agrees(42) and not card._agrees(43)
    assert not reserve.Reservation(CARD)._agrees(10 ** 6)


CHILD = """
import sys
sys.path.insert(0, %r)
from acoustics_lab.hardware import reserve
card = reserve.Reservation(%d)
card.acquire()
print(card.status, flush=True)
import time
time.sleep(60)
"""


@pytest.mark.parametrize("sig", [signal.SIGKILL, signal.SIGTERM])
def test_the_card_is_released_when_the_borrowing_process_dies(bus, spawn, holder, sig):
    holder("agree")
    root = os.path.dirname(HERE)
    child = spawn(["-c", CHILD % (root, CARD)], wait_for=reserve.TAKEN)
    mine = owner(bus)
    assert mine is not None and mine != ""
    child.send_signal(sig)
    child.wait(timeout=5)
    assert wait_until(lambda: owner(bus) is None), "the name outlived the process"
    # And it can be borrowed again straight away.
    with reserve.borrow(CARD, bus_address=bus) as again:
        assert again.status == reserve.FREE


# -- the command-line tool -------------------------------------------------------

BUILTIN_MIXER = """\
numid=4,iface=MIXER,name='Speaker Playback Switch'
  ; type=BOOLEAN,access=rw------,values=2
  : values=on,on
numid=5,iface=MIXER,name='Auto-Mute Mode'
  ; type=ENUMERATED,access=rw------,values=1,items=2
  ; Item #0 'Disabled'
  ; Item #1 'Enabled'
  : values=1
numid=6,iface=MIXER,name='Capture Source'
  ; type=ENUMERATED,access=rw------,values=1,items=3
  ; Item #0 'Internal Mic'
  ; Item #1 'Headset Mic'
  ; Item #2 'Headphone Mic'
  : values=0
"""


@pytest.fixture
def tool(bus, monkeypatch):
    """duplex_check.py, pointed at the private bus and a pretend built-in
    card 7. Nothing real is opened: PortAudio probing is stubbed to fail."""
    import importlib.util
    import io
    from acoustics_lab.hardware import desktop, discovery, mixer
    from fake_audio import FakeAlsaBackend, FakeDesktop
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", bus)
    # No real card is read and no real sound server is asked.
    monkeypatch.setattr(mixer, "default_backend",
                        lambda: FakeAlsaBackend(BUILTIN_MIXER))
    monkeypatch.setattr(desktop, "default_backend",
                        lambda: (FakeDesktop([]), ""))
    card = discovery.Card(CARD, "PCH", "HDA-Intel", "HDA Intel PCH")
    monkeypatch.setattr(discovery, "list_cards", lambda *a, **k: [card])
    monkeypatch.setattr(discovery, "attach_portaudio",
                        lambda cards, **k: "stub: no PortAudio in tests")
    monkeypatch.setattr(mixer, "read_controls",
                        lambda n, *a, **k: mixer.parse_contents(BUILTIN_MIXER))
    path = os.path.join(os.path.dirname(HERE), "tools", "duplex_check.py")
    spec = importlib.util.spec_from_file_location("duplex_check", path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)

    def run(*argv):
        out = io.StringIO()
        code = module.main(list(argv), out)
        return code, out.getvalue()
    return run


def test_tool_borrows_warns_about_speakers_and_gives_back(bus, holder, tool):
    holder("agree")
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait")
    assert code == 2 and "stub: no PortAudio" in text      # stopped at the stub
    assert "borrowed from the desktop for the duration of the test" in text
    assert f"Borrowed card {CARD} from FakeHolder" in text
    assert "internal speakers are on" in text
    assert f"--device {CARD} --mixer --set 'Speaker Playback Switch=off'" in text
    assert "Recording from: Internal Mic" in text
    assert "--set 'Capture Source=Headset Mic'" in text
    assert f"Released card {CARD}" in text
    assert owner(bus) is None


def test_tool_carries_on_with_a_warning_when_the_card_is_refused(bus, holder, tool):
    holder("refuse")
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait")
    assert "did not give it up" in text and "WARNING" in text
    assert code == 2 and "stub: no PortAudio" in text


def test_tool_without_a_bus_carries_on(monkeypatch, tool):
    monkeypatch.setenv("DBUS_SESSION_BUS_ADDRESS", "unix:path=/nonexistent/bus")
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait")
    assert "is not reserved" in text and "stub: no PortAudio" in text


def test_tool_no_borrow_leaves_the_holder_alone(bus, holder, tool):
    holder("agree")
    before = owner(bus)
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait",
                      "--no-borrow")
    assert "Not borrowing" in text and "it is not being borrowed" in text
    assert owner(bus) == before


def test_tool_mixer_only_borrows_nothing(bus, holder, tool):
    holder("agree")
    before = owner(bus)
    code, text = tool("--device", str(CARD), "--mixer")
    assert "Borrowed" not in text and owner(bus) == before


def test_tool_puts_mixer_settings_back_after_a_test(bus, holder, tool, monkeypatch):
    """Settings changed with --set on a test command are restored before the
    card goes back to the desktop."""
    from acoustics_lab.hardware import mixer
    state = {"text": BUILTIN_MIXER}
    calls = []

    def read(n, *a, **k):
        return mixer.parse_contents(state["text"])

    def set_control(card, name, value, runner=None):
        calls.append(("set", name, value))
        return mixer.SetResult(mixer.find_control(read(card), name), [1],
                               value, True)

    def restore(card, saved, runner=None):
        calls.append(("restore", card))
        return [("Speaker Playback Switch", "on")], []
    monkeypatch.setattr(mixer, "read_controls", read)
    monkeypatch.setattr(mixer, "set_control", set_control)
    monkeypatch.setattr(mixer, "restore", restore)
    holder("agree")
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait",
                      "--set", "Speaker Playback Switch=off")
    assert ("set", "Speaker Playback Switch", "off") in calls
    assert ("restore", CARD) in calls
    assert "put back as before the test" in text
    # Put back before the card is given back to the desktop.
    assert text.index("put back as before") < text.index(f"Released card {CARD}")
    calls.clear()
    code, text = tool("--device", str(CARD), "--offset-test", "--no-wait",
                      "--set", "Speaker Playback Switch=off", "--keep-mixer")
    assert ("restore", CARD) not in calls
