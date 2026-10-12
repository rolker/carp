"""The lowest hardware layer: sound cards, their mixers and duplex streams.

No Qt anywhere in this package; it also has to run headless on a Raspberry
Pi. A future hardware backend sits on top of it. Nothing in `backends/`
imports it yet.

- `discovery`: ALSA cards, their USB identity and the PortAudio devices.
- `stream`: `DuplexDevice`, the interface (sample counter, output scheduler,
  input ring, xrun log), and `PortAudioDuplex`, the real device.
- `fake`: `FakeDevice`, the same interface with no hardware.
- `alsa_ctl`: ALSA's control API in libasound, through ctypes.
- `mixer`: ALSA mixer controls (save, restore, set, watch for changes) on top of it.
- `desktop`: the sound server's own volumes for a card (save, restore, verify).
- `checks`: the offset test and the schedule test, as library functions.
- `reserve`: borrow a card from the desktop's sound server (device reservation) and give it back.
"""
