## Notes: room sonar

*Ping the room from the speakers, watch what comes back against range, and with
two speakers say where the echoes come from.*

**How it works.** Every event of the ping design is sent, each from its own
speaker with its own signal and time. The microphone records for long enough
that an echo from $max_range m has come back ($listen ms after the sound).
Each sound's time zero is its own direct sound from its speaker to the
microphone, found in that ping's own recording, so the output and the input
need not share a clock and the device's own delay between playing and
recording does not matter. Two speakers have two direct paths, so there are
two time zeros. $direct_line

**Range.** An echo that arrives t after a sound's direct sound travelled c t
further than the direct path. With that speaker and the microphone d apart
($baseline mm for the first one), the whole path speaker - target -
microphone is L = c t + d and its range, taking them as one place, is L / 2:
at $speed m/s one millisecond is $mm_per_ms mm of path, half that in range.

**Resolution and reach.** $resolution_line The chirp is $pulse ms long, which
looks like $pulse_m m of range, but the matched filter squeezes it into a
narrow peak; the merging spacing above is read off that peak by the
detection design's *resolution measure* (the first null either side by
default, about 3 / bandwidth for a fully tapered chirp; or the width at -3
or -6 dB, about 1.9 or 2.6 / bandwidth). The range bin
on screen is one sample of travel, $bin mm. The maximum range is the one
you set, $max_range m; the listening time follows from it. $ambiguity_line

**The views.** *Targets*: where the echoes put things in the plane in front of
the laptop (across and forward, or as bearing and range), fading with age;
the speakers and the microphone are drawn where the layout says. *Current
return*: the matched-filter output of each sound against range, in dB below
its direct sound (0 dB is the direct sound; the dashed line is the steady
background; triangles mark the peaks taken for echoes). *Echogram*: the last
pings, newest at the bottom. *Changes*: the echogram with the steady
background taken away. The background is the average of the last $memory
pings; what is left is what changed since: a hand, a person, a door. A person
walking towards the laptop draws a slanting line; a still room goes dark.
Put the memory in step with how fast things move: a long memory forgets
slowly, so a mover leaves a ghost behind it. *Place targets from* chooses
whether the position view uses every echo (walls and furniture too) or only
what changed.

### Two speakers, the same signal

Sent together, the copies add up where they arrive together: straight ahead
(for speakers placed symmetrically) the two are in step, +6 dB. A target off
to one side is nearer one speaker, and returns two copies a time dt =
d sin(bearing) / c apart, d being the speaker spacing ($spacing cm here). For a
broadband chirp that only matters if dt is longer than the matched filter can
resolve: while dt is below about half the merging spacing the copies sum to
one peak, which is a beam. With this chirp the merging spacing is
$path_resolution cm of path, so the beam is about +-$half_zone degrees wide
(the spacing is many wavelengths, $lambda_short to $lambda_long mm over the
band, so this is not a beam in the sense of a small array). Outside it a
target is heard twice. $fringe_line A narrow-band tone does not have a beam but
fringes (grating lobes): in some directions the copies cancel, in others they
add, every wavelength / spacing in sin(bearing).

**Steering.** Delaying one speaker by d sin(angle) / c moves the zone to that
bearing: the one nearest the target in that direction starts last, so that
both sounds arrive together there. The setting is *Steer same-signal
speakers* (now $steer degrees); the delays and the zone are in the numbers.
On hardware the delay is made of whole samples (21 us, 7 mm of path). It does
nothing when no two speakers share a signal. Same signal means one combined
sound: there is range, and the beam, but nothing tells which speaker an echo
came from, so no place across (the page says so). Even the side is not known
from two copies alone.

### Two speakers, different signals

*Which speaker did this echo come from?* If the speakers send different
signals, each gets its own matched filter and its own return: the echoes in
the left filter are the left speaker's, and the right filter's are the right's.
This is the time-difference version of a split-beam sonar. The classic phase
version compares the phase at two elements and needs them closer than half a
wavelength (1 to 8 mm here, impossible with speakers 25 cm apart); comparing
*times* works at any spacing, but needs to know which echo came from which
speaker. Different signals give that.

Coding options, measured on the lab's 10 ms chirps (see the leak line in the
numbers):

- *An up-chirp against a down-chirp of one band*: each keeps the whole band, so
  the full range resolution, but each leaks into the other's filter only
  about 17 dB down (smeared over the chirp's length). A weak echo near a
  strong one can be taken for the other speaker's. In the position view this
  shows up as a wrong spray of points close to the laptop.
- *Split bands* (2-10 kHz against 11-20 kHz): the leak is about 102 dB down,
  clean, but each signal has about half the bandwidth, so about twice the
  merging spacing in range.
- *One after the other* ("left then right"): no leak and the full band, but the
  two views of a mover are a ping apart, and a ping must be long enough for
  the first echoes to die away.

$leak_line The detection design's *leak warning* sets how weak a leak is
still warned about.

### Placing a target

With the speakers S_L and S_R and the microphone M known, an echo in a
speaker's return gives the length of the path speaker - target - microphone.
A target with that path length lies on an ellipse with the speaker and the
microphone as foci. Two speakers give two ellipses; they meet in two points,
one in front of the laptop and one behind it (the same distance on the other
side of the line of the speakers: the laptop cannot tell front from back, so
it takes the one in front). The intersection is solved exactly, not
iterated.

*Which echoes go together?* Any echo of one return might go with any of the
other, and the wrong pairs are ghosts. An echo pair is possible only if
the two paths differ by no more than the speaker spacing plus
$pair_tolerance cm (a target cannot be further from one speaker than from the
other by more than the speakers' spacing; the extra covers timing error), if
the levels differ by no more than $pair_level dB, and if the ellipses meet in
front. Among the possible pairs each echo is used once, preferring pairs of
alike levels. All three are settings of the detection design (*pairing
tolerance*, *pairing level difference*; the echo threshold is $echo_snr times
the typical level; echoes nearer than $nearest m are not placed; sounds of one
signal starting within $combine ms are one combined sound).

*How well?* The range comes out as well as the range resolution allows
(centimetres); the position *across* is worse the further away: a path
error moves a target sideways by about range x error / spacing, so 1 cm of
error at $cross_range m is about $cross_error cm across. Two targets that
are close in range merge into one peak in a return and are placed as one, or
as a ghost between them; two close in range but at different bearings are
told apart only if their peaks differ in at least one of the returns.

**Limits.** The geometry is three-dimensional: a laptop's microphone is in the
screen's bezel, about 25 cm above the speakers, and that is allowed for. A
target is taken to be at the speakers' height, though: one above or below that
is placed where its path lengths put it at that height, a little nearer or
further than it really is. How far off (placed target position error, for
targets at 30 cm / 60 cm above the speakers' height, and for the microphone's
height left out as if it had not been entered), across 0.3 x range and
forward at that range: $height_errors. A wall or the floor is not a
point: its echo is placed where a point reflector with those path lengths
would be, which is near the wall but not on its specular point. Echoes
that arrive by two routes (a reflection off the table and then the target)
make ghosts too.

### Where the speakers and the microphone are

$measured_line Every placed target depends on the positions typed in on the
left (the layout's, in cm: x across, y towards the room, z up, from any
reference point; only the differences matter). The default laptop is a guess
for a 17-inch laptop about 40 cm wide: the speakers near the left and right
side edges, 34 cm apart and symmetric; the microphone where Dell and Alienware
laptops usually have it, in the display bezel by the webcam, centred, about
25 cm above the speakers with the lid open and a little (5 cm) behind the
keyboard's front edge. Yours may differ, and the height depends on how far the
lid is open. A target's place moves by the error in these: 1 cm of speaker
position is about 1 cm of path.

*Finding the microphone.* Watch the input level (the desktop's sound settings
show it) while lightly scratching or tapping different spots of the lid, the
bezel and the keyboard deck: the loudest spot is closest to the microphone.

*Checking where it is across.* With two coded speakers the two direct sounds
arrive at different times, and the difference of those times (the device's
latency is the same for both and cancels) times c is the difference of the
two speaker-to-microphone distances. With the microphone's y and z as entered,
that gives its x: the numbers show "the microphone is about x cm towards the
left or right speaker of where the layout puts it", averaged over the recent
pings. $mic_line It is the first step towards the lab measuring its own
geometry; it says nothing about y or z.

*Later, the lab could measure all of it*: put a small reflector at a known spot
(a ball, a pen cap on a stick), ping, and read the three path lengths (each
speaker to the reflector to the microphone). A few spots give curves that must
all agree, and the speaker and microphone positions that make them agree are
the geometry. It is not built.

**What is behind the picture.** $detection_line The direct sound is the
strongest peak, moved back to the first peak at least
$first_fraction of it (a reflection off the screen or the table can be
stronger than the sound that came straight). The other speaker's direct
sound is looked for where the ping design and the layout put it relative to
the first, within the detection design's *direct-sound window*. Change these
on the detection design, not here: every threshold is a named setting, and the
one in force is saved with the recording.

**Air only.** Everything here is in air. The conversion to water (travel
times and sizes in wavelengths carry over, absorption and reflection at
surfaces do not) comes with the sound speed page.

**Simulation knows the truth.** In a simulated room the dotted lines on the
current return are where each wall, cabinet and moving thing really are, and
the green rings on the position view are where the cabinet, chair, person and
trolley really are, from the scene itself, not from the processing.
