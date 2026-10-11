#!/usr/bin/env python3
"""Stage 1 of the acoustic bench test: time of flight on one sound device.

Plays a chirp on one output channel while recording the mic input. With a
small copy of the transmit signal fed into the mic input through a resistor
(the loopback), the recording holds the chirp twice: once at the instant it
was sent, and again when it arrives through the air. The gap between them is
the time of flight, whatever the audio buffering did.

Usage:
  loopback_test.py --list
  loopback_test.py --input-device 2 --output-device 2 --save runs/run1.wav
  loopback_test.py --wav runs/run1.wav
  loopback_test.py --simulate 1.5
  loopback_test.py --input-device 2 --output-device 2 --count 50 --save runs/series1/p.wav

Needs python3-numpy and python3-scipy, plus python3-pyaudio for live audio.
See docs/navigation.md, Method 4.
"""
import argparse
import datetime
import os
import sys
import time

import numpy as np

import ranging_dsp as dsp
import wav_io


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    mode = p.add_mutually_exclusive_group()
    mode.add_argument("--list", action="store_true",
                      help="list audio devices and supported sample rates")
    mode.add_argument("--wav", metavar="FILE",
                      help="analyse a saved recording instead of the sound card")
    mode.add_argument("--simulate", metavar="METRES", type=float,
                      help="analyse a made-up recording with one echo at this distance")
    p.add_argument("--input-device", type=int, help="device index from --list")
    p.add_argument("--output-device", type=int, help="device index from --list")
    p.add_argument("--rate", type=int, default=48000, help="sample rate, Hz")
    p.add_argument("--f0", type=float, help="chirp start, Hz (default 2000)")
    p.add_argument("--f1", type=float, help="chirp end, Hz (default 20000)")
    p.add_argument("--duration", type=float,
                   help="chirp length, s (default 0.02)")
    p.add_argument("--count", type=int, default=1,
                   help="number of pings; with --save, files get _0001, _0002...")
    p.add_argument("--interval", type=float, default=0.5,
                   help="pause between pings, s")
    p.add_argument("--amplitude", type=float, default=0.5,
                   help="output level, 0 to 1")
    p.add_argument("--channel", choices=("left", "right", "both"),
                   default="left", help="output channel that carries the chirp")
    p.add_argument("--listen", type=float, default=0.3,
                   help="recording time after the chirp, s")
    p.add_argument("--threshold", type=float, default=0.1,
                   help="smallest arrival to report, as a fraction of the largest")
    p.add_argument("--temperature", type=float, default=20.0,
                   help="air temperature for the speed of sound, C")
    p.add_argument("--sound-speed", type=float,
                   help="speed of sound, m/s (overrides --temperature)")
    p.add_argument("--save", metavar="FILE", help="save the recording as WAV")
    return p.parse_args()


def print_devices():
    import audio_io
    devices = audio_io.list_devices()
    if not devices:
        print("No audio devices found. On WSL, ALSA has no sound card until "
              "it is pointed at the\nWindows sound bridge - see README.md.")
        return
    print("idx  in out  input rates / output rates           name")
    for d in devices:
        rates = "{} / {}".format(
            ",".join(str(r // 1000) + "k" for r in d["input_rates"]) or "-",
            ",".join(str(r // 1000) + "k" for r in d["output_rates"]) or "-")
        print(f"{d['index']:3d}  {d['inputs']:2d} {d['outputs']:3d}  "
              f"{rates:37s} {d['name']} [{d['api']}]")
    print('Only "hw:" devices show what the hardware supports; "default" and '
          '"pulse" convert.')


def record_live(args, chirp):
    import audio_io
    # Inputs thump when they switch on (the WSL bridge swung to full scale
    # for ~30 ms), and a thump is broadband enough to pass for a chirp. Hold
    # the chirp back and drop the start of the recording.
    settle = int(0.15 * args.rate)
    lead_in = int(0.4 * args.rate)
    total = lead_in + chirp.size + int(args.listen * args.rate)
    playback = np.zeros((total, 2), dtype=np.float32)
    columns = {"left": [0], "right": [1], "both": [0, 1]}[args.channel]
    for column in columns:
        playback[lead_in:lead_in + chirp.size, column] = args.amplitude * chirp
    recording, warnings = audio_io.play_and_record(
        playback, args.rate, args.input_device, args.output_device)
    for warning in warnings:
        print(f"WARNING: {warning} - this run's timing is suspect")
    return recording[settle:]


def report(recording, chirp, args, speed):
    peak = float(np.max(np.abs(recording))) if recording.size else 0.0
    print(f"Recording: {recording.size / args.rate:.3f} s, peak "
          f"{20 * np.log10(max(peak, 1e-6)):.1f} dBFS"
          + ("  ** clipped - lower the level **" if peak > 0.98 else ""))
    if recording.size < chirp.size:
        print("Recording is shorter than the chirp; nothing to analyse.")
        return 1
    if peak < 10 ** (-70 / 20):
        print("The recording is silent: the input is muted, unplugged or "
              "not allowed to record.")
        return 1
    envelope = dsp.matched_filter(recording, chirp)
    arrivals = dsp.find_arrivals(envelope, args.rate, args.threshold)
    # A real chirp towers over the rest of the matched-filter output; noise
    # alone gives peaks only a few times its own typical level.
    if not arrivals or envelope.max() < 8 * np.median(envelope):
        print("No chirp stands out from the noise in the recording.")
        return 1
    first, top = arrivals[0], max(a.level for a in arrivals)
    print(f"Speed of sound {speed:.1f} m/s. First arrival is taken as the "
          f"loopback copy.")
    merge = dsp.resolution(args.f0, args.f1)
    print(f"Arrivals closer than about {merge * 1e3:.2f} ms "
          f"({merge * speed:.2f} m) merge at this bandwidth.")
    print("  #   after first    path length   level")
    for i, a in enumerate(arrivals):
        delay = (a.sample - first.sample) / args.rate
        print(f"  {i}  {delay * 1e3:9.3f} ms  {delay * speed:9.3f} m   "
              f"{20 * np.log10(a.level / top):6.1f} dB")
    if len(arrivals) == 1:
        print("Only one arrival: either the loopback or the acoustic path is "
              "missing. Try a lower --threshold.")
    return 0


def main():
    args = parse_args()
    if args.list:
        print_devices()
        return 0
    speed = args.sound_speed or dsp.sound_speed_air(args.temperature)
    meta = {}
    if args.wav:
        recording, args.rate = wav_io.read_wav(args.wav)
        meta = wav_io.read_meta(args.wav)
    # Chirp settings: the command line wins, then the saved file's, then defaults.
    for name, default in (("f0", 2000.0), ("f1", 20000.0), ("duration", 0.02)):
        if getattr(args, name) is None:
            setattr(args, name, meta.get(name, default))
    chirp = dsp.make_chirp(args.rate, args.f0, args.f1, args.duration)
    result = 0
    for ping in range(args.count):
        if args.simulate is not None:
            recording = dsp.simulate_recording(
                chirp, args.rate, [0.0, args.simulate / speed], [0.2, 0.05],
                seed=ping)
        elif not args.wav:
            recording = record_live(args, chirp)
        if args.save:
            path = args.save
            if args.count > 1:
                stem, ext = os.path.splitext(args.save)
                path = f"{stem}_{ping + 1:04d}{ext}"
            os.makedirs(os.path.dirname(path) or ".", exist_ok=True)
            wav_io.write_wav(path, recording, args.rate)
            wav_io.write_meta(path, dict(
                time=datetime.datetime.now().astimezone().isoformat(),
                rate=args.rate, f0=args.f0, f1=args.f1, duration=args.duration,
                amplitude=args.amplitude, channel=args.channel,
                sound_speed=speed, simulated=args.simulate is not None))
            print(f"Saved {path}")
        result |= report(recording, chirp, args, speed)
        if ping + 1 < args.count:
            time.sleep(args.interval)
    return result


if __name__ == "__main__":
    sys.exit(main())
