#!/usr/bin/env python3
"""Ping designer and display for the acoustic ranging tests.

Left side: a list of signals (chirps) to edit, and the ping design: which
signal goes out on which output channel, and when. Right side: what came
back from the latest ping, one trace and one table row per event.

Press Ping for one ping, or tick Continuous to keep going. Optional views:
the raw recording with its spectrum, and an echogram (one column per ping,
time running down, like an echosounder). The dividers between the panels
drag, and the toolbar under the plots zooms and pans; a zoom on the top
plot is kept from ping to ping until Reset zoom.

The tabs at the bottom left are three more tools. Sweep steps short narrow
chirps through a range and charts how strongly each band comes back, to
pick a band for a given speaker, room and microphone. Noise records with
nothing playing and charts the background. Data sends a short text as
LoRa-style chirps and shows what was decoded.

Time zero on every plot is the first arrival of the loudest event, moved
back to the start of the ping. With the loopback wired in, that is when the
ping was sent; without it (a mic listening to speakers) it is the first
direct sound, and later arrivals are reflections.

Usage:
  ping_gui.py                       # default sound devices
  ping_gui.py --simulate            # no sound card: made-up echoes
  ping_gui.py --design designs/tv.json

Needs python3-tk and python3-matplotlib, plus python3-pyaudio for live audio.
"""
import argparse
import copy
import datetime
import json
import os
import queue
import sys
import threading
from dataclasses import asdict

import numpy as np

import chirp_data
import pinger
import ranging_dsp as dsp
import wav_io

HERE = os.path.dirname(os.path.abspath(__file__))
RATES = (44100, 48000, 96000, 192000)
DEFAULT_DEVICE = "System default"
MAX_ECHOGRAMS = 4


class PingDisplay:
    """The plots, on a matplotlib figure. Knows nothing about the window."""

    def __init__(self, figure, span_ms=40.0, before_ms=2.0, floor_db=-40.0,
                 history=200):
        self.figure = figure
        self.span_ms, self.before_ms = span_ms, before_ms
        self.floor_db, self.history = floor_db, history
        self.show_recording = False
        self.show_echogram = False
        self.show_sweep = False
        self.sweep = None       # dict(channels={name: bands}, suggestion=(f0, f1))
        self.show_noise = False
        self.noise = None       # dict(recording=..., rate=...)
        self.show_data = False
        self.data = None        # dict(result=DataResult, config=DataConfig, sent=bytes)
        self.trace_ax = None
        self.default_limits = None
        self.clear()

    def reset_zoom(self):
        self.trace_ax = None
        self.redraw()

    def _zoom(self):
        """The top plot's limits, if the user has zoomed or panned it."""
        if self.trace_ax is None:
            return None
        now = (self.trace_ax.get_xlim(), self.trace_ax.get_ylim())
        return None if np.allclose(now, self.default_limits) else now

    def clear(self):
        self.trace_ax = None
        self.result = None
        self.count = 0
        self.columns = []       # per ping: one column (or None) per event
        self.redraw()

    def add(self, result):
        """Take one more ping. Pings with nothing detected leave a gap."""
        self.count += 1
        events = len(result.design.events)
        if self.columns and len(self.columns[-1]) != events:
            self.columns = []   # the design changed shape: start the echogram again
        if result.detected():
            column = [result.trace_db(i, self.before_ms, self.span_ms,
                                      self.floor_db) for i in range(events)]
        else:
            column = [None] * events
        self.columns = (self.columns + [column])[-self.history:]
        self.result = result
        self.redraw()

    def _distance_axis(self, ax, speed, vertical):
        to_m, to_ms = (lambda t: t * speed / 1e3), (lambda d: d / speed * 1e3)
        if vertical:
            ax.secondary_yaxis("right", functions=(to_m, to_ms)).set_ylabel("m")
        else:
            ax.secondary_xaxis("top", functions=(to_m, to_ms)).set_xlabel(
                "path length (m)")

    def redraw(self):
        figure, result = self.figure, self.result
        zoom = self._zoom()
        figure.clear()
        events = len(self.columns[-1]) if self.columns else 0
        grams = min(events, MAX_ECHOGRAMS) if self.show_echogram else 0
        sweeping = self.show_sweep and self.sweep is not None
        noisy = self.show_noise and self.noise is not None
        talking = self.show_data and self.data is not None
        heights = [1.0] + [1.0] * (sweeping + noisy + talking) + (
            [0.7] if self.show_recording else []) + ([1.2] if grams else [])
        grid = figure.add_gridspec(len(heights), 1, height_ratios=heights)
        speed = result.setup.sound_speed if result else pinger.Setup().sound_speed

        ax = figure.add_subplot(grid[0])
        ax.set(xlim=(-self.before_ms, self.span_ms), ylim=(self.floor_db, 5),
               xlabel="time after the first arrival (ms)", ylabel="level (dB)")
        ax.grid(alpha=0.3)
        self.trace_ax = ax
        self.default_limits = (ax.get_xlim(), ax.get_ylim())
        if zoom:                # a zoom survives the next ping
            ax.set(xlim=zoom[0], ylim=zoom[1])
        self._distance_axis(ax, speed, vertical=False)
        if result is None:
            ax.set_title("No ping yet", fontsize=10)
        elif not result.detected():
            ax.set_title(f"Ping {self.count}: nothing detected "
                         f"({'; '.join(result.warnings)})", fontsize=10)
        else:
            ax.set_title(f"Ping {self.count}: matched filter, one trace per "
                         f"event", fontsize=10)
            for i, column in enumerate(self.columns[-1]):
                t = np.linspace(-self.before_ms, self.span_ms, column.size,
                                endpoint=False)
                heard = result.events[i] is not None
                ax.plot(t, column, color=f"C{i % 10}", linewidth=0.8,
                        alpha=1.0 if heard else 0.35,
                        label=result.design.label(i)
                        + ("" if heard else " (not heard)"))
                if heard:
                    ax.axvline(result.delay_ms(i), color=f"C{i % 10}",
                               alpha=0.6, linestyle="--", linewidth=0.8)
            ax.legend(loc="upper right", fontsize=8)

        row = 1
        if sweeping:
            self._draw_sweep(figure.add_subplot(grid[row]))
            row += 1
        if noisy:
            sub = grid[row].subgridspec(1, 2, width_ratios=[1.3, 1])
            self._draw_noise(figure.add_subplot(sub[0]), figure.add_subplot(sub[1]))
            row += 1
        if talking:
            sub = grid[row].subgridspec(1, 2, width_ratios=[1.6, 1])
            self._draw_data(figure.add_subplot(sub[0]), figure.add_subplot(sub[1]))
            row += 1
        if self.show_recording:
            sub = grid[row].subgridspec(1, 2, width_ratios=[1.6, 1])
            wave_ax, spec_ax = figure.add_subplot(sub[0]), figure.add_subplot(sub[1])
            wave_ax.set(xlabel="time in recording (ms)", ylabel="amplitude",
                        title="Recording")
            spec_ax.set(xlabel="frequency (kHz)", ylabel="dB re peak",
                        title="Spectrum")
            for a in (wave_ax, spec_ax):
                a.title.set_fontsize(10)
                a.grid(alpha=0.3)
            if result is not None and result.recording.size:
                rec, rate = result.recording, result.setup.rate
                wave_ax.plot(np.arange(rec.size) / rate * 1e3, rec, linewidth=0.5)
                spectrum = np.abs(np.fft.rfft(rec * np.hanning(rec.size)))
                spec_ax.plot(np.fft.rfftfreq(rec.size, 1.0 / rate) / 1e3,
                             20 * np.log10(np.maximum(spectrum, 1e-12)
                                           / max(spectrum.max(), 1e-12)),
                             linewidth=0.5)
                spec_ax.set(xlim=(0, rate / 2e3), ylim=(-90, 3))
            row += 1

        if grams:
            sub = grid[row].subgridspec(1, grams)
            first = self.count - len(self.columns) + 1
            for i in range(grams):
                gram_ax = figure.add_subplot(sub[i])
                columns = [c[i] for c in self.columns]
                rows = max((c.size for c in columns if c is not None), default=0)
                label = result.design.label(i) if result else f"event {i + 1}"
                gram_ax.set_title(label, fontsize=9)
                gram_ax.set(xlabel="ping number", ylabel="ms" if i == 0 else "")
                if rows:
                    image = np.full((rows, len(columns)), self.floor_db)
                    for n, c in enumerate(columns):
                        if c is not None and c.size == rows:
                            image[:, n] = c
                    gram_ax.imshow(
                        image, aspect="auto", cmap="viridis",
                        vmin=self.floor_db, vmax=0, interpolation="nearest",
                        extent=(first - 0.5, self.count + 0.5, self.span_ms,
                                -self.before_ms))
                self._distance_axis(gram_ax, speed, vertical=True)


    def _draw_sweep(self, ax):
        channels, suggestion = self.sweep["channels"], self.sweep["suggestion"]
        for i, (name, (centre, level, floor, heard)) in enumerate(
                _sweep_levels(channels).items()):
            colour = f"C{i}"
            ax.plot(centre, level, color=colour, linewidth=1.0, label=name)
            ax.plot(centre[heard], level[heard], "o", color=colour, markersize=4)
            ax.plot(centre[~heard], level[~heard], "o", color=colour,
                    markersize=4, markerfacecolor="white")
            ax.plot(centre, floor, color=colour, linewidth=0.8, linestyle=":",
                    label=f"{name} noise floor")
        if suggestion:
            ax.axvspan(suggestion[0] / 1e3, suggestion[1] / 1e3, color="C2",
                       alpha=0.15, label="suggested band")
            title = (f"Frequency sweep: suggested band {suggestion[0] / 1e3:g}"
                     f" to {suggestion[1] / 1e3:g} kHz")
        else:
            title = "Frequency sweep: no band stands out on every channel"
        ax.set(xlabel="frequency (kHz)", ylabel="level (dB re best band)",
               ylim=(-70, 5))
        ax.set_title(title + "   (hollow = not heard)", fontsize=10)
        ax.grid(alpha=0.3)
        ax.legend(loc="lower center", fontsize=8, ncol=5)


    def _draw_noise(self, spectrum_ax, gram_ax):
        recording, rate = self.noise["recording"], self.noise["rate"]
        freqs, db = dsp.noise_spectrum(recording, rate)
        spectrum_ax.plot(freqs / 1e3, db, linewidth=0.7, label="per Hz")
        bands = dsp.band_levels(recording, rate)
        spectrum_ax.step([b["f0"] / 1e3 for b in bands] + [bands[-1]["f1"] / 1e3],
                         [b["level_db"] for b in bands] + [bands[-1]["level_db"]],
                         where="post", color="C1", linewidth=1.0,
                         label="per 1 kHz band")
        spectrum_ax.set(xlabel="frequency (kHz)", ylabel="dB re full scale",
                        xlim=(0, rate / 2e3))
        spectrum_ax.set_title("Background noise: typical level", fontsize=10)
        spectrum_ax.grid(alpha=0.3)
        spectrum_ax.legend(loc="upper right", fontsize=8)
        from scipy import signal
        f, t, power = signal.spectrogram(recording, rate, nperseg=512, noverlap=256)
        image = 10 * np.log10(power + 1e-20)
        top = np.percentile(image, 99.5)
        gram_ax.imshow(image, aspect="auto", origin="lower", cmap="viridis",
                       vmin=top - 60, vmax=top,
                       extent=(t[0], t[-1], f[0] / 1e3, f[-1] / 1e3))
        gram_ax.set(xlabel="time (s)", ylabel="kHz")
        gram_ax.set_title("Over time (bright = loud)", fontsize=10)

    def _draw_data(self, tone_ax, snr_ax):
        result, config = self.data["result"], self.data["config"]
        if result.tones is None:
            tone_ax.set_title(f"Data: {result.message}", fontsize=10)
            tone_ax.axis("off")
            snr_ax.axis("off")
            return
        image = 10 * np.log10(result.tones / result.tones.max() + 1e-12)
        tone_ax.imshow(image.T, aspect="auto", origin="lower", cmap="viridis",
                       vmin=-30, vmax=0, interpolation="nearest",
                       extent=(0.5, image.shape[0] + 0.5, 0, config.steps))
        tone_ax.plot(np.arange(1, len(result.picked) + 1),
                     np.array(result.picked) + 0.5, "r.", markersize=4)
        tone_ax.set(xlabel="symbol number", ylabel="tone (start step)")
        tone_ax.set_title("Data symbols: one column each, red = tone chosen",
                          fontsize=10)
        snr_ax.bar(np.arange(1, len(result.symbol_snr) + 1), result.symbol_snr,
                   color="C0" if result.ok else "C3")
        snr_ax.set(xlabel="symbol number", ylabel="dB above the other tones")
        snr_ax.set_title("Symbol strength", fontsize=10)
        snr_ax.grid(alpha=0.3)


def _sweep_levels(channels):
    """Per channel: band centres in kHz, level and noise floor in dB below
    the strongest band of any channel, and which bands were heard."""
    top = max((b["peak"] for bands in channels.values() for b in bands),
              default=0.0) or 1e-12
    out = {}
    for name, bands in channels.items():
        centre = np.array([(b["f0"] + b["f1"]) / 2e3 for b in bands])
        level = np.array([20 * np.log10(max(b["peak"], 1e-12) / top)
                          for b in bands])
        floor = level - np.array([20 * np.log10(max(b["snr"], 1e-12))
                                  for b in bands])
        out[name] = (centre, level, floor,
                     np.array([b["heard"] for b in bands]))
    return out


def number(text, what):
    """float(text), with an error a person can act on."""
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{what} must be a number, not '{text.strip()}'") from None


def save_ping(folder, number, result):
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, f"p_{number:04d}.wav")
    wav_io.write_wav(path, result.recording, result.setup.rate)
    wav_io.write_meta(path, dict(
        time=datetime.datetime.now().astimezone().isoformat(),
        setup=asdict(result.setup), design=asdict(result.design),
        results=pinger.rows(result), warnings=result.warnings))
    return path


class App:
    def __init__(self, root, args):
        import tkinter as tk
        from tkinter import ttk
        from matplotlib.backends.backend_tkagg import (FigureCanvasTkAgg,
                                                       NavigationToolbar2Tk)
        from matplotlib.figure import Figure
        self.tk, self.ttk = tk, ttk
        self.root, self.args = root, args
        self.design = pinger.default_design()
        if args.design:
            with open(args.design) as f:
                self.design = pinger.Design.from_dict(json.load(f))
        self.results = queue.Queue()
        self.busy = False
        self.sent = 0
        self.folder = None
        self.devices = {}
        self.choices = {"input": {DEFAULT_DEVICE: None},
                        "output": {DEFAULT_DEVICE: None}}

        root.title("CARP acoustic ping" + (" (simulated)" if args.simulate else ""))
        self.status = tk.StringVar(value="Ready.")
        self._build_top_bar()
        self._build_device_bar()
        ttk.Label(root, textvariable=self.status, anchor="w", padding=4).pack(
            side="bottom", fill="x")
        # Every divider can be dragged: side panel | results over plots, and
        # signals over ping design within the side panel.
        body = ttk.PanedWindow(root, orient="horizontal")
        body.pack(side="top", fill="both", expand=True)
        side = ttk.PanedWindow(body, orient="vertical")
        body.add(side, weight=0)
        side.add(self._build_signals(side), weight=1)
        side.add(self._build_events(side), weight=2)
        tools = ttk.Notebook(side)
        tools.add(self._build_sweep(tools), text="Sweep")
        tools.add(self._build_noise(tools), text="Noise")
        tools.add(self._build_data(tools), text="Data")
        side.add(tools, weight=0)
        right = ttk.PanedWindow(body, orient="vertical")
        body.add(right, weight=1)
        right.add(self._build_results(right), weight=0)
        plots = ttk.Frame(right)
        right.add(plots, weight=1)
        self.figure = Figure(figsize=(9, 6.5), constrained_layout=True)
        self.display = PingDisplay(self.figure, span_ms=args.span)
        self.canvas = FigureCanvasTkAgg(self.figure, master=plots)
        # Zoom, pan, back, home and save-image buttons for the plots.
        self.toolbar = NavigationToolbar2Tk(self.canvas, plots, pack_toolbar=False)
        self.toolbar.pack(side="bottom", fill="x")
        self.canvas.get_tk_widget().pack(side="top", fill="both", expand=True)

        self.refresh_signals()
        self.refresh_events()
        root.after(50, self.poll)
        if args.simulate:
            self.refresh_button.state(["disabled"])
            self.rate_box["values"] = [str(r) for r in RATES]
        else:
            root.after(100, lambda: self.refresh_devices(first=True))
        if args.start:
            root.after(400, self.ping)

    # ---- layout -------------------------------------------------------

    def _entry(self, parent, label, value, width=5, pad=(8, 2)):
        self.ttk.Label(parent, text=label).pack(side="left", padx=pad)
        var = self.tk.StringVar(value=value)
        self.ttk.Entry(parent, textvariable=var, width=width).pack(side="left")
        return var

    def _build_top_bar(self):
        tk, ttk = self.tk, self.ttk
        bar = ttk.Frame(self.root, padding=4)
        bar.pack(side="top", fill="x")
        self.ping_button = ttk.Button(bar, text="Ping", command=self.ping)
        self.ping_button.pack(side="left")
        self.continuous = tk.BooleanVar(value=self.args.start)
        ttk.Checkbutton(bar, text="Continuous, every", variable=self.continuous,
                        command=self.on_continuous).pack(side="left", padx=(8, 0))
        self.interval = tk.StringVar(value="1.0")
        ttk.Entry(bar, textvariable=self.interval, width=4).pack(side="left")
        ttk.Label(bar, text="s").pack(side="left")
        self.listen = self._entry(bar, "Listen", "0.3", pad=(12, 2))
        ttk.Label(bar, text="s").pack(side="left")
        self.span = self._entry(bar, "Show", f"{self.args.span:g}", pad=(12, 2))
        ttk.Label(bar, text="ms").pack(side="left")
        self.first_threshold = self._entry(bar, "First arrival at", "30",
                                           width=4, pad=(12, 2))
        ttk.Label(bar, text="% of peak").pack(side="left")
        self.view_recording = tk.BooleanVar(value=False)
        self.view_echogram = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Recording", variable=self.view_recording,
                        command=self.on_view).pack(side="left", padx=(12, 0))
        ttk.Checkbutton(bar, text="Echogram", variable=self.view_echogram,
                        command=self.on_view).pack(side="left", padx=(6, 0))
        self.view_sweep = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Sweep", variable=self.view_sweep,
                        command=self.on_view).pack(side="left", padx=(6, 0))
        self.view_noise = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Noise", variable=self.view_noise,
                        command=self.on_view).pack(side="left", padx=(6, 0))
        self.view_data = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Data", variable=self.view_data,
                        command=self.on_view).pack(side="left", padx=(6, 0))
        self.saving = tk.BooleanVar(value=False)
        ttk.Checkbutton(bar, text="Save pings", variable=self.saving).pack(
            side="left", padx=(12, 0))
        ttk.Button(bar, text="Clear", command=self.clear).pack(
            side="left", padx=(8, 0))
        ttk.Button(bar, text="Reset zoom", command=self.reset_zoom).pack(
            side="left", padx=(4, 0))

    def _build_device_bar(self):
        tk, ttk = self.tk, self.ttk
        bar = ttk.Frame(self.root, padding=(4, 0, 4, 4))
        bar.pack(side="top", fill="x")
        self.chosen, self.boxes = {}, {}
        for kind in ("input", "output"):
            ttk.Label(bar, text=kind.capitalize()).pack(side="left", padx=(0, 2))
            self.chosen[kind] = tk.StringVar(value=DEFAULT_DEVICE)
            self.boxes[kind] = ttk.Combobox(
                bar, textvariable=self.chosen[kind], width=34, state="readonly",
                values=[DEFAULT_DEVICE])
            self.boxes[kind].pack(side="left", padx=(0, 10))
            self.boxes[kind].bind("<<ComboboxSelected>>",
                                  lambda _e: self.update_rates())
        ttk.Label(bar, text="Rate").pack(side="left", padx=(0, 2))
        self.rate = tk.StringVar(value=str(self.args.rate))
        self.rate_box = ttk.Combobox(bar, textvariable=self.rate, width=7,
                                     state="readonly")
        self.rate_box.pack(side="left")
        ttk.Label(bar, text="Hz").pack(side="left", padx=(2, 10))
        self.refresh_button = ttk.Button(bar, text="Refresh devices",
                                         command=self.refresh_devices)
        self.refresh_button.pack(side="left")

    def _tree(self, parent, columns, height):
        tree = self.ttk.Treeview(parent, columns=[c for c, _, _ in columns],
                                 show="headings", height=height,
                                 selectmode="browse")
        for name, title, width in columns:
            tree.heading(name, text=title)
            tree.column(name, width=width, anchor="w")
        tree.pack(side="top", fill="both", expand=True)
        return tree

    def _build_signals(self, parent):
        ttk = self.ttk
        frame = ttk.LabelFrame(parent, text="Signals", padding=4)
        self.signal_tree = self._tree(frame, (
            ("name", "Name", 110), ("f0", "From kHz", 62), ("f1", "To kHz", 55),
            ("ms", "ms", 40), ("level", "Level", 45)), height=5)
        self.signal_tree.bind("<<TreeviewSelect>>", lambda _e: self.on_signal_select())
        form = ttk.Frame(frame)
        form.pack(side="top", fill="x", pady=(4, 0))
        self.signal_form = {
            "name": self._entry(form, "Name", "", width=11, pad=(0, 2)),
            "f0": self._entry(form, "kHz", "2", width=4, pad=(4, 2)),
            "f1": self._entry(form, "to", "20", width=4, pad=(2, 2)),
            "ms": self._entry(form, "ms", "20", width=4, pad=(4, 2)),
            "level": self._entry(form, "lvl", "0.5", width=4, pad=(4, 2))}
        buttons = ttk.Frame(frame)
        buttons.pack(side="top", fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Add", width=7, command=self.add_signal).pack(side="left")
        ttk.Button(buttons, text="Update", width=7, command=self.update_signal).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", width=7, command=self.delete_signal).pack(side="left")
        return frame

    def _build_events(self, parent):
        tk, ttk = self.tk, self.ttk
        frame = ttk.LabelFrame(parent, text="Ping design", padding=4)
        self.event_tree = self._tree(frame, (
            ("n", "#", 28), ("channel", "Channel", 70), ("signal", "Signal", 130),
            ("ms", "At ms", 84)), height=7)
        self.event_tree.bind("<<TreeviewSelect>>", lambda _e: self.on_event_select())
        form = ttk.Frame(frame)
        form.pack(side="top", fill="x", pady=(4, 0))
        self.event_channel = tk.StringVar(value="left")
        ttk.Combobox(form, textvariable=self.event_channel, width=6,
                     values=pinger.CHANNELS, state="readonly").pack(side="left")
        self.event_signal = tk.StringVar()
        self.event_signal_box = ttk.Combobox(form, textvariable=self.event_signal,
                                             width=13, state="readonly")
        self.event_signal_box.pack(side="left", padx=4)
        self.event_time = self._entry(form, "at", "0", width=6, pad=(2, 2))
        ttk.Label(form, text="ms").pack(side="left")
        buttons = ttk.Frame(frame)
        buttons.pack(side="top", fill="x", pady=(4, 0))
        ttk.Button(buttons, text="Add", width=7, command=self.add_event).pack(side="left")
        ttk.Button(buttons, text="Update", width=7, command=self.update_event).pack(side="left", padx=4)
        ttk.Button(buttons, text="Delete", width=7, command=self.delete_event).pack(side="left")
        files = ttk.Frame(frame)
        files.pack(side="top", fill="x", pady=(8, 0))
        ttk.Button(files, text="Load design...", command=self.load_design).pack(side="left")
        ttk.Button(files, text="Save design...", command=self.save_design).pack(side="left", padx=4)
        return frame

    def _build_sweep(self, parent):
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(parent, padding=6)
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x")
        self.sweep_form = {
            "f0": self._entry(line, "From", "2", width=4, pad=(0, 2)),
            "f1": self._entry(line, "to", "21", width=4, pad=(4, 2)),
            "step": self._entry(line, "kHz, step", "1", width=4, pad=(4, 2))}
        ttk.Label(line, text="kHz").pack(side="left", padx=(2, 0))
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x", pady=(4, 0))
        self.sweep_channel = tk.StringVar(value="both in turn")
        ttk.Combobox(line, textvariable=self.sweep_channel, width=11,
                     values=("left", "right", "both in turn"),
                     state="readonly").pack(side="left")
        self.sweep_form["level"] = self._entry(line, "level", "0.1", width=4)
        self.sweep_form["repeats"] = self._entry(line, "repeats", "1", width=3)
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x", pady=(4, 0))
        self.sweep_button = ttk.Button(line, text="Sweep", width=7,
                                       command=self.sweep)
        self.sweep_button.pack(side="left")
        self.band_button = ttk.Button(line, text="Add suggested band to signals",
                                      command=self.use_band)
        self.band_button.pack(side="left", padx=4)
        self.band_button.state(["disabled"])
        return frame

    def _build_noise(self, parent):
        ttk = self.ttk
        frame = ttk.Frame(parent, padding=6)
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x")
        self.noise_seconds = self._entry(line, "Listen for", "3", width=4, pad=(0, 2))
        ttk.Label(line, text="s").pack(side="left", padx=(2, 8))
        self.noise_button = ttk.Button(line, text="Measure noise",
                                       command=self.measure_noise)
        self.noise_button.pack(side="left")
        ttk.Label(frame, text="Records with nothing playing.",
                  foreground="gray40").pack(side="top", anchor="w", pady=(4, 0))
        return frame

    def _build_data(self, parent):
        tk, ttk = self.tk, self.ttk
        frame = ttk.Frame(parent, padding=6)
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x")
        self.data_text = self._entry(line, "Text", "TAT 123456", width=24, pad=(0, 2))
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x", pady=(4, 0))
        self.data_form = {
            "f0": self._entry(line, "Band", "13", width=4, pad=(0, 2)),
            "f1": self._entry(line, "to", "17", width=4, pad=(4, 2))}
        ttk.Label(line, text="kHz").pack(side="left", padx=(2, 0))
        self.data_form["spread"] = self._entry(line, "spread", "7", width=3)
        self.data_form["bits"] = self._entry(line, "bits", "5", width=3)
        line = ttk.Frame(frame)
        line.pack(side="top", fill="x", pady=(4, 0))
        self.data_channel = tk.StringVar(value="right")
        ttk.Combobox(line, textvariable=self.data_channel, width=6,
                     values=pinger.CHANNELS, state="readonly").pack(side="left")
        self.data_form["level"] = self._entry(line, "level", "0.3", width=4)
        self.data_button = ttk.Button(line, text="Send", width=7,
                                      command=self.send_data)
        self.data_button.pack(side="left", padx=(8, 0))
        self.data_info = tk.StringVar(value="")
        ttk.Label(frame, textvariable=self.data_info, foreground="gray40").pack(
            side="top", anchor="w", pady=(4, 0))
        return frame

    def _build_results(self, parent):
        frame = self.ttk.Frame(parent, padding=(0, 4, 4, 0))
        self.result_tree = self._tree(frame, (
            ("n", "#", 30), ("channel", "Channel", 110), ("signal", "Signal", 130),
            ("sent", "Sent at ms", 80), ("delay", "Arrival ms", 90),
            ("path", "Path m", 80), ("level", "Level dB", 75),
            ("snr", "x noise", 70)), height=4)
        return frame

    # ---- signals and events -------------------------------------------

    def refresh_signals(self):
        self.signal_tree.delete(*self.signal_tree.get_children())
        for i, s in enumerate(self.design.signals):
            self.signal_tree.insert("", "end", iid=str(i), values=(
                s.name, f"{s.f0 / 1e3:g}", f"{s.f1 / 1e3:g}",
                f"{s.duration * 1e3:g}", f"{s.amplitude:g}"))
        names = [s.name for s in self.design.signals]
        self.event_signal_box["values"] = names
        if self.event_signal.get() not in names:
            self.event_signal.set(names[0] if names else "")

    def refresh_events(self):
        self.event_tree.delete(*self.event_tree.get_children())
        for i, e in enumerate(self.design.events):
            self.event_tree.insert("", "end", iid=str(i), values=(
                i + 1, e.channel, e.signal, f"{e.time * 1e3:g}"))

    def _selected(self, tree):
        picked = tree.selection()
        return int(picked[0]) if picked else None

    def on_signal_select(self):
        i = self._selected(self.signal_tree)
        if i is None:
            return
        s = self.design.signals[i]
        for key, value in (("name", s.name), ("f0", f"{s.f0 / 1e3:g}"),
                           ("f1", f"{s.f1 / 1e3:g}"),
                           ("ms", f"{s.duration * 1e3:g}"),
                           ("level", f"{s.amplitude:g}")):
            self.signal_form[key].set(value)

    def _signal_from_form(self):
        form = {k: v.get().strip() for k, v in self.signal_form.items()}
        if not form["name"]:
            raise ValueError("the signal needs a name")
        signal = pinger.Signal(
            name=form["name"], f0=number(form["f0"], "start frequency") * 1e3,
            f1=number(form["f1"], "end frequency") * 1e3,
            duration=number(form["ms"], "length") / 1e3,
            amplitude=number(form["level"], "level"))
        if not 0 < signal.amplitude <= 1:
            raise ValueError("level must be above 0 and at most 1")
        if signal.duration <= 0 or min(signal.f0, signal.f1) <= 0:
            raise ValueError("length and frequencies must be above zero")
        return signal

    def add_signal(self):
        try:
            signal = self._signal_from_form()
        except ValueError as error:
            return self.status.set(f"Signal not added: {error}")
        names = {s.name for s in self.design.signals}
        base, n = signal.name, 2
        while signal.name in names:
            signal.name, n = f"{base} {n}", n + 1
        self.design.signals.append(signal)
        self.refresh_signals()
        self.signal_tree.selection_set(str(len(self.design.signals) - 1))
        self.status.set(f"Added signal '{signal.name}'.")

    def update_signal(self):
        i = self._selected(self.signal_tree)
        if i is None:
            return self.status.set("Select a signal to update.")
        try:
            signal = self._signal_from_form()
        except ValueError as error:
            return self.status.set(f"Signal not updated: {error}")
        old = self.design.signals[i].name
        if signal.name != old and signal.name in {s.name for s in self.design.signals}:
            return self.status.set(f"There is already a signal called '{signal.name}'.")
        self.design.signals[i] = signal
        for e in self.design.events:        # a rename follows through
            if e.signal == old:
                e.signal = signal.name
        self.refresh_signals()
        self.refresh_events()
        self.signal_tree.selection_set(str(i))
        self.status.set(f"Updated signal '{signal.name}'.")

    def delete_signal(self):
        i = self._selected(self.signal_tree)
        if i is None:
            return self.status.set("Select a signal to delete.")
        name = self.design.signals[i].name
        if any(e.signal == name for e in self.design.events):
            return self.status.set(
                f"'{name}' is used in the ping design; remove those events first.")
        del self.design.signals[i]
        self.refresh_signals()
        self.status.set(f"Deleted signal '{name}'.")

    def on_event_select(self):
        i = self._selected(self.event_tree)
        if i is None:
            return
        e = self.design.events[i]
        self.event_channel.set(e.channel)
        self.event_signal.set(e.signal)
        self.event_time.set(f"{e.time * 1e3:g}")

    def _event_from_form(self):
        if not self.event_signal.get():
            raise ValueError("there is no signal to send")
        time = number(self.event_time.get(), "the time") / 1e3
        if time < 0:
            raise ValueError("the time cannot be negative")
        return pinger.Event(self.event_channel.get(), self.event_signal.get(), time)

    def add_event(self):
        try:
            self.design.events.append(self._event_from_form())
        except ValueError as error:
            return self.status.set(f"Event not added: {error}")
        self.design.events.sort(key=lambda e: e.time)
        self.refresh_events()
        self.status.set("Added an event to the ping design.")

    def update_event(self):
        i = self._selected(self.event_tree)
        if i is None:
            return self.status.set("Select an event to update.")
        try:
            self.design.events[i] = self._event_from_form()
        except ValueError as error:
            return self.status.set(f"Event not updated: {error}")
        self.design.events.sort(key=lambda e: e.time)
        self.refresh_events()
        self.status.set("Updated the event.")

    def delete_event(self):
        i = self._selected(self.event_tree)
        if i is None:
            return self.status.set("Select an event to delete.")
        del self.design.events[i]
        self.refresh_events()
        self.status.set("Deleted the event.")

    def load_design(self, path=None):
        if path is None:
            from tkinter import filedialog
            folder = os.path.join(HERE, "designs")
            path = filedialog.askopenfilename(
                initialdir=folder if os.path.isdir(folder) else HERE,
                filetypes=[("Ping design", "*.json")])
        if not path:
            return
        try:
            with open(path) as f:
                self.design = pinger.Design.from_dict(json.load(f))
        except (OSError, ValueError, KeyError, TypeError) as error:
            return self.status.set(f"Could not load {path}: {error}")
        self.refresh_signals()
        self.refresh_events()
        self.status.set(f"Loaded {os.path.relpath(path, HERE)}.")

    def save_design(self, path=None):
        if path is None:
            from tkinter import filedialog
            folder = os.path.join(HERE, "designs")
            os.makedirs(folder, exist_ok=True)
            path = filedialog.asksaveasfilename(
                initialdir=folder, defaultextension=".json",
                filetypes=[("Ping design", "*.json")])
        if not path:
            return
        with open(path, "w") as f:
            f.write(self.design.to_json() + "\n")
        self.status.set(f"Saved {os.path.relpath(path, HERE)}.")

    # ---- devices ------------------------------------------------------

    def refresh_devices(self, first=False):
        """Scan for sound devices: run again after plugging one in."""
        if self.busy or self.args.simulate:
            return
        import audio_io
        try:
            devices = audio_io.list_devices()
        except Exception as error:
            return self.status.set(f"Could not list sound devices: {error}")
        self.devices = {}
        for kind, count, wanted in (
                ("input", "inputs", self.args.input_device),
                ("output", "outputs", self.args.output_device)):
            previous = self.chosen[kind].get()
            self.choices[kind] = {DEFAULT_DEVICE: None}
            for d in devices:
                if d[count]:
                    label = f"{d['index']}: {d['name']}"
                    self.choices[kind][label] = d["index"]
                    self.devices[label] = d
                    if first and wanted == d["index"]:
                        previous = label
            self.boxes[kind]["values"] = list(self.choices[kind])
            self.chosen[kind].set(
                previous if previous in self.choices[kind] else DEFAULT_DEVICE)
        self.update_rates()
        self.status.set(f"Found {len(devices)} sound devices.")

    def update_rates(self):
        """Offer the rates both chosen devices accept."""
        rates = set(RATES)
        for kind, key in (("input", "input_rates"), ("output", "output_rates")):
            device = self.devices.get(self.chosen[kind].get())
            if device:
                rates &= set(device[key])
        self.rate_box["values"] = [str(r) for r in sorted(rates)]
        if rates and int(self.rate.get()) not in rates:
            self.rate.set(str(48000 if 48000 in rates else min(rates)))

    # ---- pinging ------------------------------------------------------

    def read_setup(self):
        threshold = number(self.first_threshold.get(), "first-arrival threshold") / 100.0
        if not 0 < threshold <= 1:
            raise ValueError("first-arrival threshold must be 1 to 100 %")
        listen = number(self.listen.get(), "listen time")
        if not 0 < listen <= 10:
            raise ValueError("listen time must be between 0 and 10 s")
        return pinger.Setup(
            rate=int(self.rate.get()), listen=listen, first_threshold=threshold,
            input_device=self.choices["input"].get(self.chosen["input"].get()),
            output_device=self.choices["output"].get(self.chosen["output"].get()))

    def _work(self, design, setup, index):
        try:
            if self.args.simulate:
                recording, warnings = pinger.simulate(design, setup, index), []
            else:
                recording, warnings = pinger.record(design, setup)
            self.results.put(pinger.analyse(recording, design, setup, warnings))
        except Exception as error:      # shown in the status bar, not lost
            self.results.put(error)

    def _set_busy(self, busy, text=None):
        self.busy = busy
        for button in (self.ping_button, self.sweep_button, self.noise_button,
                       self.data_button):
            button.state(["disabled" if busy else "!disabled"])
        if text:
            self.status.set(text)

    def _run_folder(self, kind):
        stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
        base = os.path.join(HERE, "runs", f"{kind}-{stamp}")
        folder, n = base, 2
        while os.path.exists(folder):       # two runs in the same second
            folder, n = f"{base}-{n}", n + 1
        os.makedirs(folder)
        return folder

    def measure_noise(self):
        """Record with nothing playing and chart the background noise."""
        if self.busy:
            return
        try:
            setup = self.read_setup()
            seconds = number(self.noise_seconds.get(), "the listening time")
            if not 0.5 <= seconds <= 60:
                raise ValueError("listen for between 0.5 and 60 s")
        except ValueError as error:
            return self.status.set(f"Check the noise settings: {error}")
        self.continuous.set(False)
        self._set_busy(True, "Listening...")
        threading.Thread(target=self._noise_work, args=(setup, seconds),
                         daemon=True).start()

    def _noise_work(self, setup, seconds):
        try:
            if self.args.simulate:
                recording, warnings = dsp.simulate_noise(setup.rate, seconds), []
            else:
                import audio_io
                # Playing silence keeps the same path as a ping. The input
                # thumps when it switches on, so the first part is dropped.
                skip = 0.5
                silence = np.zeros((int((seconds + skip) * setup.rate), 2), np.float32)
                recording, warnings = audio_io.play_and_record(
                    silence, setup.rate, setup.input_device, setup.output_device)
                recording = recording[int(skip * setup.rate):]
            self.results.put(("noise", dict(recording=recording, rate=setup.rate,
                                            warnings=warnings)))
        except Exception as error:
            self.results.put(error)

    def show_noise(self, noise):
        self.display.noise = noise
        self.view_noise.set(True)
        self.on_view()
        recording, rate = noise["recording"], noise["rate"]
        bands = dsp.band_levels(recording, rate)
        folder = self._run_folder("noise")
        path = os.path.join(folder, "noise.wav")
        wav_io.write_wav(path, recording, rate)
        wav_io.write_meta(path, dict(
            time=datetime.datetime.now().astimezone().isoformat(), rate=rate,
            bands=bands))
        overall = 20 * np.log10(max(float(np.std(recording)), 1e-10))
        audible = [b for b in bands if b["f0"] >= 1000]
        quiet = min(audible, key=lambda b: b["level_db"])
        loud = max(audible, key=lambda b: b["level_db"])
        self.status.set(
            f"Noise: {overall:.0f} dB re full scale overall; above 1 kHz the "
            f"quietest band is {quiet['f0'] / 1e3:g}-{quiet['f1'] / 1e3:g} kHz "
            f"({quiet['level_db']:.0f} dB), the loudest "
            f"{loud['f0'] / 1e3:g}-{loud['f1'] / 1e3:g} kHz ({loud['level_db']:.0f} dB)"
            + "".join(f"; {w}" for w in noise["warnings"])
            + f"   [saved {os.path.relpath(folder, HERE)}]")

    def send_data(self):
        """Send the text as chirp data on one channel and decode what the
        microphone heard."""
        if self.busy:
            return
        try:
            setup = self.read_setup()
            form = {k: number(v.get(), k) for k, v in self.data_form.items()}
            config = chirp_data.DataConfig(
                rate=setup.rate, f0=form["f0"] * 1e3, f1=form["f1"] * 1e3,
                spread=int(form["spread"]), bits=int(form["bits"]),
                amplitude=form["level"])
            config.check()
            if not 0 < config.amplitude <= 1:
                raise ValueError("level must be above 0 and at most 1")
            payload = self.data_text.get().encode("utf-8")
            samples = chirp_data.modulate(payload, config)
        except ValueError as error:
            return self.status.set(f"Check the data settings: {error}")
        self.data_info.set(
            f"{config.bit_rate:.0f} bit/s, {config.symbol_time * 1e3:.0f} ms per "
            f"symbol, message {samples.size / config.rate:.2f} s")
        self.continuous.set(False)
        self._set_busy(True, "Sending data...")
        threading.Thread(
            target=self._data_work,
            args=(setup, config, payload, samples, self.data_channel.get()),
            daemon=True).start()

    def _data_work(self, setup, config, payload, samples, channel):
        try:
            if self.args.simulate:
                recording, warnings = chirp_data.simulate_channel(
                    samples, config.rate, index=self.sent), []
            else:
                import audio_io
                lead = int(pinger.LEAD_IN * setup.rate)
                playback = np.zeros((lead + samples.size + int(0.3 * setup.rate), 2),
                                    np.float32)
                playback[lead:lead + samples.size,
                         pinger.CHANNELS.index(channel)] = samples
                recording, warnings = audio_io.play_and_record(
                    playback, setup.rate, setup.input_device, setup.output_device)
                recording = recording[int(pinger.SETTLE * setup.rate):]
            self.sent += 1
            self.results.put(("data", dict(
                result=chirp_data.demodulate(recording, config), config=config,
                sent=payload, recording=recording, channel=channel,
                warnings=warnings)))
        except Exception as error:
            self.results.put(error)

    def show_data(self, data):
        self.display.data = data
        self.view_data.set(True)
        self.on_view()
        result, sent = data["result"], data["sent"]
        errors, total = chirp_data.bit_errors(sent, result.payload)
        folder = self._run_folder("data")
        path = os.path.join(folder, "message.wav")
        wav_io.write_wav(path, data["recording"], data["config"].rate)
        wav_io.write_meta(path, dict(
            time=datetime.datetime.now().astimezone().isoformat(),
            config=asdict(data["config"]), channel=data["channel"],
            sent=sent.decode("utf-8", "replace"),
            received=result.payload.decode("utf-8", "replace"),
            found=result.found, crc_ok=result.ok, bit_errors=errors, bits=total,
            sync_snr=result.sync_snr, symbol_snr_db=result.symbol_snr))
        if not result.found:
            text = f"Data: {result.message}"
        else:
            shown = result.payload.decode("utf-8", "replace")
            text = (f"Data: {result.message}: \"{shown}\"; {errors} of {total} "
                    f"bits wrong")
            if result.symbol_snr:
                text += f"; weakest symbol {min(result.symbol_snr):.0f} dB"
        self.status.set(text + "".join(f"; {w}" for w in data["warnings"])
                        + f"   [saved {os.path.relpath(folder, HERE)}]")

    def sweep(self):
        """Step narrow chirps through a frequency range on each chosen
        channel and chart how strongly each band comes back."""
        if self.busy:
            return
        try:
            setup = self.read_setup()
            form = {k: number(v.get(), k) for k, v in self.sweep_form.items()}
            repeats = int(form["repeats"])
            if not 1 <= repeats <= 20:
                raise ValueError("repeats must be between 1 and 20")
            if not 0 < form["level"] <= 1:
                raise ValueError("level must be above 0 and at most 1")
            names = (pinger.CHANNELS if self.sweep_channel.get() == "both in turn"
                     else (self.sweep_channel.get(),))
            designs = {name: pinger.sweep_design(
                form["f0"] * 1e3, form["f1"] * 1e3, form["step"] * 1e3, name,
                form["level"]) for name in names}
            for design in designs.values():
                design.check(setup.rate)
        except ValueError as error:
            return self.status.set(f"Check the sweep settings: {error}")
        self.continuous.set(False)
        self._set_busy(True, "Sweeping...")
        threading.Thread(target=self._sweep_work, args=(designs, setup, repeats),
                         daemon=True).start()

    def _sweep_work(self, designs, setup, repeats):
        try:
            channels, recordings, warnings = {}, {}, []
            for name, design in designs.items():
                runs = []
                for i in range(repeats):
                    if self.args.simulate:
                        recording, more = pinger.simulate_sweep(design, setup, i), []
                    else:
                        recording, more = pinger.record(design, setup)
                    warnings += more
                    runs.append(pinger.analyse_sweep(recording, design, setup))
                    recordings[name] = recording
                channels[name] = pinger.average_sweeps(runs)
            self.results.put(("sweep", dict(
                channels=channels, suggestion=pinger.suggest_band(channels),
                recordings=recordings, setup=setup,
                warnings=sorted(set(warnings)))))
        except Exception as error:
            self.results.put(error)

    def show_sweep(self, sweep):
        """Chart a finished sweep and save it under runs/."""
        self.sweep_result = sweep
        self.display.sweep = sweep
        self.view_sweep.set(True)
        self.on_view()
        folder = self._run_folder("sweep")
        for name, recording in sweep["recordings"].items():
            path = os.path.join(folder, f"{name}.wav")
            wav_io.write_wav(path, recording, sweep["setup"].rate)
            wav_io.write_meta(path, dict(
                time=datetime.datetime.now().astimezone().isoformat(),
                setup=asdict(sweep["setup"]), channel=name,
                bands=sweep["channels"][name], suggestion=sweep["suggestion"]))
        heard = sum(b["heard"] for bands in sweep["channels"].values()
                    for b in bands)
        total = sum(len(bands) for bands in sweep["channels"].values())
        band = sweep["suggestion"]
        self.band_button.state(["!disabled" if band else "disabled"])
        self.status.set(
            f"Sweep: {heard} of {total} bands heard; "
            + (f"suggested band {band[0] / 1e3:g} to {band[1] / 1e3:g} kHz"
               if band else "no band to suggest")
            + "".join(f"; {w}" for w in sweep["warnings"])
            + f"   [saved {os.path.relpath(folder, HERE)}]")

    def use_band(self):
        """Add a chirp covering the suggested band to the signal list."""
        band = getattr(self, "sweep_result", {}).get("suggestion")
        if not band:
            return self.status.set("Run a sweep first.")
        names = {s.name for s in self.design.signals}
        base = f"sweep {band[0] / 1e3:g}-{band[1] / 1e3:g}k"
        name, n = base, 2
        while name in names:
            name, n = f"{base} {n}", n + 1
        self.design.signals.append(pinger.Signal(name, band[0], band[1]))
        self.refresh_signals()
        self.signal_tree.selection_set(str(len(self.design.signals) - 1))
        self.status.set(f"Added signal '{name}'. Use it in the ping design.")

    def ping(self):
        if self.busy:
            return
        try:
            setup = self.read_setup()
            design = copy.deepcopy(self.design)   # edits during a ping do not touch it
            design.check(setup.rate)
            span = number(self.span.get(), "the time shown")
            if not 1 <= span <= 2000:
                raise ValueError("show between 1 and 2000 ms")
        except ValueError as error:
            self.status.set(f"Check the settings: {error}")
            self.continuous.set(False)
            return
        if span != self.display.span_ms:
            self.display.span_ms = span
            self.display.columns = []
        self._set_busy(True, "Pinging...")
        threading.Thread(target=self._work, args=(design, setup, self.sent),
                         daemon=True).start()
        self.sent += 1

    def poll(self):
        try:
            result = self.results.get_nowait()
        except queue.Empty:
            self.root.after(50, self.poll)
            return
        self._set_busy(False)
        if isinstance(result, Exception):
            self.status.set(f"Audio error: {result}")
            self.continuous.set(False)
        elif isinstance(result, tuple):
            kind, payload = result
            {"sweep": self.show_sweep, "noise": self.show_noise,
             "data": self.show_data}[kind](payload)
        else:
            self.show(result)
            if self.continuous.get():
                try:
                    wait = max(0.0, float(self.interval.get()))
                except ValueError:
                    wait = 1.0
                self.root.after(int(wait * 1000), self.ping)
        self.root.after(50, self.poll)

    def _redrawn(self):
        """The figure was rebuilt: forget the toolbar's old zoom history."""
        self.toolbar.update()
        self.canvas.draw_idle()

    def reset_zoom(self):
        self.display.reset_zoom()
        self._redrawn()

    def show(self, result):
        self.display.add(result)
        self._redrawn()
        self.result_tree.delete(*self.result_tree.get_children())
        for row in pinger.rows(result):
            heard = row["heard"]
            shared = "".join(f" (with #{n})" for n in row["combined_with"])
            self.result_tree.insert("", "end", values=(
                row["number"], row["channel"] + shared, row["signal"],
                f"{row['sent_ms']:g}",
                f"{row['delay_ms']:+.3f}" if heard else "not heard",
                f"{row['path_m']:+.3f}" if heard else "",
                f"{row['level_db']:+.1f}" if heard else "",
                f"{row['snr']:.0f}" if heard else ""))
        text = f"Ping {self.display.count}: " + (
            "; ".join(result.warnings) if result.warnings else "all events heard")
        if self.saving.get() and result.recording.size:
            if self.folder is None:
                stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
                self.folder = os.path.join(HERE, "runs", f"gui-{stamp}")
            path = save_ping(self.folder, self.display.count, result)
            text += f"   [saved {os.path.relpath(path, HERE)}]"
        self.status.set(text)

    def on_continuous(self):
        if self.continuous.get():
            self.ping()

    def on_view(self):
        self.display.show_recording = self.view_recording.get()
        self.display.show_echogram = self.view_echogram.get()
        self.display.show_sweep = self.view_sweep.get()
        self.display.show_noise = self.view_noise.get()
        self.display.show_data = self.view_data.get()
        self.display.redraw()
        self._redrawn()

    def clear(self):
        self.display.clear()
        self.folder = None
        self.result_tree.delete(*self.result_tree.get_children())
        self._redrawn()
        self.status.set("Cleared.")


def parse_args(argv=None):
    p = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    p.add_argument("--simulate", action="store_true",
                   help="made-up recordings, no sound card")
    p.add_argument("--start", action="store_true",
                   help="start pinging continuously at once")
    p.add_argument("--design", metavar="FILE", help="ping design to load")
    p.add_argument("--input-device", type=int,
                   help="input to select at start, index from loopback_test.py --list")
    p.add_argument("--output-device", type=int,
                   help="output to select at start")
    p.add_argument("--rate", type=int, default=48000,
                   help="sample rate to select at start, Hz")
    p.add_argument("--span", type=float, default=40.0,
                   help="time shown after the first arrival, ms")
    return p.parse_args(argv)


def main():
    import tkinter as tk
    root = tk.Tk()
    App(root, parse_args())
    root.mainloop()
    return 0


if __name__ == "__main__":
    sys.exit(main())
