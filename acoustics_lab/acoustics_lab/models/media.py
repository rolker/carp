"""Sound speed and wavelength. Pure functions; the medium is always passed in.

Step 1 has air only. Water (TEOS-10, Mackenzie, Chen-Millero) comes with the
sound speed page.
"""
import numpy as np


def sound_speed_air(temperature_c):
    """Speed of sound in dry air, m/s, from the temperature in degrees C.

    c = 331.3 * sqrt(1 + T / 273.15). Good to about 0.1 m/s from -20 to
    +40 C; humidity adds up to about 0.5 m/s at 20 C and is left out.
    """
    return 331.3 * np.sqrt(1.0 + temperature_c / 273.15)


def wavelength(speed, frequency):
    """Wavelength in m, from sound speed in m/s and frequency in Hz."""
    return speed / frequency
