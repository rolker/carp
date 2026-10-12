"""A whole machine, faked, for the hardware backend: a sound card list, the
mixer, the desktop's sound server, the device reservation and the streams.
Nothing here opens a device, writes a control or makes a sound."""
from acoustics_lab.backends.hardware import Environment
from acoustics_lab.hardware import desktop, discovery, hold, mixer, reserve, shared
from acoustics_lab.hardware.fake import FakeDevice
from fake_audio import FakeAlsaBackend, FakeDesktop, node

CARD = 1
SINK = "alsa_output.pci-0000_00_1f.3.analog-stereo"
SOURCE = "alsa_input.pci-0000_00_1f.3.analog-stereo"

MIXER_TEXT = """\
numid=4,iface=MIXER,name='Speaker Playback Switch'
  ; type=BOOLEAN,access=rw------,values=2
  : values=on,on
numid=5,iface=MIXER,name='Master Playback Volume'
  ; type=INTEGER,access=rw---R--,values=1,min=0,max=87,step=0
  : values=17
  | dBscale-min=-65.25dB,step=0.75dB,mute=0
numid=7,iface=MIXER,name='Capture Volume'
  ; type=INTEGER,access=rw---R--,values=1,min=0,max=63,step=0
  : values=40
  | dBscale-min=-17.25dB,step=0.75dB,mute=0
"""


def speaker(volume=0.13):
    return node(desktop.SINK, SINK, CARD, [volume, volume], False,
                "Built-in Audio Analog Stereo")


def microphone(volume=0.70):
    return node(desktop.SOURCE, SOURCE, CARD, [volume, volume], False,
                "Built-in Audio Analog Stereo")


class FakeReservation:
    """The device reservation: records when the card is taken and given
    back, and lets the test play the desktop taking it back."""
    log = None
    on_release = None
    on_acquire = None
    refuse = False

    def __init__(self, card, **options):
        self.card = card
        self.ok = not FakeReservation.refuse

    def acquire(self):
        self.log.append("borrow")
        if FakeReservation.on_acquire:
            FakeReservation.on_acquire()

    def describe(self):
        return ([f"Borrowed card {self.card} from FakeHolder."] if self.ok
                else [f"FakeHolder refused to give up card {self.card}."])

    def release(self):
        self.log.append("release")
        if FakeReservation.on_release:
            FakeReservation.on_release()

    def describe_release(self):
        return [f"Released card {self.card}."]


class FakeEnvironment(Environment):
    """Cards, streams and server volumes for the backend. `streams` maps a
    rig device ID to a ready FakeDevice; any device not listed gets a default
    laptop-like one (the speaker heard at the mic through the air, 3195
    samples later, with an echo)."""

    def __init__(self, log, streams=None, cards=None, volumes=None):
        self.log = log
        self.streams = dict(streams or {})
        self.card_list = cards if cards is not None else [
            discovery.Card(0, "NVidia", "HDA-Intel", "HDA NVidia"),
            discovery.Card(CARD, "PCH", "HDA-Intel", "HDA Intel PCH")]
        self.volumes = volumes
        self.made = []

    def cards(self):
        return self.card_list

    def find_card(self, ref):
        if str(ref).strip():
            return discovery.find_card(self.card_list, ref)
        for card in self.card_list:
            if card.number == CARD or card.usb:
                return card
        raise LookupError("no built-in sound card")

    def make_stream(self, config, card):
        self.log.append(f"open {config['id']} "
                        + ("hw" if card is not None else config.get("server_device", "pulse")))
        stream = self.streams.get(config["id"]) or FakeDevice(
            rate=config.get("rate", 48000), in_latency=2000.0, out_latency=1195.0,
            loopback_gain=0.4, noise_rms=3.0, echoes=[(60.0, 1.5)], name=config["id"])
        self.made.append(stream)
        return stream

    def server_volumes(self):
        return self.volumes or shared.read_volumes(FakeDesktop([
            node(desktop.SINK, "sink", None, [1.0, 1.0]),
            node(desktop.SOURCE, "source", None, [1.0, 1.0])], "sink", "source"))


class World:
    """The machine around a backend: patches the mixer, the desktop and the
    reservation (the pieces hold.py looks up) to fakes, and keeps one log of
    what was done in what order."""

    def __init__(self, monkeypatch):
        self.log = []
        self.mixer = FakeAlsaBackend(MIXER_TEXT)
        self.mixer.log = self.log
        self.server = FakeDesktop([speaker(0.13), microphone(0.70)], SINK, SOURCE)
        self.server.log = self.log
        monkeypatch.setattr(mixer, "default_backend", lambda: self.mixer)
        monkeypatch.setattr(desktop, "default_backend", lambda: (self.server, ""))
        monkeypatch.setattr(desktop, "SETTLE_S", 0.0)
        monkeypatch.setattr(desktop, "TIMEOUT_S", 0.5)
        monkeypatch.setattr(desktop, "POLL_S", 0.01)
        FakeReservation.log = self.log
        FakeReservation.refuse = False
        FakeReservation.on_release = self.card_returns
        FakeReservation.on_acquire = self.card_leaves
        monkeypatch.setattr(reserve, "Reservation", FakeReservation)
        self.after_return = lambda: None

    def card_returns(self):
        """The desktop takes the card back and applies what it saw: its own
        idea of the volumes."""
        self.server.current = [speaker(0.56), microphone(0.15)]
        self.after_return()

    def card_leaves(self):
        """While the card is borrowed the desktop's sinks and sources are gone."""
        self.server.current = []


def environment(world, **kwargs):
    return FakeEnvironment(world.log, **kwargs)
