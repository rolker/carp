#!/usr/bin/env python3
"""Plots for the acoustic ranging recordings saved by loopback_test.py.

One file: the waveform, the matched-filter output with each arrival marked,
and the spectrum (where the disc actually responds).

Several files or a folder: the pings side by side, lined up on the loopback
arrival, and each arrival's delay from ping to ping. A steady path is a
straight line, a reflection is a second line, timing jitter is wobble.

Usage:
  plot_runs.py runs/run1.wav
  plot_runs.py runs/series1/                 # every .wav in the folder
  plot_runs.py runs/series1/ --out series1.png  # save the figure, open no window

Chirp settings come from the .json beside each recording; --f0, --f1 and
--duration override them. Needs python3-matplotlib.
"""
import argparse
import glob
import os
import sys

import numpy as np

import ranging_dsp as dsp
import wav_io


def parse_args():
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("paths", nargs="+", help="WAV files, or a folder of them")
    p.add_argument("--out", metavar="FILE", help="save the figure here")
    p.add_argument("--f0", type=float, help="chirp start, Hz")
    p.add_argument("--f1", type=float, help="chirp end, Hz")
    p.add_argument("--duration", type=float, help="chirp length, s")
    p.add_argument("--span", type=float, default=15.0,
                   help="time shown after the loopback arrival, ms")
    p.add_argument("--floor", type=float, default=-50.0,
                   help="lowest level shown, dB below the loopback arrival")
    p.add_argument("--threshold", type=float, default=0.1,
                   help="smallest arrival to mark, as a fraction of the largest")
    p.add_argument("--sound-speed", type=float,
                   help="speed of sound, m/s (default: from the .json, or air at 20 C)")
    return p.parse_args()


def expand(paths):
    files = []
    for path in paths:
        if os.path.isdir(path):
            files += sorted(glob.glob(os.path.join(path, "*.wav")))
        else:
            files.append(path)
    return files


class Run:
    """One recording, matched-filtered, with its arrivals."""

    def __init__(self, path, args):
        self.path = path
        self.recording, self.rate = wav_io.read_wav(path)
        meta = wav_io.read_meta(path)
        self.f0 = args.f0 or meta.get("f0", 2000.0)
        self.f1 = args.f1 or meta.get("f1", 20000.0)
        self.duration = args.duration or meta.get("duration", 0.02)
        self.speed = (args.sound_speed or meta.get("sound_speed")
                      or dsp.sound_speed_air())
        chirp = dsp.make_chirp(self.rate, self.f0, self.f1, self.duration)
        self.envelope = dsp.matched_filter(self.recording, chirp)
        self.arrivals = dsp.find_arrivals(self.envelope, self.rate,
                                          args.threshold)

    @property
    def first(self):
        return self.arrivals[0]

    def delays_ms(self):
        return [(a.sample - self.first.sample) / self.rate * 1e3
                for a in self.arrivals]

    def levels_db(self):
        return [20 * np.log10(a.level / self.first.level)
                for a in self.arrivals]

    def envelope_db(self):
        return 20 * np.log10(np.maximum(self.envelope, 1e-12)
                             / self.first.level)


def add_distance_axis(ax, speed, vertical=False):
    """Second axis: path length in metres for a time axis in ms."""
    to_m, to_ms = (lambda t: t * speed / 1e3), (lambda d: d / speed * 1e3)
    if vertical:
        ax.secondary_yaxis("right", functions=(to_m, to_ms)).set_ylabel(
            "path length (m)")
    else:
        ax.secondary_xaxis("top", functions=(to_m, to_ms)).set_xlabel(
            "path length (m)")


def plot_single(run, args, plt):
    fig, (wave_ax, match_ax, spec_ax) = plt.subplots(
        3, 1, figsize=(10, 9), constrained_layout=True)
    fig.suptitle(os.path.basename(run.path))

    t = np.arange(run.recording.size) / run.rate * 1e3
    wave_ax.plot(t, run.recording, linewidth=0.6)
    wave_ax.set(xlabel="time in recording (ms)", ylabel="amplitude (full scale = 1)",
                title="Recording")
    wave_ax.grid(alpha=0.3)

    t0 = run.first.sample / run.rate * 1e3
    t = np.arange(run.envelope.size) / run.rate * 1e3 - t0
    match_ax.plot(t, run.envelope_db(), linewidth=0.8)
    for i, (delay, level) in enumerate(zip(run.delays_ms(), run.levels_db())):
        match_ax.axvline(delay, color="C1", linewidth=0.8, alpha=0.7)
        match_ax.annotate(
            "loopback" if i == 0 else
            f"{delay:.3f} ms\n{delay * run.speed / 1e3:.3f} m",
            (delay, level), textcoords="offset points", xytext=(4, 6),
            fontsize=8)
    match_ax.set(xlim=(-1.0, args.span), ylim=(args.floor, 8),
                 xlabel="time after the loopback arrival (ms)",
                 ylabel="level (dB re loopback)", title="Matched filter")
    match_ax.grid(alpha=0.3)
    add_distance_axis(match_ax, run.speed)

    window = np.hanning(run.recording.size)
    spectrum = np.abs(np.fft.rfft(run.recording * window))
    freqs = np.fft.rfftfreq(run.recording.size, 1.0 / run.rate) / 1e3
    spec_db = 20 * np.log10(np.maximum(spectrum, 1e-12) / spectrum.max())
    spec_ax.plot(freqs, spec_db, linewidth=0.6)
    spec_ax.axvspan(run.f0 / 1e3, run.f1 / 1e3, color="C1", alpha=0.12,
                    label="chirp band")
    spec_ax.set(xlim=(0, run.rate / 2e3), ylim=(-90, 3),
                xlabel="frequency (kHz)", ylabel="level (dB re peak)",
                title="Spectrum of the whole recording")
    spec_ax.grid(alpha=0.3)
    spec_ax.legend(loc="upper right")
    return fig


def plot_stack(runs, args, plt):
    rate, speed = runs[0].rate, runs[0].speed
    before, after = int(0.001 * rate), int(args.span / 1e3 * rate)
    image = np.full((before + after, len(runs)), args.floor)
    for column, run in enumerate(runs):
        start = int(round(run.first.sample)) - before
        db = run.envelope_db()
        lo, hi = max(start, 0), min(start + before + after, db.size)
        image[lo - start:hi - start, column] = db[lo:hi]

    fig, (stack_ax, delay_ax) = plt.subplots(
        2, 1, figsize=(10, 9), constrained_layout=True, sharex=True)
    folder = os.path.basename(os.path.dirname(os.path.abspath(runs[0].path)))
    fig.suptitle(f"{len(runs)} pings, {folder}/")

    shown = stack_ax.imshow(
        image, aspect="auto", cmap="viridis", vmin=args.floor, vmax=0,
        extent=(0.5, len(runs) + 0.5, args.span, -1.0),
        interpolation="nearest")
    fig.colorbar(shown, ax=[stack_ax, delay_ax], label="level (dB re loopback)",
                 pad=0.09)
    stack_ax.set(ylabel="time after the loopback arrival (ms)",
                 title="Matched filter, pings side by side")
    add_distance_axis(stack_ax, speed, vertical=True)

    for number, run in enumerate(runs, start=1):
        delays, levels = run.delays_ms()[1:], run.levels_db()[1:]
        delay_ax.scatter([number] * len(delays), delays, c=levels,
                         cmap="viridis", vmin=args.floor, vmax=0, s=14)
    delay_ax.set(xlabel="ping number", ylabel="delay after loopback (ms)",
                 ylim=(args.span, -1.0), title="Detected arrivals")
    delay_ax.grid(alpha=0.3)
    add_distance_axis(delay_ax, speed, vertical=True)
    return fig


def print_spread(runs):
    """How steady is the strongest arrival after the loopback, ping to ping?"""
    delays = []
    for run in runs:
        later = list(zip(run.levels_db()[1:], run.delays_ms()[1:]))
        if later:
            delays.append(max(later)[1])
    if len(delays) < 2:
        return
    delays = np.array(delays)
    speed = runs[0].speed
    print(f"Strongest arrival after the loopback, over {delays.size} pings: "
          f"mean {delays.mean():.3f} ms ({delays.mean() * speed / 1e3:.3f} m), "
          f"spread {delays.std() * 1e3:.1f} us "
          f"({delays.std() * speed:.1f} mm) standard deviation")


def main():
    args = parse_args()
    files = expand(args.paths)
    if not files:
        print("No WAV files found.")
        return 1
    import matplotlib
    if args.out:
        matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    runs = []
    for path in files:
        run = Run(path, args)
        if run.arrivals:
            runs.append(run)
        else:
            print(f"{path}: no chirp found, skipped")
    if not runs:
        return 1
    if len(runs) == 1:
        fig = plot_single(runs[0], args, plt)
    else:
        if len({run.rate for run in runs}) > 1:
            print("The recordings have different sample rates; plot them "
                  "separately.")
            return 1
        fig = plot_stack(runs, args, plt)
        print_spread(runs)
    if args.out:
        fig.savefig(args.out, dpi=110)
        print(f"Saved {args.out}")
    else:
        plt.show()
    return 0


if __name__ == "__main__":
    sys.exit(main())
