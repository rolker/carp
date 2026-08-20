# Navigation and Contact Relocation

## The actual problem

The ROV is not the hard part. **Relocation is.** A sidescan contact carries
position error, and with 3 m visibility you can sit nearly on top of a target
and never see it. Sortie time gets spent searching, not inspecting.

## Method 1 — Downline as datum (primary, v1)

Drop a weighted marker on the contact position. Anchor the kayak upcurrent.
Clip the tether to the **downline**, not the boat. Descend along the line, work
a spiral out from its base.

This converts an unbounded search into a bounded one around a known datum. The
tether length becomes the search radius — which is why **15 m is better than
30 m** here. It's also the only thing preventing re-covering the same ground,
since there's no positioning to say where you've already been.

**Kayak safety:** a kayak on a rode with an ROV pulling on a second line is two
things that may need to be shed fast. Both get quick-releases, **both to the
boat, neither to the body.** Flake tether into a milk crate in the tank well,
not a spool that can't be worked one-handed. A drift sock helps hold station.

## Method 2 — Parallel scaling lasers (cheap, high value)

Two green line lasers potted in acrylic, fixed distance apart (10 cm is
convenient), aimed parallel to the optical axis. **Green penetrates turbid
water far better than red.**

Every frame carries its own scale bar. A contact can be *sized* from imagery
instead of guessed — the difference between "some debris" and "1.2 m section of
pipe." ~$20, converts the camera into a measuring instrument.

**Down-looking pair does double duty:** separation in pixels gives altitude
directly, and altitude converts optical flow from pixels/sec to m/s. Also
supplies the altitude-hold that would otherwise need an echosounder. One part,
three jobs.

## Method 3 — Optical flow as poor-man's DVL

Sparse LK flow on downsampled frames — 320×240 at 30 Hz is trivial on a Pi 4,
let alone a 5. **Not** full VSLAM.

Publish as `TwistWithCovarianceStamped` — literally what a real DVL publishes —
and fuse in `robot_localization`.

**Requires** global shutter (OV9281). Rolling shutter plus vehicle roll gives
skew that biases flow *systematically*, not just noisily. Mono is also more
sensitive, and colour is nearly gone in turbid green water anyway.

**Two failure modes:**

- **Featureless bottom.** Flat silt or rippleless sand gives the tracker
  nothing. A real DVL doesn't care about texture; a camera cares about nothing
  else. In New England mud this will be the common case.
- **Marine snow.** Particulate drifting through the column at 3 m viz looks
  exactly like platform motion. Needs RANSAC against a dominant-plane model
  with hard rejection of anything inconsistent.

**Lighting conflict** (only if lights are fitted — v1 runs ambient-only, see
ADR-004; in direct sun, mask the vehicle's own shadow out of the flow field):
off-axis lights kill backscatter on the forward camera,
but a moving off-axis source casts shadows that sweep across the bottom as the
vehicle translates — apparent motion that isn't ours. The down camera wants
flat, near-coaxial, diffuse light. Separate light. At 1 m altitude the
backscatter penalty is affordable.

**Fundamental limit:** integrated flow is dead reckoning and drifts as a random
walk. The architecture that works is VO for smooth short-term velocity,
**bounded by occasional absolute range fixes off the downline.** Neither is
sufficient alone.

## Method 4 — Acoustic ranging (the interesting one)

**Not a literal USBL.** Phase-based bearing needs elements under λ/2 apart; at
sound-card frequencies that's a few centimetres of baseline with 2–3 samples
per cycle. Fighting for phase resolution that isn't obtainable.

**Broadband TDOA instead.** Transmit a chirp (8–20 kHz sweep, ~10 ms),
cross-correlate at receivers, take time-difference of arrival across a ~1 m
rigid baseline. Correlating a chirp gives unambiguous delay with no phase
wrapping. At 96 kHz that's ~1.5 cm over a 1 m baseline — roughly a degree of
bearing. Short-baseline, which suits a 15 m working hemisphere.

### The tether is the unlock

What kills homebrew acoustic positioning is **transponder turnaround jitter** —
the vehicle hears a ping and replies after a fixed delay, but USB audio
buffering on Linux gives tens of milliseconds of slop. Every 10 ms is 15 m of
range error.

But there's Ethernet to the vehicle. **Run PTP or chrony over it, schedule the
chirp at a known instant, and it becomes one-way ranging.** Sub-100 µs sync is
~15 cm. Fixed DAC/ADC buffer offsets calibrate out with one known-distance
measurement in a pool; only jitter hurts.

This is the single strongest argument against going tetherless (ADR-009).

### Build range-only first

Time of flight plus the MS5837 gives horizontal radius directly:
√(r² − Δz²). One channel, no array, no bearing math — and it already answers
the question that matters during a spiral search: *am I 2 m from the downline
or 9 m?* Bearing is a later increment on the same signal chain.

### Hardware

- Pi has **no ADC at all**; its PWM audio out is unsuitable for driving a
  transducer
- USB interface with genuinely synchronous multichannel input at 96 or 192 kHz.
  CM6206-class does 96k stereo; Scarlett-class does better
- 27 mm piezo discs potted in polyurethane — they work far better underwater
  than they have any right to
- High-impedance preamp per channel, small amp for transmit
- ~$100–200 total

### Three things that will bite

- **Shallow-water multipath.** At 5 m, surface and bottom bounces arrive within
  1–2 ms of the direct path. **Detect leading edge, not correlation peak.**
- **Kayak motion.** Heave and roll inject straight into bearing. The array
  needs its own IMU and must be rigid to the hull — pole mount under the
  gunwale, not zip-tied to the deck.
- **Sound speed.** 1450 vs 1520 m/s is 5% of range, and nobody checks until the
  fixes are consistently off.

### ROS integration

Publish `PoseWithCovarianceStamped` with **honest covariance** — range tight,
bearing loose. `robot_localization` will do the right thing with a noisy
bearing if the uncertainty isn't understated.

**Effort warning:** this is a genuine DSP project, not a weekend. Getting the
acoustics reliable is probably more work than the ROV itself.

## Method 5 — GNSS

**Does not propagate underwater.** At 1.5 GHz, centimetres of penetration in
fresh water, less in salt. Only meaningful at the surface.

**On the vehicle: pointless here.** Hot-start with injected AssistNow/MGA down
the tether works mechanically, but GNSS gives 2–4 m CEP and the working radius
is 15 m. The fix would say less than the tether already does. This technique
earns its keep bounding INS drift on untethered AUVs over kilometres.

**On the kayak: this is where it matters.** The anchor datum ties every
inspection back to the sonar mosaic. The boat swings on the rode, so log
continuously and take the mean — never a single sample.

**PPK, not RTK.** Log raw observables on one receiver, post-process against
NOAA CORS with RTKLIB. Free, needs no cell coverage, decimetre or better after
the fact. Nothing here is real-time. A ZED-F9P (~$220) blows the ROV budget but
improves every sidescan survey too.

**Only worth it if the sonar's own navigation is comparable.** See
`sidescan-datum.md`.
