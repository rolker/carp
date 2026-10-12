"""Stereo with two parallel, rectified cameras.

Symbols: z range along the optical axes (mm), B baseline (mm, distance
between the two entrance pupils), f_px focal length in pixels (focal length
divided by pixel pitch, in the medium the points are in), d disparity (px,
x_left - x_right of the same point).

    d = f_px B / z                      depth from disparity z = f_px B / d
    dz = z^2 dd / (f_px B)              first-order error from a disparity
                                        error dd (differentiate z = f B / d)
    z_min = f_px B / d_max              nearest range if the matcher searches
                                        at most d_max pixels
    z for a relative error e:  z = e f_px B / dd

Source: any stereo text, e.g. Hartley and Zisserman, "Multiple View Geometry",
ch. 9-10, or Szeliski, "Computer Vision: Algorithms and Applications", 12.1.
The formulas assume a pinhole model per camera; a fisheye lens is first
rectified to a pinhole image, with f_px the on-axis value. Off-axis the
angular form is used (`range_error_off_axis_mm`).

Underwater, f_px is the in-water value: through a dome with the pupil at the
centre it is the in-air value; behind a flat port it is n_water times larger
near the axis (`ports.py`) because the angles shrink.
"""
import numpy as np


def disparity_px(z_mm, f_px, baseline_mm):
    """Disparity (px) of a point at range z (mm)."""
    return f_px * baseline_mm / np.asarray(z_mm, float)


def depth_from_disparity_mm(d_px, f_px, baseline_mm):
    """Range (mm) from a disparity (px)."""
    return f_px * baseline_mm / np.asarray(d_px, float)


def depth_error_mm(z_mm, f_px, baseline_mm, disparity_error_px):
    """Range error (mm), one standard deviation if `disparity_error_px` is
    one: z^2 dd / (f_px B). First order; valid while the error is small
    against z (the exact two-sided interval is z^2 dd / (f B +- z dd))."""
    z = np.asarray(z_mm, float)
    return z ** 2 * disparity_error_px / (f_px * baseline_mm)


def range_for_relative_error_mm(relative_error, f_px, baseline_mm, disparity_error_px):
    """Range (mm) at which the depth error equals `relative_error` (0.05 =
    5 %) of the range: z = e f_px B / dd."""
    return relative_error * f_px * baseline_mm / disparity_error_px


def min_range_for_disparity_mm(f_px, baseline_mm, max_disparity_px):
    """Nearest range (mm) the matcher can resolve if it searches at most
    `max_disparity_px` pixels: f_px B / d_max."""
    return f_px * baseline_mm / max_disparity_px


def range_error_off_axis_mm(r_mm, bearing_rad, px_per_rad, baseline_mm, disparity_error_px):
    """Range error for a point at range r and bearing theta from the rig's
    axis, in the plane of the baseline. For r much larger than B the angular
    parallax is B cos(theta) / r, one pixel of disparity is 1 / px_per_rad
    of angle at that bearing, so dr = r^2 dd / (px_per_rad B cos(theta))."""
    return (np.asarray(r_mm, float) ** 2 * disparity_error_px
            / (px_per_rad * baseline_mm * np.cos(bearing_rad)))


def footprint_width_mm(z_mm, full_fov_deg):
    """Width (mm) of the strip of a flat target square to the axis, at range
    z, that a camera with this full field of view sees: 2 z tan(fov / 2).
    Infinite at 180 degrees and more."""
    half = np.radians(full_fov_deg) / 2
    if half >= np.pi / 2:
        return np.full_like(np.asarray(z_mm, float), np.inf)
    return 2 * np.asarray(z_mm, float) * np.tan(half)


def overlap_fraction(z_mm, baseline_mm, full_fov_deg):
    """Fraction of one camera's footprint on a flat target square to the
    axes, at range z, that the other camera also sees (parallel cameras):
    1 - B / W with W the footprint width. 0 where the footprints do not
    meet."""
    w = footprint_width_mm(z_mm, full_fov_deg)
    return np.clip(1 - baseline_mm / w, 0, 1)


def first_overlap_range_mm(baseline_mm, full_fov_deg):
    """Range (mm) at which the two footprints first touch, B / (2 tan(fov/2)).
    Nothing nearer can be seen by both cameras."""
    return baseline_mm / (2 * np.tan(np.radians(full_fov_deg) / 2))


def range_for_overlap_mm(fraction, baseline_mm, full_fov_deg):
    """Range (mm) at which `overlap_fraction` reaches `fraction`:
    B / ((1 - fraction) 2 tan(fov/2))."""
    return baseline_mm / ((1 - fraction) * 2 * np.tan(np.radians(full_fov_deg) / 2))


def sync_depth_error_mm(z_mm, speed_mm_s, sync_s, baseline_mm):
    """Depth error (mm) from the two frames being taken `sync_s` apart while
    the vehicle moves sideways (along the baseline) at `speed_mm_s`: the
    target shifts by v t, which reads as a disparity error
    f_px v t / z, and so as dz = z^2 (f_px v t / z) / (f_px B) = z v t / B.
    Independent of the lens. Forward motion adds `sync_forward_error_mm`."""
    return np.asarray(z_mm, float) * speed_mm_s * sync_s / baseline_mm


def sync_forward_error_mm(speed_mm_s, sync_s):
    """Position error (mm) along the axes from the two frames being
    `sync_s` apart while moving forward at `speed_mm_s`: v t. (Forward motion
    changes the disparity only through the change in range, so this is
    the whole effect to first order.)"""
    return speed_mm_s * sync_s


def sync_disparity_error_px(z_mm, speed_mm_s, sync_s, f_px):
    """The sideways sync error as a disparity error in pixels,
    f_px v t / z; compare with the matcher's own disparity accuracy."""
    return f_px * speed_mm_s * sync_s / np.asarray(z_mm, float)
