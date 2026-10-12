"""Resolution and motion: pixels on a target against range, motion blur
against exposure and speed, and frame rate against data rate and frame
overlap."""
import numpy as np

from ..models import imaging
from ..qtcompat import Qt, QtWidgets, pg, pg
from ..ui.widgets import FieldsPanel, Notes, colour, hline, pen, plot, vline
from .base import Page


class ResolutionPage(Page):
    title = "Resolution & motion"

    def __init__(self, ws, session, parent=None):
        super().__init__(ws, session, parent)
        lay = QtWidgets.QHBoxLayout(self)
        lay.setContentsMargins(4, 4, 4, 4)
        side = QtWidgets.QWidget()
        side.setFixedWidth(250)
        sl = QtWidgets.QVBoxLayout(side)
        sl.setContentsMargins(0, 0, 0, 0)
        self.scene_panel = FieldsPanel(ws, ["target_small_mm", "target_large_mm", "pixels_needed",
                                            "speed_m_s", "blur_limit_px", "visibility_m"])
        self.rig_panel = FieldsPanel(ws, ["exposure_ms", "fps", "image_scale", "encoded_bpp"])
        for title, w in (("Assumptions (scene)", self.scene_panel), ("Primary rig", self.rig_panel)):
            box = QtWidgets.QGroupBox(title)
            QtWidgets.QVBoxLayout(box).addWidget(w)
            sl.addWidget(box)
        sl.addStretch(1)
        lay.addWidget(side)
        right = QtWidgets.QSplitter(Qt.Orientation.Vertical)
        grid = QtWidgets.QWidget()
        g = QtWidgets.QGridLayout(grid)
        g.setContentsMargins(0, 0, 0, 0)
        self.p_px = plot("Pixels across a target", "range (m)", "pixels", log_y=True)
        self.p_blur = plot("Motion blur", "exposure time (ms)", "blur (px)", log_x=True, log_y=True)
        self.p_rate = plot("Data rate, one camera", "frame rate (fps)", "Mbit/s", log_y=True)
        self.p_ov = plot("Overlap between consecutive frames", "frame rate (fps)", "overlap (%)")
        for p in (self.p_px, self.p_blur, self.p_rate, self.p_ov):
            p.addLegend(offset=(8, 8), labelTextColor="k", brush=pg.mkBrush(255, 255, 255, 200))
            p.setMinimumWidth(160)
        self.notes = Notes()
        self.table = QtWidgets.QTableWidget()
        for i, w in enumerate((self.p_px, self.p_blur, self.p_rate, self.p_ov)):
            g.addWidget(w, i // 2, i % 2)
        top = QtWidgets.QSplitter(Qt.Orientation.Horizontal)
        top.addWidget(grid)
        top.addWidget(self.notes)
        top.setSizes([900, 380])
        right.addWidget(top)
        right.addWidget(self.table)
        right.setSizes([620, 230])
        lay.addWidget(right, 1)

    def redraw_empty(self):
        for p in (self.p_px, self.p_blur, self.p_rate, self.p_ov):
            p.clear()
        self.notes.setHtml("<p>Pick a scene and at least one rig.</p>")

    def redraw(self):
        s = self.session
        scene = s.scene()
        primary = s.primary() or s.shown_rigs()[0]
        self.scene_panel.set_object("scenes", s.scene_id)
        self.rig_panel.set_object("rigs", primary.id)
        rigs = s.shown_rigs()
        vis = scene["visibility_m"]
        v = scene["speed_m_s"] * 1000

        # pixels on target
        p = self.p_px
        p.clear()
        z = np.linspace(0.1, max(vis * 1.4, 1), 120)
        for res in rigs:
            for size, style in ((scene["target_small_mm"], None), (scene["target_large_mm"], Qt.PenStyle.DashLine)):
                lw = 3 if res.id == primary.id else 1.5
                p.plot(z, imaging.pixels_on_target(size, z * 1000, res.optics.px_per_rad_axis),
                       pen=pen(res.colour_index, lw, style),
                       name=f"{res.name}, {size:g} mm" if style is None or len(rigs) == 1 else None)
        hline(p, np.log10(scene["pixels_needed"]), "#222", label=f"{scene['pixels_needed']:g} px needed")
        vline(p, vis, "#222", label=f"visibility {vis:g} m")
        p.setTitle(f"Pixels across: solid {scene['target_small_mm']:g} mm, dashed {scene['target_large_mm']:g} mm",
                   color="k", size="9pt")
        p.setXRange(0, max(vis * 1.4, 1))

        # motion blur
        p = self.p_blur
        p.clear()
        t_ms = np.geomspace(0.1, 200, 80)
        f = primary.optics.px_per_rad_axis
        for zz, ci in ((1.0, 3), (2.0, 4), (3.0, 5)):
            p.plot(t_ms, imaging.motion_blur_px(v, t_ms / 1000, zz * 1000, f), pen=pen(ci, 2), name=f"{zz:g} m range")
            _ = pg.TextItem
        hline(p, np.log10(scene["blur_limit_px"]), "#222", label=f"{scene['blur_limit_px']:g} px limit")
        vline(p, np.log10(primary.rig["exposure_ms"]), "#222", Qt.PenStyle.SolidLine,
              f"this rig: {primary.rig['exposure_ms']:g} ms")
        vline(p, np.log10(1000 / primary.rig["fps"]), "#888", label="one frame")
        p.setTitle(f"Motion blur at {scene['speed_m_s']:g} m/s", color="k", size="9pt")

        # data rate
        p = self.p_rate
        p.clear()
        fps = np.linspace(1, max(60.0, primary.rig["fps"] * 1.5), 80)
        w_px, h_px = primary.optics.width_px, primary.optics.height_px
        bits = self.ws.get("sensors", primary.rig["sensor"])["bits"]
        p.plot(fps, imaging.raw_data_rate_mbit_s(w_px, h_px, bits, fps), pen=pen(2, 2), name="raw (uncompressed)")
        p.plot(fps, imaging.encoded_data_rate_mbit_s(w_px, h_px, fps, primary.rig["encoded_bpp"]), pen=pen(0, 2),
               name=f"encoded at {primary.rig['encoded_bpp']:g} bit/px")
        vline(p, primary.rig["fps"], "#222", Qt.PenStyle.SolidLine, f"this rig: {primary.rig['fps']:g} fps")
        sensor_max = self.ws.get("sensors", primary.rig["sensor"])["max_fps"]
        vline(p, sensor_max, "#888", label=f"sensor mode max {sensor_max:g}")
        p.setTitle("Data rate, one camera", color="k", size="9pt")

        # overlap
        p = self.p_ov
        p.clear()
        vfov = primary.optics.fov_deg[1]
        for zz, ci in ((0.5, 6), (1.0, 3), (2.0, 4), (3.0, 5)):
            p.plot(fps, 100 * imaging.frame_overlap(v, fps, zz * 1000, vfov), pen=pen(ci, 2), name=f"{zz:g} m range")
        vline(p, primary.rig["fps"], "#222", Qt.PenStyle.SolidLine, "this rig")
        p.setYRange(0, 101)
        p.setTitle(f"Frame overlap, travel along the {vfov:.0f} deg view", color="k", size="9pt")

        self._table(rigs, scene, v)
        self._notes(primary, scene, v)

    def _table(self, rigs, scene, v):
        def gsd(z):
            return lambda r: f"{float(imaging.ground_sample_mm(z * 1000, r.optics.px_per_rad_axis)):.2f}"

        def px(size_key, z):
            return lambda r: f"{float(imaging.pixels_on_target(scene[size_key], z * 1000, r.optics.px_per_rad_axis)):.0f}"

        def blur(z):
            return lambda r: f"{float(imaging.motion_blur_px(v, r.rig['exposure_ms'] / 1000, z * 1000, r.optics.px_per_rad_axis)):.2f}"

        def reach(size_key):
            return lambda r: f"{float(imaging.range_for_pixels_mm(scene[size_key], scene['pixels_needed'], r.optics.px_per_rad_axis)) / 1000:.2f}"

        def rate(r):
            bits = self.ws.get("sensors", r.rig["sensor"])["bits"]
            return f"{imaging.raw_data_rate_mbit_s(r.optics.width_px, r.optics.height_px, bits, r.rig['fps']):.0f}"

        def enc(r):
            return f"{imaging.encoded_data_rate_mbit_s(r.optics.width_px, r.optics.height_px, r.rig['fps'], r.rig['encoded_bpp']):.2f}"

        rows = [("Image size (px)", lambda r: f"{r.optics.width_px:.0f} x {r.optics.height_px:.0f}"),
                ("mm per pixel at 1 m", gsd(1)), ("mm per pixel at 2 m", gsd(2)), ("mm per pixel at 3 m", gsd(3)),
                ("Small target, pixels across at 2 m", px("target_small_mm", 2)),
                ("Large target, pixels across at 2 m", px("target_large_mm", 2)),
                ("Small target recognisable to (m)", reach("target_small_mm")),
                ("Large target recognisable to (m)", reach("target_large_mm")),
                ("Blur at 1 m (px)", blur(1)), ("Blur at 2 m (px)", blur(2)), ("Blur at 3 m (px)", blur(3)),
                ("Raw rate per camera (Mbit/s)", rate), ("Encoded rate per camera (Mbit/s)", enc)]
        self.rig_table(self.table, rigs, rows)

    def _notes(self, primary, scene, v):
        f = primary.optics.px_per_rad_axis
        e = primary.rig["exposure_ms"] / 1000
        tmax = {z: float(imaging.max_exposure_s(scene["blur_limit_px"], v, z * 1000, f)) * 1000 for z in (1, 2, 3)}
        h = [f"<h4>{primary.name}</h4>",
             f"<p>One pixel covers <b>{float(imaging.ground_sample_mm(2000, f)):.2f} mm</b> on a target 2 m away "
             f"(z / f<sub>px</sub> with f<sub>px</sub> = {f:.0f}). A {scene['target_small_mm']:g} mm object is "
             f"{float(imaging.pixels_on_target(scene['target_small_mm'], 2000, f)):.0f} px across there, and reaches "
             f"your {scene['pixels_needed']:g} px threshold out to "
             f"{float(imaging.range_for_pixels_mm(scene['target_small_mm'], scene['pixels_needed'], f)) / 1000:.1f} m.</p>",
             f"<p>At {scene['speed_m_s']:g} m/s across the view, a {primary.rig['exposure_ms']:g} ms exposure moves the "
             f"scene {v * e:.1f} mm, which is {float(imaging.motion_blur_px(v, e, 2000, f)):.2f} px at 2 m. To stay under "
             f"{scene['blur_limit_px']:g} px the exposure may be at most {tmax[1]:.1f} ms at 1 m, {tmax[2]:.1f} ms at 2 m, "
             f"{tmax[3]:.1f} ms at 3 m (blur = v t / GSD). Dim water pushes exposures the other way.</p>",
             f"<p>Frame rate: at {primary.rig['fps']:g} fps the vehicle moves {v / primary.rig['fps']:.0f} mm between "
             f"frames, which keeps "
             f"{100 * float(imaging.frame_overlap(v, primary.rig['fps'], 1000, primary.optics.fov_deg[1])):.1f} % of the "
             f"view at 1 m. Motion blur and frame rate are separate limits: a long exposure blurs, a low rate loses overlap.</p>",
             "<p class='dim'>Pixels are counted, not detail: lens sharpness, colour demosaicing, compression and "
             "turbid water all reduce what can be resolved.</p>"]
        if self.ws.get("sensors", primary.rig["sensor"])["shutter"] == "rolling":
            h.append("<p class='dim'>Rolling shutter: rows are exposed one after another, so fast motion also shears "
                     "the image. Not modelled here.</p>")
        self.notes.setHtml("".join(h))
