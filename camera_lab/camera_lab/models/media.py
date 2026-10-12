"""Optical properties of the media the cameras look through.

Sources
-------
* Quan and Fry (1995), "Empirical equation for the index of refraction of
  seawater", Applied Optics 34(18), 3477-3480. Valid for salinity 0-35 PSU,
  temperature 0-30 C, wavelength 400-700 nm. The coefficients below were
  written from memory; `tests/test_models.py` checks that they reproduce the
  textbook values (fresh water 1.3331 at 589 nm and 20 C, seawater near
  1.339).
* Visibility to attenuation: the rule of thumb c = 4.6 / V (Koschmieder
  contrast threshold of 1 %). A rule of thumb, not a measurement: real
  water differs between "visibility" as a diver sees it, Secchi depth and
  the beam attenuation coefficient. Marked as such wherever it is used.
"""
import numpy as np

N_AIR = 1.0003          # at 1 atm, 15 C, visible light (textbook value)

_QF = dict(n0=1.31405, n1=1.779e-4, n2=-1.05e-6, n3=1.6e-8, n4=-2.02e-6,
           n5=15.868, n6=0.01155, n7=-0.00423, n8=-4382.0, n9=1.1455e6)


def water_refractive_index(wavelength_nm=550.0, temperature_c=15.0,
                           salinity_psu=0.0):
    """Refractive index of water (Quan and Fry 1995).

    Valid 400-700 nm, 0-30 C, 0-35 PSU; outside that it still answers (the
    caller can compare with `water_index_is_valid`)."""
    q, S, T, L = _QF, salinity_psu, temperature_c, np.asarray(wavelength_nm, float)
    return (q["n0"] + (q["n1"] + q["n2"] * T + q["n3"] * T * T) * S
            + q["n4"] * T * T + (q["n5"] + q["n6"] * S + q["n7"] * T) / L
            + q["n8"] / L ** 2 + q["n9"] / L ** 3)


def water_index_is_valid(wavelength_nm, temperature_c, salinity_psu):
    """Whether the inputs are inside the range of the Quan-Fry fit."""
    return (400 <= wavelength_nm <= 700 and 0 <= temperature_c <= 30
            and 0 <= salinity_psu <= 35)


def attenuation_from_visibility(visibility_m):
    """Beam attenuation coefficient c (1/m) from a visibility (m), by the
    rule of thumb c = 4.6 / V (1 % contrast threshold)."""
    return 4.6 / visibility_m


def contrast_remaining(range_m, visibility_m):
    """Fraction of an object's inherent contrast left after `range_m` of
    water, exp(-c r) with c from `attenuation_from_visibility`. By
    construction it is 1 % at the visibility. Ignores veiling light and
    illumination; a sketch of the later visibility page."""
    return np.exp(-attenuation_from_visibility(visibility_m) * np.asarray(range_m, float))
