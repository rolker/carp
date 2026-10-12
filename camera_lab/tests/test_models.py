"""Models against hand calculations. The arithmetic in the comments is done
by hand, not by the code under test."""
import math

import numpy as np
import pytest

from camera_lab.models import geometry, imaging, media, ports, projection, stereo, system


# ---- media ---------------------------------------------------------------

def test_fresh_water_index_at_sodium_d_line():
    # Textbook: 1.3330 at 589 nm, 20 C (Quan-Fry gives 1.33301).
    assert media.water_refractive_index(589, 20, 0) == pytest.approx(1.3330, abs=5e-4)


def test_seawater_index_is_higher_than_fresh_and_near_1_339():
    n = media.water_refractive_index(589, 15, 35)
    assert n == pytest.approx(1.3399, abs=1e-3)
    assert n > media.water_refractive_index(589, 15, 0)


def test_blue_bends_more_than_red():
    assert media.water_refractive_index(450) > media.water_refractive_index(650)


def test_contrast_is_one_percent_at_the_visibility():
    assert media.contrast_remaining(3.0, 3.0) == pytest.approx(0.01, rel=0.01)


# ---- projection ----------------------------------------------------------

def test_pinhole_fov_from_focal_length_and_sensor_size():
    # 6.4 mm wide sensor, 4 mm lens: 2 atan(3.2 / 4) = 2 * 38.66 = 77.32 deg.
    assert projection.full_fov_deg(6.4, 4.0, "rectilinear") == pytest.approx(77.32, abs=0.01)


def test_equidistant_fov():
    # 2.784 mm half width, f 2.1 mm: 2 * 2.784 / 2.1 rad = 2.6514 rad = 151.9 deg.
    assert projection.full_fov_deg(5.568, 2.1, "equidistant") == pytest.approx(151.91, abs=0.01)


def test_equisolid_and_stereographic_fov():
    # equisolid: 2 * 2 asin(2.784 / 4.2) ; sin^-1(0.66286) = 41.52 deg -> 166.1
    assert projection.full_fov_deg(5.568, 2.1, "equisolid") == pytest.approx(166.1, abs=0.1)
    # stereographic: 2 * 2 atan(2.784 / 4.2) = 4 * 33.54 = 134.2 deg
    assert projection.full_fov_deg(5.568, 2.1, "stereographic") == pytest.approx(134.2, abs=0.1)


@pytest.mark.parametrize("model", projection.MODELS)
def test_radius_and_angle_are_inverses_and_agree_on_axis(model):
    theta = np.radians([0.5, 10, 25])
    r = projection.image_radius_mm(theta, 2.5, model)
    assert projection.ray_angle_rad(r, 2.5, model) == pytest.approx(theta)
    small = projection.image_radius_mm(1e-4, 2.5, model)
    assert small == pytest.approx(2.5e-4, rel=1e-6)


@pytest.mark.parametrize("model", projection.MODELS)
def test_radial_scale_is_the_derivative_of_radius(model):
    t, h = 0.6, 1e-6
    numeric = (projection.image_radius_mm(t + h, 2.5, model)
               - projection.image_radius_mm(t - h, 2.5, model)) / (2 * h)
    assert projection.radial_scale_mm_per_rad(t, 2.5, model) == pytest.approx(numeric, rel=1e-6)


def test_focal_for_fov_inverts_fov():
    f = projection.focal_for_fov_mm(5.568, 141.4, "equidistant")
    assert f == pytest.approx(5.568 / 2 / math.radians(70.7), rel=1e-9)
    assert projection.full_fov_deg(5.568, f, "equidistant") == pytest.approx(141.4)


# ---- flat port -----------------------------------------------------------

def test_flat_port_narrows_the_field_by_snells_law():
    # Half angle 30 deg in air; n_air = 1 here; n = 1.333.
    # sin(theta_w) = 0.5 / 1.333 = 0.37509 -> 22.03 deg.
    got = ports.flat_port_angle_rad(math.radians(30), 1.333, n_air=1.0)
    assert math.degrees(got) == pytest.approx(22.03, abs=0.01)


def test_flat_port_limit_is_the_critical_angle():
    # asin(1 / 1.333) = 48.61 deg: a 97.2 degree full field however wide the lens.
    assert ports.flat_port_max_half_fov_deg(1.333, n_air=1.0) == pytest.approx(48.61, abs=0.01)
    wide = ports.flat_port_angle_rad(math.radians(89.9), 1.333, n_air=1.0)
    assert math.degrees(wide) == pytest.approx(48.6, abs=0.1)


def test_flat_port_caustic_paraxial_is_gap_times_index():
    got = ports.flat_port_caustic_mm(1e-6, 10.0, 1.333, n_air=1.0)
    assert got == pytest.approx(13.33, abs=0.01)
    # At 40 degrees: tan(40)/tan(asin(sin40/1.333)) * 10
    #   sin40 = 0.64279 -> /1.333 = 0.48221 -> 28.83 deg -> tan = 0.5506; tan40 = 0.8391 -> 15.24
    assert ports.flat_port_caustic_mm(math.radians(40), 10.0, 1.333, n_air=1.0) == pytest.approx(15.24, abs=0.02)


def test_flat_port_chromatic_difference_is_small_but_nonzero():
    n_b, n_r = media.water_refractive_index(450), media.water_refractive_index(650)
    d = ports.flat_port_chromatic_deg(math.radians(60), n_b, n_r)
    # blue has the higher index, so it bends closer to the axis: blue minus red is negative
    assert -0.5 < d < -0.1
    assert abs(ports.flat_port_chromatic_deg(1e-3, n_b, n_r)) < 1e-3


# ---- dome port -----------------------------------------------------------

def test_centred_dome_keeps_every_angle_and_one_viewpoint():
    angles = np.radians([0, 20, 50, 70.7, 85])
    tw, cross = ports.dome_trace(angles, 0.0, 26.3, 2.0, 1.49, 1.333)
    assert tw == pytest.approx(angles, abs=1e-12)
    assert cross == pytest.approx(0, abs=1e-9)


def test_offset_dome_refracts_like_one_surface_when_glass_matches_water():
    # Glass index = water index = 1.33 (so only the inner surface bends), n_air = 1.
    # Pupil 5 mm behind the centre of a 25 mm inner sphere, ray at 30 deg.
    # Sine rule: sin(alpha) = (5 / 25) sin(30) = 0.1 -> alpha = 5.739 deg incidence.
    # The surface normal there is at theta + alpha = 35.739 deg from the axis.
    # Refracted: sin(beta) = 0.1 / 1.33 -> beta = 4.311 deg; ray leaves at 35.739 - 4.311 = 31.43 deg.
    tw, _ = ports.dome_trace(math.radians(30), 5.0, 26.0, 1.0, 1.33, 1.33, n_air=1.0)
    assert math.degrees(tw) == pytest.approx(31.43, abs=0.01)


def test_virtual_image_of_a_far_object_is_about_three_radii_out():
    # One surface, glass index 1 (no inner refraction), water 1.333, R = 26.3:
    # s' = n2 R / (n2 - n1) = 26.3 / (1 - 1.333) = -78.98 mm from the vertex;
    # the dome centre is R behind the vertex: 26.3 + 78.98 = 105.3 mm.
    got = ports.dome_virtual_image_mm(np.inf, 26.3, 2.0, 1.0, 1.333, n_air=1.0)
    assert got == pytest.approx(26.3 + 26.3 / 0.333, abs=0.05)


def test_virtual_image_gets_nearer_as_the_object_does():
    far = ports.dome_virtual_image_mm(np.inf, 26.3, 2.0, 1.49, 1.333)
    near = ports.dome_virtual_image_mm(500.0, 26.3, 2.0, 1.49, 1.333)
    assert 60 < near < far and 3 * 26.3 < far < 4.5 * 26.3


# ---- stereo --------------------------------------------------------------

def test_depth_error_at_a_known_point():
    # f_px 800, B 74 mm, z 2000 mm, dd 0.25 px:
    # dz = 2000^2 * 0.25 / (800 * 74) = 1e6 / 59200 = 16.89 mm.
    assert stereo.depth_error_mm(2000, 800, 74, 0.25) == pytest.approx(16.892, abs=0.001)


def test_disparity_depth_roundtrip():
    d = stereo.disparity_px(1500, 800, 74)          # 800 * 74 / 1500 = 39.47 px
    assert d == pytest.approx(39.4667, abs=1e-3)
    assert stereo.depth_from_disparity_mm(d, 800, 74) == pytest.approx(1500)


def test_first_order_error_matches_the_exact_disparity_difference():
    z, f, B, dd = 2000.0, 800.0, 74.0, 0.25
    exact = f * B / (f * B / z - dd) - z
    assert stereo.depth_error_mm(z, f, B, dd) == pytest.approx(exact, rel=0.02)


def test_range_for_relative_error_and_minimum_range():
    # 5 % at 800 px, 74 mm, 0.25 px: 0.05 * 800 * 74 / 0.25 = 11840 mm.
    assert stereo.range_for_relative_error_mm(0.05, 800, 74, 0.25) == pytest.approx(11840)
    # 800 * 74 / 256 = 231.25 mm
    assert stereo.min_range_for_disparity_mm(800, 74, 256) == pytest.approx(231.25)


def test_error_grows_with_the_square_of_range_and_shrinks_with_baseline():
    e1 = stereo.depth_error_mm(1000, 800, 74, 0.25)
    assert stereo.depth_error_mm(2000, 800, 74, 0.25) == pytest.approx(4 * e1)
    assert stereo.depth_error_mm(1000, 800, 148, 0.25) == pytest.approx(e1 / 2)


def test_off_axis_error_reduces_to_on_axis_and_grows_with_bearing():
    on = stereo.range_error_off_axis_mm(2000, 0.0, 800, 74, 0.25)
    assert on == pytest.approx(stereo.depth_error_mm(2000, 800, 74, 0.25))
    assert stereo.range_error_off_axis_mm(2000, math.radians(60), 800, 74, 0.25) == pytest.approx(2 * on)


def test_overlap_of_two_parallel_cameras():
    # 90 degree full field: W = 2 z = 2000 at 1000 mm; overlap = 1 - 100/2000 = 0.95.
    assert stereo.overlap_fraction(1000, 100, 90) == pytest.approx(0.95)
    # first touch at B / (2 tan 45) = 50 mm; 90 % at 100 / (0.1 * 2) = 500 mm
    assert stereo.first_overlap_range_mm(100, 90) == pytest.approx(50)
    assert stereo.range_for_overlap_mm(0.9, 100, 90) == pytest.approx(500)
    assert stereo.overlap_fraction(25, 100, 90) == 0


def test_sync_error():
    # 2 m, 0.5 m/s, 1 ms, B 74: 2000 * 500 * 0.001 / 74 = 13.51 mm
    assert stereo.sync_depth_error_mm(2000, 500, 1e-3, 74) == pytest.approx(13.514, abs=0.001)
    # same case as disparity: 800 * 500 * 0.001 / 2000 = 0.2 px; and dz from that
    # disparity: 2000^2 * 0.2 / (800 * 74) = 13.51 mm (the same, as derived)
    d = stereo.sync_disparity_error_px(2000, 500, 1e-3, 800)
    assert d == pytest.approx(0.2)
    assert stereo.depth_error_mm(2000, 800, 74, d) == pytest.approx(13.514, abs=0.001)
    assert stereo.sync_forward_error_mm(500, 23e-6) == pytest.approx(0.0115)


# ---- imaging -------------------------------------------------------------

def test_ground_sample_and_pixels_on_target():
    # f_px 800 at 2 m: 2000 / 800 = 2.5 mm per pixel; a 300 mm target: 120 px.
    assert imaging.ground_sample_mm(2000, 800) == pytest.approx(2.5)
    assert imaging.pixels_on_target(300, 2000, 800) == pytest.approx(120)
    assert imaging.range_for_pixels_mm(300, 120, 800) == pytest.approx(2000)
    # 60 degrees off axis the pixel covers 1 / cos^2 = 4 times as much
    assert imaging.ground_sample_mm(2000, 800, math.radians(60)) == pytest.approx(10.0)


def test_motion_blur():
    # 0.5 m/s, 10 ms: 5 mm of travel; 2.5 mm pixels: 2 px.
    assert imaging.motion_blur_px(500, 0.010, 2000, 800) == pytest.approx(2.0)
    assert imaging.max_exposure_s(1.0, 500, 2000, 800) == pytest.approx(0.005)


def test_frame_overlap_and_data_rates():
    # 90 degrees at 1 m: 2000 mm wide; 500 mm/s at 10 fps = 50 mm per frame: 97.5 %.
    assert imaging.frame_overlap(500, 10, 1000, 90) == pytest.approx(0.975)
    # 1920 * 1080 * 10 bit * 10 fps = 207.36 Mbit/s
    assert imaging.raw_data_rate_mbit_s(1920, 1080, 10, 10) == pytest.approx(207.36)
    assert imaging.encoded_data_rate_mbit_s(1920, 1080, 10, 0.1) == pytest.approx(2.0736)
    assert imaging.storage_gb_per_hour(8.0, 2) == pytest.approx(7.2)


# ---- geometry ------------------------------------------------------------

def test_overlap_polygon_of_two_wedges():
    # Two 90 degree wedges 100 apart, cut off at z = 500 (a square-ish arc of
    # many points). The overlap's apex is at z = 50 where the inner edges cross.
    left = geometry.wedge(-50, 0, 0, 90, 5000)
    right = geometry.wedge(50, 0, 0, 90, 5000)
    inter = geometry.clip_convex(left, right)
    assert inter[:, 1].min() == pytest.approx(50, abs=1e-6)
    assert geometry.polygon_area(inter) > 0
    far = geometry.wedge(10000, 0, 0, 10, 100)
    assert len(geometry.clip_convex(left, far)) == 0


# ---- the pieces together -------------------------------------------------

SENSOR = dict(width_px=1920, height_px=1080, pixel_um=2.9)
LENS = dict(focal_mm=2.2562, projection="equidistant")
WATER = dict(kind="water", temperature_c=15, salinity_psu=0, wavelength_nm=550)
AIR = dict(kind="air")
DOME = dict(kind="dome", radius_mm=26.3, thickness_mm=2.0, n_glass=1.49, pupil_offset_mm=0)
FLAT = dict(kind="flat", thickness_mm=3, n_glass=1.49, pupil_offset_mm=10)


def test_centred_dome_in_water_keeps_the_air_field_of_view():
    o = system.optics(SENSOR, LENS, DOME, WATER)
    assert o.fov_air_deg[0] == pytest.approx(141.4, abs=0.1)
    assert o.fov_deg[0] == pytest.approx(o.fov_air_deg[0], abs=1e-6)
    assert o.px_per_rad_axis == pytest.approx(2.2562 / 0.0029, rel=1e-6)


def test_flat_port_in_water_narrows_it():
    n = media.water_refractive_index(550, 15, 0)
    o = system.optics(SENSOR, LENS, FLAT, WATER)
    expected = 2 * math.degrees(math.asin(math.sin(math.radians(70.7)) / n))
    assert o.fov_deg[0] == pytest.approx(expected, abs=0.2)
    assert o.fov_deg[0] < o.fov_air_deg[0] - 40
    # on-axis the angles shrink by n, so there are n times more pixels per radian
    assert o.px_per_rad_axis == pytest.approx(o.f_px * n / media.N_AIR, rel=2e-3)


def test_air_medium_changes_nothing():
    o = system.optics(SENSOR, LENS, FLAT, AIR)
    assert o.fov_deg == pytest.approx(o.fov_air_deg)


def test_stereo_summary_hand_check():
    o = system.optics(SENSOR, LENS, DOME, WATER)
    rig = dict(baseline_mm=74.0)
    scene = dict(disparity_error_px=0.25, max_disparity_px=256, overlap_fraction=0.9,
                 depth_tolerance=0.05, visibility_m=3.0)
    s = system.stereo_summary(o, rig, scene)
    f_px = 2.2562 / 0.0029                      # 777.99
    assert s["error_mm"][2.0] == pytest.approx(2000 ** 2 * 0.25 / (f_px * 74), rel=1e-6)
    assert s["z_min_search_mm"] == pytest.approx(f_px * 74 / 256, rel=1e-6)    # 224.9 mm
    assert s["z_first_overlap_mm"] == pytest.approx(74 / (2 * math.tan(math.radians(70.7))), rel=2e-3)
    assert s["far_limited_by"] == "visibility"
    assert s["near_limited_by"] == "disparity search range"
