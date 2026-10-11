"""Audio device access for the acoustic ranging tests, through PyAudio.

Kept apart from ranging_dsp.py so the processing can be tested without any
audio hardware. PyAudio comes from apt (python3-pyaudio), the same system
Python that ROS uses.
"""
import contextlib
import os
import sys
import threading

import numpy as np
import pyaudio

TEST_RATES = (44100, 48000, 96000, 192000)


@contextlib.contextmanager
def _quiet():
    """Hide what ALSA and JACK print while PortAudio probes for devices.

    They write straight to stderr for every device name that does not exist
    on this machine, which buries the real output. Python errors still show.
    """
    sys.stderr.flush()
    saved = os.dup(2)
    null = os.open(os.devnull, os.O_WRONLY)
    try:
        os.dup2(null, 2)
        yield
    finally:
        os.dup2(saved, 2)
        os.close(null)
        os.close(saved)


def _open_portaudio():
    with _quiet():
        return pyaudio.PyAudio()


def _supports(pa, rate, index, channels, is_input):
    kwargs = dict(input_device=index, input_channels=channels,
                  input_format=pyaudio.paInt16) if is_input else dict(
                  output_device=index, output_channels=channels,
                  output_format=pyaudio.paInt16)
    try:
        return pa.is_format_supported(rate, **kwargs)
    except ValueError:
        return False


def _open_with_retry(pa, attempts=3, **kwargs):
    """Open a stream, trying again if it times out while starting.

    Through WSL's sound bridge the microphone side takes about a second to
    connect, longer than PortAudio waits, so the first try fails and the
    second works. Real sound cards start at once.
    """
    for attempt in range(attempts):
        try:
            with _quiet():      # PortAudio prints its own trace on a timeout
                return pa.open(**kwargs)
        except OSError as error:
            if error.errno != pyaudio.paTimedOut or attempt + 1 == attempts:
                raise


def list_devices():
    """One dict per device, with the sample rates it accepts each way.

    Only "hw:" devices report what the hardware really does. Devices such as
    "default" or "pulse" convert behind the scenes and accept nearly anything.
    """
    pa = _open_portaudio()
    try:
        devices = []
        for index in range(pa.get_device_count()):
            info = pa.get_device_info_by_index(index)
            inputs = int(info["maxInputChannels"])
            outputs = int(info["maxOutputChannels"])
            devices.append(dict(
                index=index, name=info["name"],
                api=pa.get_host_api_info_by_index(info["hostApi"])["name"],
                inputs=inputs, outputs=outputs,
                input_rates=[r for r in TEST_RATES if inputs and _supports(
                    pa, r, index, 1, True)],
                output_rates=[r for r in TEST_RATES if outputs and _supports(
                    pa, r, index, min(outputs, 2), False)]))
        return devices
    finally:
        pa.terminate()


def play_and_record(playback, rate, input_device=None, output_device=None,
                    block=1024):
    """Play a stereo float array while recording one input channel.

    Two separate streams, because a cheap dongle is stereo out and mono in
    and one duplex stream cannot have both. The offset between the streams
    is unknown, which is fine: the loopback copy in the recording is the
    time reference. Returns (mono float32 recording, list of warnings).

    The whole ping is handed to PortAudio in one write, and the recording
    is taken in a few long reads on another thread. Feeding it block by
    block from Python left gaps in the playback whenever the program was
    busy (redrawing plots, or at 96 kHz), because the audio thread had to
    wait its turn for the interpreter.
    """
    frames = (np.clip(playback, -1.0, 1.0) * 32767).astype("<i2").tobytes()
    total = playback.shape[0] + int(0.1 * rate)   # let the tail reach the recorder
    chunk = int(0.25 * rate)
    chunks = []
    warnings = set()
    input_channels = 1

    def read_all(stream):
        remaining = total
        while remaining > 0:
            count = min(chunk, remaining)
            try:
                chunks.append(stream.read(count, exception_on_overflow=True))
            except OSError as error:
                if error.errno != pyaudio.paInputOverflowed:
                    warnings.add(f"recording stopped early: {error}")
                    return
                warnings.add("input overflow (samples lost)")
                chunks.append(bytes(2 * input_channels * count))
            remaining -= count

    pa = _open_portaudio()
    try:
        common = dict(rate=rate, format=pyaudio.paInt16,
                      frames_per_buffer=block)
        try:
            recorder = _open_with_retry(pa, channels=1, input=True,
                                        input_device_index=input_device,
                                        **common)
        except OSError as error:
            if error.errno != pyaudio.paInvalidChannelCount:
                raise
            # Some inputs only come in stereo; record both, keep the first.
            input_channels = 2
            recorder = _open_with_retry(pa, channels=2, input=True,
                                        input_device_index=input_device,
                                        **common)
        reader = threading.Thread(target=read_all, args=(recorder,))
        reader.start()
        try:
            player = _open_with_retry(pa, channels=2, output=True,
                                      output_device_index=output_device,
                                      **common)
            try:
                player.write(frames, exception_on_underflow=True)
            except OSError as error:
                if error.errno != pyaudio.paOutputUnderflowed:
                    raise
                warnings.add("output underflow (gap in playback)")
            player.stop_stream()
            player.close()
        finally:
            reader.join()
            recorder.stop_stream()
            recorder.close()
    finally:
        pa.terminate()
    recording = np.frombuffer(b"".join(chunks), dtype="<i2")
    recording = recording.reshape(-1, input_channels)[:, 0]
    return recording.astype(np.float32) / 32768.0, sorted(warnings)
