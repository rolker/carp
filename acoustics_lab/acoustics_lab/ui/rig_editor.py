"""The rig editor: which real device and channel each transducer of a layout
is on, how each device is taken hold of, and which inputs carry loopbacks.

A table of transducers against devices, a table of devices (card, access
mode, mixer values to apply, latency allowance), loopbacks, and an
**Identify** button that plays a short tone on one transducer so a person can
say which one it is. Every committed cell is one undo step, and the rig's
as-built scene follows (objects/rigs.py). Nothing is opened or played until
Identify is pressed.
"""
from ..backends.hardware import Environment
from ..objects import rigs, schema as s
from ..objects.schema import InUseError, WorkspaceError
from ..qtcompat import Qt, QtWidgets
from .widgets import CallWorker, ComboDelegate, read_only

DEVICE_COLUMNS = ["ID", "Card", "Access", "Server device", "Rate (Hz)", "Block",
                  "Input ch.", "Latency allowance (s)", "Mixer settings to apply"]
D_ID, D_CARD, D_ACCESS, D_SERVER, D_RATE, D_BLOCK, D_INPUT, D_LATENCY, D_MIXER = range(9)
TRANSDUCER_COLUMNS = ["Transducer", "Name", "Can", "Device", "Channel"]
T_ID, T_NAME, T_CAN, T_DEVICE, T_CHANNEL = range(5)
LOOPBACK_COLUMNS = ["Input", "Output"]
SERVER_DEVICES = ("pulse", "pipewire", "default")
CHANNELS = (("left", "left"), ("right", "right"), ("0", 0), ("1", 1))
NOT_PLACED = "(not placed)"


def mixer_text(settings):
    return "; ".join(f"{k}={v}" for k, v in (settings or {}).items())


def parse_mixer(text):
    """{control: value} from 'Name=value; Name=value'. ValueError for a part
    without '='."""
    out = {}
    for part in text.split(";"):
        if not part.strip():
            continue
        if "=" not in part:
            raise ValueError(f"'{part.strip()}' needs NAME=VALUE (for example "
                             "Master Playback Volume=-15dB)")
        name, value = part.rsplit("=", 1)
        out[name.strip()] = value.strip()
    return out


class RigEditor(QtWidgets.QDialog):
    def __init__(self, session, parent=None, environment=None):
        super().__init__(parent)
        self.session = session
        self.ws = session.workspace
        self.env = environment or session.environment or Environment()
        self.rig_id = session.rig_id
        self._filling = False
        self.worker = None
        self.setWindowTitle("Rigs")
        self.resize(1100, 700)
        self._build()
        self.ws.changed.connect(self._changed)
        self.fill()

    # ---- layout --------------------------------------------------------

    def _button(self, text, slot, tip=""):
        b = QtWidgets.QPushButton(text)
        b.setToolTip(tip)
        b.clicked.connect(lambda _=False: slot())
        return b

    def _build(self):
        box = QtWidgets.QVBoxLayout(self)
        top = QtWidgets.QHBoxLayout()
        top.addWidget(QtWidgets.QLabel("Rig"))
        self.rig_box = QtWidgets.QComboBox()
        self.rig_box.setMinimumWidth(240)
        self.rig_box.currentIndexChanged.connect(self._rig_picked)
        top.addWidget(self.rig_box)
        top.addWidget(self._button("New rig for a layout", self.new_rig,
                                   "A rig for the selected layout; place its transducers below"))
        top.addWidget(self._button("New laptop rig", self.laptop_template,
                                   "The laptop's own speaker and microphone, with a demo room "
                                   "scene and a ping design for the room sonar"))
        top.addWidget(self._button("Delete", self.delete_rig,
                                   "Deletes the rig and its as-built scene"))
        top.addStretch(1)
        box.addLayout(top)

        form = QtWidgets.QFormLayout()
        self.name = QtWidgets.QLineEdit()
        self.name.editingFinished.connect(self._name_edited)
        self.layout_box = QtWidgets.QComboBox()
        self.layout_box.currentIndexChanged.connect(self._layout_picked)
        form.addRow("Name", self.name)
        form.addRow("Layout", self.layout_box)
        box.addLayout(form)

        t = self.device_table = QtWidgets.QTableWidget(0, len(DEVICE_COLUMNS))
        t.setHorizontalHeaderLabels(DEVICE_COLUMNS)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.itemChanged.connect(self._device_edited)
        t.setItemDelegateForColumn(D_CARD, ComboDelegate(self._card_choices, t))
        t.setItemDelegateForColumn(D_ACCESS, ComboDelegate(
            lambda: [(a, a) for a in s.ACCESS], t))
        t.setItemDelegateForColumn(D_SERVER, ComboDelegate(
            lambda: [(n, n) for n in SERVER_DEVICES], t))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button("Add device", self.add_device))
        row.addWidget(self._button("Delete device", self.delete_device))
        row.addWidget(self._button("Refresh cards", self.fill,
                                   "Look at the sound cards again"))
        row.addStretch(1)
        group = QtWidgets.QGroupBox("Devices  (exclusive: the card is borrowed from the "
                                    "desktop and opened directly; shared: through the sound server)")
        inner = QtWidgets.QVBoxLayout(group)
        inner.addWidget(t)
        inner.addLayout(row)
        box.addWidget(group, 3)

        t = self.transducer_table = QtWidgets.QTableWidget(0, len(TRANSDUCER_COLUMNS))
        t.setHorizontalHeaderLabels(TRANSDUCER_COLUMNS)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setSelectionBehavior(QtWidgets.QAbstractItemView.SelectionBehavior.SelectRows)
        t.itemChanged.connect(self._transducer_edited)
        t.setItemDelegateForColumn(T_DEVICE, ComboDelegate(self._device_choices, t))
        t.setItemDelegateForColumn(T_CHANNEL, ComboDelegate(lambda: list(CHANNELS), t))
        row = QtWidgets.QHBoxLayout()
        self.identify_button = self._button(
            "Identify", self.identify,
            "Play a short, quiet tone on the selected transducer so you can tell which it is. "
            "An exclusive device is borrowed from the desktop for that moment.")
        row.addWidget(self.identify_button)
        self.identify_text = QtWidgets.QLabel()
        self.identify_text.setWordWrap(True)
        row.addWidget(self.identify_text, 1)
        group = QtWidgets.QGroupBox("Transducers of the layout, and where each is wired")
        inner = QtWidgets.QVBoxLayout(group)
        inner.addWidget(t)
        inner.addLayout(row)
        box.addWidget(group, 3)

        t = self.loopback_table = QtWidgets.QTableWidget(0, len(LOOPBACK_COLUMNS))
        t.setHorizontalHeaderLabels(LOOPBACK_COLUMNS)
        t.verticalHeader().setVisible(False)
        t.horizontalHeader().setStretchLastSection(True)
        t.setMaximumHeight(110)
        t.itemChanged.connect(self._loopback_edited)
        t.setItemDelegateForColumn(0, ComboDelegate(lambda: self._placed(receivers=True), t))
        t.setItemDelegateForColumn(1, ComboDelegate(lambda: self._placed(receivers=False), t))
        row = QtWidgets.QHBoxLayout()
        row.addWidget(self._button("Add loopback", self.add_loopback))
        row.addWidget(self._button("Delete loopback", self.delete_loopback))
        row.addStretch(1)
        group = QtWidgets.QGroupBox("Loopbacks  (an electrical copy of an output mixed into an "
                                    "input; time zero for pings of that output)")
        inner = QtWidgets.QVBoxLayout(group)
        inner.addWidget(t)
        inner.addLayout(row)
        box.addWidget(group, 1)

        self.message = QtWidgets.QLabel()
        self.message.setWordWrap(True)
        box.addWidget(self.message)

    # ---- choices ---------------------------------------------------------

    def _cards(self):
        try:
            return self.env.cards()
        except Exception:               # noqa: no /proc/asound here: no cards
            return []

    def _card_choices(self):
        out = [("(the built-in card)", "")]
        for card in self._cards():
            ref = card.usb_port or card.id if card.usb else card.id
            out.append((card.label(), ref))
        return out

    def _device_choices(self):
        rig = self.ws.get("rigs", self.rig_id or "") or {}
        return [(NOT_PLACED, None)] + [(d["id"], d["id"]) for d in rig.get("devices", [])]

    def _placed(self, receivers):
        rig = self.ws.get("rigs", self.rig_id or "") or {}
        layout = self.ws.get("layouts", rig.get("layout", "")) or {"transducers": []}
        placed = rigs.placements(rig)
        key = "can_receive" if receivers else "can_send"
        return [(t.get("name", t["id"]), t["id"]) for t in layout["transducers"]
                if t.get(key) and t["id"] in placed]

    def _card_text(self, ref):
        if not ref:
            return "(the built-in card)"
        for label, value in self._card_choices():
            if value == ref:
                return label
        return f"{ref} (not found: moved or unplugged?)"

    # ---- filling ---------------------------------------------------------

    def _changed(self, kind, object_id):
        if kind in ("rigs", "layouts"):
            self.fill()

    def fill(self):
        self._filling = True
        self.rig_box.clear()
        for rid in self.ws.ids("rigs"):
            self.rig_box.addItem(self.ws.name_of("rigs", rid), rid)
        at = self.rig_box.findData(self.rig_id)
        self.rig_box.setCurrentIndex(at if at >= 0 else (0 if self.rig_box.count() else -1))
        self.rig_id = self.rig_box.currentData()
        self.layout_box.clear()
        for lid in self.ws.ids("layouts"):
            self.layout_box.addItem(self.ws.name_of("layouts", lid), lid)
        self._filling = False
        self._fill_rig()

    def _rig_picked(self, _):
        if self._filling:
            return
        self.rig_id = self.rig_box.currentData()
        self._fill_rig()

    def _fill_rig(self):
        rig = self.ws.get("rigs", self.rig_id) if self.rig_id else None
        self._filling = True
        enabled = rig is not None
        for w in (self.name, self.layout_box, self.device_table, self.transducer_table,
                  self.loopback_table, self.identify_button):
            w.setEnabled(enabled)
        for table in (self.device_table, self.transducer_table, self.loopback_table):
            table.setRowCount(0)
        if rig is None:
            self.name.clear()
            self.message.setText("No rig yet. 'New laptop rig' makes one for this computer's "
                                 "speaker and microphone; 'New rig for a layout' starts an "
                                 "empty one.")
            self._filling = False
            return
        if not self.name.hasFocus():
            self.name.setText(rig["name"])
        self.layout_box.setCurrentIndex(self.layout_box.findData(rig["layout"]))
        t = self.device_table
        for d in rig["devices"]:
            n = t.rowCount()
            t.insertRow(n)
            shared = d.get("access", "exclusive") == "shared"
            cells = {D_ID: d["id"], D_CARD: "" if shared else self._card_text(d.get("card", "")),
                     D_ACCESS: d.get("access", "exclusive"),
                     D_SERVER: d.get("server_device", "pulse") if shared else "",
                     D_RATE: f"{d.get('rate', 48000):g}", D_BLOCK: f"{d.get('block', 512)}",
                     D_INPUT: f"{d.get('input_channel', 0)}",
                     D_LATENCY: f"{d.get('latency_allowance_s', 0.15):g}",
                     D_MIXER: "" if shared else mixer_text(d.get("mixer"))}
            for column, text in cells.items():
                item = QtWidgets.QTableWidgetItem(text)
                if column == D_ID:
                    item.setData(Qt.ItemDataRole.UserRole, d["id"])
                if column == D_CARD:
                    item.setData(Qt.ItemDataRole.UserRole, d.get("card", ""))
                if column == D_ACCESS:
                    item.setData(Qt.ItemDataRole.UserRole, d.get("access", "exclusive"))
                if column == D_SERVER:
                    item.setData(Qt.ItemDataRole.UserRole, d.get("server_device", "pulse"))
                if (column == D_CARD and shared) or (column == D_SERVER and not shared) \
                        or (column == D_MIXER and shared):
                    read_only(item)
                t.setItem(n, column, item)
        t.resizeColumnsToContents()
        layout = self.ws.get("layouts", rig["layout"]) or {"transducers": []}
        placed = rigs.placements(rig)
        t = self.transducer_table
        for tr in layout["transducers"]:
            n = t.rowCount()
            t.insertRow(n)
            place = placed.get(tr["id"])
            can = " and ".join(w for w, on in (("send", tr.get("can_send")),
                                                ("receive", tr.get("can_receive"))) if on)
            cells = {T_ID: tr["id"], T_NAME: tr.get("name", tr["id"]), T_CAN: can,
                     T_DEVICE: place["device"] if place else NOT_PLACED,
                     T_CHANNEL: str(place.get("channel", "left")) if place else ""}
            for column, text in cells.items():
                item = QtWidgets.QTableWidgetItem(text)
                if column in (T_ID, T_NAME, T_CAN):
                    read_only(item)
                if column == T_ID:
                    item.setData(Qt.ItemDataRole.UserRole, tr["id"])
                if column == T_DEVICE:
                    item.setData(Qt.ItemDataRole.UserRole, place["device"] if place else None)
                if column == T_CHANNEL and place:
                    item.setData(Qt.ItemDataRole.UserRole, place.get("channel", "left"))
                t.setItem(n, column, item)
        t.resizeColumnsToContents()
        t = self.loopback_table
        names = {tr["id"]: tr.get("name", tr["id"]) for tr in layout["transducers"]}
        for lb in rig.get("loopbacks", []):
            n = t.rowCount()
            t.insertRow(n)
            for column, key in ((0, "receiver"), (1, "emitter")):
                item = QtWidgets.QTableWidgetItem(names.get(lb[key], lb[key]))
                item.setData(Qt.ItemDataRole.UserRole, lb[key])
                t.setItem(n, column, item)
        t.resizeColumnsToContents()
        self._filling = False
        problems = rigs.problems(rig, layout)
        self.message.setText("\n".join(problems))

    # ---- editing ---------------------------------------------------------

    def _update(self, text=None, **changes):
        """One undo step: change the rig and bring its as-built scene in step.
        A refusal is shown and the old values come back."""
        try:
            rigs.update_rig(self.ws, self.rig_id, text, **changes)    # refills, which says
                                                                      # what is still missing
        except (WorkspaceError, ValueError) as error:
            self._fill_rig()
            self.message.setText(f"Not changed: {error}")

    def _rig(self):
        return self.ws.get("rigs", self.rig_id)

    def _name_edited(self):
        text = self.name.text().strip()
        if self.rig_id and text and text != self.ws.name_of("rigs", self.rig_id):
            self._update(name=text)

    def _layout_picked(self, _):
        if self._filling or not self.rig_id:
            return
        layout_id = self.layout_box.currentData()
        rig = self._rig()
        if layout_id and layout_id != rig["layout"]:
            self._update(layout=layout_id, transducers=[], loopbacks=[])
            self.message.setText("The layout changed, so the transducers must be placed again.")

    def _device_edited(self, item):
        if self._filling or not self.rig_id:
            return
        rig = self._rig()
        n, column, text = item.row(), item.column(), item.text().strip()
        devices = rig["devices"]
        old_id = devices[n]["id"]
        d = devices[n]
        try:
            if column == D_ID:
                if not text:
                    raise ValueError("a device needs an ID")
                d["id"] = text
                transducers = [dict(t, device=text) if t["device"] == old_id else t
                               for t in rig["transducers"]]
                self._update(devices=devices, transducers=transducers)
                return
            if column == D_CARD:
                d["card"] = item.data(Qt.ItemDataRole.UserRole) or ""
            elif column == D_ACCESS:
                d["access"] = item.data(Qt.ItemDataRole.UserRole) or text
            elif column == D_SERVER:
                d["server_device"] = item.data(Qt.ItemDataRole.UserRole) or text
            elif column == D_RATE:
                d["rate"] = _number(text, "The sample rate")
            elif column == D_BLOCK:
                d["block"] = int(_number(text, "The block size"))
            elif column == D_INPUT:
                d["input_channel"] = int(_number(text, "The input channel"))
            elif column == D_LATENCY:
                d["latency_allowance_s"] = _number(text, "The latency allowance")
            elif column == D_MIXER:
                d["mixer"] = parse_mixer(text)
        except ValueError as error:
            self._fill_rig()
            self.message.setText(f"Not changed: {error}")
            return
        self._update(devices=devices)

    def add_device(self):
        if not self.rig_id:
            return
        devices = self._rig()["devices"]
        n = len(devices) + 1
        while any(d["id"] == f"device{n}" for d in devices):
            n += 1
        devices.append(s.device_config(f"device{n}"))
        self._update(devices=devices)

    def delete_device(self):
        rows = self.device_table.selectionModel().selectedRows()
        if not (self.rig_id and rows):
            return
        rig = self._rig()
        gone = rig["devices"][rows[0].row()]["id"]
        users = [t["id"] for t in rig["transducers"] if t["device"] == gone]
        if users:
            self.message.setText(f"Not deleted: {', '.join(users)} are wired to device "
                                 f"'{gone}'; place them elsewhere first.")
            return
        self._update(devices=[d for d in rig["devices"] if d["id"] != gone])

    def _transducer_edited(self, item):
        if self._filling or not self.rig_id:
            return
        rig = self._rig()
        tid = self.transducer_table.item(item.row(), T_ID).data(Qt.ItemDataRole.UserRole)
        placed = [dict(t) for t in rig["transducers"]]
        entry = next((t for t in placed if t["id"] == tid), None)
        row = item.row()
        if item.column() == T_DEVICE:
            device = item.data(Qt.ItemDataRole.UserRole)
            if device is None:
                placed = [t for t in placed if t["id"] != tid]
                loopbacks = [lb for lb in rig["loopbacks"]
                             if tid not in (lb["receiver"], lb["emitter"])]
                self._update(transducers=placed, loopbacks=loopbacks)
                return
            if entry is None:
                layout = self.ws.get("layouts", rig["layout"])
                info = next(t for t in layout["transducers"] if t["id"] == tid)
                entry = dict(id=tid, device=device,
                             channel="left" if info.get("can_send") else 0)
                placed.append(entry)
            else:
                entry["device"] = device
            loopbacks = [lb for lb in rig["loopbacks"]
                         if not (tid in (lb["receiver"], lb["emitter"])
                                 and {p["id"]: p["device"] for p in placed}.get(
                                     lb["receiver"]) != {p["id"]: p["device"] for p in placed}.get(
                                         lb["emitter"]))]
            self._update(transducers=placed, loopbacks=loopbacks)
        elif item.column() == T_CHANNEL and entry is not None:
            entry["channel"] = item.data(Qt.ItemDataRole.UserRole)
            if entry["channel"] is None:
                text = item.text().strip()
                entry["channel"] = int(text) if text.isdigit() else (text or "left")
            self._update(transducers=placed)
        else:
            self._fill_rig()

    def _loopback_edited(self, item):
        if self._filling or not self.rig_id:
            return
        loopbacks = [dict(lb) for lb in self._rig()["loopbacks"]]
        key = "receiver" if item.column() == 0 else "emitter"
        loopbacks[item.row()][key] = item.data(Qt.ItemDataRole.UserRole)
        self._update(loopbacks=loopbacks)

    def add_loopback(self):
        if not self.rig_id:
            return
        inputs, outputs = self._placed(True), self._placed(False)
        if not (inputs and outputs):
            self.message.setText("A loopback needs an output and an input that are placed on a device.")
            return
        loopbacks = self._rig()["loopbacks"]
        loopbacks.append(dict(receiver=inputs[0][1], emitter=outputs[0][1]))
        self._update(loopbacks=loopbacks)

    def delete_loopback(self):
        rows = self.loopback_table.selectionModel().selectedRows()
        if self.rig_id and rows:
            loopbacks = self._rig()["loopbacks"]
            del loopbacks[rows[0].row()]
            self._update(loopbacks=loopbacks)

    # ---- rigs ------------------------------------------------------------

    def new_rig(self):
        layout_id = self.layout_box.currentData() or next(iter(self.ws.ids("layouts")), None)
        if layout_id is None:
            self.message.setText("There is no layout to make a rig for.")
            return
        name = f"{self.ws.name_of('layouts', layout_id)} rig"
        self.rig_id = rigs.create_rig(self.ws, name, layout_id, [s.device_config("device1")], [])
        self.fill()

    def laptop_template(self):
        ids = rigs.laptop_template(self.ws)
        self.rig_id = ids["rig"]
        self.fill()
        self.message.setText("The laptop rig, its as-built scene, a demo room scene and a "
                             "ping design for the room sonar are in the workspace.")

    def delete_rig(self):
        if self.rig_id:
            try:
                rigs.delete_rig(self.ws, self.rig_id)
            except InUseError as error:
                self.message.setText(f"Not deleted: {error}")

    # ---- Identify --------------------------------------------------------

    def identify(self):
        rows = self.transducer_table.selectionModel().selectedRows()
        if not (self.rig_id and rows):
            self.identify_text.setText("Select an output first.")
            return
        tid = self.transducer_table.item(rows[0].row(), T_ID).data(Qt.ItemDataRole.UserRole)
        if self.worker is not None:
            return
        self.identify_button.setEnabled(False)
        self.identify_text.setText("Playing a short tone ... (a card that is not open is "
                                   "borrowed from the desktop for this, and given back)")
        rig_id = self.rig_id
        self.worker = CallWorker(lambda: self.session.identify(tid, rig_id), self)
        self.worker.done.connect(self._identified)
        self.worker.failed.connect(self._identify_failed)
        self.worker.start()

    def _identify_finished(self):
        worker, self.worker = self.worker, None
        if worker is not None:
            worker.wait()
            worker.deleteLater()
        self.identify_button.setEnabled(True)

    def _identified(self, sentence):
        self._identify_finished()
        self.identify_text.setText(sentence)

    def _identify_failed(self, text):
        self._identify_finished()
        self.identify_text.setText(f"Could not play: {text}")

    def done(self, result):
        if self.worker is not None:
            self.worker.wait()
        super().done(result)


def _number(text, what):
    try:
        return float(text)
    except ValueError:
        raise ValueError(f"{what} must be a number, not '{text}'") from None
