## Notes: ranging

*A stub for step 1; the live numbers are the point.*

**Sound speed.** In air at $temperature C it is $speed m/s, so one
millisecond of delay is $mm_per_ms mm of path. One sample at $rate Hz is
$mm_per_sample mm.

**What the table says.** The matched filter finds each signal in the
recording. With no loopback, times are measured from the loudest event's
first arrival, so a path *difference* is what you get. With a loopback (an
electrical copy of the output mixed into the input), the copy marks the
instant of sending and the next arrival after it is the time of flight, so
the path is a distance.

**Selected signal: $signal.** $details

**Two arrivals closer than the resolution merge.** The figure is read off
this signal's own matched-filter peak, by the detection design's
*resolution measure*: the first null either side by default (about 3 /
bandwidth for a fully tapered chirp, 1 / bandwidth with no taper), or the
peak's width at -3 or -6 dB. $resolution_line

**Processing gain.** The matched filter lifts a signal above white noise by
about 10 log10(length x bandwidth): $gain_line

**Simulation knows the truth.** In a simulated capture the dotted lines on
the trace and the "true path" and "error" columns come from the scene itself,
not from the processing.
