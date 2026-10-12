"""Plane geometry for the coverage views: wedges (field-of-view sectors of a
camera) and their intersection. All lengths in the same unit (mm in the
app); angles in degrees measured from +z (straight ahead) towards +x, in
the top view (x sideways, z ahead)."""
import numpy as np


def wedge(x_mm, z_mm, axis_deg, full_fov_deg, length_mm, arc_points=24):
    """Polygon (N x 2 array of x, z) of a camera's field of view out to
    `length_mm`: the apex at the camera, then an arc at that range. A field
    of view of 180 degrees or more is drawn as a half plane to the arc, and
    the polygon is then not convex."""
    half = np.radians(full_fov_deg) / 2
    a = np.radians(axis_deg) + np.linspace(-half, half, arc_points)
    arc = np.column_stack([x_mm + length_mm * np.sin(a), z_mm + length_mm * np.cos(a)])
    return np.vstack([[x_mm, z_mm], arc])


def clip_convex(subject, clip):
    """Intersection of two convex polygons (Sutherland-Hodgman). Both are
    N x 2 arrays. Returns an M x 2 array, empty if they do not meet."""
    def inside(p, a, b):
        return (b[0] - a[0]) * (p[1] - a[1]) - (b[1] - a[1]) * (p[0] - a[0]) >= 0

    def cross(p, q, a, b):
        d1, d2 = q - p, b - a
        den = d1[0] * d2[1] - d1[1] * d2[0]
        t = ((a[0] - p[0]) * d2[1] - (a[1] - p[1]) * d2[0]) / den
        return p + t * d1

    clip = np.asarray(clip, float)
    if _area(clip) < 0:                       # make the clip polygon counter-clockwise
        clip = clip[::-1]
    out = [np.asarray(p, float) for p in subject]
    for i in range(len(clip)):
        a, b = clip[i], clip[(i + 1) % len(clip)]
        previous, out = out, []
        if not previous:
            break
        s = previous[-1]
        for e in previous:
            if inside(e, a, b):
                if not inside(s, a, b):
                    out.append(cross(s, e, a, b))
                out.append(e)
            elif inside(s, a, b):
                out.append(cross(s, e, a, b))
            s = e
    return np.array(out).reshape(-1, 2)


def _area(poly):
    x, y = poly[:, 0], poly[:, 1]
    return 0.5 * float(np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y))


def polygon_area(poly):
    """Area of a simple polygon (N x 2), always positive."""
    return abs(_area(np.asarray(poly, float))) if len(poly) >= 3 else 0.0
