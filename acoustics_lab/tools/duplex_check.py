#!/usr/bin/env python3
"""Check a USB sound dongle for the acoustics lab: list, mixer, timing.

    duplex_check.py --list
    duplex_check.py --device donglea --mixer
    duplex_check.py --device donglea --mixer --set 'Speaker Playback Volume=60%'
    duplex_check.py --device 1-2.3 --offset-test --minutes 5 --level -20 --channel left
    duplex_check.py --device donglea --schedule-test --tat 0.2
    duplex_check.py --fake --offset-test --minutes 5      # no hardware

A device is only ever opened when it is named with --device (card number,
ALSA card id or USB port path) together with a test. A card that is not on
USB (the built-in sound, HDMI) gets a prominent warning, since the desktop
uses it. The output level defaults to -20 dBFS; above -6 dBFS gets a
prominent warning, and above 0 dBFS is played clipped at full scale, with a
warning, to show what clipping does. The plan, including how loud, is printed before anything
is played.

Results go to <acoustics_lab>/runs/hardware/<date time>_<device>_<test>/
(a CSV of every ping and summary.json), git-ignored.
"""
import argparse
import os
import signal
import sys
import time

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.dirname(HERE)
sys.path.insert(0, ROOT)

from acoustics_lab.hardware import checks, discovery, mixer      # noqa: E402
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
    p.add_argument("--no-wait", action="store_true",
                   help="skip the 3 s pause after printing the plan")
    return p.parse_args(argv)


# -- listing and mixer --------------------------------------------------------

def warn(text, out):
    """A warning that stands out from the rest of the output."""
    bar = "!" * 72
    print(bar, file=out)
    print("WARNING: " + text, file=out)
    print(bar, file=out)


def warn_not_usb(card, out):
    warn(f"{card.label()} is not a USB card. It is the desktop's (built-in "
         "sound or HDMI): opening it may fail as busy, or stop the desktop's "
         "sound on it while the test runs, and test signals go to its "
         "speakers or screen.", out)


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


def make_real(args, out):
    """The PortAudioDuplex for the named card, after the safety checks.
    Returns (device, card) or (None, code)."""
    cards = discovery.list_cards()
    try:
        card = discovery.find_card(cards, args.device)
    except LookupError as error:
        print(error, file=out)
        return None, 2
    if not card.usb:
        warn_not_usb(card, out)
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

def main(argv=None, out=None):
    args = parse_args(argv)
    out = out or sys.stdout
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
        if args.mixer or args.set:
            try:
                card = discovery.find_card(discovery.list_cards(), args.device)
            except LookupError as error:
                print(error, file=out)
                return 2
            if not card.usb:
                warn_not_usb(card, out)
            code = 0
            try:
                if args.mixer or not args.set:
                    print_mixer(card, out)
                if args.set:
                    code = do_set(card, args.set, out)
                    print_mixer(card, out) if args.mixer else None
            except mixer.MixerError as error:
                print(error, file=out)
                return 1
            if not (args.offset_test or args.schedule_test):
                return code
        device, card = make_real(args, out)
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
        print("If another program (the desktop's sound server) holds it, "
              "close that program; hw: devices are exclusive.", file=out)
        return 1
    try:
        tests = []
        if args.offset_test:
            tests.append(lambda: checks.run_offset_test(
                device, args.minutes * 60, args.level, args.channel,
                args.interval, args.ping, _progress(out), lambda: bool(stopped)))
        if args.schedule_test:
            tests.append(lambda: checks.run_schedule_test(
                device, args.tat, args.pulses, args.level, args.channel,
                args.ping, _progress(out), lambda: bool(stopped)))
        for run in tests:
            result = run()
            print("", file=out)
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
