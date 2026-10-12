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
