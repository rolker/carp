"""ALSA's control interface (a sound card's mixer) through `libasound`.

`ctypes` on `libasound.so.2`, which every machine with ALSA already has, so
nothing needs installing. This is the same C API `amixer` is built on
(alsa-lib `snd_ctl_*`), used directly: no text to parse, no command to run,
and the card can tell us when something changes a control.

    with Ctl(1) as ctl:                      # hw:1
        for element in ctl.elements():       # all controls, with their ranges
            print(element.numid, element.name, ctl.read(element))
        ctl.write(element, [60, 60])         # raw values
    with Ctl(1, nonblock=True) as ctl:       # to watch for changes
        ctl.subscribe()
        if ctl.wait(0.5):
            print(ctl.read_events())         # [(numid, mask), ...]

Values are the raw integers of the card (booleans 0/1, enumerated item
numbers). dB figures are floats in dB; the card's own scale is used, so the
nonlinear ones ("dBrange" blocks) come out right.

This opens the card's control device (`/dev/snd/controlC<N>`), which is not
exclusive: it works while the desktop's sound server or a running stream
holds the card.
"""
import ctypes
import ctypes.util
import select
from dataclasses import dataclass, field

# snd_ctl_elem_type_t
TYPE_BOOLEAN = 1
TYPE_INTEGER = 2
TYPE_ENUMERATED = 3
TYPE_BYTES = 4
TYPE_INTEGER64 = 6

NONBLOCK = 1                      # SND_CTL_NONBLOCK
EVENT_ELEM = 1                    # SND_CTL_EVENT_ELEM
# Event mask bits (snd_ctl_event_elem_get_mask)
MASK_VALUE = 1
MASK_INFO = 2
MASK_ADD = 4
MASK_TLV = 8
DB_MUTE = -9999999                # SND_CTL_TLV_DB_GAIN_MUTE, in 1/100 dB
MAX_DB_STEPS = 4096               # no dB table for a control with more steps


class AlsaError(Exception):
    """libasound is missing or an ALSA call failed."""


class PollFd(ctypes.Structure):
    _fields_ = [("fd", ctypes.c_int), ("events", ctypes.c_short),
                ("revents", ctypes.c_short)]


_P = ctypes.c_void_p
_PP = ctypes.POINTER(ctypes.c_void_p)
_LP = ctypes.POINTER(ctypes.c_long)
_I = ctypes.c_int
_UI = ctypes.c_uint
_L = ctypes.c_long

# name: (restype, argtypes)
_PROTOTYPES = {
    "snd_strerror": (ctypes.c_char_p, [_I]),
    "snd_ctl_open": (_I, [_PP, ctypes.c_char_p, _I]),
    "snd_ctl_close": (_I, [_P]),
    "snd_ctl_elem_list_malloc": (_I, [_PP]),
    "snd_ctl_elem_list_free": (None, [_P]),
    "snd_ctl_elem_list": (_I, [_P, _P]),
    "snd_ctl_elem_list_alloc_space": (_I, [_P, _UI]),
    "snd_ctl_elem_list_free_space": (None, [_P]),
    "snd_ctl_elem_list_get_count": (_UI, [_P]),
    "snd_ctl_elem_list_get_used": (_UI, [_P]),
    "snd_ctl_elem_list_get_numid": (_UI, [_P, _UI]),
    "snd_ctl_elem_id_malloc": (_I, [_PP]),
    "snd_ctl_elem_id_free": (None, [_P]),
    "snd_ctl_elem_info_malloc": (_I, [_PP]),
    "snd_ctl_elem_info_free": (None, [_P]),
    "snd_ctl_elem_info_set_numid": (None, [_P, _UI]),
    "snd_ctl_elem_info_set_item": (None, [_P, _UI]),
    "snd_ctl_elem_info": (_I, [_P, _P]),
    "snd_ctl_elem_info_get_id": (None, [_P, _P]),
    "snd_ctl_elem_info_get_numid": (_UI, [_P]),
    "snd_ctl_elem_info_get_name": (ctypes.c_char_p, [_P]),
    "snd_ctl_elem_info_get_interface": (_I, [_P]),
    "snd_ctl_elem_info_get_type": (_I, [_P]),
    "snd_ctl_elem_info_get_count": (_UI, [_P]),
    "snd_ctl_elem_info_get_min": (_L, [_P]),
    "snd_ctl_elem_info_get_max": (_L, [_P]),
    "snd_ctl_elem_info_get_step": (_L, [_P]),
    "snd_ctl_elem_info_get_items": (_UI, [_P]),
    "snd_ctl_elem_info_get_item_name": (ctypes.c_char_p, [_P]),
    "snd_ctl_elem_info_is_readable": (_I, [_P]),
    "snd_ctl_elem_info_is_writable": (_I, [_P]),
    "snd_ctl_elem_info_is_volatile": (_I, [_P]),
    "snd_ctl_elem_info_is_inactive": (_I, [_P]),
    "snd_ctl_elem_info_is_tlv_readable": (_I, [_P]),
    "snd_ctl_elem_iface_name": (ctypes.c_char_p, [_I]),
    "snd_ctl_elem_type_name": (ctypes.c_char_p, [_I]),
    "snd_ctl_elem_value_malloc": (_I, [_PP]),
    "snd_ctl_elem_value_free": (None, [_P]),
    "snd_ctl_elem_value_set_numid": (None, [_P, _UI]),
    "snd_ctl_elem_read": (_I, [_P, _P]),
    "snd_ctl_elem_write": (_I, [_P, _P]),
    "snd_ctl_elem_value_get_boolean": (_I, [_P, _UI]),
    "snd_ctl_elem_value_get_integer": (_L, [_P, _UI]),
    "snd_ctl_elem_value_get_integer64": (ctypes.c_longlong, [_P, _UI]),
    "snd_ctl_elem_value_get_enumerated": (_UI, [_P, _UI]),
    "snd_ctl_elem_value_get_byte": (ctypes.c_ubyte, [_P, _UI]),
    "snd_ctl_elem_value_set_boolean": (None, [_P, _UI, _L]),
    "snd_ctl_elem_value_set_integer": (None, [_P, _UI, _L]),
    "snd_ctl_elem_value_set_integer64": (None, [_P, _UI, ctypes.c_longlong]),
    "snd_ctl_elem_value_set_enumerated": (None, [_P, _UI, _UI]),
    "snd_ctl_elem_value_set_byte": (None, [_P, _UI, ctypes.c_ubyte]),
    "snd_ctl_get_dB_range": (_I, [_P, _P, _LP, _LP]),
    "snd_ctl_convert_to_dB": (_I, [_P, _P, _L, _LP]),
    "snd_ctl_convert_from_dB": (_I, [_P, _P, _L, _LP, _I]),
    "snd_ctl_subscribe_events": (_I, [_P, _I]),
    "snd_ctl_poll_descriptors_count": (_I, [_P]),
    "snd_ctl_poll_descriptors": (_I, [_P, ctypes.POINTER(PollFd), _UI]),
    "snd_ctl_event_malloc": (_I, [_PP]),
    "snd_ctl_event_free": (None, [_P]),
    "snd_ctl_read": (_I, [_P, _P]),
    "snd_ctl_event_get_type": (_I, [_P]),
    "snd_ctl_event_elem_get_numid": (_UI, [_P]),
    "snd_ctl_event_elem_get_mask": (_UI, [_P]),
}

_library = []


def load():
    """The loaded libasound with argument types set, or AlsaError."""
    if _library:
        return _library[0]
    lib = None
    for name in ("libasound.so.2", ctypes.util.find_library("asound")):
        if not name:
            continue
        try:
            lib = ctypes.CDLL(name)
            break
        except OSError:
            continue
    if lib is None:
        raise AlsaError("libasound.so.2 not found (apt: libasound2t64)")
    try:
        for name, (restype, argtypes) in _PROTOTYPES.items():
            function = getattr(lib, name)
            function.restype = restype
            function.argtypes = argtypes
    except AttributeError as error:
        raise AlsaError(f"libasound is too old: {error}")
    _library.append(lib)
    return lib


def available():
    """True when libasound can be loaded."""
    try:
        load()
        return True
    except AlsaError:
        return False


@dataclass
class Element:
    """One control, as `snd_ctl_elem_info` describes it."""
    numid: int
    iface: str = ""                # MIXER, CARD, PCM, ...
    name: str = ""
    type: str = ""                 # BOOLEAN, INTEGER, ENUMERATED, ...
    kind: int = 0                  # the type as a number (TYPE_*)
    count: int = 0                 # values (channels)
    minimum: int = 0
    maximum: int = 0
    step: int = 0
    items: list = field(default_factory=list)   # names, for ENUMERATED
    readable: bool = False
    writable: bool = False
    volatile: bool = False
    inactive: bool = False
    tlv_readable: bool = False     # the card has a dB scale for it
    db: list = None                # dB at minimum..maximum (None: mute), or None


class Ctl:
    """An open control device, `hw:<card>`. Close it, or use `with`."""

    def __init__(self, card, nonblock=False):
        self.lib = load()
        self.card = card
        self.handle = _P()
        err = self.lib.snd_ctl_open(ctypes.byref(self.handle),
                                    f"hw:{int(card)}".encode(),
                                    NONBLOCK if nonblock else 0)
        if err < 0:
            self.handle = None
            raise AlsaError(f"cannot open the mixer of card {card}: "
                            f"{self._strerror(err)}")

    def _strerror(self, err):
        return self.lib.snd_strerror(err).decode(errors="replace")

    def _check(self, err, what):
        if err < 0:
            raise AlsaError(f"{what}: {self._strerror(err)}")
        return err

    def _alloc(self, kind):
        pointer = _P()
        self._check(getattr(self.lib, f"snd_ctl_{kind}_malloc")(
            ctypes.byref(pointer)), f"out of memory ({kind})")
        return pointer

    def _free(self, kind, pointer):
        getattr(self.lib, f"snd_ctl_{kind}_free")(pointer)

    def close(self):
        if self.handle:
            self.lib.snd_ctl_close(self.handle)
            self.handle = None

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # -- listing and describing ------------------------------------------------

    def numids(self):
        """The numid of every control."""
        lib = self.lib
        listing = self._alloc("elem_list")
        try:
            self._check(lib.snd_ctl_elem_list(self.handle, listing), "listing controls")
            count = lib.snd_ctl_elem_list_get_count(listing)
            if count == 0:
                return []
            self._check(lib.snd_ctl_elem_list_alloc_space(listing, count),
                        "listing controls")
            try:
                self._check(lib.snd_ctl_elem_list(self.handle, listing),
                            "listing controls")
                return [lib.snd_ctl_elem_list_get_numid(listing, i)
                        for i in range(lib.snd_ctl_elem_list_get_used(listing))]
            finally:
                lib.snd_ctl_elem_list_free_space(listing)
        finally:
            self._free("elem_list", listing)

    def elements(self, with_db=True):
        """Every control as an `Element`. `with_db` also reads the dB scale
        of the integer controls that have one."""
        return [self.element(numid, with_db) for numid in self.numids()]

    def element(self, numid, with_db=True):
        lib = self.lib
        info = self._alloc("elem_info")
        ident = self._alloc("elem_id")
        try:
            lib.snd_ctl_elem_info_set_numid(info, numid)
            self._check(lib.snd_ctl_elem_info(self.handle, info),
                        f"reading control {numid}")
            kind = lib.snd_ctl_elem_info_get_type(info)
            element = Element(
                numid=numid,
                iface=lib.snd_ctl_elem_iface_name(
                    lib.snd_ctl_elem_info_get_interface(info)).decode(),
                name=lib.snd_ctl_elem_info_get_name(info).decode(errors="replace"),
                type=lib.snd_ctl_elem_type_name(kind).decode(),
                kind=kind,
                count=lib.snd_ctl_elem_info_get_count(info),
                readable=bool(lib.snd_ctl_elem_info_is_readable(info)),
                writable=bool(lib.snd_ctl_elem_info_is_writable(info)),
                volatile=bool(lib.snd_ctl_elem_info_is_volatile(info)),
                inactive=bool(lib.snd_ctl_elem_info_is_inactive(info)),
                tlv_readable=bool(lib.snd_ctl_elem_info_is_tlv_readable(info)))
            if kind in (TYPE_INTEGER, TYPE_INTEGER64):
                element.minimum = lib.snd_ctl_elem_info_get_min(info)
                element.maximum = lib.snd_ctl_elem_info_get_max(info)
                element.step = lib.snd_ctl_elem_info_get_step(info)
            if kind == TYPE_ENUMERATED:
                for item in range(lib.snd_ctl_elem_info_get_items(info)):
                    lib.snd_ctl_elem_info_set_item(info, item)
                    self._check(lib.snd_ctl_elem_info(self.handle, info),
                                f"reading control {numid}")
                    element.items.append(lib.snd_ctl_elem_info_get_item_name(
                        info).decode(errors="replace"))
            if with_db and kind == TYPE_INTEGER and element.tlv_readable:
                lib.snd_ctl_elem_info_get_id(info, ident)
                element.db = self._db_table(ident, element)
            return element
        finally:
            self._free("elem_id", ident)
            self._free("elem_info", info)

    def _db_table(self, ident, element):
        """dB at each raw value from minimum to maximum, None where the card
        says mute; None if the control has no usable scale."""
        lib = self.lib
        low, high = _L(), _L()
        if lib.snd_ctl_get_dB_range(self.handle, ident, ctypes.byref(low),
                                    ctypes.byref(high)) < 0:
            return None
        steps = element.maximum - element.minimum + 1
        if not 0 < steps <= MAX_DB_STEPS:
            return None
        table = []
        gain = _L()
        for raw in range(element.minimum, element.maximum + 1):
            if lib.snd_ctl_convert_to_dB(self.handle, ident, raw,
                                         ctypes.byref(gain)) < 0:
                return None
            table.append(None if gain.value <= DB_MUTE else gain.value / 100.0)
        return table if any(d is not None for d in table) else None

    def from_dB(self, element, db, direction=0):
        """The raw value of `element` nearest `db` (dB), rounded down for
        direction < 0 and up for > 0, by the card's own scale."""
        ident = self._alloc("elem_id")
        info = self._alloc("elem_info")
        try:
            self.lib.snd_ctl_elem_info_set_numid(info, element.numid)
            self._check(self.lib.snd_ctl_elem_info(self.handle, info), "reading control")
            self.lib.snd_ctl_elem_info_get_id(info, ident)
            raw = _L()
            self._check(self.lib.snd_ctl_convert_from_dB(
                self.handle, ident, int(round(db * 100)), ctypes.byref(raw),
                direction), f"{element.name} has no dB scale")
            return raw.value
        finally:
            self._free("elem_info", info)
            self._free("elem_id", ident)

    # -- values ----------------------------------------------------------------

    def read(self, element):
        """The values of a control: a list of ints (booleans 0/1)."""
        lib = self.lib
        value = self._alloc("elem_value")
        try:
            lib.snd_ctl_elem_value_set_numid(value, element.numid)
            self._check(lib.snd_ctl_elem_read(self.handle, value),
                        f"reading '{element.name}'")
            getter = {TYPE_BOOLEAN: lib.snd_ctl_elem_value_get_boolean,
                      TYPE_INTEGER: lib.snd_ctl_elem_value_get_integer,
                      TYPE_INTEGER64: lib.snd_ctl_elem_value_get_integer64,
                      TYPE_ENUMERATED: lib.snd_ctl_elem_value_get_enumerated,
                      TYPE_BYTES: lib.snd_ctl_elem_value_get_byte}.get(element.kind)
            if getter is None:          # IEC958 and the like: not shown
                return []
            return [int(getter(value, i)) for i in range(element.count)]
        finally:
            self._free("elem_value", value)

    def write(self, element, values):
        """Set the values of a control (raw ints, one per channel)."""
        lib = self.lib
        if len(values) != element.count:
            raise AlsaError(f"'{element.name}' takes {element.count} values, "
                            f"got {len(values)}")
        setter = {TYPE_BOOLEAN: lib.snd_ctl_elem_value_set_boolean,
                  TYPE_INTEGER: lib.snd_ctl_elem_value_set_integer,
                  TYPE_INTEGER64: lib.snd_ctl_elem_value_set_integer64,
                  TYPE_ENUMERATED: lib.snd_ctl_elem_value_set_enumerated,
                  TYPE_BYTES: lib.snd_ctl_elem_value_set_byte}.get(element.kind)
        if setter is None:
            raise AlsaError(f"'{element.name}' ({element.type}) cannot be set here")
        value = self._alloc("elem_value")
        try:
            lib.snd_ctl_elem_value_set_numid(value, element.numid)
            # Read first: the card fills in whatever we do not set.
            self._check(lib.snd_ctl_elem_read(self.handle, value),
                        f"reading '{element.name}'")
            for index, item in enumerate(values):
                setter(value, index, int(item))
            self._check(lib.snd_ctl_elem_write(self.handle, value),
                        f"setting '{element.name}'")
        finally:
            self._free("elem_value", value)

    # -- events ----------------------------------------------------------------

    def subscribe(self, on=True):
        """Ask the card to queue an event whenever a control changes (made by
        any program, this one included)."""
        self._check(self.lib.snd_ctl_subscribe_events(self.handle, 1 if on else 0),
                    "subscribing to mixer events")

    def wait(self, timeout):
        """Wait up to `timeout` s for an event; True when one is queued."""
        count = self.lib.snd_ctl_poll_descriptors_count(self.handle)
        fds = (PollFd * max(count, 1))()
        got = self.lib.snd_ctl_poll_descriptors(self.handle, fds, count)
        poller = select.poll()
        for i in range(got):
            poller.register(fds[i].fd, select.POLLIN)
        return bool(poller.poll(max(0.0, timeout) * 1000.0))

    def read_events(self):
        """Drain the queued events (the control must be open non-blocking):
        a list of (numid, mask) for control events. The mask has MASK_VALUE
        when a value changed."""
        events = []
        event = self._alloc("event")
        try:
            while self.lib.snd_ctl_read(self.handle, event) > 0:
                if self.lib.snd_ctl_event_get_type(event) == EVENT_ELEM:
                    events.append((self.lib.snd_ctl_event_elem_get_numid(event),
                                   self.lib.snd_ctl_event_elem_get_mask(event)))
        finally:
            self._free("event", event)
        return events
