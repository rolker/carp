## Notes: room sonar

*Ping the room, watch what comes back against range, and let the steady part
go so that what moves stands out.*

**How it works.** The speaker sends the ping design's chirp; the microphone
records for long enough that an echo from $max_range m has come back
($listen ms after the sound). Every ping's time zero is the direct sound from
the speaker to the microphone, found in that ping's own recording, so the
output and the input need not share a clock and the device's own delay
between playing and recording does not matter. $direct_line

**Range.** An echo that arrives t after the direct sound travelled c t
further than the direct path. With the speaker and microphone $baseline mm
apart, its range is (c t + d) / 2, taking them as one place: at $speed m/s one
millisecond is $mm_per_ms mm of path, which is half that in range.

**Resolution and reach.** $resolution_line The chirp is $pulse ms long, which
looks like $pulse_m m of range, but the matched filter squeezes it to about
3 / bandwidth: that is the spacing below which two echoes merge. The range bin
on screen is one sample of travel, $bin mm. The maximum range is the one
you set, $max_range m; the listening time follows from it. $ambiguity_line

**The three views.** *Current return*: the matched-filter output against
range, in dB below the direct sound (0 dB is the direct sound; the grey line
is the steady background). *Echogram*: the last pings, newest at the bottom.
*Changes*: the echogram with the steady background taken away. The background
is the average of the last $memory pings; what is left is what changed since:
a hand, a person, a door. A person walking towards the laptop draws a slanting
line; a still room goes dark. Put the memory in step with how fast things
move: a long memory forgets slowly, so a mover leaves a ghost behind it.

**What is behind the picture.** $detection_line The direct sound is the
strongest peak, moved back to the first peak at least
$first_fraction of it (a reflection off the screen or the table can be
stronger than the sound that came straight). Change these on the detection
design, not here: every threshold is a named setting, and the one in force is
saved with the recording.

**Air only.** Everything here is in air. The conversion to water (travel
times and sizes in wavelengths carry over, absorption and reflection at
surfaces do not) comes with the sound speed page.

**Simulation knows the truth.** In a simulated room the dotted lines on the
current return are where each wall, cabinet and the moving person really are,
from the scene itself, not from the processing.
