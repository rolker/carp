"""The hardware backend: pings through real sound devices, on the
device-stream layer (`hardware/`), described by a rig.

A rig (workspace object, `objects/rigs.py`) says which device and channel
each transducer is on, how each device is taken hold of, and which inputs
carry loopbacks. Pages and ping designs only ever name transducers.

**One stream per device, kept open.** The first ping opens every device it
needs (an exclusive one is borrowed from the desktop first, its mixer and the
desktop's volumes saved and set as the rig says; a shared one is opened
through the sound server, whose volume is read and recorded) and lets the
input settle; the streams then stay open, ping after ping, until `close()`,
which puts everything back in the order `hardware/hold.py` describes.

**Timing is measured, not assumed.** Output sample n of a device is not heard
at input sample n. A ping is scheduled on each sending device a little ahead
of that device's output counter, and each receiving device's recording starts
when the first sound can reach it and runs long enough for the sound, the
listening time and the rig's latency allowance for that device. A recording's
`started` is its first input sample's time on the device's own clock
(sample number over rate); `emitted` is the send time on the sender's clock.
Two devices are two clocks and are not started together; the room sonar and
the ranging analysis take time zero from the loopback or the direct arrival,
never from `started`.

**What the capture says.** `meta` holds the rig and layout used, per device
the access mode, card, rate, the mixer settings applied, the sound server's
volumes (shared), the input check made while settling, dropouts (xruns) in
the recording, and the messages (warnings included) from taking hold.

Nothing here makes a sound or opens a device unless a ping, an `identify` or
a `warm_up` is asked for.
"""
import copy
import datetime
import time

import numpy as np

from ..hardware import discovery, shared
from ..hardware.checks import settle_and_check
from ..hardware.hold import CardHold
from ..hardware.stream import DeviceError, LateError, PortAudioDuplex
from ..models.detection_design import DEFAULT, from_dict
from ..objects import rigs
from .base import (Backend, Cancelled, Capture, PingStream, Recording,
                   TransducerInfo, never_cancel, no_progress)

LEAD_S = 0.05                 # schedule this far ahead of the output counter (at least)
LOUD_DBFS = -6.0
ANYWAY_PEAK = 1.0
POLL_S = 0.05                 # how often a wait for the input looks at cancel


class Environment:
    """What the backend needs from the machine: the sound cards, and a
    stream for a device of a rig. Tests replace it with one that never
    touches the machine."""

    def cards(self):
        cards = discovery.list_cards()
        return cards

    def find_card(self, ref):
        """The card a rig device names. An empty reference means the built-in
        card: the first one that is not on USB and that PortAudio lists with
        both an input and an output."""
        cards = self.cards()
        if str(ref).strip():
            return discovery.find_card(cards, ref)
        card = discovery.builtin_card(cards)
        if card is None:
            raise LookupError("no built-in sound card with both an input and an "
                              "output was found; name the card in the rig")
        return card

    def make_stream(self, config, card):
        """The (not yet started) PortAudioDuplex for a rig device: the card's
        hw: device (exclusive) or the sound server's device (shared)."""
        rate = float(config.get("rate", 48000))
        if card is not None:
            error = discovery.attach_portaudio([card])
            if error:
                raise DeviceError(error)
            pa = card.pa_device()
            if pa is None or not (pa.inputs and pa.outputs):
                raise DeviceError(f"{card.label()} has no hw: device with both "
                                  "input and output in PortAudio")
            if pa.input_rates and (rate not in pa.input_rates or rate not in pa.output_rates):
                raise DeviceError(
                    f"{rate:g} Hz is not accepted both ways by {pa.name}; it accepts "
                    f"in {pa.input_rates}, out {pa.output_rates}. Change the rate "
                    "of this device in the rig.")
            return PortAudioDuplex(pa, rate=rate, frames_per_buffer=int(config.get("block", 512)),
                                   input_channel=int(config.get("input_channel", 0)),
                                   name=card.id)
        try:
            pa = shared.find_server_device(config.get("server_device") or "pulse")
        except LookupError as error:
            raise DeviceError(str(error)) from None
        return PortAudioDuplex(pa, rate=rate, frames_per_buffer=int(config.get("block", 512)),
                               input_channel=int(config.get("input_channel", 0)),
                               name=pa.name)

    def server_volumes(self):
        return shared.read_volumes()


class OpenDevice:
    """One rig device while it is open."""

    def __init__(self, config, stream, hold=None, card=None):
        self.config, self.stream, self.hold, self.card = config, stream, hold, card
        self.volumes = None            # shared: shared.ServerVolumes
        self.check = None              # the input check made while settling
        self.opened_wall = time.monotonic()

    @property
    def id(self):
        return self.config["id"]


class HardwareBackend(Backend):
    name = "Hardware"
    realtime = True

    def __init__(self, rig, layout, rig_id="", sound_speed=343.2, environment=None,
                 on_message=None):
        self.rig, self.layout, self.rig_id = rig, layout, rig_id
        self.sound_speed_ms = float(sound_speed)
        self.env = environment or Environment()
        self.on_message = on_message
        self.log = []                  # (level, text), everything said while taking hold
        self.count = 0                 # pings made
        self._open = {}                # device ID -> OpenDevice
        self._info = {t["id"]: t for t in layout["transducers"]}
        self._place = rigs.placements(rig)
        for tid, p in self._place.items():
            if rigs.device_of(rig, p["device"]) is None:
                raise ValueError(f"'{tid}' is on device '{p['device']}', which the "
                                 "rig does not have")
        for lb in rig.get("loopbacks", []):
            rx, tx = self._place.get(lb["receiver"]), self._place.get(lb["emitter"])
            if rx is None or tx is None or rx["device"] != tx["device"]:
                raise ValueError("a loopback needs its input and output on the same "
                                 f"device ({lb['emitter']} -> {lb['receiver']})")

    @classmethod
    def from_workspace(cls, workspace, rig_id, sound_speed=343.2, environment=None,
                       on_message=None):
        rig = workspace.get("rigs", rig_id)
        if rig is None:
            raise ValueError(f"no rig with ID {rig_id!r}")
        layout = workspace.get("layouts", rig["layout"])
        if layout is None:
            raise ValueError(f"the rig's layout {rig['layout']!r} is missing")
        return cls(rig, layout, rig_id, sound_speed, environment, on_message)

    # ---- messages ------------------------------------------------------

    def _say(self, text):
        self._note("info", text)

    def _warn(self, text):
        self._note("warning", text)

    def _note(self, level, text):
        self.log.append((level, text))
        if self.on_message:
            self.on_message(level, text)

    # ---- the interface -------------------------------------------------

    def transducers(self):
        out = []
        for tid, t in self._info.items():
            place = self._place.get(tid)
            if place is None:
                continue
            config = rigs.device_of(self.rig, place["device"])
            out.append(TransducerInfo(
                id=tid, name=t.get("name", tid), can_send=bool(t.get("can_send")),
                can_receive=bool(t.get("can_receive")),
                rate=float(config.get("rate", 48000))))
        return out

    def sound_speed(self):
        return self.sound_speed_ms

    def open_stream(self, ping):
        return HardwareStream(self, ping)

    def is_open(self):
        return bool(self._open)

    # ---- taking hold ---------------------------------------------------

    def _device(self, device_id, design, progress=no_progress, cancel=never_cancel):
        """The open device `device_id`, opening it (and letting its input
        settle) if need be."""
        if device_id in self._open:
            return self._open[device_id]
        config = rigs.device_of(self.rig, device_id)
        shared_mode = config.get("access", "exclusive") == "shared"
        hold = card = None
        try:
            if shared_mode:
                self._say(f"Device '{device_id}': shared access through the sound "
                          f"server ('{config.get('server_device') or 'pulse'}'); "
                          "the desktop keeps working, and its volume applies.")
                stream = self.env.make_stream(config, None)
            else:
                try:
                    card = self.env.find_card(config.get("card", ""))
                except LookupError as error:
                    raise DeviceError(f"device '{device_id}': {error}. Is it plugged "
                                      "in, and is the rig pointing at the right card "
                                      "(it may have moved)?") from None
                if not card.usb:
                    self._warn(f"Device '{device_id}' is {card.label()}: the desktop's "
                               "own sound. It is borrowed from the desktop while "
                               "Hardware is the backend and given back when you leave "
                               "it; desktop sound on this card stops meanwhile, and "
                               "the test sounds come out of its speakers.")
                hold = CardHold(card, say=self._say, warn=self._warn)
                hold.prepare(config.get("mixer") or {})
                hold.borrow()
                stream = self.env.make_stream(config, card)
            progress(0.0, f"opening {device_id}")
            stream.start()
        except BaseException:
            if hold is not None:
                hold.finish()
            raise
        opened = OpenDevice(config, stream, hold, card)
        self._open[device_id] = opened
        try:
            if shared_mode:
                opened.volumes = self.env.server_volumes()
                for warning in opened.volumes.warnings:
                    self._warn(f"Device '{device_id}': {warning}")
            progress(0.0, f"letting the input of {device_id} settle ({design.settle_s:g} s)")
            opened.check = settle_and_check(stream, design=design)
            opened.check.pop("window", None)
            for warning in opened.check.get("warnings", []):
                self._warn(f"Device '{device_id}': {warning}")
        except BaseException:
            self._discard(device_id)
            raise
        return opened

    def _discard(self, device_id):
        opened = self._open.pop(device_id, None)
        if opened is None:
            return
        try:
            opened.stream.stop()
        finally:
            if opened.hold is not None:
                opened.hold.finish()

    def close(self):
        """Stop every stream and put everything back: mixers, the card to
        the desktop's volumes. Safe to call again."""
        if self._open:
            self._say("Giving the sound card back to the desktop and putting its "
                      "volumes back ...")
        for device_id in list(self._open):
            try:
                self._discard(device_id)
            except Exception as error:      # noqa: keep putting the rest back
                self._warn(f"Closing device '{device_id}' failed: {error}")

    # ---- a ping --------------------------------------------------------

    def fire(self, ping, progress=no_progress, cancel=never_cancel):
        rig = self.rig
        design = self._design(ping)
        senders = {}
        for e in ping.emissions:
            place, info = self._place.get(e.transducer), self._info.get(e.transducer)
            if place is None or info is None or not info.get("can_send"):
                raise ValueError(f"{e.transducer!r} cannot send on this rig")
            senders.setdefault(place["device"], []).append(e)
        if not ping.emissions:
            raise ValueError("the ping has no emissions")
        listeners = {}
        for rid in ping.receivers:
            place, info = self._place.get(rid), self._info.get(rid)
            if place is None or info is None or not info.get("can_receive"):
                raise ValueError(f"{rid!r} cannot receive on this rig")
            listeners.setdefault(place["device"], []).append(rid)
        for device_id, ids in listeners.items():
            channels = {int(self._place[r].get("channel", 0)) for r in ids}
            config = rigs.device_of(rig, device_id)
            if channels != {int(config.get("input_channel", 0))}:
                raise ValueError(f"device '{device_id}' records input channel "
                                 f"{config.get('input_channel', 0)}; "
                                 + ", ".join(ids) + f" is on channel {sorted(channels)}")
        self._warn_levels(ping)

        wanted = list(dict.fromkeys(list(senders) + list(listeners)))
        for n, device_id in enumerate(wanted):
            if cancel():
                raise Cancelled()
            self._device(device_id, design, lambda f, text="", n=n: progress(
                0.3 * (n + f) / len(wanted), text), cancel)
        if cancel():
            raise Cancelled()

        index = self.count
        self.count += 1
        last_end = max(e.start + len(e.samples) / e.rate for e in ping.emissions)
        starts, wall = {}, {}
        for device_id, emissions in senders.items():
            dev = self._open[device_id].stream
            first = dev.out_position + max(dev.lead_samples, int(LEAD_S * dev.rate))
            starts[device_id] = first
            wall[device_id] = time.monotonic()
            for e in emissions:
                channel = self._place[e.transducer].get("channel", "left")
                samples = e.samples
                if abs(e.rate - dev.rate) > 1e-6:
                    raise ValueError(f"{e.transducer}: the signal is at {e.rate:g} Hz but "
                                     f"its device runs at {dev.rate:g} Hz")
                try:
                    dev.schedule(samples, first + int(round(e.start * dev.rate)), channel)
                except LateError as error:
                    raise DeviceError(f"the output of '{device_id}' could not be scheduled "
                                      f"in time ({error}); is the computer too busy?") from None
        windows = {}
        for device_id in listeners:
            dev = self._open[device_id].stream
            config = rigs.device_of(rig, device_id)
            allowance = float(config.get("latency_allowance_s", 0.15))
            if device_id in starts:
                a, length_s = starts[device_id], last_end + ping.listen + allowance
            else:
                a = dev.in_position
                length_s = max(LEAD_S, dev.lead_samples / dev.rate) + last_end + ping.listen + allowance
            windows[device_id] = (a, a + int(np.ceil(length_s * dev.rate)))
        total = max((b - a) / self._open[d].stream.rate
                    for d, (a, b) in windows.items())
        t0 = time.monotonic()
        for device_id, (a, b) in windows.items():
            dev = self._open[device_id].stream
            while not dev.wait_input(b, timeout=POLL_S):
                if cancel():
                    raise Cancelled()
                progress(min(0.3 + 0.7 * (time.monotonic() - t0) / max(total, 1e-3), 0.99),
                         "listening")
        progress(1.0, "done")

        recordings, device_meta, warnings = {}, {}, []
        for device_id, (a, b) in windows.items():
            opened = self._open[device_id]
            dev = opened.stream
            raw = dev.read_input(a, b)
            lost = dev.xruns_between(a, b)
            if lost:
                warnings.append(f"{len(lost)} dropout(s) on '{device_id}' during this "
                                "ping: its samples or timing may be wrong")
            loopback_of = sorted({lb["emitter"] for lb in rig.get("loopbacks", [])
                                  if lb["receiver"] in listeners[device_id]})
            for rid in listeners[device_id]:
                recordings[rid] = Recording(
                    samples=raw.astype(np.float64) / 32768.0, rate=dev.rate,
                    clock=device_id, started=a / dev.rate, loopback_of=loopback_of)
        for device_id in wanted:
            opened = self._open[device_id]
            device_meta[device_id] = self._device_meta(opened, windows.get(device_id),
                                                       starts.get(device_id))
        emitted = {}
        for e in ping.emissions:
            device_id = self._place[e.transducer]["device"]
            dev = self._open[device_id].stream
            emitted.setdefault(e.transducer,
                               (starts[device_id] + int(round(e.start * dev.rate))) / dev.rate)
        meta = dict(
            backend=self.name, rig_id=self.rig_id, rig_name=rig.get("name", ""),
            sound_speed=self.sound_speed_ms, ping_index=index,
            time=datetime.datetime.now().astimezone().isoformat(),
            rig=copy.deepcopy(rig), layout=copy.deepcopy(self.layout),
            devices=device_meta, warnings=warnings,
            samples_were="int16 from the device, mono, converted to float by /32768",
            ping=copy.deepcopy(ping.meta),
            messages=[text for _, text in self.log][-50:])
        return Capture(recordings=recordings, emitted=emitted, truth=None,
                       meta=meta, ping=ping)

    def _design(self, ping):
        """The detection design the ping asks for (its settle time and input
        check limits matter when a device opens)."""
        settings = ping.meta.get("detection_settings")
        try:
            return from_dict(settings) if settings else DEFAULT
        except ValueError:
            return DEFAULT

    def _warn_levels(self, ping):
        """Before a run (principle 6: warn, do not refuse): how loud, from
        where, and what is being borrowed."""
        peak = max((float(np.max(np.abs(e.samples))) for e in ping.emissions), default=0.0)
        db = 20 * np.log10(max(peak, 1e-9))
        if peak > ANYWAY_PEAK:
            self._warn(f"The ping's peak is {db:+.1f} dBFS, above full scale: the output "
                       "is clipped flat, as a sound card would, so what comes back shows "
                       "what clipping does.")
        elif db > LOUD_DBFS:
            self._warn(f"The ping's peak is {db:.1f} dBFS, loud: cheap outputs can "
                       "distort and the input can clip; keep ears and headphones away.")

    def _device_meta(self, opened, window, start):
        dev, config = opened.stream, opened.config
        info = dict(
            access=config.get("access", "exclusive"), config=copy.deepcopy(config),
            stream=dev.describe(), rate=dev.rate, started_output_sample=start,
            input_window=list(window) if window else None,
            xruns_total=dev.xrun_count, input_check=opened.check)
        if opened.card is not None:
            info["card"] = opened.card.label()
        if opened.hold is not None:
            info.update(mixer_applied=dict(opened.hold.applied),
                        desktop_volumes_saved=(
                            [n.label() + " " + n.volume_text() for n in opened.hold.desktop_saved[0].nodes]
                            if opened.hold.desktop_saved else None),
                        mixer_changes_seen=opened.hold.seen_changes())
        if opened.volumes is not None:
            info["server_volumes"] = opened.volumes.as_dict()
            info["note"] = ("shared access: the server's volume applies, other sounds "
                            "can mix in, and if output and input are on different cards "
                            "the server keeps their rates together")
        return info

    # ---- Identify ------------------------------------------------------

    def identify(self, transducer_id, seconds=0.5, frequency=1000.0, level_db=-20.0,
                 keep_open=None, progress=no_progress):
        """Play a short tone on one transducer, so that a person can say
        which it is. Opens the device if it is not open and, unless
        `keep_open`, closes it again (giving the card back). Returns a
        sentence for the person. Raises ValueError if the transducer cannot
        send, DeviceError if the device cannot be opened."""
        place, info = self._place.get(transducer_id), self._info.get(transducer_id)
        if place is None or info is None or not info.get("can_send"):
            raise ValueError(f"{transducer_id!r} is not an output on this rig")
        was_open = place["device"] in self._open
        keep = was_open if keep_open is None else keep_open
        try:
            opened = self._device(place["device"], DEFAULT, progress)
            dev = opened.stream
            t = np.arange(int(seconds * dev.rate)) / dev.rate
            tone = 10 ** (level_db / 20) * np.sin(2 * np.pi * frequency * t)
            ramp = np.minimum(1.0, np.minimum(t, t[-1] - t) / 0.01)
            start = dev.out_position + max(dev.lead_samples, int(LEAD_S * dev.rate))
            dev.schedule(tone * ramp, start, place.get("channel", "left"))
            dev.wait_input(start + len(tone) + int(0.1 * dev.rate), timeout=seconds + 5)
        finally:
            if not keep:
                self._discard(place["device"])
        return (f"Played a {frequency:g} Hz tone at {level_db:g} dBFS for {seconds:g} s on "
                f"{info.get('name', transducer_id)} (device '{place['device']}', channel "
                f"{place.get('channel', 'left')}).")


class HardwareStream(PingStream):
    """Repeated pings of one design. The devices are the backend's and stay
    open when this closes (a page reopens its stream whenever anything it
    depends on changes); `HardwareBackend.close()` ends them."""

    def close(self):
        pass
