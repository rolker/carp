"""Find sound cards and say which one is which.

Identical USB dongles report the same name to PortAudio, so a card is known
by its ALSA card number, its ALSA card id (which a udev rule can set, for
example `donglea`) and its USB port path (for example `1-2.3`, the hub port
it is plugged into). The USB facts come from /proc/asound and sysfs; PyAudio
does not expose them.

Only "hw:" PortAudio devices are used: they report what the hardware really
does. "default", "pulse", "pipewire" and "plughw" convert behind the scenes.
Enumerating devices does not open a stream. Probing the sample rates a card
accepts asks PortAudio to try the format, which briefly touches the card, so
it is only done for USB cards unless asked otherwise.
"""
import contextlib
import os
import re
import sys
from dataclasses import dataclass, field
from typing import Optional

TEST_RATES = (44100, 48000, 96000, 192000)

PROC_ASOUND = "/proc/asound"
SYSFS = "/sys"

_CARD_LINE = re.compile(r"^\s*(\d+)\s+\[(\S*?)\s*\]:\s*(\S+)\s+-\s+(.*?)\s*$")
_USB_INTERFACE = re.compile(r"^(\d+-\d+(?:\.\d+)*):(\d+)\.(\d+)$")
_HW_NAME = re.compile(r"\(hw:(\d+),(\d+)\)")


@contextlib.contextmanager
def quiet():
    """Hide what ALSA and JACK print to stderr while PortAudio probes.

    Same as `acoustic/audio_io._quiet`: they write straight to file
    descriptor 2 for every device name that does not exist here.
    """
    sys.stderr.flush()
    saved = os.dup(2)
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(null)
        os.close(saved)


@dataclass
class PortAudioDevice:
    """One "hw:" device as PortAudio sees it."""
    index: int               # PortAudio device index
    name: str
    pcm: int                 # PCM device number on the card (hw:card,pcm)
    inputs: int              # most input channels
    outputs: int             # most output channels
    default_rate: float      # Hz
    high_input_latency: float = 0.1     # s, PortAudio's "high" default
    high_output_latency: float = 0.1    # s
    input_rates: list = field(default_factory=list)    # Hz, probed
    output_rates: list = field(default_factory=list)   # Hz, probed


@dataclass
class Card:
    """One ALSA sound card."""
    number: int
    id: str                  # ALSA card id, the name in brackets
    driver: str              # e.g. "USB-Audio", "HDA-Intel"
    name: str                # long name from /proc/asound/cards
    usb: bool = False
    usb_id: str = ""         # "vendor:product", lowercase hex, e.g. "0d8c:0014"
    usb_port: str = ""       # USB port path, e.g. "1-2.3"
    usb_interface: str = ""  # sysfs interface name, e.g. "1-2.3:1.0"
    usb_serial: str = ""     # often empty on cheap dongles
    usb_product: str = ""
    portaudio: list = field(default_factory=list)      # of PortAudioDevice

    @property
    def hw(self):
        return f"hw:{self.number}"

    def pa_device(self):
        """The PortAudio device to open: the first one that has both an
        input and an output, else the first one. None if PortAudio does not
        list the card."""
        for device in self.portaudio:
            if device.inputs and device.outputs:
                return device
        return self.portaudio[0] if self.portaudio else None

    def label(self):
        kind = (f"USB {self.usb_id} port {self.usb_port}" if self.usb
                else "not USB")
        return f"card {self.number} [{self.id}] {self.name} ({kind})"


def _read(path):
    try:
        with open(path, "r", errors="replace") as handle:
            return handle.read().strip()
    except OSError:
        return ""


def parse_cards(text):
    """Cards listed in /proc/asound/cards text, as (number, id, driver, name)."""
    found = []
    for line in text.splitlines():
        match = _CARD_LINE.match(line)
        if match:
            number, card_id, driver, name = match.groups()
            found.append((int(number), card_id, driver, name))
    return found


def usb_facts(number, proc_root=PROC_ASOUND, sys_root=SYSFS):
    """USB details of card `number`, or {} if it is not a USB card.

    The card's sysfs `device` link points at the USB interface directory,
    named like `1-2.3:1.0`; the part before the colon is the port path. The
    vendor and product IDs are files in the directory above it.
    """
    link = os.path.join(sys_root, "class", "sound", f"card{number}", "device")
    real = os.path.realpath(link) if os.path.exists(link) else ""
    interface = ""
    for part in reversed(real.split(os.sep)):
        if _USB_INTERFACE.match(part):
            interface = part
            break
    usb_id = _read(os.path.join(proc_root, f"card{number}", "usbid")).lower()
    if not interface and not usb_id:
        return {}
    facts = {"usb_interface": interface, "usb_id": usb_id}
    if interface:
        facts["usb_port"] = _USB_INTERFACE.match(interface).group(1)
        inside = real[:real.rindex(interface) + len(interface)]
        device_dir = os.path.dirname(inside)
        vendor = _read(os.path.join(device_dir, "idVendor"))
        product = _read(os.path.join(device_dir, "idProduct"))
        if vendor and product:
            facts["usb_id"] = f"{vendor}:{product}".lower()
        facts["usb_serial"] = _read(os.path.join(device_dir, "serial"))
        facts["usb_product"] = _read(os.path.join(device_dir, "product"))
    return facts


def list_cards(proc_root=PROC_ASOUND, sys_root=SYSFS):
    """All ALSA cards, from /proc/asound/cards and sysfs. No PortAudio."""
    text = _read(os.path.join(proc_root, "cards"))
    cards = []
    for number, card_id, driver, name in parse_cards(text):
        facts = usb_facts(number, proc_root, sys_root)
        cards.append(Card(
            number=number, id=card_id, driver=driver, name=name,
            usb=bool(facts), usb_id=facts.get("usb_id", ""),
            usb_port=facts.get("usb_port", ""),
            usb_interface=facts.get("usb_interface", ""),
            usb_serial=facts.get("usb_serial", ""),
            usb_product=facts.get("usb_product", "")))
    return cards


def _supports(pa, pyaudio, rate, index, channels, is_input):
    kwargs = (dict(input_device=index, input_channels=channels,
                   input_format=pyaudio.paInt16) if is_input else
              dict(output_device=index, output_channels=channels,
                   output_format=pyaudio.paInt16))
    try:
        return bool(pa.is_format_supported(rate, **kwargs))
    except ValueError:
        return False


def attach_portaudio(cards, probe_rates=None):
    """Fill in each card's `portaudio` list from PyAudio's "hw:" devices.

    `probe_rates` is a set of card numbers whose supported rates are probed
    (default: the USB cards). Other cards get their default rate only.
    Returns an error text if PyAudio is missing, else "".
    """
    try:
        import pyaudio
    except ImportError as error:
        return f"PyAudio is not available ({error})"
    if probe_rates is None:
        probe_rates = {card.number for card in cards if card.usb}
    by_number = {card.number: card for card in cards}
    with quiet():
        pa = pyaudio.PyAudio()
    try:
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            match = _HW_NAME.search(info["name"])
            if not match:
                continue            # default, pulse, pipewire, plughw, ...
            number, pcm = int(match.group(1)), int(match.group(2))
            card = by_number.get(number)
            if card is None:
                continue
            inputs = int(info["maxInputChannels"])
            outputs = int(info["maxOutputChannels"])
            device = PortAudioDevice(
                index=index, name=info["name"], pcm=pcm, inputs=inputs,
                outputs=outputs, default_rate=float(info["defaultSampleRate"]),
                high_input_latency=float(info["defaultHighInputLatency"]),
                high_output_latency=float(info["defaultHighOutputLatency"]))
            if number in probe_rates:
                with quiet():
                    device.input_rates = [
                        r for r in TEST_RATES if inputs and
                        _supports(pa, pyaudio, r, index, 1, True)]
                    device.output_rates = [
                        r for r in TEST_RATES if outputs and
                        _supports(pa, pyaudio, r, index, min(outputs, 2), False)]
            card.portaudio.append(device)
    finally:
        with quiet():
            pa.terminate()
    for card in cards:
        card.portaudio.sort(key=lambda d: d.pcm)
    return ""


def discover(probe_rates=None, proc_root=PROC_ASOUND, sys_root=SYSFS):
    """Cards with their PortAudio devices. Returns (cards, error text)."""
    cards = list_cards(proc_root, sys_root)
    error = attach_portaudio(cards, probe_rates)
    return cards, error


def find_card(cards, ref):
    """The one card that `ref` names, or raise LookupError.

    `ref` is a card number ("2", "hw:2"), an ALSA card id ("donglea") or a
    USB port path ("1-2.3", "usb:1-2.3"). Identical dongles without serial
    numbers get ids like Device, Device_1, which can change when plugged in
    another order, so the port path or a udev-assigned id is the stable name.
    """
    ref = str(ref).strip()
    if not ref:
        raise LookupError("no device named")
    text = ref[4:] if ref.lower().startswith("usb:") else ref
    if text.lower().startswith("hw:"):
        text = text[3:].split(",")[0]
    matches = []
    if text.isdigit():
        matches = [c for c in cards if c.number == int(text)]
    if not matches:
        matches = [c for c in cards if c.id == text]
    if not matches:
        matches = [c for c in cards if c.usb_port and c.usb_port == text]
    if not matches:
        known = ", ".join(f"{c.number}:{c.id}" +
                          (f"@{c.usb_port}" if c.usb_port else "")
                          for c in cards) or "none"
        raise LookupError(f"no sound card matches '{ref}' (cards: {known})")
    if len(matches) > 1:
        raise LookupError(f"'{ref}' matches {len(matches)} cards; "
                          "use the port path or the card number")
    return matches[0]


def describe(card: Optional[Card]):
    """Several plain lines about one card, for the command-line tool."""
    lines = [card.label()]
    if card.usb:
        extra = []
        if card.usb_product:
            extra.append(f"product '{card.usb_product}'")
        extra.append(f"serial '{card.usb_serial}'" if card.usb_serial
                     else "no serial number")
        lines.append("    " + ", ".join(extra))
    if not card.portaudio:
        lines.append("    PortAudio: no hw: device listed")
    for device in card.portaudio:
        rates = ""
        if device.input_rates or device.output_rates:
            rates = (f", in {_khz(device.input_rates)}, "
                     f"out {_khz(device.output_rates)}")
        lines.append(f"    PortAudio {device.index}: {device.name}, "
                     f"{device.inputs} in / {device.outputs} out, "
                     f"default {device.default_rate:g} Hz{rates}")
    return lines


def _khz(rates):
    return "/".join(f"{r / 1000:g}" for r in rates) + " kHz" if rates else "?"
