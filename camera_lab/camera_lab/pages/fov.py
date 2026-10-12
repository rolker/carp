"""Field of view and coverage: what each camera and each stereo pair sees,
in top and side views and in 3D, with footprints, the visibility limit and
target sizes."""
import numpy as np

from ..models import geometry, ports, stereo
from ..models.media import water_refractive_index
from ..qtcompat import Qt, QtCore, QtGui, QtWidgets, pg
from ..ui.widgets import FieldsPanel, Notes, brush, colour, fmt, pen, plot
from .base import Page

try:                                    # 3D is optional: the page works without it
    import pyqtgraph.opengl as gl
    from OpenGL import GL                # noqa: F401
    HAVE_GL = True
except Exception:                       # noqa: any import problem means no 3D
    HAVE_GL = False


def _polygon_item(points, pen_, brush_):
    item = QtWidgets.QGraphicsPolygonItem(QtGui.QPolygonF([QtCore.QPointF(x, y) for x, y in points]))
    item.setPen(pen_)
    item.setBrush(brush_)
    return item


def _text(plot_widget, x, y, text, colour_="k", anchor=(0, 1)):
    t = pg.TextItem(text, color=colour_, anchor=anchor)
    t.setPos(x, y)
    plot_widget.addItem(t)
    return t


def camera_poses(res):
    """[(x_mm, axis_deg)] for each camera of a rig: left and right of the
    centre line, each toed in by the rig's toe-in angle (towards the centre)."""
    r = res.rig
    if r["cameras"] == 1:
        return [(0.0, 0.0)]
    b, t = r["baseline_mm"], r["toe_in_deg"]
    return [(-b / 2, t), (b / 2, -t)]


class FovPage(Page):
    title = "Field of view & coverage"

    def __init__(self, ws, session, parent=None):
        super().__init__(ws, session, parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)

        side = QtWidgets.QWidget()
        side.setFixedWidth(250)
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        sl.addWidget(self._group("Scene", scene_panel := FieldsPanel(
            ws, ["visibility_m", "target_small_mm", "target_large_mm", "target_range_m"])))
        sl.addWidget(self._group("Primary rig (the one in bold)", rig_panel := FieldsPanel(
            ws, ["baseline_mm", "toe_in_deg", "cameras"])))
        self.scene_panel, self.rig_panel = scene_panel, rig_panel
        opts = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(opts)
        form.setContentsMargins(0, 0, 0, 0)
        self.length = QtWidgets.QDoubleSpinBox(decimals=1, minimum=0.5, maximum=50, value=4.0, suffix=" m")
        self.length.setToolTip("How far the wedges are drawn (a display choice, not a physical limit).")
        self.altitude = QtWidgets.QDoubleSpinBox(decimals=1, minimum=0.1, maximum=20, value=1.0, suffix=" m")
        self.altitude.setToolTip("Height of the cameras above the seabed in the side view.")
        form.addRow("Draw wedges to", self.length)
        form.addRow("Height above seabed", self.altitude)
        for w in (self.length, self.altitude):
            w.setKeyboardTracking(False)
            w.valueChanged.connect(self.schedule)
        sl.addWidget(self._group("This page", opts))
        sl.addStretch(1)
        lay.addWidget(side)

        right = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        views = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.top = plot("Top view (looking down)", "sideways (m)", "ahead (m)")
        self.top.setAspectLocked(True)
        self.side = plot("Side view", "ahead (m)", "up (m)")
        self.side.setAspectLocked(True)
        flat = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        flat.addWidget(self.top)
        flat.addWidget(self.side)
        views.addWidget(flat)
        self.gl = None
        # The offscreen platform has no OpenGL: creating the widget crashes it.
        if HAVE_GL and QtGui.QGuiApplication.platformName() != "offscreen":
            try:
                self.gl = gl.GLViewWidget()
                self.gl.setBackgroundColor("w")
                self.gl.setMinimumWidth(260)
                views.addWidget(self.gl)
            except Exception:           # noqa: no usable GL context
                self.gl = None
        if self.gl is None:
            views.addWidget(QtWidgets.QLabel("3D view needs python3-opengl and a working OpenGL."))
        bottom = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        self.table = QtWidgets.QTableWidget()
        self.notes = Notes()
        bottom.addWidget(self.table)
        bottom.addWidget(self.notes)
        bottom.setSizes([760, 440])
        right.addWidget(views)
        right.addWidget(bottom)
        views.setSizes([620, 520])
        right.setSizes([520, 330])
        lay.addWidget(right, 1)
        self._gl_framed = False

    @staticmethod
    def _group(title, widget):
        box = QtWidgets.QGroupBox(title)
        QtWidgets.QVBoxLayout(box).addWidget(widget)
        return box

    # ---- drawing ---------------------------------------------------------

    def redraw_empty(self):
        self.top.clear()
        self.side.clear()
        self.notes.setHtml("<p>Pick a scene and at least one rig.</p>")

    def redraw(self):
        s = self.session
        scene = s.scene()
        primary = s.primary()
        self.scene_panel.set_object("scenes", s.scene_id)
        self.rig_panel.set_object("rigs", s.primary_id)
        rigs = s.shown_rigs()
        L = self.length.value()
        vis = scene["visibility_m"]
        self._draw_top(rigs, primary, scene, L, vis)
        self._draw_side(rigs, primary, scene, L, vis)
        self._draw_3d(rigs, primary, scene, vis)
        self._fill_table(rigs, scene)
        self._fill_notes(primary or rigs[0], scene)

    def _draw_top(self, rigs, primary, scene, L, vis):
        p = self.top
        p.clear()
        for res in rigs:
            h = res.optics.fov_deg[0]
            if not np.isfinite(h):
                continue
            lw = 3 if primary and res.id == primary.id else 1.5
            polys = []
            for x_mm, axis in camera_poses(res):
                wd = geometry.wedge(x_mm / 1000, 0, axis, h, L) if h < 180 else None
                if wd is None:
                    continue
                polys.append(wd)
                p.addItem(_polygon_item(wd, pen(res.colour_index, lw, alpha=200),
                                        brush(res.colour_index, 22)))
                p.plot([x_mm / 1000], [0], pen=None, symbol="o", symbolSize=6,
                       symbolBrush=colour(res.colour_index), symbolPen="k")
            if len(polys) == 2:
                ov = geometry.clip_convex(polys[0], polys[1])
                if len(ov) >= 3:
                    p.addItem(_polygon_item(ov, pen(res.colour_index, 1, alpha=255),
                                            brush(res.colour_index, 90)))
        a = np.linspace(-np.pi / 2, np.pi / 2, 90)
        p.plot(vis * np.sin(a), vis * np.cos(a), pen=pg.mkPen("#222", width=1.5, style=Qt.PenStyle.DashLine))
        _text(p, 0, vis, f"visibility {vis:g} m", "#222", (0.5, 0))
        if primary:
            for z in (1.0, 2.0, 3.0):
                w = self._union_width_m(primary, z)
                if np.isfinite(w) and z <= L:
                    p.plot([-w / 2, w / 2], [z, z], pen=pg.mkPen(colour(primary.colour_index), width=1))
                    clipped = w / 2 > L
                    _text(p, min(w / 2, L), z, f" {z:g} m: {w:.1f} m wide ", "k", (1 if clipped else 0, 0.5))
        zt = scene["target_range_m"]
        for size, c, label in ((scene["target_small_mm"], "#d62728", "small"),
                               (scene["target_large_mm"], "#222", "large")):
            p.plot([-size / 2000, size / 2000], [zt, zt], pen=pg.mkPen(c, width=5))
        _text(p, -L * 1.05, zt, f"targets {scene['target_small_mm']:g}, {scene['target_large_mm']:g} mm at {zt:g} m",
              "#d62728", (0, 1.3))
        p.setRange(xRange=(-L * 1.05, L * 1.05), yRange=(-0.3, L * 1.05), padding=0)

    @staticmethod
    def _union_width_m(res, z_m):
        """Width of the strip seen by the pair together (or the single
        camera) on a flat target square to the axes at z, ignoring toe-in's
        small tilt of the target plane."""
        h = res.optics.fov_deg[0]
        if not np.isfinite(h) or h >= 180:
            return np.inf
        half = z_m * np.tan(np.radians(h) / 2)
        xs = [x / 1000 for x, _ in camera_poses(res)]
        return (max(xs) - min(xs)) + 2 * half

    def _draw_side(self, rigs, primary, scene, L, vis):
        p = self.side
        p.clear()
        alt = self.altitude.value()
        for res in rigs:
            v = res.optics.fov_deg[1]
            if not np.isfinite(v) or v >= 180:
                continue
            wd = geometry.wedge(0, 0, 0, v, L)[:, ::-1]        # (ahead, up)
            lw = 3 if primary and res.id == primary.id else 1.5
            p.addItem(_polygon_item(wd, pen(res.colour_index, lw, alpha=200),
                                    brush(res.colour_index, 22)))
        p.addItem(_polygon_item([(0, -alt), (L, -alt), (L, -alt - 0.3), (0, -alt - 0.3)],
                                pg.mkPen("#8d6e63"), pg.mkBrush("#d7ccc8")))
        a = np.linspace(-np.pi / 2, np.pi / 2, 90)
        p.plot(vis * np.cos(a), vis * np.sin(a), pen=pg.mkPen("#222", width=1.5, style=Qt.PenStyle.DashLine))
        if primary and np.isfinite(primary.optics.fov_deg[1]):
            v = primary.optics.fov_deg[1]
            zs = alt / np.tan(np.radians(v) / 2)
            _text(p, zs, -alt, f" lower edge meets seabed at {zs:.2f} m", "k", (0, -0.3))
        zt = scene["target_range_m"]
        for size, c in ((scene["target_small_mm"], "#d62728"), (scene["target_large_mm"], "#222")):
            p.plot([zt, zt], [-alt, -alt + size / 1000], pen=pg.mkPen(c, width=5))
        p.setRange(xRange=(-0.2, L * 1.05), yRange=(-max(alt + 0.4, L * 0.5), L * 0.5), padding=0)

    def _draw_3d(self, rigs, primary, scene, vis):
        if self.gl is None:
            return
        v = self.gl
        v.clear()
        grid = gl.GLGridItem()
        grid.setSize(2 * vis, 2 * vis)
        grid.setSpacing(1, 1)
        grid.translate(0, vis / 2, -self.altitude.value())
        grid.setColor((0, 0, 0, 60))
        v.addItem(grid)
        for res in rigs:
            c = colour(res.colour_index)
            rgba = (c.redF(), c.greenF(), c.blueF(), 1.0)
            loop, corners = res.optics.boundary_rays(16)
            for x_mm, axis in camera_poses(res):
                a = np.radians(axis)
                # rotate (right, ahead) by the toe angle: positive axis turns towards +x
                ca, sa = np.cos(-a), np.sin(-a)
                def place(d, length, ca=ca, sa=sa, x_mm=x_mm):
                    right = d[:, 0] * ca - d[:, 2] * sa
                    ahead = d[:, 0] * sa + d[:, 2] * ca
                    return np.column_stack([x_mm / 1000 + right * length, ahead * length, -d[:, 1] * length])
                pts = place(loop, vis)
                good = np.isfinite(pts).all(axis=1)
                if good.sum() > 2:
                    v.addItem(gl.GLLinePlotItem(pos=pts[good], color=rgba, width=2, antialias=True))
                apex = np.array([x_mm / 1000, 0, 0])
                for c3 in place(corners, vis):
                    if np.isfinite(c3).all():
                        v.addItem(gl.GLLinePlotItem(pos=np.array([apex, c3]), color=rgba, width=1, antialias=True))
            if primary and res.id == primary.id:
                for z in (1.0, 2.0, 3.0):
                    for x_mm, axis in camera_poses(res)[:1]:
                        d = loop[loop[:, 2] > 0.05]
                        if len(d):
                            pl = np.column_stack([x_mm / 1000 + d[:, 0] * z / d[:, 2], np.full(len(d), z),
                                                  -d[:, 1] * z / d[:, 2]])
                            v.addItem(gl.GLLinePlotItem(pos=pl, color=(0, 0, 0, 0.45), width=1))
        zt = scene["target_range_m"]
        for size, col in ((scene["target_small_mm"], (0.84, 0.15, 0.16, 1)), (scene["target_large_mm"], (0, 0, 0, 1))):
            h = size / 2000
            sq = np.array([[-h, zt, -self.altitude.value()], [h, zt, -self.altitude.value()],
                           [h, zt, -self.altitude.value() + 2 * h], [-h, zt, -self.altitude.value() + 2 * h],
                           [-h, zt, -self.altitude.value()]])
            v.addItem(gl.GLLinePlotItem(pos=sq, color=col, width=3))
        if not self._gl_framed:
            v.setCameraPosition(pos=pg.Vector(0, vis * 0.45, -0.3), distance=vis * 2.3, elevation=28, azimuth=-60)
            self._gl_framed = True

    # ---- numbers -----------------------------------------------------------

    def _fill_table(self, rigs, scene):
        def fov(i):
            return lambda r: f"{r.optics.fov_deg[i]:.1f}"

        def foot(z, i):
            return lambda r: fmt(float(stereo.footprint_width_mm(z * 1000, r.optics.fov_deg[i])) / 1000, 3) + " m"

        def pxmm(z):
            return lambda r: f"{r.optics.px_per_rad_axis / (z * 1000):.2f}"

        rows = [("Horizontal FOV, in air (deg)", lambda r: f"{r.optics.fov_air_deg[0]:.1f}"),
                ("Horizontal FOV, in the medium (deg)", fov(0)),
                ("Vertical FOV (deg)", fov(1)),
                ("Diagonal FOV (deg)", fov(2)),
                ("Footprint width at 1 m", foot(1, 0)),
                ("Footprint width at 2 m", foot(2, 0)),
                ("Footprint width at 3 m", foot(3, 0)),
                ("Footprint height at 2 m", foot(2, 1)),
                ("Pixels per mm on target at 1 m", pxmm(1)),
                ("Pixels per mm on target at 2 m", pxmm(2)),
                ("Pixels per mm on target at 3 m", pxmm(3)),
                ("Pair sees together at 2 m (width)",
                 lambda r: fmt(self._union_width_m(r, 2.0), 3) + " m" if np.isfinite(self._union_width_m(r, 2.0)) else "n/a"),
                ("Overlap of the pair at 1 m",
                 lambda r: "single camera" if r.rig["cameras"] == 1 else
                 f"{100 * float(stereo.overlap_fraction(1000, r.rig['baseline_mm'], r.optics.fov_deg[0])):.1f} %")]
        self.rig_table(self.table, rigs, rows)

    def _fill_notes(self, res, scene):
        o, medium = res.optics, self.session.medium()
        port = self.ws.get("ports", res.rig["port"])
        lens = self.ws.get("lenses", res.rig["lens"])
        n = o.n_medium
        html = [f"<h4>{res.name} in {medium['name'].lower()} (n = {n:.4f})</h4>"]
        html.append(f"<p>The lens ({lens['projection']}, f = {lens['focal_mm']:g} mm) on a "
                    f"{o.width_px:.0f} x {o.height_px:.0f} px sensor with {o.pitch_mm * 1000:.2f} um pixels "
                    f"sees <b>{o.fov_air_deg[0]:.1f} x {o.fov_air_deg[1]:.1f} deg</b> in air "
                    f"(horizontal x vertical).</p>")
        kind = port["kind"]
        if kind == "dome":
            far = ports.dome_virtual_image_mm(np.inf, port["radius_mm"], port["thickness_mm"], port["n_glass"], n)
            near = ports.dome_virtual_image_mm(1000, port["radius_mm"], port["thickness_mm"], port["n_glass"], n)
            off = port["pupil_offset_mm"]
            html.append(f"<p><b>Dome, pupil {abs(off):.1f} mm {'behind' if off >= 0 else 'in front of'} the centre.</b> "
                        f"Centred, every ray crosses the dome along its normal, so the field of view stays "
                        f"<b>{o.fov_deg[0]:.1f} deg</b> in the water. The dome acts as a negative lens "
                        f"in water: a far object appears {far:.0f} mm from the pupil ({far / port['radius_mm']:.1f} dome radii) and "
                        f"one at 1 m appears at {near:.0f} mm, so the lens must be focused close, not at infinity.</p>")
        elif kind == "flat":
            lim = 2 * ports.flat_port_max_half_fov_deg(n)
            nb, nr = water_refractive_index(450, 15, 0), water_refractive_index(650, 15, 0)
            ang = np.radians(o.fov_air_deg[0] / 2)
            ch = ports.flat_port_chromatic_deg(ang, nb, nr)
            html.append(f"<p><b>Flat port.</b> Refraction narrows the field to <b>{o.fov_deg[0]:.1f} deg</b> "
                        f"(sin of the half angle divided by n = {n:.3f}). No lens can see more than {lim:.1f} deg "
                        f"horizontally through a flat port in this water. Blue and red rays at the edge differ by "
                        f"{abs(ch):.2f} deg (colour fringes), and rays at different angles appear to come from "
                        f"different points, so the pinhole model only holds near the axis. On axis, angles shrink "
                        f"by n, so there are {o.px_per_rad_axis / o.f_px:.2f} times more pixels per radian.</p>")
        else:
            html.append("<p>No port: the camera is treated as if it were in air.</p>")
        for w in o.warnings:
            html.append(f"<p class='warn'>Warning: {w}.</p>")
        listed = lens.get("listed_fov_h_deg", 0)
        if listed:
            html.append(f"<p class='dim'>Manufacturer's listed horizontal FOV: {listed:g} deg "
                        f"(model in air: {o.fov_air_deg[0]:.1f}).</p>")
        vis = scene["visibility_m"]
        w3 = float(stereo.footprint_width_mm(vis * 1000, o.fov_deg[0])) / 1000
        html.append(f"<p>At the {vis:g} m visibility limit one camera's footprint is {fmt(w3)} m wide and its "
                    f"pixels are {vis * 1000 / o.px_per_rad_axis:.2f} mm on target "
                    f"(footprint = 2 z tan(FOV/2), pixel = z / f_px). Water in front of the target is what "
                    f"limits the picture long before the optics do.</p>")
        self.notes.setHtml("".join(html))
