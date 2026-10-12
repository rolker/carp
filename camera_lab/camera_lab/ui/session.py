"""What is selected right now, shared by all pages: the scene, the medium
(the scene's own unless overridden in the toolbar), the rigs shown and the
primary rig. Turns workspace objects into the numbers pages draw."""
from ..models import system
from ..qtcompat import QtCore, Signal


def scene_for_models(scene):
    """A scene's stored values in the units the models want (fractions, not
    percent)."""
    s = dict(scene)
    s["depth_tolerance"] = scene["depth_tolerance_pct"] / 100.0
    s["overlap_fraction"] = scene["overlap_pct"] / 100.0
    return s


class Resolved:
    """One rig with everything it refers to, looked up and computed."""

    def __init__(self, rig_id, rig, optics, colour_index):
        self.id, self.rig, self.optics, self.colour_index = rig_id, rig, optics, colour_index
        self.name = rig["name"]


class Session(QtCore.QObject):
    changed = Signal()          # the selection changed (not the objects)

    def __init__(self, ws, parent=None):
        super().__init__(parent)
        self.ws = ws
        self.scene_id = self._first("scenes")
        self.medium_override = None
        self.shown = set(i for i in ("carp_95", "carp_74", "narrow_4mm") if ws.exists("rigs", i))
        self.primary_id = "carp_95" if ws.exists("rigs", "carp_95") else self._first("rigs")
        if not self.shown and self.primary_id:
            self.shown = {self.primary_id}

    def _first(self, kind):
        ids = self.ws.ids(kind)
        return ids[0] if ids else None

    def set(self, **kw):
        for k, v in kw.items():
            setattr(self, k, v)
        self.changed.emit()

    # ---- derived -------------------------------------------------------

    def scene(self):
        data = self.ws.get("scenes", self.scene_id) if self.scene_id else None
        return scene_for_models(data) if data else None

    def medium_id(self):
        scene = self.ws.get("scenes", self.scene_id) if self.scene_id else None
        return self.medium_override or (scene["medium"] if scene else None)

    def medium(self):
        m = self.medium_id()
        return self.ws.get("media", m) if m and self.ws.exists("media", m) else None

    def resolve(self, rig_id):
        rig = self.ws.get("rigs", rig_id)
        medium = self.medium()
        if rig is None or medium is None:
            return None
        o = system.optics(self.ws.get("sensors", rig["sensor"]), self.ws.get("lenses", rig["lens"]),
                          self.ws.get("ports", rig["port"]), medium, rig["image_scale"])
        order = self.ws.ids("rigs")
        return Resolved(rig_id, rig, o, order.index(rig_id))

    def shown_rigs(self):
        """Resolved rigs that are shown, in list order; the primary first
        if it is shown."""
        out = [r for i in self.ws.ids("rigs") if i in self.shown
               for r in [self.resolve(i)] if r]
        return out

    def primary(self):
        return self.resolve(self.primary_id) if self.primary_id else None
