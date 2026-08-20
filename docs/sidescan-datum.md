# Sidescan Contact Positioning — What the Datum Is Actually Worth

The quality of the downline drop depends entirely on how well the contact was
positioned in the first place. That is not the same as how well the survey
vessel was positioned.

## Vessel navigation ≠ contact position

Centimetre-level RTK/PPK with a good INS puts the *transducer* within a couple
of centimetres. The **contact** picks up several more error terms downstream:

| Term | Magnitude | Notes |
|---|---|---|
| Slant-range correction | decimetres | Assumes flat bottom at nadir depth. Sloped or irregular ground breaks it |
| Sound speed | 2% of range | 20 cm at 10 m for a 2% error |
| Along-track resolution | ~22 cm at 25 m | 0.5° beam footprint. Can't localise a feature tighter than the thing that imaged it |
| Contact pick | often the largest | Someone clicks a centroid on an acoustic blob with a shadow |
| **Uncompensated roll** | **~35 cm per degree at 20 m** | The dominant term if attitude isn't applied |

**Realistic outcome: decimetres, not centimetres** — still excellent, and much
better than the several metres a naive estimate assumes.

## The two kinds of survey chain

A small survey vessel often carries two chains of very different quality, and
the contact's datum quality depends on which one imaged it:

**Survey-grade chain.** Multibeam or sidescan tied to an INS, sound velocity
measured, RTK/PPK positioning, lever arms surveyed, acquisition software that
applies attitude. Decimetre or better on the resulting soundings.

**Consumer sidescan chain.** A recreational sonar geotagging pings with its
*own* GNSS and receiving **no attitude compensation at all** — even when a
high-quality INS is aboard, if it never touches the sidescan data it may as
well not exist.

Consequences for the consumer chain:

- **Roll dominates.** A small hull rolls several degrees in any chop. That term
  alone puts contacts in decimetres-to-metres regardless of what the INS knows,
  because the INS never touches the sidescan data.
- **Timestamping compounds it.** Consumer chains rarely have disciplined
  clocks. At 1.5 m/s, 100 ms of timestamp uncertainty is 15 cm along-track.
- **The sonar itself is not the limit.** Sub-degree along-track beams give a
  ~15 cm footprint at 20 m. Everything between the transducer and the geodetic
  frame is the limit.

### Practical rule for CARP

| Contact source | Expected datum quality | Search strategy |
|---|---|---|
| Survey-grade chain | decimetres | Drop on it, expect to be close, short spiral |
| Consumer sidescan | couple of metres | Full spiral search, budget the time |

### Free improvement available

If raw pings can be logged and the vessel nav shares a common timebase, the
sidescan can be **re-georeferenced in post** against the good nav. That yields
INS-quality position — still without roll correction, so probably decimetres
instead of metres. **Zero hardware cost.**

## Closing the loop

Log a rosbag with camera, attitude, depth, plus the kayak's GPS fix at anchor,
**all on one clock**. Each inspection then ties back to a specific contact in
the mosaic.

Over a season this builds a labelled truth set against sidescan imagery — which
is worth more than the inspections themselves if a detector is ever trained or
validated.

## The asymmetry that matters

Even with perfectly positioned contacts, **the ROV has no positioning**. If the
contact is known to 20 cm and the vehicle to ±3 m, the uncertainty is ±3 m.

Good sonar nav buys a *better datum* — the downline lands within a metre or two
instead of five or ten, so the spiral is short and the target is found on the
first pass. It makes the downline more valuable, not obsolete.

**This is the argument for prioritising acoustic ranging** (`navigation.md`
Method 4): it addresses the side of the chain with metres of slop in it.
