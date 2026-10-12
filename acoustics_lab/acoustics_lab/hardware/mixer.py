"""A sound card's ALSA mixer controls, through `libasound`.

The controls are read and set with ALSA's own control API (`alsa_ctl`,
ctypes on `libasound.so.2`): no command is run and no text is parsed. A
control is a `MixerControl`: its type, range, dB scale, enumerated item
names and values. The card can also say when something changes a control
(`Watcher`), which is how a test reports that the desktop or another program
touched the mixer while it ran.

Everything goes through a backend, so tests use a fake:

- `AlsaBackend` (the default) uses `libasound`;
- `AmixerBackend(runner)` runs `amixer` and parses the text of
  `amixer -c N contents`; it is the fallback, with a warning, when
  `libasound` cannot be loaded, and what the sample-text fixtures exercise.

Functions take `backend=` (a backend, or a function standing in for
`amixer`, as before); the default is `default_backend()`.

The controls that matter for the ranging tests are flagged by `role`:
playback volume (sets how loud), capture volume and auto gain control
(change the recorded level, and AGC changes it during a ping), and the
microphone playback or monitor path (mixes the mic into the output, a
second loopback nobody asked for).

`amixer`'s text looks like

    numid=3,iface=MIXER,name='Speaker Playback Volume'
      ; type=INTEGER,access=rw---R--,values=2,min=0,max=151,step=0
      : values=100,100
      | dBminmax-min=-95.00dB,max=0.00dB
"""
import logging
import os
import re
import shutil
import subprocess
import threading
import time
import warnings
import threading
import time
import warnings
from dataclasses import dataclass, field, replace

from . import alsa_ctl

log = logging.getLogger(__name__)

from . import alsa_ctl

log = logging.getLogger(__name__)

_HEAD = re.compile(r"^numid=(\d+),iface=(\w+),name='(.*?)'(?:,(?:index|device|subdevice)=\d+)*\s*$")
_FIELD = re.compile(r"(\w+)=([^,]*)")

PLAYBACK_VOLUME = "playback volume"
CAPTURE_VOLUME = "capture volume"
AUTO_GAIN = "auto gain control"
MIC_MONITOR = "mic monitor"
PLAYBACK_SWITCH = "playback switch"
CAPTURE_SWITCH = "capture switch"

ADVICE = {
    PLAYBACK_VOLUME: "sets how loud the output is; note it, keep it fixed",
    CAPTURE_VOLUME: "sets the recording gain; keep it fixed between runs",
    AUTO_GAIN: "should be off: it changes the gain while a ping is recorded",
    MIC_MONITOR: "should be off: it mixes the mic into the output",
    PLAYBACK_SWITCH: "mute for the output; must be on to hear anything",
    CAPTURE_SWITCH: "mute for the input; must be on to record",
}


class MixerError(Exception):
    """The mixer could not be read or set (libasound or amixer refused)."""


@dataclass
class MixerControl:
    numid: int
    iface: str
    name: str
    type: str = ""                 # INTEGER, BOOLEAN, ENUMERATED, ...
    access: str = ""
    count: int = 0                 # number of values (channels)
    minimum: int = 0
    maximum: int = 0
    step: int = 0
    values: list = field(default_factory=list)   # ints; booleans as 0/1
    items: list = field(default_factory=list)    # names, for ENUMERATED
    db_min: float = None           # dB at `minimum`, where the card says
    db_max: float = None           # dB at `maximum`
    db_step: float = None          # dB per step, for "dBscale" cards
    db_mute_at_min: bool = False
    db_table: list = None          # dB at each raw value minimum..maximum
                                   # (None where the card says mute), from
                                   # the card's own scale; set by libasound
    db_table: list = None          # dB at each raw value minimum..maximum
                                   # (None where the card says mute), from
                                   # the card's own scale; set by libasound

    @property
    def writable(self):
        return "w" in self.access[:2]

    @property
    def role(self):
        return classify(self.name)

    def to_db(self, value):
        """dB for a raw value, or None where the card gives no scale."""
        if self.db_table is not None:
            index = value - self.minimum
            return self.db_table[index] if 0 <= index < len(self.db_table) else None
        if self.db_table is not None:
            index = value - self.minimum
            return self.db_table[index] if 0 <= index < len(self.db_table) else None
        if self.db_min is None:
            return None
        if self.db_step is not None:
            return self.db_min + (value - self.minimum) * self.db_step
        span = self.maximum - self.minimum
        if self.db_max is None or span <= 0:
            return None
        return self.db_min + (value - self.minimum) * (self.db_max - self.db_min) / span

    def value_text(self):
        """The values as readable text: on/off, a name, or numbers with dB."""
        if self.type == "BOOLEAN":
            return ", ".join("on" if v else "off" for v in self.values)
        if self.type == "ENUMERATED":
            return ", ".join(self.items[v] if 0 <= v < len(self.items) else str(v)
                             for v in self.values)
        parts = []
        for value in self.values:
            db = self.to_db(value)
            parts.append(f"{value}" + (f" ({db:.1f} dB)" if db is not None else ""))
        return ", ".join(parts)

    def range_text(self):
        if self.type == "BOOLEAN":
            return "on/off"
        if self.type == "ENUMERATED":
            return "one of: " + ", ".join(self.items)
        text = f"{self.minimum}..{self.maximum}"
        if self.db_min is not None:
            top = self.to_db(self.maximum)
            if top is not None:
                text += f" ({self.db_min:.1f}..{top:.1f} dB)"
        return text


def classify(name):
    """Which role a control name plays for these tests, or "". Names vary by
    chipset ("Speaker Playback Volume", "PCM Playback Volume", "Mic Capture
    Volume", "Auto Gain Control", "Mic Playback Switch", ...)."""
    lower = name.lower()
    if "auto gain" in lower or lower.endswith(" agc") or lower == "agc":
        return AUTO_GAIN
    if "mic" in lower and "playback" in lower:
        return MIC_MONITOR
    if "sidetone" in lower or "monitor" in lower:
        return MIC_MONITOR
    if "capture volume" in lower:
        return CAPTURE_VOLUME
    if "capture switch" in lower:
        return CAPTURE_SWITCH
    if "playback volume" in lower:
        return PLAYBACK_VOLUME
    if "playback switch" in lower:
        return PLAYBACK_SWITCH
    return ""


def _fields(text):
    return {key: value for key, value in _FIELD.findall(text)}


def _ints(text):
    out = []
    for part in text.split(","):
        part = part.strip()
        if part in ("on", "off"):
            out.append(1 if part == "on" else 0)
        elif part.lstrip("-").isdigit():
            out.append(int(part))
    return out


def parse_contents(text):
    """Controls in `amixer contents` (or `cget`) output."""
    controls = []
    current = None
    in_range = False         # inside a multi-part dBrange block
    for line in text.splitlines():
        head = _HEAD.match(line)
        if head:
            current = MixerControl(int(head.group(1)), head.group(2), head.group(3))
            controls.append(current)
            in_range = False
            continue
        if current is None:
            continue
        stripped = line.strip()
        if stripped.startswith(";"):
            body = stripped[1:].strip()
            if body.startswith("Item #"):
                item = re.match(r"Item #(\d+) '(.*)'", body)
                if item:
                    current.items.append(item.group(2))
                continue
            info = _fields(body)
            current.type = info.get("type", "")
            current.access = info.get("access", "")
            current.count = int(info.get("values", 0) or 0)
            for key, attr in (("min", "minimum"), ("max", "maximum"),
                              ("step", "step")):
                if key in info and info[key].lstrip("-").isdigit():
                    setattr(current, attr, int(info[key]))
        elif stripped.startswith(":"):
            body = stripped[1:].strip()
            if body.startswith("values="):
                current.values = _ints(body[len("values="):])
        elif stripped.startswith("|"):
            body = stripped[1:].strip()
            if body.startswith("dBrange"):
                in_range = True      # several scales; none is used
            elif not in_range:
                _parse_db(current, body)
    return controls


def _parse_db(control, body):
    """dB scale lines: `dBminmax-min=-95.00dB,max=0.00dB` or
    `dBscale-min=-17.25dB,step=0.75dB,mute=0`. Other TLV forms (dBrange)
    leave the control without a dB scale."""
    numbers = {key: float(value) for key, value in
               re.findall(r"(min|max|step)=(-?[\d.]+)dB", body)}
    if body.startswith("dBminmax") and "min" in numbers and "max" in numbers:
        control.db_min, control.db_max = numbers["min"], numbers["max"]
    elif body.startswith("dBscale") and "min" in numbers and "step" in numbers:
        control.db_min, control.db_step = numbers["min"], numbers["step"]
        control.db_max = numbers["min"] + (control.maximum - control.minimum) * numbers["step"]
        control.db_mute_at_min = "mute=1" in body


def important(controls):
    """The controls that matter for the tests, with a note on each."""
    return [(c, ADVICE[c.role]) for c in controls if c.role]


def run_amixer(args):
    """Text printed by `amixer` with these arguments (C locale)."""
    path = shutil.which("amixer")
    if path is None:
        raise MixerError("amixer is not installed (apt: alsa-utils)")
    env = dict(os.environ, LC_ALL="C")
    result = subprocess.run([path] + list(args), capture_output=True,
                            text=True, env=env, timeout=10)
    if result.returncode:
        raise MixerError(f"amixer {' '.join(args)}: "
                         f"{(result.stderr or result.stdout).strip()}")
    return result.stdout


# -- backends -----------------------------------------------------------------

class AmixerBackend:
    """The mixer through the `amixer` command; `runner(args)` returns its
    text (tests pass a fake). It cannot report changes."""
    name = "amixer"

    def __init__(self, runner=run_amixer):
        self.runner = runner

    def read_controls(self, card):
        return parse_contents(self.runner(["-c", str(card), "contents"]))

    def write(self, card, control, values):
        """Set a control to raw `values` (ints, one per channel)."""
        if control.type == "BOOLEAN":
            text = ",".join("on" if v else "off" for v in values)
        else:
            text = ",".join(str(v) for v in values)
        self.runner(["-c", str(card), "cset", f"numid={control.numid}", text])

    def open_events(self, card):
        raise MixerError("amixer cannot report mixer changes")


class AlsaBackend:
    """The mixer through ALSA's control API in libasound (`alsa_ctl`)."""
    name = "libasound"

    def read_controls(self, card):
        try:
            with alsa_ctl.Ctl(card) as ctl:
                controls = []
                for element in ctl.elements():
                    values = ctl.read(element) if element.readable else []
                    controls.append(_control_from(element, values))
                return controls
        except alsa_ctl.AlsaError as error:
            raise MixerError(str(error))

    def write(self, card, control, values):
        try:
            with alsa_ctl.Ctl(card) as ctl:
                ctl.write(ctl.element(control.numid, with_db=False), values)
        except alsa_ctl.AlsaError as error:
            raise MixerError(str(error))

    def open_events(self, card):
        try:
            return AlsaEvents(card)
        except alsa_ctl.AlsaError as error:
            raise MixerError(str(error))


class AlsaEvents:
    """Mixer change events of one card: `wait(timeout)` returns the numids
    of the controls whose value changed (empty on timeout)."""

    def __init__(self, card):
        self.ctl = alsa_ctl.Ctl(card, nonblock=True)
        try:
            self.ctl.subscribe()
        except alsa_ctl.AlsaError:
            self.ctl.close()
            raise

    def wait(self, timeout):
        try:
            if not self.ctl.wait(timeout):
                return []
            events = self.ctl.read_events()
        except alsa_ctl.AlsaError as error:
            raise MixerError(str(error))
        return sorted({numid for numid, mask in events
                       if mask & alsa_ctl.MASK_VALUE})

    def close(self):
        self.ctl.close()


def _control_from(element, values):
    """A MixerControl from an `alsa_ctl.Element` and its values."""
    access = ("r" if element.readable else "-") + ("w" if element.writable else "-")
    access += ("v" if element.volatile else "-") + ("i" if element.inactive else "-")
    access += "-" + ("R" if element.tlv_readable else "-") + "--"
    control = MixerControl(element.numid, element.iface, element.name,
                           element.type, access, element.count, element.minimum,
                           element.maximum, element.step, list(values),
                           list(element.items))
    if element.db:
        control.db_table = list(element.db)
        known = [d for d in element.db if d is not None]
        control.db_min, control.db_max = min(known), max(known)
        control.db_mute_at_min = element.db[0] is None
    return control


_fallback_reason = []


def default_backend():
    """libasound where it loads; else `amixer`, with a warning (once)."""
    try:
        alsa_ctl.load()
        return AlsaBackend()
    except alsa_ctl.AlsaError as error:
        if not _fallback_reason:
            _fallback_reason.append(str(error))
            warnings.warn(f"{error}; using the amixer command for the mixer "
                          "instead", RuntimeWarning, stacklevel=3)
    return AmixerBackend()


def fallback_reason():
    """Why the mixer is using `amixer` instead of libasound, or ""."""
    return _fallback_reason[0] if _fallback_reason else ""


def _backend(backend):
    """None: the default; a backend: itself; a function: an amixer stand-in."""
    if backend is None:
        return default_backend()
    if hasattr(backend, "read_controls"):
        return backend
    return AmixerBackend(backend)


def read_controls(card, backend=None):
    """All mixer controls of ALSA card number `card`."""
    return _backend(backend).read_controls(card)


def find_control(controls, name):
    """The control called `name` (exact, case-insensitive; else a unique
    substring) or MixerError."""
    lower = name.lower()
    exact = [c for c in controls if c.name.lower() == lower]
    if len(exact) == 1:
        return exact[0]
    partial = [c for c in controls if lower in c.name.lower()]
    if len(partial) == 1:
        return partial[0]
    if not partial:
        raise MixerError(f"no mixer control called '{name}'")
    raise MixerError(f"'{name}' matches several controls: "
                     + ", ".join(c.name for c in partial))


@dataclass
class SetResult:
    control: MixerControl            # as read back after the change
    before: list
    requested: str
    verified: bool
    note: str = ""


def set_control(card, name, value, backend=None):
    """Set a control, read it back and say whether it took.

    `value` is an integer, "on"/"off", a percentage ("60%"), a dB figure
    ("-6dB"), an enumerated item number or name, or a comma list for several
    channels. The result's `verified` is True when the read-back is what was
    asked for: exactly for integers and switches, within one step for
    percentages and dB (the card rounds).
    """
    backend = _backend(backend)
    control = find_control(backend.read_controls(card), name)
    if not control.writable:
        raise MixerError(f"'{control.name}' is read-only")
    before = list(control.values)
    backend.write(card, control, to_raw_values(control, str(value).strip()))
    after = find_control(backend.read_controls(card), control.name)
    verified, note = _verify(after, str(value).strip())
    return SetResult(after, before, str(value), verified, note)


DB_VALUE = re.compile(r"^\s*([+-]?\d+(?:\.\d+)?)\s*dB\s*$", re.IGNORECASE)


def db_to_raw(control, value):
    """`value` as a raw number text. A dB figure ("-25dB") becomes the
    nearest raw step, from the control's own dB scale. Anything else is
    passed through unchanged."""
    match = DB_VALUE.match(value)
    if not match:
        return value
    if control.type != "INTEGER" or control.to_db(control.maximum) is None:
        raise MixerError(f"'{control.name}' has no dB scale; give a raw value "
                         f"({control.range_text()})")
    wanted = float(match.group(1))
    steps = [v for v in range(control.minimum, control.maximum + 1)
             if control.to_db(v) is not None]
    return str(min(steps, key=lambda v: abs(control.to_db(v) - wanted)))


def to_raw_values(control, text):
    """The raw values to write for `text` (see `set_control`): one int per
    channel; a single figure is used for every channel."""
    values = []
    for part in (p.strip() for p in text.split(",")):
        lower = part.lower()
        try:
            if lower in ("on", "off"):
                values.append(1 if lower == "on" else 0)
            elif lower.endswith("%"):
                span = control.maximum - control.minimum
                values.append(int(round(control.minimum
                                        + float(lower[:-1]) / 100.0 * span)))
            elif lower.endswith("db"):
                values.append(int(db_to_raw(control, part)))
            elif control.type == "ENUMERATED" and not lower.lstrip("-").isdigit():
                names = [item.lower() for item in control.items]
                if lower not in names:
                    raise MixerError(f"'{part}' is not one of: "
                                     + ", ".join(control.items))
                values.append(names.index(lower))
            else:
                values.append(int(part))
        except ValueError:
            raise MixerError(f"cannot read '{part}' as a value for "
                             f"'{control.name}' ({control.range_text()})")
    if len(values) == 1:
        values = values * max(control.count, 1)
    if len(values) != control.count:
        raise MixerError(f"asked for {len(values)} values, "
                         f"'{control.name}' has {control.count}")
    return values


def snapshot(card, backend=None):
    """The values of every writable control of card `card`, to put back
    later with `restore`: {numid: (name, type, values)}."""
    return {c.numid: (c.name, c.type, list(c.values))
            for c in read_controls(card, backend) if c.writable and c.values}


def restore(card, saved, backend=None):
    """Put back the controls whose values differ from `saved` (from
    `snapshot`). Returns (restored, failed): lists of (name, value text)
    and (name, error text). A control that cannot be set is reported, not
    raised, so one bad control does not stop the others."""
    backend = _backend(backend)
    restored, failed = [], []
    current = {c.numid: c for c in backend.read_controls(card)}
    for numid, (name, kind, values) in saved.items():
        control = current.get(numid)
        if control is None or control.values == values:
            continue
        try:
            backend.write(card, control, list(values))
            restored.append((name, _values_text(kind, values)))
        except MixerError as error:
            failed.append((name, str(error)))
    return restored, failed


@dataclass
class Difference:
    """A control that is not as saved."""
    name: str
    saved: str                # value text, as `MixerControl.value_text`
    now: str
    setting: str              # what to give --set to put it back


def differences(card, saved, backend=None):
    """Controls whose values are not those in `saved` (from `snapshot`), as
    a list of `Difference`. Empty when all match."""
    out = []
    current = {c.numid: c for c in read_controls(card, backend)}
    for numid, (name, kind, values) in saved.items():
        control = current.get(numid)
        if control is None:
            out.append(Difference(name, _values_text(kind, values), "gone", ""))
        elif control.values != values:
            before = replace(control, values=list(values))
            setting = (",".join(before.items[v] if v < len(before.items) else str(v)
                                for v in values) if kind == "ENUMERATED"
                       else _values_text(kind, values))
            out.append(Difference(name, before.value_text(), control.value_text(),
                                  setting))
    return out


def _values_text(kind, values):
    if kind == "BOOLEAN":
        return ",".join("on" if v else "off" for v in values)
    return ",".join(str(v) for v in values)


# -- watching for changes ------------------------------------------------------

@dataclass
class Change:
    """A control that changed while watched."""
    numid: int
    name: str
    old: str                  # value text before
    new: str                  # value text after
    seconds: float            # since the watch began

    def text(self):
        return f"{self.name}: {self.old} -> {self.new} (after {self.seconds:.1f} s)"


class Watcher:
    """Notices mixer controls that change while a test runs.

    `start()` records the values; changes are picked up from the card's
    events (libasound) or, where the backend has none, by reading the whole
    mixer every `interval` s. `stop()` returns the list of `Change`s. A
    thread of its own does the waiting; tests call `poll()` instead.

    The values at `start()` are the baseline, so start after your own
    settings are made, and stop before putting the mixer back, or those show
    up as changes too.
    """

    def __init__(self, card, backend=None, interval=0.5, clock=time.monotonic):
        self.card = card
        self.backend = _backend(backend)
        self.interval = interval
        self.clock = clock
        self.changes = []
        self.error = ""
        self.mode = ""               # "events" or "polling"
        self._events = None
        self._baseline = {}
        self._began = 0.0
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread = None

    def start(self, thread=True):
        self._baseline = {c.numid: c for c in self.backend.read_controls(self.card)}
        self._began = self.clock()
        try:
            self._events = self.backend.open_events(self.card)
            self.mode = "events"
        except MixerError as error:
            self._events = None
            self.mode = "polling"
            log.info("mixer events not available (%s); polling", error)
        if thread:
            self._thread = threading.Thread(target=self._run, daemon=True,
                                            name="mixer-watch")
            self._thread.start()
        return self

    def poll(self, timeout=0.0):
        """Wait up to `timeout` s for a change; returns the new Changes."""
        if self._events is not None:
            if not self._events.wait(timeout):
                return []
        elif timeout:
            time.sleep(timeout)
        now = {c.numid: c for c in self.backend.read_controls(self.card)}
        found = []
        for numid, control in now.items():
            before = self._baseline.get(numid)
            if before is not None and before.values != control.values:
                found.append(Change(numid, control.name, before.value_text(),
                                    control.value_text(),
                                    self.clock() - self._began))
        self._baseline = now
        with self._lock:
            self.changes.extend(found)
        return found

    def _run(self):
        while not self._stop.is_set():
            try:
                self.poll(self.interval if self._events is None else 0.2)
            except MixerError as error:
                self.error = str(error)
                return

    def seen(self):
        """The changes seen so far, in order (the watch goes on)."""
        with self._lock:
            return list(self.changes)

    def stop(self):
        """Stop watching; the changes seen, in order."""
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)
        try:
            self.poll(0)
        except MixerError as error:
            self.error = self.error or str(error)
        if self._events is not None:
            self._events.close()
            self._events = None
        with self._lock:
            return list(self.changes)


def _verify(control, requested):
    wanted = [part.strip() for part in requested.split(",")]
    values = control.values
    if len(wanted) == 1 and len(values) > 1:
        wanted = wanted * len(values)
    if len(wanted) != len(values):
        return False, f"asked for {len(wanted)} values, the control has {len(values)}"
    problems = []
    for want, got in zip(wanted, values):
        if want in ("on", "off"):
            ok = got == (1 if want == "on" else 0)
        elif want.endswith("%"):
            span = max(control.maximum - control.minimum, 1)
            target = control.minimum + float(want[:-1]) / 100.0 * span
            ok = abs(got - target) <= max(1.0, span * 0.01)
        elif want.endswith("dB"):
            db = control.to_db(got)
            tolerance = abs(control.db_step) if control.db_step else 1.0
            ok = db is not None and abs(db - float(want[:-2])) <= tolerance + 0.5
        else:
            try:
                ok = got == int(want)
            except ValueError:
                ok = control.type == "ENUMERATED" and got < len(control.items) \
                    and control.items[got].lower() == want.lower()
        if not ok:
            problems.append(f"asked {want}, read back {got}")
    return not problems, "; ".join(problems)
