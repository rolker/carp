#!/usr/bin/env python3
"""Check a USB sound dongle for the acoustics lab: list, mixer, timing.

    duplex_check.py --list
    duplex_check.py --device donglea --mixer
    duplex_check.py --device donglea --mixer --set 'Speaker Playback Volume=60%'
    duplex_check.py --device 1-2.3 --offset-test --minutes 5 --level -20 --channel left
    duplex_check.py --device donglea --schedule-test --tat 0.2
    duplex_check.py --fake --offset-test --minutes 5      # no hardware
    duplex_check.py --reanalyse RUN_FOLDER --detection design.json --detect first_fraction=0.6

A device is only ever opened when it is named with --device (card number,
ALSA card id or USB port path) together with a test. Before a test opens
the card's hw: device, the card is borrowed from the desktop's sound server
through the device-reservation protocol on the session bus, and given back
afterwards, or at once if this program dies; nothing on the machine is
changed (--no-borrow skips this). A card that is not on USB (the built-in
sound, HDMI) gets a prominent warning, since the desktop uses it, and the
built-in card's speakers and capture source are checked first. The output level defaults to -20 dBFS; above -6 dBFS gets a
prominent warning, and above 0 dBFS is played clipped at full scale, with a
warning, to show what clipping does. The plan, including how loud, is printed before anything
is played.

Results go to <acoustics_lab>/runs/hardware/<date time>_<device>_<test>/
(a CSV of every ping, summary.json, and input.wav with input.wav.json: the
input exactly as the device gave it), git-ignored. --reanalyse reads a saved
offset test's input again with another detection design (a design file from
a workspace's detection_designs/, and/or --detect KEY=VALUE changes to it),
without touching any sound device, and saves the new result inside that
folder. Every result records the detection design it used.
"""
import argparse
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

import json                                                    # noqa: E402

from acoustics_lab.hardware import (checks, desktop, discovery, mixer,  # noqa: E402
                                    reserve)
from acoustics_lab.models import detection_design                # noqa: E402
from acoustics_lab.hardware.stream import (DeviceError,          # noqa: E402
                                           PortAudioDuplex)

DEFAULT_RUNS = os.path.join(ROOT, "runs", "hardware")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n\n")[0],
                                formatter_class=argparse.RawTextHelpFormatter)
    p.add_argument("--list", action="store_true",
                   help="list sound cards (USB ones marked) and exit")
    p.add_argument("--device", metavar="X",
                   help="card number, ALSA card id (donglea) or USB port path (1-2.3)")
    p.add_argument("--fake", action="store_true",
                   help="use a simulated dongle instead of hardware")
    p.add_argument("--mixer", action="store_true", help="show the mixer controls")
    p.add_argument("--set", action="append", default=[], metavar="NAME=VALUE",
                   help="set a mixer control (with --mixer); repeatable")
    p.add_argument("--offset-test", action="store_true")
    p.add_argument("--schedule-test", action="store_true")
    p.add_argument("--minutes", type=float, default=5.0,
                   help="offset test length (default 5)")
    p.add_argument("--interval", type=float, default=0.5,
                   help="s between pings in the offset test (default 0.5)")
    p.add_argument("--level", type=float, default=-20.0,
                   help="output peak level in dBFS (default -20)")
    p.add_argument("--channel", default="left", choices=["left", "right", "both"],
                   help="output channel wired to the loopback (default left)")
    p.add_argument("--tat", type=float, default=0.2,
                   help="turnaround time of the schedule test, s (default 0.2)")
    p.add_argument("--pulses", type=int, default=40,
                   help="replies to collect in the schedule test (default 40)")
    p.add_argument("--ping", default="chirp", choices=["chirp", "click"])
    p.add_argument("--rate", type=float, help="sample rate, Hz (default: the device's)")
    p.add_argument("--block", type=int, default=512,
                   help="frames per callback (default 512)")
    p.add_argument("--runs", default=DEFAULT_RUNS, help="folder for results")
    p.add_argument("--keep-mixer", action="store_true",
                   help="leave mixer settings as the test left them instead of "
                        "putting them back (for debugging)")
    p.add_argument("--no-borrow", action="store_true",
                   help="do not borrow the card from the desktop's sound server "
                        "(for debugging; opening a card it holds then fails as busy)")
    p.add_argument("--no-wait", action="store_true",
                   help="skip the 3 s pause after printing the plan")
    p.add_argument("--detection", metavar="FILE",
                   help="detection design (a detection_designs/<id>.json file) for "
                        "the tests and --reanalyse; default: the built-in one "
                        "(for --reanalyse: the one the run was made with)")
    p.add_argument("--detect", action="append", default=[], metavar="KEY=VALUE",
                   help="change one detection setting, e.g. first_fraction=0.6 or "
                        "method=envelope; repeatable")
    p.add_argument("--reanalyse", metavar="RUN_FOLDER",
                   help="analyse a saved offset test again from its input.wav; "
                        "opens no device")
    return p.parse_args(argv)


# -- listing and mixer --------------------------------------------------------

def warn(text, out):
    """A warning that stands out from the rest of the output."""
    bar = "!" * 72
    print(bar, file=out)
    print("WARNING: " + text, file=out)
    print(bar, file=out)


def warn_not_usb(card, out, borrowing=True):
    if borrowing:
        warn(f"{card.label()} is not a USB card. It is the desktop's (built-in "
             "sound or HDMI). It is borrowed from the desktop for the duration "
             "of the test and returned afterwards; desktop sound on this card "
             "stops meanwhile, and test signals go to its speakers or screen.",
             out)
    else:
        warn(f"{card.label()} is not a USB card. It is the desktop's (built-in "
             "sound or HDMI), and it is not being borrowed: opening it may "
             "fail as busy, mixer changes are heard on the desktop at once, "
             "and test signals go to its speakers or screen.", out)


def borrow_card(card, args, out):
    """Borrow the card from the desktop's sound server before its hw: device
    is opened. Returns the Reservation (to give back afterwards), or None
    with --no-borrow. A refusal or a missing session bus is a warning, not
    a failure: the open is tried anyway."""
    if args.no_borrow:
        print(f"Not borrowing card {card.number} (--no-borrow).", file=out)
        return None
    reservation = reserve.Reservation(card.number)
    reservation.acquire()
    for line in reservation.describe():
        if reservation.ok:
            print(line, file=out)
        else:
            warn(line, out)
    return reservation


def give_back(reservation, out):
    """Release a borrowed card and say what happened to it."""
    if reservation is None:
        return
    reservation.release()
    for line in reservation.describe_release():
        print(line, file=out)


def check_builtin(card, out):
    """For a card that is not USB (the built-in sound): with direct hw:
    access the desktop's port switching is not in charge, so test signals can
    come out of the internal speakers as well as the jack, and the capture
    source decides which mic is recorded. Say so, with the command to fix it."""
    try:
        controls = mixer.read_controls(card.number)
    except mixer.MixerError as error:
        print(f"Built-in card mixer not read ({error}).", file=out)
        return
    for c in controls:
        if (c.role == mixer.PLAYBACK_SWITCH and "speaker" in c.name.lower()
                and any(c.values)):
            warn(f"The internal speakers are on ('{c.name}' is on). While the "
                 "card is borrowed the desktop no longer switches them off when "
                 "something is plugged in, so test signals may play through "
                 "the laptop speakers as well as the jack. To mute them for "
                 f"the test only, add --set '{c.name}=off' to the test command "
                 "(put back afterwards); or on their own, kept until changed:\n"
                 f"  python3 tools/duplex_check.py --device {card.number} --mixer "
                 f"--set '{c.name}=off'", out)
        if "auto-mute" in c.name.lower():
            print(f"  {c.name}: {c.value_text()} (the driver's own muting of "
                  "the speakers when a jack is plugged in)", file=out)
    for c in controls:
        if c.name.lower() == "capture source" and c.type == "ENUMERATED":
            source = c.value_text()
            print(f"Recording from: {source} (Capture Source; choices: "
                  f"{', '.join(c.items)})", file=out)
            if "internal" in source.lower():
                warn(f"The capture source is '{source}', the laptop's own "
                     "microphone, not the jack. For a loopback or a headset "
                     "mic input, add --set 'Capture Source=Headset Mic' to the "
                     "test command (put back afterwards); or on its own, kept "
                     "until changed:\n"
                     f"  python3 tools/duplex_check.py --device {card.number} --mixer "
                     "--set 'Capture Source=Headset Mic'", out)


def do_list(out):
    cards = discovery.list_cards()
    if not cards:
        print("No ALSA sound cards found in /proc/asound/cards.", file=out)
        return 0
    error = discovery.attach_portaudio(cards)
    print(f"{len(cards)} sound cards. USB cards are marked [USB]; the others "
          "belong to the desktop.", file=out)
    for card in cards:
        lines = discovery.describe(card)
        print(("[USB]     " if card.usb else "[not USB] ") + lines[0], file=out)
        for line in lines[1:]:
            print("          " + line, file=out)
    if error:
        print(error, file=out)
    usb = [c for c in cards if c.usb]
    if usb:
        print("\nName a card with --device using its number, id or port path, "
              "e.g. --device " + (usb[0].usb_port or str(usb[0].number)), file=out)
        ids = [c.usb_id for c in usb]
        if len(set(ids)) < len(ids):
            print("Several USB cards share one vendor:product; use the port "
                  "path, which stays the same while a dongle stays in its socket.",
                  file=out)
    return 0


def print_mixer(card, out):
    controls = mixer.read_controls(card.number)
    print(f"Mixer of card {card.number} [{card.id}]: {len(controls)} controls", file=out)
    for c in controls:
        flag = f"  <-- {c.role}" if c.role else ""
        print(f"  [{c.numid}] {c.name}: {c.value_text()}  "
              f"(range {c.range_text()}{'' if c.writable else ', read-only'}){flag}",
              file=out)
    notes = mixer.important(controls)
    if notes:
        print("Controls that matter here:", file=out)
        for c, note in notes:
            print(f"  {c.name}: {c.value_text()} - {note}", file=out)
    return controls


def do_set(card, assignments, out):
    code = 0
    for text in assignments:
        if "=" not in text:
            print(f"--set needs NAME=VALUE, got '{text}'", file=out)
            return 2
        name, value = text.rsplit("=", 1)
        try:
            result = mixer.set_control(card.number, name.strip(), value.strip())
        except mixer.MixerError as error:
            print(f"cannot set '{name}': {error}", file=out)
            return 1
        status = "ok" if result.verified else f"NOT AS ASKED ({result.note})"
        print(f"set {result.control.name} = {value}: read back "
              f"{result.control.value_text()} (was {result.before}): {status}",
              file=out)
        code = code or (0 if result.verified else 1)
    return code


# -- device and plan ------------------------------------------------------------

def make_fake(args):
    from acoustics_lab.hardware.fake import FakeDevice
    return FakeDevice(frames_per_buffer=args.block, in_latency=130.3,
                      out_latency=args.block + 240.6, name="fake")


def make_real(args, out, holds):
    """The PortAudioDuplex for the named card, after the safety checks, with
    the card borrowed from the desktop first. The reservation is appended to
    `holds` for the caller to give back. Returns (device, card) or
    (None, code)."""
    cards = discovery.list_cards()
    try:
        card = discovery.find_card(cards, args.device)
    except LookupError as error:
        print(error, file=out)
        return None, 2
    if not card.usb and not getattr(args, "warned_not_usb", False):
        warn_not_usb(card, out, borrowing=not args.no_borrow)
    # Borrow before PortAudio looks at the card: a card the sound server holds
    # may not probe correctly.
    holds.append(borrow_card(card, args, out))
    if not card.usb:
        check_builtin(card, out)
    error = discovery.attach_portaudio([card])
    if error:
        print(error, file=out)
        return None, 2
    pa = card.pa_device()
    if pa is None or not (pa.inputs and pa.outputs):
        print(f"{card.label()} has no hw: device with both input and output "
              "in PortAudio.", file=out)
        return None, 2
    rate = args.rate or pa.default_rate
    if pa.input_rates and (rate not in pa.input_rates or rate not in pa.output_rates):
        print(f"{rate:g} Hz is not accepted both ways by {pa.name}; it accepts "
              f"in {pa.input_rates}, out {pa.output_rates}. Use --rate.", file=out)
        return None, 2
    return PortAudioDuplex(pa, rate=rate, frames_per_buffer=args.block,
                           name=card.id), card


def print_plan(args, device, card, out):
    print("\nPlan", file=out)
    where = card.label() if card else "simulated device (no hardware)"
    print(f"  device:   {where}", file=out)
    print(f"  stream:   one duplex stream, {device.rate:g} Hz, int16, "
          f"{device.in_channels} in / {device.out_channels} out, "
          f"{device.frames_per_buffer} frames per block "
          f"({1000 * device.frames_per_buffer / device.rate:.1f} ms)", file=out)
    if args.offset_test:
        pings = int(args.minutes * 60 / args.interval)
        print(f"  test:     offset test, {pings} {args.ping} pings every "
              f"{args.interval:g} s for {args.minutes:g} min", file=out)
    if args.schedule_test:
        print(f"  test:     schedule test, {args.pulses} replies at a "
              f"{args.tat * 1000:.0f} ms turnaround", file=out)
    print(f"  loudness: {checks.level_text(args.level)} on the {args.channel} "
          "output channel", file=out)
    if card:
        try:
            for c in mixer.read_controls(card.number):
                if c.role in (mixer.PLAYBACK_VOLUME, mixer.PLAYBACK_SWITCH,
                              mixer.AUTO_GAIN, mixer.MIC_MONITOR,
                              mixer.CAPTURE_VOLUME):
                    print(f"  mixer:    {c.name} = {c.value_text()}", file=out)
                    if (c.role in (mixer.AUTO_GAIN, mixer.MIC_MONITOR)
                            and any(c.values)):
                        print(f"  WARNING:  {c.name} is on; {mixer.ADVICE[c.role]}",
                              file=out)
        except mixer.MixerError as error:
            print(f"  mixer:    not read ({error})", file=out)
        print("  The sound level depends on the mixer's playback volume and on "
              "what is plugged in.\n  Keep transducers and headphones away "
              "from ears until the level is known.", file=out)


# -- main ---------------------------------------------------------------------

class Session:
    """What a run has taken hold of and must put back, in this order: stop
    watching the mixer, put the mixer back, give the card back, put the
    desktop's volumes back, then check both."""

    def __init__(self):
        self.holds = []             # borrowed cards (Reservations)
        self.restores = []          # (card, mixer snapshot)
        self.desktops = []          # (card, desktop.Saved, backend)
        self.watchers = []          # (card, mixer.Watcher)
        self.changes = []           # (card, [mixer.Change]) after the watch


def main(argv=None, out=None):
    args = parse_args(argv)
    out = out or sys.stdout
    session = Session()
    try:
        return run(args, out, session)
    finally:
        finish(session, out)


def finish(session, out):
    """Put everything back, in order, and say what was found."""
    for card, watcher in session.watchers:
        session.changes.append((card, watcher.stop()))
        report_changes(card, session.changes[-1][1], watcher, out)
    for card, saved in session.restores:
        put_back_mixer(card, saved, out)
    for reservation in session.holds:
        give_back(reservation, out)
    for card, saved, backend in session.desktops:
        put_back_desktop(card, saved, backend, out)
    for card, saved in session.restores:
        verify_mixer(card, saved, out)


def report_changes(card, changes, watcher, out):
    """Say what changed the mixer while the card was being tested."""
    if watcher.error:
        warn(f"Watching the mixer of {card.label()} stopped: {watcher.error}", out)
    if changes:
        warn(f"Something changed the mixer of {card.label()} during the test "
             "(the desktop's sound server, or another program):\n"
             + "\n".join("  " + c.text() for c in changes), out)
    elif not watcher.error:
        print(f"Nothing changed the mixer of card {card.number} during the "
              f"test (watched through {watcher.mode}).", file=out)


def put_back_mixer(card, saved, out):
    """Restore the mixer settings saved before a test, so the desktop gets
    the card back as it was."""
    try:
        restored, failed = mixer.restore(card.number, saved)
    except mixer.MixerError as error:
        warn(f"Could not put the mixer of {card.label()} back: {error}", out)
        return
    if restored:
        print(f"Mixer of card {card.number} put back as before the test: "
              + "; ".join(f"{name} = {value}" for name, value in restored),
              file=out)
    for name, error in failed:
        warn(f"Could not put back {name}: {error}", out)


def put_back_desktop(card, saved, backend, out):
    """After the card is back with the desktop: wait for its sinks and
    sources to reappear, set the saved volumes and mute, and say whether they
    stayed."""
    if saved.nodes:
        print(f"Waiting for the desktop to take card {card.number} back, to "
              "put its volumes back ...", file=out)
        out.flush()
    result = desktop.restore(saved, backend)
    if not saved.nodes:
        return
    if result.ok:
        print(f"Desktop volumes of card {card.number} are as before the test "
              f"(the sound server had them again after {result.waited:.1f} s):",
              file=out)
        for line in result.lines():
            print("  " + line, file=out)
        return
    warn(f"The desktop volumes of card {card.number} are NOT as before the "
         "test:\n" + "\n".join("  " + line for line in result.lines())
         + "\nTo set them by hand:\n"
         + "\n".join("  " + c for c in result.fix_commands()), out)


def verify_mixer(card, saved, out):
    """Compare the hardware mixer with what was saved, after the desktop
    has taken the card back and put its volumes back (it may change the
    mixer too)."""
    try:
        different = mixer.differences(card.number, saved)
    except mixer.MixerError as error:
        warn(f"Could not check the mixer of {card.label()}: {error}", out)
        return
    if not different:
        print(f"Mixer of card {card.number} is as before the test.", file=out)
        return
    commands = [f"  python3 tools/duplex_check.py --device {card.number} --mixer "
                f"--set '{d.name}={d.setting}'" for d in different if d.setting]
    warn(f"The mixer of {card.label()} is NOT as before the test, after the "
         "desktop took the card back:\n"
         + "\n".join(f"  {d.name}: was {d.saved}, is {d.now}" for d in different)
         + "\nTo set them back:\n" + "\n".join(commands), out)


def save_desktop(card, args, session, out):
    """Save the desktop's volumes for the card, before anything touches it.
    A missing sound server or Python binding is a warning, not a failure."""
    backend, note = desktop.default_backend()
    if note:
        warn(note, out)
    if backend is None:
        return
    try:
        saved = desktop.save(card.number, backend)
    except desktop.DesktopError as error:
        warn(f"Could not save the desktop's volumes, so they will not be put "
             f"back: {error}", out)
        return
    for line in saved.lines():
        print(line, file=out)
    session.desktops.append((card, saved, backend))


def start_watching(card, session, out):
    """Watch the card's mixer for changes made while the test runs."""
    try:
        watcher = mixer.Watcher(card.number).start()
    except mixer.MixerError as error:
        warn(f"Not watching the mixer for changes: {error}", out)
        return
    session.watchers.append((card, watcher))
    if watcher.mode == "polling":
        print("The mixer is watched by reading it every "
              f"{watcher.interval:g} s (no change events from this backend).",
              file=out)


def detection_from_args(args, base=None):
    """The DetectionDesign the options ask for: --detection's file (else
    `base`, else the built-in one), with --detect changes on top. Raises
    ValueError with a message for a bad file, key or value."""
    data = (base or detection_design.DEFAULT).to_dict()
    if args.detection:
        try:
            with open(args.detection) as f:
                data.update(json.load(f))
        except (OSError, ValueError) as error:
            raise ValueError(f"cannot read the detection design {args.detection}: "
                             f"{error}") from None
    for text in args.detect:
        if "=" not in text:
            raise ValueError(f"--detect needs KEY=VALUE, got '{text}'")
        key, value = (part.strip() for part in text.split("=", 1))
        if key not in detection_design.SETTING:
            raise ValueError(f"no detection setting '{key}'; they are: "
                             + ", ".join(detection_design.SETTING))
        data[key] = value if key == "method" else _number(key, value)
    return detection_design.from_dict(data)


def _number(key, text):
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{key} needs a number, not '{text}'") from None


def do_reanalyse(args, out):
    """Analyse a saved offset test again with another detection design."""
    try:
        raw = checks.load_run(args.reanalyse)
        was = detection_design.from_dict(raw.meta.get("detection_design", {}))
        design = detection_from_args(args, base=was)
        result = checks.reanalyse_offset(raw, design)
    except (ValueError, OSError) as error:
        print(error, file=out)
        return 2
    print(f"Run {args.reanalyse}", file=out)
    print(f"  made with:      {was.summary()}", file=out)
    print(f"  analysed with:  {design.summary()}", file=out)
    changed = design.differences(was)
    if changed:
        print("  changed:        " + ", ".join(
            f"{k} {a:g} (was {b:g})" if not isinstance(a, str) else f"{k} {a} (was {b})"
            for k, (a, b) in changed.items()), file=out)
    for line in result.verdict:
        print("  " + line, file=out)
    folder = checks.save(result, args.reanalyse, "reanalysis")
    print(f"  Saved in {folder}", file=out)
    return 0 if result.summary["verdict_ok"] else 1


def run(args, out, session):
    if args.reanalyse:
        return do_reanalyse(args, out)
    if args.list:
        return do_list(out)
    if not (args.device or args.fake):
        print("Name a device with --device (see --list), or use --fake. "
              "Nothing is opened unless one is named.", file=out)
        return 2
    if not (args.mixer or args.offset_test or args.schedule_test):
        print("Nothing to do: add --mixer, --offset-test or --schedule-test.",
              file=out)
        return 2
    try:
        design = detection_from_args(args)
    except ValueError as error:
        print(error, file=out)
        return 2
    if args.level > 0:
        warn(f"{args.level:g} dBFS is above full scale: the output is clipped "
             "flat at full scale, as a sound card would, so the test shows "
             "what clipping does (harmonics, a blunter matched-filter peak, "
             "timing errors) rather than a clean result.", out)
    elif args.level > -6:
        warn(f"{args.level:g} dBFS is loud. Near full scale cheap outputs can "
             "distort and the loopback can clip the input, which spoils the "
             "timing; keep ears and headphones away.", out)

    card = None
    if args.fake:
        if args.mixer or args.set:
            print("The fake device has no mixer.", file=out)
            return 2
        device = make_fake(args)
    else:
        testing = args.offset_test or args.schedule_test
        if args.mixer or args.set or testing:
            try:
                card = discovery.find_card(discovery.list_cards(), args.device)
            except LookupError as error:
                print(error, file=out)
                return 2
            if not card.usb and (args.mixer or args.set):
                warn_not_usb(card, out, borrowing=bool(
                    testing and not args.no_borrow))
                args.warned_not_usb = True
            # Before anything touches the card, mixer settings included: the
            # desktop's sound server watches the mixer and follows it.
            if testing and not args.keep_mixer:
                if not args.no_borrow:
                    save_desktop(card, args, session, out)
                try:
                    session.restores.append((card, mixer.snapshot(card.number)))
                    print("Mixer settings saved; they are put back after the "
                          "test (--keep-mixer leaves them).", file=out)
                except mixer.MixerError as error:
                    warn(f"Could not save the mixer settings, so they will "
                         f"not be put back: {error}", out)
            code = 0
            try:
                if args.mixer or not (args.set or testing):
                    print_mixer(card, out)
                if args.set:
                    code = do_set(card, args.set, out)
                    print_mixer(card, out) if args.mixer else None
            except mixer.MixerError as error:
                print(error, file=out)
                return 1
            if not testing:
                return code
            # Our own settings are made; from here on a change is not ours.
            start_watching(card, session, out)
        device, card = make_real(args, out, session.holds)
        if device is None:
            return card
    if not (args.offset_test or args.schedule_test):
        return 0

    print_plan(args, device, card, out)
    if not args.fake and not args.no_wait:
        print("Starting in 3 s; Ctrl-C to stop.", file=out)
        out.flush()
        time.sleep(3)

    stopped = []
    signal.signal(signal.SIGINT, lambda *a: stopped.append(True))
    label = card.id if card else "fake"
    exit_code = 0
    try:
        device.start()
    except DeviceError as error:
        print(f"\nCannot open the device: {error}", file=out)
        print("hw: devices are exclusive. If another program holds the card "
              "(the desktop's sound server refused to give it up, or "
              "--no-borrow), close that program.", file=out)
        return 1
    try:
        tests = []
        if args.offset_test:
            tests.append(lambda: checks.run_offset_test(
                device, args.minutes * 60, args.level, args.channel,
                args.interval, args.ping, _progress(out), lambda: bool(stopped),
                design=design))
        if args.schedule_test:
            tests.append(lambda: checks.run_schedule_test(
                device, args.tat, args.pulses, args.level, args.channel,
                args.ping, _progress(out), lambda: bool(stopped), design=design))
        for run in tests:
            result = run()
            print("", file=out)
            attach_mixer_changes(result, session)
            folder = checks.save(result, args.runs, label)
            print(f"{result.kind.capitalize()} test: ", file=out)
            for line in result.verdict:
                print("  " + line, file=out)
            print(f"  Saved in {folder}", file=out)
            if not result.summary["verdict_ok"]:
                exit_code = 1
            if stopped:
                print("Stopped early.", file=out)
                break
    except DeviceError as error:
        print(f"\nThe stream failed: {error}", file=out)
        exit_code = 1
    finally:
        device.stop()
    return exit_code


def attach_mixer_changes(result, session):
    """Put what changed the mixer so far into a test's verdict and summary."""
    for card, watcher in session.watchers:
        changes = [c.text() for c in watcher.seen()]
        result.summary["mixer_changes"] = changes
        if changes:
            result.verdict.append("Something changed the mixer during the test: "
                                  + "; ".join(changes))


def _progress(out):
    last = [0.0]

    def show(done, total):
        now = time.monotonic()
        if now - last[0] > 5 or done == total:
            last[0] = now
            print(f"  ... {done}/{total}", file=out)
            out.flush()
    return show


if __name__ == "__main__":
    sys.exit(main())
