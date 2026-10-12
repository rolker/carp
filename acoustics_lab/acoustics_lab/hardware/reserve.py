"""Borrow a sound card from the desktop's sound server, and give it back.

The desktop (PipeWire with WirePlumber, or PulseAudio) keeps every card open.
The standard way for a program to ask for one is the freedesktop Device
Reservation protocol, `org.freedesktop.ReserveDevice1`, on the session bus:

- The program that has card N owns the bus name
  `org.freedesktop.ReserveDevice1.AudioN` and exports, at
  `/org/freedesktop/ReserveDevice1/AudioN`, the method `RequestRelease(i
  priority) -> b` and the properties `Priority` (i), `ApplicationName` (s)
  and `ApplicationDeviceName` (s).
- To get a card: try to own the name. If it is taken, call `RequestRelease`
  on the owner with our priority. If it answers true it lets go of the card
  and the name, and we take the name.

WirePlumber holds each card at priority -20 and releases it to anyone who
asks. We ask with a higher priority, hold the name while a test runs, and
let go of it afterwards so that the desktop takes the card back. Nothing on
disk changes and no sound server is stopped.

Crash safety: the name belongs to an in-process D-Bus connection (GDBus from
python3-gi, served by a thread of its own). A bus name lives only as long as
the connection that owns it, so if this process dies, even by SIGKILL, the bus
closes the connection and drops the name; the desktop sees the card free and
takes it back. No helper process is involved. (python3-dbus was tried first
and crashed when a connection was used from two threads; GDBus is
thread-safe.)

If nobody holds the card (a headless Pi, a USB dongle the server ignores) the
name is simply ours. If there is no session bus, or python3-gi is missing,
`acquire()` says so and carries on without a reservation: a warning, not a
failure.

    with borrow(1) as card:
        print(card.describe())
        ...                       # open hw:1 here
"""
import logging
import os
import threading
import time
from dataclasses import dataclass, field

try:
    from gi.repository import Gio, GLib
    AVAILABLE = True
except ImportError:                       # depends on the machine
    AVAILABLE = False

log = logging.getLogger(__name__)

APPLICATION = "acoustics_lab"
DEFAULT_PRIORITY = 100        # WirePlumber holds cards at -20
SERVICE = "org.freedesktop.ReserveDevice1"
PATH = "/org/freedesktop/ReserveDevice1"
PROPERTIES = "org.freedesktop.DBus.Properties"

# Outcomes of acquire()
TAKEN = "taken"              # ours: the previous holder gave it up
FREE = "free"                # ours: nobody held it
REFUSED = "refused"          # the holder would not give it up; not ours
NO_BUS = "no bus"            # no session bus or no python3-gi; not reserved
FAILED = "failed"            # something else went wrong; not reserved

# org.freedesktop.DBus.RequestName flags and replies
_REPLACE_EXISTING, _DO_NOT_QUEUE = 2, 4
_PRIMARY_OWNER, _ALREADY_OWNER = 1, 4
_BUS = ("org.freedesktop.DBus", "/org/freedesktop/DBus", "org.freedesktop.DBus")

_INTERFACE_XML = f"""
<node><interface name="{SERVICE}">
  <method name="RequestRelease">
    <arg type="i" name="priority" direction="in"/>
    <arg type="b" name="result" direction="out"/>
  </method>
  <property name="Priority" type="i" access="read"/>
  <property name="ApplicationName" type="s" access="read"/>
  <property name="ApplicationDeviceName" type="s" access="read"/>
</interface></node>"""


class ReserveError(Exception):
    """Raised by `borrow(..., require=True)` when the card is not ours."""


@dataclass
class Holder:
    """Who held a card when we asked."""
    bus_name: str = ""             # unique name on the bus, e.g. ":1.8"
    application: str = ""          # ApplicationName, e.g. "WirePlumber"
    device: str = ""               # ApplicationDeviceName
    priority: int = None

    def text(self):
        who = self.application or self.bus_name or "an unknown program"
        extra = f" ({self.device})" if self.device else ""
        prio = "" if self.priority is None else f", priority {self.priority}"
        return f"{who}{extra}{prio}"


@dataclass
class Request:
    """A RequestRelease call from another program while we held the card."""
    priority: int
    sender: str
    released: bool
    time: float = field(default_factory=time.time)


def session_bus_address():
    """The session bus address: $DBUS_SESSION_BUS_ADDRESS, else the usual
    per-user socket, else None."""
    address = os.environ.get("DBUS_SESSION_BUS_ADDRESS")
    if address:
        return address
    path = f"/run/user/{os.getuid()}/bus"
    return f"unix:path={path}" if os.path.exists(path) else None


def call(connection, destination, path, interface, method, args=None,
         reply="()", timeout=5.0):
    """One blocking D-Bus method call; returns the reply's values as a tuple.
    `args` is a GLib.Variant tuple or None. Raises GLib.Error."""
    result = connection.call_sync(
        destination, path, interface, method, args, GLib.VariantType(reply),
        Gio.DBusCallFlags.NONE, int(timeout * 1000), None)
    return result.unpack()


class Reservation:
    """A hold on one sound card (ALSA card number N is device `AudioN`).

    acquire() does not raise for the ordinary outcomes; look at `status` (or
    `ok`) afterwards and print `describe()`. release() is safe to call twice
    and on a reservation that was never acquired.

    priority: higher than WirePlumber's -20, so that it gives way to us.
    release: what to do when another program calls RequestRelease while we
    hold the card: "refuse" (default: a test must not lose its card halfway;
    the request is logged and kept in `requests`), "release" (give way to
    anyone), "priority" (give way to a higher priority than ours, as the
    spec suggests), or a function taking the asker's priority and returning
    True to give way.
    bus_address: a bus to use instead of the session bus (tests).
    """

    def __init__(self, card, priority=DEFAULT_PRIORITY, release="refuse",
                 application=APPLICATION, device_name=None, bus_address=None,
                 timeout=5.0):
        self.card = int(card)
        self.priority = int(priority)
        self.application = application
        self.device_name = device_name or f"hw:{self.card}"
        self.bus_address = bus_address
        self.timeout = timeout
        self.release_policy = release
        self.status = None
        self.previous = None          # Holder, if someone had the card
        self.error = ""
        self.requests = []            # Requests received while we held it
        self.returned_to = None       # Holder that took the card after release()
        self.lost = False             # True if we gave it up on request
        self._connection = None
        self._loop = None
        self._thread = None
        self._lock = threading.Lock()

    @property
    def name(self):
        return f"{SERVICE}.Audio{self.card}"

    @property
    def path(self):
        return f"{PATH}/Audio{self.card}"

    @property
    def ok(self):
        """True if the card is ours, or no reservation is possible (no bus)
        and the caller should simply carry on."""
        return self.status in (TAKEN, FREE, NO_BUS)

    @property
    def held(self):
        """True while we own the card's bus name."""
        return (self._connection is not None and not self.lost
                and self.status in (TAKEN, FREE))

    # -- acquiring ----------------------------------------------------------

    def acquire(self):
        """Try to take the card. Returns the status."""
        if self._connection is not None:
            return self.status
        if not AVAILABLE:
            return self._give_up(NO_BUS, "python3-gi is not installed")
        address = self.bus_address or session_bus_address()
        if not address:
            return self._give_up(NO_BUS, "there is no D-Bus session bus")
        try:
            connection = Gio.DBusConnection.new_for_address_sync(
                address, Gio.DBusConnectionFlags.AUTHENTICATION_CLIENT
                | Gio.DBusConnectionFlags.MESSAGE_BUS_CONNECTION, None, None)
        except GLib.Error as error:
            return self._give_up(NO_BUS, "cannot connect to the session bus: "
                                 + error.message)
        self._connection = connection
        self.lost = False
        self.previous = None
        try:
            self._serve(connection)
            return self._acquire(connection)
        except Exception as error:               # do not keep half a hold
            log.exception("reserving card %d failed", self.card)
            self._close()
            return self._give_up(FAILED, f"{type(error).__name__}: {error}")

    def _serve(self, connection):
        """Export the reservation object, answered from a thread of its own
        (so that RequestRelease is answered while the test blocks)."""
        failure = []
        ready = threading.Event()
        loop = None

        def run():
            nonlocal loop
            context = GLib.MainContext()
            context.push_thread_default()
            loop = GLib.MainLoop(context)
            try:
                info = Gio.DBusNodeInfo.new_for_xml(_INTERFACE_XML).interfaces[0]
                connection.register_object(
                    self.path, info, self._on_method, self._on_property, None)
            except Exception as error:
                failure.append(error)
            ready.set()
            if not failure:
                loop.run()
            context.pop_thread_default()

        self._thread = threading.Thread(target=run, daemon=True,
                                        name=f"reserve-audio{self.card}")
        self._thread.start()
        ready.wait(5.0)
        if failure:
            raise failure[0]
        self._loop = loop

    def _acquire(self, connection):
        if self._request_name(connection, replace=False):
            self.status = FREE
            log.info("card %d borrowed: nobody held it", self.card)
            return self.status
        (owner,) = call(connection, *_BUS, "GetNameOwner",
                        GLib.Variant("(s)", (self.name,)), "(s)")
        self.previous = self._read_holder(connection, owner)
        log.info("card %d is held by %s; asking it to let go (priority %d)",
                 self.card, self.previous.text(), self.priority)
        self.error = ""
        try:
            (agreed,) = call(connection, self.name, self.path, SERVICE,
                             "RequestRelease", GLib.Variant("(i)", (self.priority,)),
                             "(b)", self.timeout)
        except GLib.Error as error:
            self.error = error.message
            agreed = False
        if not agreed:
            self._close()
            return self._give_up(REFUSED, self.error)
        # The holder replies first and lets go of the name just after.
        deadline = time.monotonic() + self.timeout
        while time.monotonic() < deadline:
            if self._request_name(connection, replace=True):
                self.status = TAKEN
                log.info("card %d borrowed: the holder gave it up", self.card)
                return self.status
            time.sleep(0.02)
        self._close()
        return self._give_up(FAILED, "the holder agreed but did not let go of the name")

    def _request_name(self, connection, replace):
        flags = _DO_NOT_QUEUE | (_REPLACE_EXISTING if replace else 0)
        (reply,) = call(connection, *_BUS, "RequestName",
                        GLib.Variant("(su)", (self.name, flags)), "(u)")
        return reply in (_PRIMARY_OWNER, _ALREADY_OWNER)

    def _read_holder(self, connection, owner):
        holder = Holder(bus_name=owner)
        for key, attribute in (("ApplicationName", "application"),
                               ("ApplicationDeviceName", "device"),
                               ("Priority", "priority")):
            try:
                (value,) = call(connection, owner, self.path, PROPERTIES, "Get",
                                GLib.Variant("(ss)", (SERVICE, key)), "(v)", 2.0)
            except GLib.Error:
                continue
            setattr(holder, attribute, value)
        return holder

    def _give_up(self, status, error):
        self.status = status
        self.error = error
        log.warning("card %d not reserved (%s): %s", self.card, status, error)
        return status

    # -- being asked for the card ------------------------------------------

    def _on_property(self, connection, sender, path, interface, name):
        values = {"Priority": GLib.Variant("i", self.priority),
                  "ApplicationName": GLib.Variant("s", self.application),
                  "ApplicationDeviceName": GLib.Variant("s", self.device_name)}
        return values.get(name)

    def _on_method(self, connection, sender, path, interface, method, params,
                   invocation):
        if method != "RequestRelease":
            invocation.return_dbus_error(
                "org.freedesktop.DBus.Error.UnknownMethod", method)
            return
        (priority,) = params.unpack()
        agree = self._request_release(priority, sender)
        invocation.return_value(GLib.Variant("(b)", (agree,)))
        if agree:
            self._let_go()          # the reply is already on its way

    def _agrees(self, priority):
        policy = self.release_policy
        if callable(policy):
            return bool(policy(priority))
        if policy == "release":
            return True
        if policy == "priority":
            return priority > self.priority
        return False

    def _request_release(self, priority, sender):
        """Another program wants the card (runs on the serving thread)."""
        agree = self._agrees(priority)
        with self._lock:
            self.requests.append(Request(priority, sender, agree))
        if agree:
            log.warning("%s asked for card %d (priority %d): giving it up",
                        sender, self.card, priority)
        else:
            log.warning("%s asked for card %d (priority %d): refused, a test "
                        "is running", sender, self.card, priority)
        return agree

    def _let_go(self):
        with self._lock:
            self.lost = True
        try:
            call(self._connection, *_BUS, "ReleaseName",
                 GLib.Variant("(s)", (self.name,)), "(u)")
        except GLib.Error as error:
            log.warning("letting go of card %d: %s", self.card, error.message)

    # -- giving it back -------------------------------------------------------

    def release(self):
        """Give the card back. For a card that had a holder, wait briefly to
        see who took it and set `returned_to`."""
        connection = self._connection
        if connection is None:
            return
        try:
            if self.held:
                call(connection, *_BUS, "ReleaseName",
                     GLib.Variant("(s)", (self.name,)), "(u)")
                if self.previous is not None:
                    self.returned_to = self._wait_for_owner(connection)
        except GLib.Error as error:
            log.warning("releasing card %d: %s", self.card, error.message)
        finally:
            self._close()

    def _wait_for_owner(self, connection, wait=3.0):
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline:
            try:
                (owner,) = call(connection, *_BUS, "GetNameOwner",
                                GLib.Variant("(s)", (self.name,)), "(s)")
                return self._read_holder(connection, owner)
            except GLib.Error:
                time.sleep(0.05)
        return None

    def _close(self):
        connection, self._connection = self._connection, None
        loop, self._loop = self._loop, None
        if loop is not None:
            loop.quit()
        if self._thread is not None:
            self._thread.join(2.0)
            self._thread = None
        if connection is not None:
            try:
                connection.close_sync(None)
            except GLib.Error:
                pass

    # -- reporting ----------------------------------------------------------

    def describe(self):
        """Plain-language lines on what happened when acquiring."""
        card = f"card {self.card}"
        if self.status == FREE:
            return [f"Borrowed {card}: nobody held it (no sound server on it), "
                    "so there was nothing to ask."]
        if self.status == TAKEN:
            return [f"Borrowed {card} from {self.previous.text()}, which "
                    "agreed to let go. Desktop sound on this card stops until "
                    "the test ends."]
        if self.status == REFUSED:
            who = self.previous.text() if self.previous else "its holder"
            why = f" ({self.error})" if self.error else ""
            return [f"{card} is held by {who}, which did not give it up{why}. "
                    "Opening it will probably fail as busy."]
        if self.status == NO_BUS:
            return [f"{card} is not reserved: {self.error}. Carrying on; if a "
                    "sound server is running, it may still hold the card."]
        if self.status == FAILED:
            return [f"{card} could not be reserved: {self.error}. Carrying on."]
        return [f"{card} not reserved."]

    def describe_release(self):
        """Plain-language lines on what happened after release()."""
        card = f"card {self.card}"
        if self.lost:
            asked = self.requests[-1] if self.requests else None
            by = f" (asked for by {asked.sender})" if asked else ""
            return [f"{card} was taken from us during the test{by}; the test "
                    "may have been cut short."]
        if self.status not in (TAKEN, FREE):
            return []
        if self.previous is None:
            return [f"Released {card}."]
        if self.returned_to is not None:
            return [f"Released {card}; {self.returned_to.text()} has it back."]
        return [f"Released {card}; {self.previous.text()} has not taken it "
                "back yet (check: busctl --user list | grep ReserveDevice1)."]

    def __enter__(self):
        self.acquire()
        return self

    def __exit__(self, *exc):
        self.release()
        return False


def borrow(card, require=False, **options):
    """A `Reservation` for ALSA card number `card`, for a `with` block.
    Options are those of `Reservation`. With require=True the card is
    acquired here and ReserveError is raised if it is refused or fails; by
    default a refusal or a missing bus is only reported in the status."""
    reservation = Reservation(card, **options)
    if require:
        reservation.acquire()
        if reservation.status in (REFUSED, FAILED):
            raise ReserveError(" ".join(reservation.describe()))
    return reservation
