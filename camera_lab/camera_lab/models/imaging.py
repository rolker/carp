"""Resolution on target, motion blur and data rates for one camera.

The ground sample distance (GSD) is the size on the target of one pixel. On
a flat target square to the axis, at range z (mm) and ray angle theta, with
the local scale p (pixels per radian) of the image in the medium:

    GSD = z / (cos^2(theta) p)        (on axis: z / f_px)

because a small angle d_theta covers z d_theta / cos^2(theta) along the
target. Motion blur is the distance the target moves during the exposure
expressed in pixels: v t_exp / GSD, for motion across the view.

Limits worth remembering: this counts pixels, not detail. Lens sharpness
(MTF), demosaicing of a colour sensor (about two pixels per resolvable line
pair), compression and turbid water all cost resolution; `contrast_remaining`
in `media.py` sketches the water.
"""
import numpy as np


def ground_sample_mm(z_mm, px_per_rad, theta_rad=0.0):
    """Size (mm) on a flat target square to the axis of one pixel."""
    return np.asarray(z_mm, float) / (np.cos(theta_rad) ** 2 * px_per_rad)


def pixels_on_target(size_mm, z_mm, px_per_rad, theta_rad=0.0):
    """How many pixels span a target of `size_mm`."""
    return size_mm / ground_sample_mm(z_mm, px_per_rad, theta_rad)


def range_for_pixels_mm(size_mm, pixels, px_per_rad):
    """On-axis range (mm) at which a target of `size_mm` spans `pixels`."""
    return size_mm * px_per_rad / pixels


def motion_blur_px(speed_mm_s, exposure_s, z_mm, px_per_rad, theta_rad=0.0):
    """Blur length (px) for motion across the view at `speed_mm_s`."""
    return speed_mm_s * exposure_s / ground_sample_mm(z_mm, px_per_rad, theta_rad)


def max_exposure_s(blur_px, speed_mm_s, z_mm, px_per_rad, theta_rad=0.0):
    """Longest exposure (s) that keeps blur within `blur_px`."""
    return blur_px * ground_sample_mm(z_mm, px_per_rad, theta_rad) / speed_mm_s


def frame_overlap(speed_mm_s, fps, z_mm, full_fov_deg):
    """Fraction of a frame's footprint, in the direction of travel, still in
    the next frame: 1 - v / (fps W) with W the footprint extent along the
    travel direction (use the vertical field of view for forward motion in a
    landscape image, the horizontal one for sideways motion)."""
    w = 2 * np.asarray(z_mm, float) * np.tan(np.radians(full_fov_deg) / 2)
    return np.clip(1 - speed_mm_s / fps / w, 0, 1)


def raw_data_rate_mbit_s(width_px, height_px, bits_per_pixel, fps):
    """Uncompressed rate (Mbit/s, 1e6 bits) for one camera."""
    return width_px * height_px * bits_per_pixel * fps / 1e6


def encoded_data_rate_mbit_s(width_px, height_px, fps, bits_per_pixel_encoded):
    """Encoded rate (Mbit/s) for a chosen compressed size per pixel; a
    setting, since it depends on the encoder and the scene."""
    return width_px * height_px * fps * bits_per_pixel_encoded / 1e6


def storage_gb_per_hour(rate_mbit_s, cameras=1):
    """Storage (GB, 1e9 bytes) per hour for `cameras` streams."""
    return rate_mbit_s * cameras * 3600 / 8 / 1000
