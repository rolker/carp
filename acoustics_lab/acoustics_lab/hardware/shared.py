"""The shared access mode: going through the desktop's sound server.

The tool is an ordinary audio client of the server, through the PortAudio
device the server offers (`pulse`, `pipewire` or `default`), so the desktop
keeps working and nothing is borrowed. What it gives up: the server's volume
for the device still applies and other sounds can mix in, so the volumes are
read and recorded with each capture, and a volume that is not 100 % is a
warning. Timing comes from a loopback or the first arrival only, and when
output and input are on different cards the server adjusts their rates to
keep them together; captures say so.

Reading only: this module never changes a volume.
"""
from dataclasses import dataclass, field
from typing import Optional

from . import desktop
from .discovery import PortAudioDevice, _HW_NAME, quiet

SERVER_NAMES = ("pulse", "pipewire", "default")
FULL = 1.0
TOLERANCE = 0.005           # a volume this close to 100 % is 100 %


def server_devices():
    """The PortAudio devices that are not direct hw: ones (`default`,
    `pulse`, `pipewire`, `sysdefault` ...), as PortAudioDevice, or [] if
    PyAudio is missing."""
    try:
        import pyaudio
    except ImportError:
        return []
    found = []
    with quiet():
        pa = pyaudio.PyAudio()
    try:
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            if _HW_NAME.search(info["name"]):
                continue
            found.append(PortAudioDevice(
                index=index, name=info["name"], pcm=0,
                inputs=int(info["maxInputChannels"]),
                outputs=int(info["maxOutputChannels"]),
                default_rate=float(info["defaultSampleRate"]),
                high_input_latency=float(info["defaultHighInputLatency"]),
                high_output_latency=float(info["defaultHighOutputLatency"])))
    finally:
        with quiet():
            pa.terminate()
    return found


def find_server_device(name, devices=None):
    """The server device called `name` (exactly, else the first whose name
    starts with it) that has both an input and an output. Raises
    LookupError, listing what there is."""
    devices = server_devices() if devices is None else devices
    usable = [d for d in devices if d.inputs and d.outputs]
    for match in (lambda d: d.name == name, lambda d: d.name.startswith(name)):
        for d in usable:
            if match(d):
                return d
    known = ", ".join(d.name for d in usable) or "none with both input and output"
    raise LookupError(f"the sound server offers no device called '{name}' "
                      f"(devices with input and output: {known})")


@dataclass
class ServerVolumes:
    """The sound server's default sink and source volumes, and what is wrong
    with them for measuring."""
    sink: str = ""
    sink_volume: Optional[float] = None     # 1.0 is 100 %
    sink_mute: bool = False
    source: str = ""
    source_volume: Optional[float] = None
    source_mute: bool = False
    warnings: list = field(default_factory=list)
    note: str = ""

    def as_dict(self):
        return dict(sink=self.sink, sink_volume=self.sink_volume,
                    sink_mute=self.sink_mute, source=self.source,
                    source_volume=self.source_volume, source_mute=self.source_mute,
                    warnings=list(self.warnings), note=self.note)


def _mean(volumes):
    return sum(volumes) / len(volumes) if volumes else None


def read_volumes(backend=None):
    """The default sink and source volumes from the sound server, with a
    warning for each that is not 100 % (or is muted). Without a sound server
    binding the answer says so in `note` and has no numbers."""
    note = ""
    if backend is None:
        backend, note = desktop.default_backend()
    result = ServerVolumes(note=note)
    if backend is None:
        result.warnings.append(
            "The sound server's volume cannot be read here"
            + (f" ({note})" if note else "") + ", so it is not known whether "
            "the signal is played and recorded at 100 %.")
        return result
    try:
        nodes = backend.nodes()
        sink_name, source_name = backend.defaults()
    except desktop.DesktopError as error:
        result.warnings.append(f"The sound server's volume cannot be read: {error}")
        return result
    for kind, name in ((desktop.SINK, sink_name), (desktop.SOURCE, source_name)):
        node = next((n for n in nodes if n.kind == kind and n.name == name), None)
        if node is None:
            result.warnings.append(f"The server's default {kind} was not found, so "
                                   "its volume is not known.")
            continue
        volume = _mean(node.volumes)
        setattr(result, kind, node.description or node.name)
        setattr(result, f"{kind}_volume", volume)
        setattr(result, f"{kind}_mute", bool(node.mute))
        if node.mute:
            result.warnings.append(f"The server's {kind} '{node.description or node.name}' "
                                   "is muted.")
        elif volume is not None and abs(volume - FULL) > TOLERANCE:
            result.warnings.append(
                f"The server's {kind} '{node.description or node.name}' is at "
                f"{100 * volume:.0f} %, not 100 %: the level the device gets or "
                "gives is not the level in the file. It is recorded with each ping.")
    return result
