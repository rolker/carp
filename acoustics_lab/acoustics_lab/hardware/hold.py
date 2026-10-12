"""Taking hold of a sound card and putting everything back.

The sequence that `tools/duplex_check.py` worked out on the laptop's card, as
reusable code, for the tool and for the hardware backend alike:

1. save the desktop's own volumes for the card, then the hardware mixer;
2. apply the settings the run wants (mixer controls), then start watching the
   mixer for changes by anyone else;
3. borrow the card from the sound server (device reservation) and open it;
4. ... the run ...
5. stop watching and report what changed; put the mixer back; give the card
   back; wait for the desktop to make its sinks and sources again and put its
   volumes back; check the mixer once more.

The pieces are functions taking `say(text)` and `warn(text)`, so a command
line can print them and a window can collect them. `CardHold` strings them
together for one card. Nothing here opens an audio stream; the module looks
up `reserve.Reservation`, `mixer` and `desktop` when it runs, so a test can
replace them with fakes.
"""
from . import desktop, mixer, reserve


# ---- the pieces ---------------------------------------------------------------

def borrow(card, say, warn):
    """Borrow the card from the desktop's sound server before its hw: device
    is opened. Returns the Reservation (to give back afterwards). A refusal
    or a missing session bus is a warning, not a failure: the open is tried
    anyway."""
    reservation = reserve.Reservation(card.number)
    reservation.acquire()
    for line in reservation.describe():
        (say if reservation.ok else warn)(line)
    return reservation


def give_back(reservation, say):
    """Release a borrowed card and say what happened to it."""
    if reservation is None:
        return
    reservation.release()
    for line in reservation.describe_release():
        say(line)


def save_desktop(card, say, warn):
    """Save the desktop's volumes for the card, before anything touches it.
    A missing sound server or Python binding is a warning, not a failure.
    Returns (saved, backend) or None."""
    backend, note = desktop.default_backend()
    if note:
        warn(note)
    if backend is None:
        return None
    try:
        saved = desktop.save(card.number, backend)
    except desktop.DesktopError as error:
        warn(f"Could not save the desktop's volumes, so they will not be put "
             f"back: {error}")
        return None
    for line in saved.lines():
        say(line)
    return saved, backend


def save_mixer(card, say, warn,
               note="Mixer settings saved; they are put back after the run."):
    """The card's mixer as it is now, for putting back; None (with a
    warning) if it cannot be read."""
    try:
        saved = mixer.snapshot(card.number)
    except mixer.MixerError as error:
        warn(f"Could not save the mixer settings, so they will not be put "
             f"back: {error}")
        return None
    say(note)
    return saved


def start_watching(card, say, warn):
    """Watch the card's mixer for changes made while the run goes on.
    Returns the Watcher, or None."""
    try:
        watcher = mixer.Watcher(card.number).start()
    except mixer.MixerError as error:
        warn(f"Not watching the mixer for changes: {error}")
        return None
    if watcher.mode == "polling":
        say("The mixer is watched by reading it every "
            f"{watcher.interval:g} s (no change events from this backend).")
    return watcher


def apply_settings(card, assignments, say):
    """Set mixer controls from (name, value) pairs, reading each back.
    Returns 0 if all took, 1 if one did not, 2 for a bad pair or a mixer
    error (a message is said)."""
    code = 0
    for name, value in assignments:
        try:
            result = mixer.set_control(card.number, name.strip(), str(value).strip())
        except mixer.MixerError as error:
            say(f"cannot set '{name}': {error}")
            return 1
        status = "ok" if result.verified else f"NOT AS ASKED ({result.note})"
        say(f"set {result.control.name} = {value}: read back "
            f"{result.control.value_text()} (was {result.before}): {status}")
        code = code or (0 if result.verified else 1)
    return code


def report_changes(card, changes, watcher, say, warn):
    """Say what changed the mixer while the card was in use."""
    if watcher.error:
        warn(f"Watching the mixer of {card.label()} stopped: {watcher.error}")
    if changes:
        warn(f"Something changed the mixer of {card.label()} during the test "
             "(the desktop's sound server, or another program):\n"
             + "\n".join("  " + c.text() for c in changes))
    elif not watcher.error:
        say(f"Nothing changed the mixer of card {card.number} during the "
            f"test (watched through {watcher.mode}).")


def put_back_mixer(card, saved, say, warn):
    """Restore the mixer settings saved before a run, so the desktop gets
    the card back as it was."""
    try:
        restored, failed = mixer.restore(card.number, saved)
    except mixer.MixerError as error:
        warn(f"Could not put the mixer of {card.label()} back: {error}")
        return
    if restored:
        say(f"Mixer of card {card.number} put back as before the test: "
            + "; ".join(f"{name} = {value}" for name, value in restored))
    for name, error in failed:
        warn(f"Could not put back {name}: {error}")


def put_back_desktop(card, saved, backend, say, warn):
    """After the card is back with the desktop: wait for its sinks and
    sources to reappear, set the saved volumes and mute, and say whether they
    stayed. Returns the desktop.Result."""
    if saved.nodes:
        say(f"Waiting for the desktop to take card {card.number} back, to "
            "put its volumes back ...")
    result = desktop.restore(saved, backend)
    if not saved.nodes:
        return result
    if result.ok:
        say(f"Desktop volumes of card {card.number} are as before the test "
            f"(the sound server had them again after {result.waited:.1f} s):")
        for line in result.lines():
            say("  " + line)
        return result
    warn(f"The desktop volumes of card {card.number} are NOT as before the "
         "test:\n" + "\n".join("  " + line for line in result.lines())
         + "\nTo set them by hand:\n"
         + "\n".join("  " + c for c in result.fix_commands()))
    return result


def verify_mixer(card, saved, say, warn):
    """Compare the hardware mixer with what was saved, after the desktop
    has taken the card back and put its volumes back (it may change the
    mixer too)."""
    try:
        different = mixer.differences(card.number, saved)
    except mixer.MixerError as error:
        warn(f"Could not check the mixer of {card.label()}: {error}")
        return
    if not different:
        say(f"Mixer of card {card.number} is as before the test.")
        return
    commands = [f"  python3 tools/duplex_check.py --device {card.number} --mixer "
                f"--set '{d.name}={d.setting}'" for d in different if d.setting]
    warn(f"The mixer of {card.label()} is NOT as before the test, after the "
         "desktop took the card back:\n"
         + "\n".join(f"  {d.name}: was {d.saved}, is {d.now}" for d in different)
         + "\nTo set them back:\n" + "\n".join(commands))


# ---- the whole sequence for one card -------------------------------------------

class CardHold:
    """Everything a run takes hold of on one card, put back in the right
    order by `finish()`. `say` and `warn` receive plain sentences; the
    `messages` list keeps (level, text) for a window to show.

    Typical use (exclusive access)::

        hold = CardHold(card)
        hold.prepare({"Master Playback Volume": "-15dB"})  # saves, then sets
        hold.borrow()                                       # then open the hw: device
        ...
        hold.finish()                                       # after closing the device
    """

    def __init__(self, card, say=None, warn=None):
        self.card = card
        self.messages = []
        self._say, self._warn = say, warn
        self.reservation = None
        self.mixer_saved = None
        self.desktop_saved = None           # (desktop.Saved, backend)
        self.watcher = None
        self.changes = []
        self.applied = {}                   # control -> value asked for
        self.finished = False

    def say(self, text):
        self.messages.append(("info", text))
        if self._say:
            self._say(text)

    def warn(self, text):
        self.messages.append(("warning", text))
        if self._warn:
            self._warn(text)

    def save(self, desktop_too=True):
        """Save the desktop's volumes and the mixer, before anything is set."""
        if desktop_too:
            self.desktop_saved = save_desktop(self.card, self.say, self.warn)
        self.mixer_saved = save_mixer(self.card, self.say, self.warn)

    def apply(self, settings):
        """Set mixer controls from a dict of name -> value."""
        pairs = [(k, v) for k, v in dict(settings or {}).items() if str(v).strip()]
        if pairs:
            apply_settings(self.card, pairs, self.say)
            self.applied.update(dict(pairs))

    def watch(self):
        self.watcher = start_watching(self.card, self.say, self.warn)

    def prepare(self, settings=None):
        """save(), apply(settings), watch(): everything before the card is
        borrowed."""
        self.save()
        self.apply(settings)
        self.watch()

    def borrow(self):
        self.reservation = borrow(self.card, self.say, self.warn)
        return self.reservation

    def seen_changes(self):
        """What changed the mixer so far (plain sentences)."""
        return [c.text() for c in self.watcher.seen()] if self.watcher else []

    def finish(self):
        """Put everything back, in order, and say what was found. Safe to
        call twice."""
        if self.finished:
            return
        self.finished = True
        if self.watcher is not None:
            self.changes = self.watcher.stop()
            report_changes(self.card, self.changes, self.watcher, self.say, self.warn)
        if self.mixer_saved is not None:
            put_back_mixer(self.card, self.mixer_saved, self.say, self.warn)
        give_back(self.reservation, self.say)
        if self.desktop_saved is not None:
            put_back_desktop(self.card, *self.desktop_saved, self.say, self.warn)
        if self.mixer_saved is not None:
            verify_mixer(self.card, self.mixer_saved, self.say, self.warn)
