"""A sound card's ALSA mixer controls, through the `amixer` command.

python3-alsaaudio is not installed, so this parses the text of
`amixer -c N contents`, which looks like

    numid=3,iface=MIXER,name='Speaker Playback Volume'
      ; type=INTEGER,access=rw---R--,values=2,min=0,max=151,step=0
      : values=100,100
      | dBminmax-min=-95.00dB,max=0.00dB

The ones that matter for the ranging tests are flagged by `role`: playback
volume (sets how loud), capture volume and auto gain control (change the
recorded level, and AGC changes it during a ping), and the microphone
playback or monitor path (mixes the mic into the output, a second loopback
nobody asked for).
"""
import os
import re
import shutil
import subprocess
from dataclasses import dataclass, field

_HEAD = re.compile(r"^numid=(\d+),iface=(\w+),name='(.*)'\s*$")
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
    """amixer is missing or refused."""


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

    @property
    def writable(self):
        return "w" in self.access[:2]

    @property
    def role(self):
        return classify(self.name)

    def to_db(self, value):
        """dB for a raw value, or None where the card gives no scale."""
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


def read_controls(card, runner=run_amixer):
    """All mixer controls of ALSA card number `card`."""
    return parse_contents(runner(["-c", str(card), "contents"]))


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


def set_control(card, name, value, runner=run_amixer):
    """Set a control, read it back and say whether it took.

    `value` is what `amixer cset` accepts: an integer, "on"/"off", a
    percentage ("60%"), a dB figure ("-6dB"), an enumerated item number or
    a comma list for several channels. The result's `verified` is True when
    the read-back is what was asked for: exactly for integers and switches,
    within one step for percentages and dB (the card rounds).
    """
    controls = read_controls(card, runner)
    control = find_control(controls, name)
    if not control.writable:
        raise MixerError(f"'{control.name}' is read-only")
    before = list(control.values)
    runner(["-c", str(card), "cset", f"numid={control.numid}", str(value)])
    after = find_control(read_controls(card, runner), control.name)
    verified, note = _verify(after, str(value).strip())
    return SetResult(after, before, str(value), verified, note)


def snapshot(card, runner=run_amixer):
    """The values of every writable control of card `card`, to put back
    later with `restore`: {numid: (name, type, values)}."""
    return {c.numid: (c.name, c.type, list(c.values))
            for c in read_controls(card, runner) if c.writable}


def restore(card, saved, runner=run_amixer):
    """Put back the controls whose values differ from `saved` (from
    `snapshot`). Returns (restored, failed): lists of (name, value text)
    and (name, error text). A control that cannot be set is reported, not
    raised, so one bad control does not stop the others."""
    restored, failed = [], []
    current = {c.numid: c for c in read_controls(card, runner)}
    for numid, (name, kind, values) in saved.items():
        control = current.get(numid)
        if control is None or control.values == values:
            continue
        if kind == "BOOLEAN":
            text = ",".join("on" if v else "off" for v in values)
        else:
            text = ",".join(str(v) for v in values)
        try:
            runner(["-c", str(card), "cset", f"numid={numid}", text])
            restored.append((name, text))
        except MixerError as error:
            failed.append((name, str(error)))
    return restored, failed


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
