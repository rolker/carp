"""Ranging: build a ping from a ping design, and read the arrivals out of a
capture.

Experiments sit between pages and backends. Nothing here draws anything.
"""
from dataclasses import dataclass, field
from fractions import Fraction

import numpy as np
from scipy import signal as sps

from ..backends.base import Emission, Ping
from ..models import detection
from ..models.detection_design import DEFAULT
from ..objects import signals as signal_objects
from ..objects.schema import WorkspaceError

FIRST_THRESHOLD = DEFAULT.first_fraction   # now a setting of the detection design
DEFAULT_SOUND_SPEED = 343.2


def build_ping(workspace, design_id, infos):
    """A backend Ping from a ping design.

    infos is the backend's list of TransducerInfo, which says each
    transducer's device sample rate. Raises ValueError, with a message a
    person can act on, for a design that cannot be played.
    """
    design = workspace.get("ping_designs", design_id)
    if design is None:
        raise ValueError("no ping design is selected")
    if not design["events"]:
        raise ValueError(f"ping design '{design['name']}' has no events")
    info = {t.id: t for t in infos}
    emissions, specs = [], {}
    for n, event in enumerate(design["events"], 1):
        tid = event["transducer"]
        if tid not in info or not info[tid].can_send:
            raise ValueError(f"event {n}: '{tid}' cannot send with this backend "
                             "and scene")
        rate = info[tid].rate
        try:
            x = signal_objects.samples(workspace.get_signal, event["signal"], rate)
        except WorkspaceError as error:
            raise ValueError(f"event {n}: {error}") from None
        emissions.append(Emission(transducer=tid, samples=x, start=event["time"],
                                  rate=rate, signal=event["signal"]))
        if event["signal"] not in specs:
            f0, f1, duration = signal_objects.band(workspace.get_signal, event["signal"])
            specs[event["signal"]] = dict(
                name=workspace.name_of("signals", event["signal"]), f0=f0, f1=f1,
                duration=duration,
                amplitude=signal_objects.level(workspace.get_signal, event["signal"]))
    receivers = [r for r in design.get("receivers", []) if r in info]
    for r in design.get("receivers", []):
        if r not in info or not info[r].can_receive:
            raise ValueError(f"'{r}' cannot receive with this backend and scene")
    if not receivers:
        receivers = [t.id for t in infos if t.can_receive]
    if not receivers:
        raise ValueError("nothing can receive with this backend and scene")
    return Ping(emissions=emissions, receivers=receivers, listen=design["listen"],
                meta=dict(design_id=design_id, design_name=design["name"],
                          detection_design=design.get("detection_design"),
                          signals=specs))


def _template(emission, rate):
    x = np.asarray(emission.samples, dtype=np.float64)
    if emission.rate != rate:
        ratio = Fraction(rate / emission.rate).limit_denominator(1000)
        x = sps.resample_poly(x, ratio.numerator, ratio.denominator)
    return x / max(float(np.max(np.abs(x))), 1e-12)


def events_from_ping(ping, rate):
    """The ping's emissions as EventSpecs for the detector, with templates
    at the recording's sample rate."""
    specs = ping.meta.get("signals", {})
    events = []
    for i, e in enumerate(ping.emissions):
        name = specs.get(e.signal, {}).get("name", e.signal or "signal")
        events.append(detection.EventSpec(
            label=f"{i + 1}: {e.transducer} {name} @ {e.start * 1e3:g} ms",
            key=e.signal or f"#{i}", template=_template(e, rate), time=e.start))
    return events


def ping_warnings(ping, design=DEFAULT):
    """Problems a ping design has before it is even sent: events that cannot
    be told apart, or that leak into each other's filters (by the detection
    design's search window and leak limit). A list of plain sentences."""
    rate = ping.emissions[0].rate
    events = events_from_ping(ping, rate)
    out = []
    for group in detection.inseparable(events, design):
        out.append("events " + " and ".join(str(i + 1) for i in group)
                   + " use the same signal at nearly the same time and cannot "
                     "be told apart")
    for i, j, isolation in detection.leaking(events, rate, design):
        out.append(f"events {i + 1} and {j + 1} overlap in time and band and leak "
                   f"into each other's filters ({isolation:.0f} dB)")
    return out


@dataclass
class RangingResult:
    receiver: str
    analysis: detection.Analysis
    loopback: list                  # emitters whose loopback this recording holds
    sound_speed: float
    rows: list = field(default_factory=list)
    truth: dict = None
    design: detection.DetectionDesign = DEFAULT   # the settings it was read with
    design_id: str = ""

    @property
    def warnings(self):
        return self.analysis.warnings


def analyse_capture(capture, receiver, design=DEFAULT, design_id=""):
    """Where each event of the ping turned up in one receiver's recording,
    read with a detection design (every threshold and window in it; the
    result keeps it and its ID).

    Without a loopback, arrivals are timed against the loudest event's first
    arrival. Where the recording holds an electrical loopback copy of an
    event's emitter, that copy is time zero and the event's time of flight
    is the gap to the next arrival after it.
    """
    recording, ping = capture.recordings[receiver], capture.ping
    speed = capture.meta.get("sound_speed") or DEFAULT_SOUND_SPEED
    specs = ping.meta.get("signals", {})
    events = events_from_ping(ping, recording.rate)
    analysis = detection.analyse_events(recording.samples, recording.rate, events,
                                        design=design)
    result = RangingResult(receiver=receiver, analysis=analysis,
                           loopback=list(recording.loopback_of), sound_speed=speed,
                           truth=capture.truth, design=design, design_id=design_id)
    result.rows = _rows(result, ping, specs)
    return result


def _true_path(truth, receiver, emission):
    if not truth:
        return None
    for p in truth["paths"]:
        if p["receiver"] == receiver and p["emission"] == emission and p["route"] == "direct":
            return p["length_m"]
    return None


def _rows(result, ping, specs):
    analysis, speed = result.analysis, result.sound_speed
    groups = detection.inseparable(analysis.events, result.design)
    rows = []
    for i, e in enumerate(ping.emissions):
        found = analysis.results[i]
        row = dict(
            number=i + 1, receiver=result.receiver, transducer=e.transducer,
            signal=specs.get(e.signal, {}).get("name", e.signal), sent_ms=e.start * 1e3,
            heard=found is not None, mode="first arrival", delay_ms=None,
            path_m=None, level_db=None, snr=None, error_mm=None, note="",
            true_path_m=_true_path(result.truth, result.receiver, i),
            combined_with=[j + 1 for g in groups if i in g for j in g if j != i])
        if found is not None:
            arrival = found.arrivals[0]
            row.update(snr=found.snr, delay_ms=analysis.delay_ms(i),
                       level_db=20 * np.log10(found.level / analysis.top()))
            if e.transducer in result.loopback:
                row["mode"] = "loopback"
                if len(found.arrivals) >= 2:
                    second = found.arrivals[1]
                    row.update(
                        delay_ms=(second.sample - arrival.sample) / analysis.rate * 1e3,
                        level_db=20 * np.log10(second.level / analysis.top()))
                else:
                    row.update(delay_ms=None, level_db=None,
                               note="loopback heard, no acoustic arrival after it")
            if row["delay_ms"] is not None:
                row["path_m"] = row["delay_ms"] * speed / 1e3
                if row["mode"] == "loopback" and row["true_path_m"] is not None:
                    row["error_mm"] = (row["path_m"] - row["true_path_m"]) * 1e3
        rows.append(row)
    return rows


def truth_marks_ms(result, emission):
    """For a simulated capture: where each path of one event should show up
    on the matched-filter trace, as (route, ms after the trace's time zero).
    Empty without truth."""
    analysis = result.analysis
    if not result.truth or analysis.reference is None:
        return []
    sent = int(round(analysis.events[emission].time * analysis.rate))
    return [(p["route"],
             (p["arrival_sample"] - sent - analysis.reference) / analysis.rate * 1e3)
            for p in result.truth["paths"]
            if p["receiver"] == result.receiver and p["emission"] == emission]


def describe(result):
    """One line summing up a ping, for a status bar or a log."""
    analysis = result.analysis
    if not analysis.detected():
        return "No ping detected: " + "; ".join(analysis.warnings)
    parts = []
    for row in result.rows:
        if row["delay_ms"] is not None:
            parts.append(f"{row['number']} {row['transducer']}: "
                         f"{row['delay_ms']:+.3f} ms, {row['level_db']:+.1f} dB")
        else:
            parts.append(f"{row['number']} {row['transducer']}: not heard")
    return "   |   ".join(parts + analysis.warnings)
