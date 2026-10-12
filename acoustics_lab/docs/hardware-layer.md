# Hardware layer

The lowest layer for real sound hardware, under the hardware backend of
design step 2 (`design.md`, "Backend interface"). It lives in
`acoustics_lab/hardware/`, has no Qt, and nothing in `backends/` uses it yet.
`tools/duplex_check.py` is the command-line check to run on a new dongle.

## What is in it

| Module | Does |
|---|---|
| `discovery` | ALSA cards from `/proc/asound/cards` and sysfs: card number, card id, USB vendor:product, USB port path (`1-2.3`), serial if any; the PortAudio `hw:` device for each, with its rates. Look a card up by number, id or port path. Never touches `default`, `pulse`, `pipewire` or `plughw`. |
| `stream` | `DuplexDevice` (interface and core) and `PortAudioDuplex` (the real stream). |
| `fake` | `FakeDevice`: the same core with a simulated loopback. |
| `mixer` | `amixer -c N contents` parsed; set a control, read it back, verify; dB ranges; the controls that matter are flagged. |
| `checks` | The offset test and the schedule test as functions on any device. |
| `reserve` | Borrow a card from the desktop's sound server (device reservation over D-Bus) and give it back; see "Borrowing a card". |

## Borrowing a card from the desktop

The desktop's sound server (PipeWire with WirePlumber, PulseAudio) keeps
sound cards open, and a card opened as `hw:N` is exclusive. `reserve.py`
takes a card over the way other audio programs do, through the freedesktop
device-reservation protocol (`org.freedesktop.ReserveDevice1`) on the
session bus, so no configuration changes and no sound server stops.

**How it works.** The holder of card N owns the bus name
`org.freedesktop.ReserveDevice1.AudioN` (ALSA card N is `AudioN`) and
exports `RequestRelease(priority) -> bool` and the properties `Priority`,
`ApplicationName`, `ApplicationDeviceName`. `acquire()`:

1. tries to own the name; if free, the card is ours (a headless Pi, or a
   USB dongle the server ignores);
2. otherwise reads who holds it, calls `RequestRelease` with our priority
   (100; WirePlumber holds at -20 and gives way to anything higher);
3. if the answer is yes, takes the name over when the holder lets go of it;
   if no, reports who refused and carries on (a warning: the open that
   follows then fails as busy, with a message saying so);
4. with no session bus (or no python3-gi) it says "not reserved" and
   carries on.

While we hold the card we answer `RequestRelease` from others from a thread
of the program. The default policy refuses (a test must not lose its card
halfway) and logs the request; `Reservation(release=...)` takes `"refuse"`,
`"release"`, `"priority"` (give way to a higher priority than ours, as the
spec suggests) or a function of the asker's priority.

**If the program dies.** The reservation is the bus name, which belongs to
this process's own D-Bus connection (GDBus from python3-gi, served by a
thread). When the process ends, however it ends (exception, Ctrl-C,
SIGTERM, SIGKILL), the bus closes the connection and drops the name, and
the desktop takes the card back. There is no helper process to outlive us.
A test starts a child that holds a card, SIGKILLs it, and checks the name is
gone. (python3-dbus crashed when a connection was used from two threads, so
GDBus is used instead.)

```python
from acoustics_lab.hardware import reserve
with reserve.borrow(1) as card:        # ALSA card number
    print(*card.describe())            # who had it, whether they gave it up
    ...                                # open hw:1 here
print(*card.describe_release())        # who has it back
```

**What `duplex_check.py` does with it.** For a test it borrows the card
before PortAudio looks at it (built-in cards, USB dongles the server has
grabbed, and cards nobody holds alike) and gives it back afterwards, on
errors and Ctrl-C too. It prints who held the card and whether they let go,
and after the test who has it back. `--no-borrow` skips all this, for
debugging. `--mixer` on its own reads and sets the mixer without borrowing.

For the built-in card, after borrowing and before playing, it also reads
the mixer: it warns if the internal speakers are on (while borrowed the
desktop's port switching is not in charge, so the test signal can come out
of the laptop speakers as well as the jack), printing the exact `--mixer
--set 'Speaker Playback Switch=off'` command, and says which `Capture
Source` (Internal Mic, Headset Mic, Headphone Mic) is being recorded,
warning when it is the internal one. Mixer settings stay changed afterwards;
set them back by hand if wanted (the first line of `--mixer` shows them).

**Checking by hand.**

- `busctl --user list | grep ReserveDevice1` shows who owns each card's
  name. Normally `wireplumber` owns `...Audio0`, `...Audio1`. During a test
  `Audio1` is owned by the python process, and afterwards by `wireplumber`
  again.
- `busctl --user get-property org.freedesktop.ReserveDevice1.Audio1
  /org/freedesktop/ReserveDevice1/Audio1 org.freedesktop.ReserveDevice1
  ApplicationName` (also `Priority`, `ApplicationDeviceName`) says who it is
  and at what priority; during a test it is `acoustics_lab`, 100.
- `pw-reserve -n Audio1 -m` (from PipeWire) only monitors a name. Without
  `-m` it tries to acquire it (`-r`: and asks the holder to release), which
  takes the card from the desktop just as a test does; do not do that while
  a test is running.
- Desktop sound is back when `wpctl status` lists the card's sink again.

## The duplex stream

One PortAudio callback stream per device, input and output together, int16,
the device's native rate (default 48 kHz on a dongle), started once and left
running. PyAudio can only open a duplex stream with the same channel count
both ways, and a dongle is stereo out and mono in, so the stream is opened
through `libportaudio` with `ctypes`.

- **Sample counter.** One per device, on its own clock. Output sample `n`
  is the first frame the callback produces when the counter is `n`; input
  sample `n` is the first frame it receives then.
- **Output.** `schedule(samples, start, channel, gain)` plays `samples`
  from output sample `start`. Any number of items may be pending, on either
  channel; they are added and clipped. Silence otherwise. An item whose
  start has already passed raises `LateError` (or, with `late="play"`, plays
  the rest and sets `skipped` on the handle).
- **Input.** A ring of 30 s. `read_input(a, b)` returns samples `a..b`;
  asking for samples not yet captured, or already overwritten, raises
  `LostDataError`. `wait_input(n)` blocks until sample `n` has arrived.
- **Xruns.** PortAudio's callback status flags are counted per kind and
  logged with the sample number of the block (`xruns()`,
  `xruns_between(a, b)`). A capture whose range overlaps one should be
  thrown away. The "priming" flag is not a fault and is ignored.
- **Callback.** Copies the input into the ring, adds the pending items
  into the output block, logs flags. Items are converted to int16 when
  scheduled, in the caller's thread. The callback takes no lock.

## How timing is handled

Output sample `n` is not heard at input sample `n`: the output passes the
DAC and USB buffers, the input the ADC's. The delay between them is the
**offset**, and it is *measured*, never computed. A resistor from an output
channel into the mic input puts an electrical copy of everything played into
the recording; the offset is where a scheduled ping is found in the input,
minus where it was scheduled. PortAudio's own time stamps give a figure
too (`timing()["claimed_offset_samples"]`); it is kept and printed beside the
measured one, and not used.

A pulse can only start on a whole output sample. At 48 kHz that is 20.8 us
per sample, 7.1 mm of sound in air. Arrivals are located to a fraction of a
sample (matched filter, band-limited 16x interpolation, parabola on the
envelope top).

**Xruns shift timing.** If the input drops samples, the input counter falls
behind real time while the output counter does not, and the offset steps
by the number of samples lost, permanently until the stream restarts. So a
dropout is a reason to distrust everything after it, not only the block.
The offset test shows it as a step.

**Clocks.** Each device has its own clock. `timing()["clock_ratio"]` compares
the device's sample count with PortAudio's time (a ratio of 1.0001 means 100
ppm fast). Comparing two devices needs a shared signal, as in the design's
"clocks are compared by measurement"; not built here.

## Running the checks when the dongles arrive

All from `acoustics_lab/`. Nothing is opened unless a device is named. Close
anything else using the dongle (it is exclusive). If the desktop's sound
server has picked the card up, the tool borrows it first (see "Borrowing a
card from the desktop") and returns it afterwards.

1. `python3 tools/duplex_check.py --list`. Each dongle is marked `[USB]`
   with its vendor:product, port path, whether it has a serial number, and
   the rates PortAudio accepts both ways. Expect `1 in / 2 out`, 48 kHz.
   Identical dongles with no serial: tell them apart by port path, and
   keep each in its socket. Note the chipset's vendor:product.
2. `python3 tools/duplex_check.py --device <port or id> --mixer`. Look at
   the flagged controls: playback volume, capture volume, **Auto Gain Control
   (should be off)**, **mic playback / monitor (should be off)**. Set them
   with `--set 'NAME=VALUE'` (`60%`, `-6dB`, `off`, a raw number); the tool
   reads back and says if it took. Write down the volumes: they set how
   loud the output is.
3. Wire the loopback resistor (output to mic input, as in the bench
   circuit). With a disc or headphones attached, keep it away from ears.
4. `python3 tools/duplex_check.py --device <...> --offset-test --minutes 1 --channel left`
   (a quick one). Then `--minutes 5` for the real one.
5. `python3 tools/duplex_check.py --device <...> --schedule-test --tat 0.2`.
6. Repeat 4 after unplugging and replugging, and on each dongle.

Output level defaults to -20 dBFS; above -6 dBFS, and any card that is not
on USB (it is borrowed from the desktop, whose sound on it stops meanwhile),
get a prominent warning rather than a refusal. Above 0 dBFS the
output is clipped flat at full scale, as a sound card would, to show what
clipping does. The plan,
with the loudness and the mixer settings, is printed first and there is a
3 s pause (`--no-wait` skips it).

Results go to `acoustics_lab/runs/hardware/<time>_<card>_<test>/` (git-ignored):
`offset.csv` or `schedule.csv` with every ping, and `summary.json`. Without
hardware, `--fake` runs the same tests on the simulated dongle in seconds.

## What to look for

- **Offset test.** A line like "Offset steady to +-0.1 sample over 5 min, no
  dropouts" is what a usable dongle gives. Look at:
  - *Spread / max deviation.* Under 0.5 sample is good enough for a fixed
    turnaround time; a few samples or more means the USB buffering moves.
  - *Drift.* A slope in samples per minute. Small and steady can be
    calibrated out; steps are not.
  - *Dropouts.* Any count is a problem to chase (try a larger `--block`,
    another USB port, no hub).
  - *Missed pings or "loopback" complaint:* wrong channel, resistor not
    wired, capture switch off, or the level too low/high (arrival level is
    printed; keep it between about -40 and -6 dBFS).
  - *Offset across restarts.* If it differs by whole blocks after
    replugging, it is not a constant of the dongle and has to be re-measured
    per session.
  - *PortAudio's claim vs measured.* Expect them to differ; that is why
    the loopback is the reference.
- **Schedule test.** The reply should land within the +-0.5 sample that
  whole-sample starts allow, a little more for noise. "Decision margin" is
  how long the program had between choosing a start and the output reaching
  it; a short margin means a shorter turnaround would fail. The reply offset
  here should agree with the offset test.
- **Mixer.** Whether the card has dB scales, whether AGC exists and
  stays off, whether the mic monitor exists.

## Only checkable on real hardware

- Borrowing from the real WirePlumber: the protocol is tested against a fake
  holder on a private bus. That WirePlumber agrees at priority 100, that the
  desktop's sink comes back after release, and what the built-in card's
  mixer looks like once borrowed, need the real session.

- The ctypes PortAudio stream itself (open, start, rate/channel acceptance,
  the callback's thread and GIL behaviour at 512-frame blocks). Its callback
  is tested by calling it with C buffers; the PortAudio calls are not.
- That a dongle accepts a duplex hw: stream with 1 in / 2 out at 48 kHz.
- Real xrun behaviour and start-up flags (ALSA often flags the first blocks;
  those are separated from flags during the test).
- The real amixer text of the dongle (parsed from written samples only), and
  what the chipset's controls are called.
- The size of real jitter and drift.
- Naming the cards: a udev rule setting `ATTR{id}` by `KERNELS` (the
  interface path `1-2.3:1.0` shown by `--list`) would give stable ids such
  as `donglea`; untested.

## Limits

- Playback and capture share one stream, so one rate and one block size.
- The ring holds one input channel (`input_channel`, default the first).
- No resampling, no format other than int16, no sample-rate conversion.
- One process per device: a second program on the same `hw:` card fails (a borrowed card is also refused to others who ask: see the release policy).
- A glitch in the callback (Python being slow) shows as an xrun, not hidden.
- Two devices are two independent streams and clocks; starting them is
  not simultaneous.
