"""Stereo performance: depth error against range, what limits the near and
far ends, how baseline, resolution and field of view trade off (with the
baseline decision front and centre), and what a timing offset between the
cameras costs."""
import numpy as np

from ..models import stereo, system
from ..qtcompat import Qt, QtWidgets, pg
from ..ui.session import scene_for_models
from ..ui.widgets import FieldsPanel, Notes, colour, fmt, hline, pen, plot, vline
from .base import Page


class StereoPage(Page):
    title = "Stereo performance"

    def __init__(self, ws, session, parent=None):
        super().__init__(ws, session, parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        side = QtWidgets.QWidget()
        side.setFixedWidth(250)
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.scene_panel = FieldsPanel(ws, ["disparity_error_px", "max_disparity_px", "overlap_pct",
                                            "depth_tolerance_pct", "visibility_m", "speed_m_s"])
        self.rig_panel = FieldsPanel(ws, ["baseline_mm", "sync_us", "image_scale", "fps"])
        sl.addWidget(self._group("Assumptions (scene)", self.scene_panel))
        sl.addWidget(self._group("Primary rig", self.rig_panel))
        opts = QtWidgets.QWidget()
        form = QtWidgets.QFormLayout(opts)
        form.setContentsMargins(0, 0, 0, 0)

        def spin(value, lo, hi, suffix, tip, decimals=1):
            w = QtWidgets.QDoubleSpinBox(decimals=decimals, minimum=lo, maximum=hi, value=value, suffix=suffix)
            w.setKeyboardTracking(False)
            w.setToolTip(tip)
            w.valueChanged.connect(self.schedule)
            return w
        self.test_range = spin(2.0, 0.2, 20, " m", "The range at which errors are compared in the sweeps.")
        self.decision_lo = spin(74.0, 10, 1000, " mm", "Smallest baseline the housing allows (docs/sled.md).", 0)
        self.decision_hi = spin(95.0, 10, 1000, " mm", "Largest baseline the housing allows (docs/sled.md).", 0)
        self.sweep_lo = spin(40.0, 5, 1000, " mm", "Start of the baseline sweep.", 0)
        self.sweep_hi = spin(200.0, 10, 2000, " mm", "End of the baseline sweep.", 0)
        form.addRow("Compare at range", self.test_range)
        form.addRow("Baseline decision: from", self.decision_lo)
        form.addRow("to", self.decision_hi)
        form.addRow("Sweep baseline from", self.sweep_lo)
        form.addRow("to", self.sweep_hi)
        sl.addWidget(self._group("This page", opts))
        sl.addStretch(1)
        lay.addWidget(side)

        right = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        grid = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        self.p_err = plot("Depth error against range", "range (m)", "depth error (mm)")
        self.p_base = plot("Error against baseline", "baseline (mm)", "depth error (mm)")
        self.p_lim = plot("Usable range against baseline", "baseline (mm)", "range (m)")
        self.p_trade = plot("Lens trade-off", "horizontal FOV in the medium (deg)",
                            "mm", log_y=True)
        self.p_sync = plot("Sync error between cameras", "time between exposures (us)", "depth error (mm)",
                           log_x=True, log_y=True)
        for p in (self.p_err, self.p_lim, self.p_trade, self.p_sync):
            p.addLegend(offset=(8, 8), labelTextColor="k", brush=pg.mkBrush(255, 255, 255, 200))
            p.setMinimumWidth(180)
        self.notes = Notes()
        for i, w in enumerate((self.p_err, self.p_base, self.p_lim, self.p_trade, self.p_sync, self.notes)):
            g.addWidget(w, i // 3, i % 3)
        self.table = QtWidgets.QTableWidget()
        right.addWidget(grid)
        right.addWidget(self.table)
        right.setSizes([620, 230])
        lay.addWidget(right, 1)

    @staticmethod
    def _group(title, widget):
        box = QtWidgets.QGroupBox(title)
        QtWidgets.QVBoxLayout(box).addWidget(widget)
        return box

    def redraw_empty(self):
        for p in (self.p_err, self.p_base, self.p_lim, self.p_trade, self.p_sync):
            p.clear()
        self.notes.setHtml("<p>Pick a scene and at least one rig.</p>")

    # ---- the page ---------------------------------------------------------

    def redraw(self):
        s = self.session
        scene = s.scene()
        primary = s.primary() or s.shown_rigs()[0]
        self.scene_panel.set_object("scenes", s.scene_id)
        self.rig_panel.set_object("rigs", primary.id)
        rigs = s.shown_rigs()
        R = self.test_range.value() * 1000
        self._error_plot(rigs, primary, scene)
        self._baseline_plots(primary, scene, R)
        self._tradeoff_plot(rigs, primary, scene, R)
        self._sync_plot(primary, scene)
        self._table(rigs, scene, R)
        self._notes(primary, scene, R)

    @staticmethod
    def _summary(res, scene, baseline_mm=None):
        rig = dict(res.rig)
        if baseline_mm is not None:
            rig["baseline_mm"] = baseline_mm
        return system.stereo_summary(res.optics, rig, scene)

    def _error_plot(self, rigs, primary, scene):
        p = self.p_err
        p.clear()
        vis = scene["visibility_m"]
        zmax = max(vis * 1.4, 1.0)
        z = np.linspace(0.05, zmax, 200)
        for res in rigs:
            f = res.optics.px_per_rad_axis
            e = stereo.depth_error_mm(z * 1000, f, res.rig["baseline_mm"], scene["disparity_error_px"])
            lw = 3 if res.id == primary.id else 1.5
            p.plot(z, e, pen=pen(res.colour_index, lw), name=res.name)
        p.plot(z, scene["depth_tolerance"] * z * 1000, pen=pg.mkPen("#555", width=1, style=Qt.PenStyle.DashLine),
               name=f"{scene['depth_tolerance_pct']:g} % of range")
        p.plot([], [], pen=pg.mkPen("#59a14f", width=8), name="usable (primary rig)")
        sm = self._summary(primary, scene)
        a, b = sm["z_near_mm"] / 1000, min(sm["z_far_mm"] / 1000, zmax)
        if b > a:
            region = pg.LinearRegionItem([a, b], movable=False, brush=pg.mkBrush(89, 161, 79, 35))
            region.setZValue(-10)
            for line in region.lines:
                line.setPen(pg.mkPen(None))
            p.addItem(region)
        vline(p, vis, "#222", label=f"visibility {vis:g} m")
        p.setLabel("bottom", "range (m)")
        p.setXRange(0, zmax)
        p.setYRange(0, scene["depth_tolerance"] * zmax * 1000 * 1.1)

    def _baseline_plots(self, primary, scene, R):
        lo, hi = sorted((self.sweep_lo.value(), self.sweep_hi.value()))
        dlo, dhi = sorted((self.decision_lo.value(), self.decision_hi.value()))
        B = np.linspace(lo, max(hi, lo + 1), 120)
        f = primary.optics.px_per_rad_axis
        h = primary.optics.fov_deg[0]
        for p in (self.p_base, self.p_lim):
            p.clear()
            band = pg.LinearRegionItem([dlo, dhi], movable=False, brush=pg.mkBrush(237, 201, 72, 70))
            band.setZValue(-10)
            for line in band.lines:
                line.setPen(pg.mkPen("#b8860b", width=1))
            p.addItem(band)
        self.p_base.plot(B, stereo.depth_error_mm(R, f, B, scene["disparity_error_px"]),
                         pen=pen(primary.colour_index, 3))
        for bm in (dlo, dhi):
            e = float(stereo.depth_error_mm(R, f, bm, scene["disparity_error_px"]))
            self.p_base.plot([bm], [e], pen=None, symbol="o", symbolSize=9, symbolBrush="#b8860b", symbolPen="k")
            t = pg.TextItem(f"{bm:g} mm: {e:.1f} mm", color="k", anchor=(0, 1))
            t.setPos(bm, e)
            self.p_base.addItem(t)
        self.p_base.setLabel("bottom", f"baseline (mm); yellow = allowed {dlo:g} to {dhi:g}")
        self.p_base.setLabel("left", f"depth error at {R / 1000:g} m (mm)")
        self.p_base.setTitle(f"Error against baseline at {R / 1000:g} m", color="k", size="10pt")
        search = stereo.min_range_for_disparity_mm(f, B, scene["max_disparity_px"]) / 1000
        overlap = stereo.range_for_overlap_mm(scene["overlap_fraction"], B, h) / 1000 if h < 180 else 0 * B
        tol = stereo.range_for_relative_error_mm(scene["depth_tolerance"], f, B, scene["disparity_error_px"]) / 1000
        self.p_lim.plot(B, search, pen=pg.mkPen("#e15759", width=2), name="nearest: matcher search")
        self.p_lim.plot(B, overlap, pen=pg.mkPen("#f28e2b", width=2, style=Qt.PenStyle.DashLine), name="nearest: overlap")
        self.p_lim.plot(B, np.minimum(tol, scene["visibility_m"]), pen=pg.mkPen("#4e79a7", width=2), name="farthest")
        self.p_lim.setLabel("bottom", "baseline (mm)")
        self.p_lim.setYRange(0, scene["visibility_m"] * 1.1)
        self.p_lim.setXRange(lo, max(hi, lo + 1))
        self.p_base.setXRange(lo, max(hi, lo + 1))

    def _tradeoff_plot(self, rigs, primary, scene, R):
        p = self.p_trade
        p.clear()
        rig = primary.rig
        sensor, port = self.ws.get("sensors", rig["sensor"]), self.ws.get("ports", rig["port"])
        lens = self.ws.get("lenses", rig["lens"])
        medium = self.session.medium()
        fov, err, err720, ov = [], [], [], []
        for f_mm in np.geomspace(1.0, 12.0, 50):
            o = system.optics(sensor, dict(lens, focal_mm=float(f_mm)), port, medium, rig["image_scale"])
            o2 = system.optics(sensor, dict(lens, focal_mm=float(f_mm)), port, medium, rig["image_scale"] * 0.667)
            h = o.fov_deg[0]
            if not np.isfinite(h) or h >= 175:
                continue
            fov.append(h)
            err.append(float(stereo.depth_error_mm(R, o.px_per_rad_axis, rig["baseline_mm"], scene["disparity_error_px"])))
            err720.append(float(stereo.depth_error_mm(R, o2.px_per_rad_axis, rig["baseline_mm"], scene["disparity_error_px"])))
            ov.append(float(stereo.range_for_overlap_mm(scene["overlap_fraction"], rig["baseline_mm"], h)))
        if fov:
            p.plot(fov, err, pen=pen(primary.colour_index, 3), name=f"error at {R / 1000:g} m")
            p.plot(fov, err720, pen=pg.mkPen(colour(primary.colour_index), width=2, style=Qt.PenStyle.DotLine),
                   name="same at 720p")
            p.plot(fov, ov, pen=pg.mkPen("#f28e2b", width=2, style=Qt.PenStyle.DashLine), name="range for full overlap")
        for res in rigs:
            h = res.optics.fov_deg[0]
            e = float(stereo.depth_error_mm(R, res.optics.px_per_rad_axis, res.rig["baseline_mm"],
                                            scene["disparity_error_px"]))
            if np.isfinite(h):
                p.plot([h], [e], pen=None, symbol="o", symbolSize=9,
                       symbolBrush=colour(res.colour_index), symbolPen="k")
        p.setTitle("Lens trade-off (sensor and port as primary)", color="k", size="9pt")
        p.setLabel("left", "mm (log)")

    def _sync_plot(self, primary, scene):
        p = self.p_sync
        p.clear()
        t_us = np.geomspace(1.0, 2e5, 80)
        v = scene["speed_m_s"] * 1000
        B = primary.rig["baseline_mm"]
        f = primary.optics.px_per_rad_axis
        for z, ci in ((1.0, 0), (2.0, 1), (3.0, 2)):
            p.plot(t_us, stereo.sync_depth_error_mm(z * 1000, v, t_us * 1e-6, B),
                   pen=pen(ci + 3, 2), name=f"{z:g} m")
            vline_y = float(stereo.depth_error_mm(z * 1000, f, B, scene["disparity_error_px"]))
            hline(p, np.log10(vline_y), colour(ci + 3).name())
        vline(p, np.log10(max(primary.rig["sync_us"], 1.0)), "#222", Qt.PenStyle.SolidLine,
              f"this rig: {primary.rig['sync_us']:g} us")
        frame = 1e6 / primary.rig["fps"]
        vline(p, np.log10(frame), "#888", label="one frame")
        p.setTitle(f"Sync error at {scene['speed_m_s']:g} m/s sideways", color="k", size="9pt")

    # ---- numbers -------------------------------------------------------------

    def _table(self, rigs, scene, R):
        sums = {r.id: self._summary(r, scene) for r in rigs}

        def err(z):
            return lambda r: f"{sums[r.id]['error_mm'][z]:.1f}"

        rows = [("Baseline (mm)", lambda r: f"{r.rig['baseline_mm']:g}"),
                ("f in pixels (in the medium)", lambda r: f"{r.optics.px_per_rad_axis:.0f}"),
                ("Depth error at 1 m (mm)", err(1.0)), ("Depth error at 2 m (mm)", err(2.0)),
                ("Depth error at 3 m (mm)", err(3.0)),
                ("Error at compare range (mm)",
                 lambda r: f"{float(stereo.depth_error_mm(R, r.optics.px_per_rad_axis, r.rig['baseline_mm'], scene['disparity_error_px'])):.1f}"),
                ("Nearest: matcher search range (m)", lambda r: f"{sums[r.id]['z_min_search_mm'] / 1000:.2f}"),
                ("Nearest: footprints touch (m)", lambda r: f"{sums[r.id]['z_first_overlap_mm'] / 1000:.3f}"),
                ("Nearest: overlap counts as full (m)", lambda r: f"{sums[r.id]['z_overlap_mm'] / 1000:.3f}"),
                ("Farthest: error reaches tolerance (m)", lambda r: f"{sums[r.id]['z_tolerance_mm'] / 1000:.1f}"),
                ("Usable range (m)", lambda r: f"{sums[r.id]['z_near_mm'] / 1000:.2f} to {sums[r.id]['z_far_mm'] / 1000:.2f}"),
                ("Sync error at 2 m, sideways (mm)",
                 lambda r: f"{float(stereo.sync_depth_error_mm(2000, scene['speed_m_s'] * 1000, r.rig['sync_us'] * 1e-6, r.rig['baseline_mm'])):.2f}")]
        self.rig_table(self.table, rigs, rows)

    def _notes(self, primary, scene, R):
        lo, hi = sorted((self.decision_lo.value(), self.decision_hi.value()))
        a, b = self._summary(primary, scene, lo), self._summary(primary, scene, hi)
        f = primary.optics.px_per_rad_axis
        dd = scene["disparity_error_px"]
        ea = float(stereo.depth_error_mm(R, f, lo, dd))
        eb = float(stereo.depth_error_mm(R, f, hi, dd))
        v = scene["speed_m_s"] * 1000
        h = ["<h4>Baseline decision</h4>",
             f"<p><b>{lo:g} mm</b> gives {ea:.1f} mm error at {R / 1000:g} m, <b>{hi:g} mm</b> gives {eb:.1f} mm "
             f"(<b>{100 * (1 - eb / ea):.0f} % smaller</b>: error scales as 1/B). Nearest usable range "
             f"{a['z_near_mm'] / 1000:.2f} m against {b['z_near_mm'] / 1000:.2f} m, "
             f"limited by the {a['near_limited_by']}. The sync error at {R / 1000:g} m is "
             f"{float(stereo.sync_depth_error_mm(R, v, primary.rig['sync_us'] * 1e-6, lo)):.3f} against "
             f"{float(stereo.sync_depth_error_mm(R, v, primary.rig['sync_us'] * 1e-6, hi)):.3f} mm.</p>",
             "<h4>The formulas, with the live values</h4>",
             f"<p>Depth z = f B / d. With f = {f:.0f} px and B = {primary.rig['baseline_mm']:g} mm, a point at "
             f"{R / 1000:g} m has disparity {float(stereo.disparity_px(R, f, primary.rig['baseline_mm'])):.1f} px. "
             f"A disparity error of {dd:g} px moves it by dz = z<sup>2</sup> dd / (f B) = "
             f"{float(stereo.depth_error_mm(R, f, primary.rig['baseline_mm'], dd)):.1f} mm.</p>",
             f"<p>The matcher searches {scene['max_disparity_px']:g} px, so nothing nearer than "
             f"f B / d<sub>max</sub> = {self._summary(primary, scene)['z_min_search_mm'] / 1000:.2f} m "
             f"can be matched. A sideways motion of {v / 1000:g} m/s during the "
             f"{primary.rig['sync_us']:g} us between exposures shifts the target "
             f"{v * primary.rig['sync_us'] * 1e-6:.4f} mm, a disparity error of "
             f"{float(stereo.sync_disparity_error_px(R, v, primary.rig['sync_us'] * 1e-6, f)):.5f} px at "
             f"{R / 1000:g} m (against the matcher's {dd:g} px).</p>"]
        h.append("<p class='dim'>First-order formulas for rectified pinhole images; a fisheye is rectified first, "
                 "so only its central part is usable for stereo. The disparity accuracy is an assumption, not a "
                 "measurement of this system.</p>")
        self.notes.setHtml("".join(h))
