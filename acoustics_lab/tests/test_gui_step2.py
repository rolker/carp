"""The window for step 2, driven headlessly (Qt's offscreen platform): the
room sonar page on simulation, hardware (a faked machine) and replay, the
rig editor with Identify, the As built button, detection designs. No sound
device is opened, no card borrowed, no mixer written."""
import json
import time

import numpy as np
import pytest

from acoustics_lab.objects import rigs, starter
from acoustics_lab.qtcompat import Qt, QtCore, pg
from acoustics_lab.ui.detection_dialog import DetectionDesignDialog
from acoustics_lab.ui.mainwindow import MainWindow
from acoustics_lab.ui.rig_editor import RigEditor
from acoustics_lab.workspace import Workspace
from fake_hardware import World, environment

app = pg.mkQApp("test")


@pytest.fixture
def world(monkeypatch):
    return World(monkeypatch)


@pytest.fixture
def window(tmp_path, world):
    settings = QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.Format.IniFormat)
    ws = Workspace(tmp_path / "ws")
    starter.populate(ws)
    w = MainWindow(ws, settings, environment=environment(world))
    w.show()
    yield w
    w.close()


def wait(condition, seconds=20):
    start = time.time()
    while not condition() and time.time() - start < seconds:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "timed out"


def room_page(window):
    window.page_list.setCurrentRow(window._row_of("Room sonar"))
    return window.page("Room sonar")


def ping(window, page=None):
    page = page or window.current_page()
    before = page.count
    window.ping_action.trigger()
    wait(lambda: page.count > before and not page.busy)
    return page


def laptop(window):
    page = room_page(window)
    page.make_laptop()
    return page


# ---- the room sonar page needs a speaker near a microphone ---------------------

def test_the_page_says_what_it_needs_offers_a_template_and_the_run_controls_wait(window):
    page = room_page(window)
    assert not page.needs_group.isHidden() and "no output within 0.5 m" in page.needs_text.text()
    assert not window.ping_action.isEnabled() and "no output within" in window.ping_action.toolTip()
    texts = [page.needs_buttons.itemAt(i).widget().text() for i in range(page.needs_buttons.count())]
    assert any("laptop speakers and microphone" in t for t in texts)
    page.make_laptop()
    assert page.needs_group.isHidden() and window.ping_action.isEnabled()
    assert window.session.scene_id == rigs.LAPTOP_DEMO and window.session.rig_id == rigs.LAPTOP_RIG
    assert page.design_box.currentData() == rigs.LAPTOP_DEFAULT_DESIGN
    assert page.input_box.currentData() == "mic"


def test_a_scene_that_fits_is_offered_when_the_active_one_does_not(window):
    laptop(window)
    window.session.set_scene("dongle_bench")                   # no speaker near a microphone
    page = window.page("Room sonar")
    labels = [page.needs_buttons.itemAt(i).widget().text() for i in range(page.needs_buttons.count())]
    assert "Use scene: Laptop in a room" in labels
    page.needs_buttons.itemAt(labels.index("Use scene: Laptop in a room")).widget().click()
    assert window.session.scene_id == rigs.LAPTOP_DEMO and page.needs_group.isHidden()


def test_pings_make_an_a_scan_an_echogram_and_changes_and_the_mover_stands_out(window):
    page = laptop(window)
    window.interval.setValue(0.2)
    assert page.rate_spin.value() == pytest.approx(5.0)         # the page and the toolbar are one setting
    for _ in range(25):
        ping(window, page)
    assert page.count == 25 and len(page.levels) == 25 and len(page.diffs) == 25
    assert "direct sound" in page.headline.text() and page.last.heard
    assert page.echogram.image.image is not None and page.changes.image.image.shape[1] == 25
    # the last ping's changes peak where the mover really is
    channel = page.last.channels[0]
    truth = [at for route, at in channel.truth if route in ("mover:person", "mover:trolley")]
    diff = page.diffs[-1][0]
    grid = channel.range_m
    assert min(abs(grid[np.argmax(np.where(grid > 0.4, diff, 0.0))] - at) for at in truth) < 0.1
    assert "Range resolution" in page.numbers.text() and "6.5 cm" in page.numbers.text()
    assert "the matched filter squeezes" in page.notes.toPlainText()
    assert "30.2 ms" in page.notes.toPlainText()


def test_numbers_and_listening_follow_the_maximum_range(window):
    page = laptop(window)
    page.range_spin.setValue(10.0)
    assert "10 m, listening 59" in page.numbers.text().replace("<b>", "").replace("</b>", "")
    ping(window, page)
    assert page.last.channels[0].range_m[-1] == pytest.approx(10.0, abs=0.01)
    page.range_spin.setValue(3.0)                              # other bins: the old pings are dropped
    assert page.levels == [] and page.count == 0


def test_the_background_memory_and_colour_floor_redraw_without_pinging(window):
    page = laptop(window)
    for _ in range(6):
        ping(window, page)
    before = page.changes.image.image.copy()
    page.memory_spin.setValue(2)
    assert not np.array_equal(before, page.changes.image.image)
    page.floor_spin.setValue(-50.0)
    assert page.changes.image.levels[0] == -50.0
    page.clear()
    assert page.levels == [] and "No ping yet" in page.headline.text()


def test_a_ping_design_with_no_signal_or_a_far_pair_is_a_warning_not_a_refusal(window):
    page = laptop(window)
    window.session.set_scene("dongle_bench")
    page.needs_buttons.itemAt(0).widget().click()               # back to a scene that fits
    window.ws.update("ping_designs", page.design_id, events=[])
    window.ping_action.trigger()
    app.processEvents()
    assert "Check the ping design" in window.statusBar().currentMessage()


# ---- detection designs on the pages ------------------------------------------------

def test_the_detection_in_force_is_recorded_with_the_capture_and_can_be_changed(window):
    page = laptop(window)
    strict = window.ws.create("detection_designs", "strict", dict(
        starter.detection_design.new_default("strict"), first_fraction=0.9, hit_snr=20.0))
    ping(window, page)
    assert page.capture.meta["detection_design"]["id"] == starter.DEFAULT_DETECTION
    assert page.last.design_id == starter.DEFAULT_DETECTION
    page.detection_box.setCurrentIndex(page.detection_box.findData(strict))
    ping(window, page)
    assert page.last.design_id == strict and page.last.design.first_fraction == 0.9
    assert page.capture.meta["detection_design"]["hit_snr"] == 20.0
    assert "strict" in page.notes.toPlainText()
    page.detection_box.setCurrentIndex(0)                       # the ping design's own again
    page.reanalyse()
    assert page.last.design_id == starter.DEFAULT_DETECTION and page.count == 2
    assert "Analysed again" in page.headline.text() and len(page.levels) == 2


def test_the_ranging_page_has_the_same_choice_and_analyses_again(window):
    page = window.page("Ranging & positioning")
    window.page_list.setCurrentRow(window._row_of("Ranging & positioning"))
    assert page.default_detection.currentData() == starter.DEFAULT_DETECTION
    other = window.ws.create("detection_designs", "wide", dict(
        starter.detection_design.new_default("wide"), first_fraction=0.05))
    ping(window, page)
    assert page.results["mic"].design_id == starter.DEFAULT_DETECTION
    page.detection_box.setCurrentIndex(page.detection_box.findData(other))
    page.reanalyse()
    assert page.results["mic"].design_id == other and page.results["mic"].design.first_fraction == 0.05
    assert "Analysed again" in page.headline.text()
    page.default_detection.setCurrentIndex(page.default_detection.findData(other))
    assert window.ws.get("ping_designs", "left_then_right")["detection_design"] == other
    window.ws.undo_stack.undo()
    assert window.ws.get("ping_designs", "left_then_right")["detection_design"] == starter.DEFAULT_DETECTION


def test_recordings_carry_their_detection_design_and_replay_can_use_another(window, tmp_path):
    page = laptop(window)
    page.save_check.setChecked(True)
    for _ in range(3):
        ping(window, page)
    runs = list((window.ws.path / "runs").rglob("*.wav"))
    assert len(runs) == 3
    sidecar = json.loads((str(runs[0]) + ".json") and open(str(runs[0]) + ".json").read())
    assert sidecar["acoustics_lab"]["detection_design"]["id"] == starter.DEFAULT_DETECTION
    assert sidecar["acoustics_lab"]["detection_design"]["first_fraction"] == 0.3
    other = window.ws.create("detection_designs", "wide", dict(
        starter.detection_design.new_default("wide"), first_fraction=0.05))
    window.open_replay(str(runs[0].parent))
    page.clear()
    ping(window, page)
    assert "Recording 1 of 3" in page.headline.text() and page.last.heard
    assert page.last.design_id == starter.DEFAULT_DETECTION          # the ping design's own default
    page.detection_box.setCurrentIndex(page.detection_box.findData(other))
    page.reanalyse()
    assert page.last.design_id == other and page.last.design.first_fraction == 0.05
    assert page.last.channels[0].baseline_m == pytest.approx(0.3064, abs=1e-3)   # from the recording's layout
    assert not page.input_box.isEnabled()                             # replay: the recording decides


def test_the_detection_design_editor_edits_with_undo_and_refuses(window):
    dialog = DetectionDesignDialog(window.ws)
    ws = window.ws
    rows = {dialog.table.item(r, 0).text(): r for r in range(dialog.table.rowCount())}
    value = dialog.table.item(rows["first_fraction"], 2)
    count = ws.undo_stack.count()
    value.setText("0.6")
    assert ws.get("detection_designs", starter.DEFAULT_DETECTION)["first_fraction"] == 0.6
    assert ws.undo_stack.count() == count + 1
    assert dialog.table.item(rows["first_fraction"], 2).font().bold()          # differs from the default
    value = dialog.table.item(rows["first_fraction"], 2)
    value.setText("7")
    assert "First-arrival fraction must be between" in dialog.message.text()
    assert ws.get("detection_designs", starter.DEFAULT_DETECTION)["first_fraction"] == 0.6
    dialog.table.item(rows["detect_snr"], 2).setText("abc")
    assert "must be a number" in dialog.message.text()
    ws.undo_stack.undo()
    assert ws.get("detection_designs", starter.DEFAULT_DETECTION)["first_fraction"] == 0.3
    dialog.delete()
    assert "Not deleted" in dialog.message.text() and "left_then_right" in dialog.message.text()
    dialog.new_copy()
    assert len(ws.ids("detection_designs")) == 2
    dialog.method_changed = None
    dialog.table.item(rows["method"], 2).setText("envelope")
    assert ws.get("detection_designs", dialog.design_id)["method"] == "envelope"
    dialog.close()


# ---- hardware ------------------------------------------------------------------------

def test_hardware_is_a_choice_and_makes_the_as_built_scene_active(window, world):
    page = laptop(window)
    assert window.backend_box.model().item(2).isEnabled()
    session = window.session
    assert session.scene_id == rigs.LAPTOP_DEMO
    assert "simulating Laptop in a room, not built" in window.built_label.text()
    assert window.as_built_button.isEnabled()
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    built = window.ws.get("rigs", rigs.LAPTOP_RIG)["as_built"]
    assert session.mode == "hardware" and session.scene_id == built
    assert "the bench as built" in window.built_label.text()
    assert not window.as_built_button.isEnabled() and not window.sim_widgets[1].isVisible()
    assert window.ping_action.isEnabled()
    ping(window, page)
    assert page.last.heard and page.capture.meta["backend"] == "Hardware"
    assert world.log.count("borrow") == 1 and world.log.count("open laptop hw") == 1
    ping(window, page)
    assert world.log.count("borrow") == 1                                 # kept open
    assert "hardware: Laptop speaker and mic (open)" in window.backend_label.text()
    assert "the desktop's own sound" in window.hardware_log.toPlainText()
    assert not window.hardware_dock.isHidden()                            # a warning shows it
    # going back to simulation gives the card back and puts the volumes back
    window.backend_box.setCurrentIndex(window.backend_box.findData("simulation"))
    assert world.log.count("release") == 1
    assert [n.volumes for n in world.server.current] == [[0.13, 0.13], [0.70, 0.70]]
    assert session.mode == "simulation"


def test_the_as_built_button_comes_back_from_a_simulated_variant(window):
    laptop(window)
    session = window.session
    assert not session.is_as_built() and window.as_built_button.isEnabled()
    window.as_built_button.click()
    assert session.is_as_built() and window.built_label.text().strip() == "as built"
    assert not window.as_built_button.isEnabled()
    session.set_scene(rigs.LAPTOP_DEMO)
    assert "not built" in window.built_label.text()
    assert "color: #d35400" in window.built_label.styleSheet()            # said plainly
    assert window.scene_box.currentData() == rigs.LAPTOP_DEMO


def test_the_as_built_scene_follows_a_rig_edit_made_while_it_is_active(window):
    laptop(window)
    window.as_built_button.click()
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    window.temp.setValue(25.0)                                           # the bench's air
    built = window.session.scene_id
    assert window.ws.get("scenes", built)["medium"]["temperature_c"] == 25.0
    assert window.session.hardware().sound_speed() == pytest.approx(346.1, abs=0.2)
    devices = window.ws.get("rigs", rigs.LAPTOP_RIG)["devices"]
    devices[0]["rate"] = 44100
    rigs.update_rig(window.ws, rigs.LAPTOP_RIG, devices=devices)
    assert window.ws.get("scenes", built)["devices"][0]["rate"] == 44100
    assert window.ws.get("scenes", built)["medium"]["temperature_c"] == 25.0   # kept


def test_hardware_without_a_rig_says_so_and_the_page_waits(window):
    page = room_page(window)
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    assert not window.ping_action.isEnabled()
    assert "no rig" in window.ping_action.toolTip()
    page.make_laptop()                                                   # also makes the rig usable here
    assert window.ping_action.isEnabled() and window.session.mode == "hardware"


def test_closing_the_window_gives_everything_back(tmp_path, world):
    settings = QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.Format.IniFormat)
    ws = Workspace(tmp_path / "ws")
    starter.populate(ws)
    rigs.laptop_template(ws)
    window = MainWindow(ws, settings, environment=environment(world))
    window.show()
    page = room_page(window)
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    ping(window, page)
    assert "release" not in world.log
    window.close()
    assert world.log.count("release") == 1
    assert [n.volumes for n in world.server.current] == [[0.13, 0.13], [0.70, 0.70]]
    assert [c.values for c in world.mixer.controls.values()
            if c.name in ("Master Playback Volume", "Capture Volume")] == [[17], [40]]


def test_the_ranging_page_runs_on_hardware_too(window, world):
    page = laptop(window)
    ws = window.ws
    sig = ws.ids("signals")[0]
    ws.create("ping_designs", "speaker to mic", dict(
        name="", roles=["bench"], receivers=["mic"], listen=0.1,
        events=[dict(transducer="left", signal=rigs.LAPTOP_SIGNAL, time=0.0)],
        detection_design=starter.DEFAULT_DETECTION))
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    window.page_list.setCurrentRow(window._row_of("Ranging & positioning"))
    ranging = window.page("Ranging & positioning")
    ranging.design_box.setCurrentIndex(ranging.design_box.findData("speaker_to_mic"))
    ping(window, ranging)
    rows = ranging.results["mic"].rows
    assert rows[0]["heard"] and rows[0]["transducer"] == "left"
    assert "all events heard" in ranging.headline.text()
    assert ranging.capture.meta["backend"] == "Hardware"
    assert ranging.capture.meta["detection_design"]["id"] == starter.DEFAULT_DETECTION


# ---- the rig editor ----------------------------------------------------------------------

def test_the_rig_editor_edits_a_rig_with_undo_and_keeps_the_as_built_scene_in_step(window):
    laptop(window)
    ws = window.ws
    editor = window.edit_rigs()
    assert isinstance(editor, RigEditor) and editor.rig_id == rigs.LAPTOP_RIG
    t = editor.device_table
    assert t.item(0, 1).text() == "(the built-in card)" and t.item(0, 2).text() == "exclusive"
    count = ws.undo_stack.count()
    t.item(0, 4).setText("44100")
    assert ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["rate"] == 44100
    built = ws.get("rigs", rigs.LAPTOP_RIG)["as_built"]
    assert ws.get("scenes", built)["devices"][0]["rate"] == 44100
    assert ws.undo_stack.count() == count + 1                            # one step for both
    t.item(0, 8).setText("Master Playback Volume=-15dB; Capture Volume=5dB")
    assert ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["mixer"] == {
        "Master Playback Volume": "-15dB", "Capture Volume": "5dB"}
    t.item(0, 8).setText("no equals sign")
    assert "needs NAME=VALUE" in editor.message.text()
    assert ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["mixer"]["Capture Volume"] == "5dB"
    t.item(0, 4).setText("abc")
    assert "must be a number" in editor.message.text()
    ws.undo_stack.undo()
    ws.undo_stack.undo()
    assert ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]["rate"] == 48000
    assert ws.get("scenes", built)["devices"][0]["rate"] == 48000


def test_the_rig_editor_changes_access_places_transducers_and_adds_loopbacks(window):
    laptop(window)
    ws = window.ws
    editor = window.edit_rigs()
    t = editor.device_table
    count = ws.undo_stack.count()
    item = t.item(0, 2)                           # a combo box commits text, then the value
    item.setText("shared")
    assert ws.undo_stack.count() == count         # the text alone changes nothing
    t.item(0, 2).setData(Qt.ItemDataRole.UserRole, "shared")
    device = ws.get("rigs", rigs.LAPTOP_RIG)["devices"][0]
    assert device["access"] == "shared" and device["server_device"] == "pulse"
    assert t.item(0, 3).text() == "pulse"                                 # now editable, was blank
    editor.add_device()
    assert [d["id"] for d in ws.get("rigs", rigs.LAPTOP_RIG)["devices"]] == ["laptop", "device2"]
    tt = editor.transducer_table
    tt.item(2, 3).setText("device2")                                      # the microphone's device
    tt.item(2, 3).setData(Qt.ItemDataRole.UserRole, "device2")
    placed = {p["id"]: p["device"] for p in ws.get("rigs", rigs.LAPTOP_RIG)["transducers"]}
    assert placed == {"left": "laptop", "right": "laptop", "mic": "device2"}
    assert ws.get("scenes", ws.get("rigs", rigs.LAPTOP_RIG)["as_built"])["devices"][1]["transducers"] == ["mic"]
    editor.add_loopback()
    assert "same device" in editor.message.text()                         # refused, said so
    tt.item(2, 3).setText("(not placed)")
    tt.item(2, 3).setData(Qt.ItemDataRole.UserRole, None)
    assert {p["id"] for p in ws.get("rigs", rigs.LAPTOP_RIG)["transducers"]} == {"left", "right"}
    assert "not placed" in editor.message.text()                         # the layout's mic is unplaced
    editor.delete_device()                                                # nothing selected: nothing
    t.selectRow(1)
    editor.delete_device()
    assert [d["id"] for d in ws.get("rigs", rigs.LAPTOP_RIG)["devices"]] == ["laptop"]


def test_identify_plays_a_tone_on_the_selected_transducer_off_the_gui_thread(window, world):
    laptop(window)
    editor = window.edit_rigs()
    editor.identify()
    assert "Select an output first" in editor.identify_text.text()
    editor.transducer_table.selectRow(0)
    editor.identify()
    assert not editor.identify_button.isEnabled()                         # busy while it plays
    wait(lambda: editor.worker is None)
    assert "1000 Hz tone" in editor.identify_text.text() and "Left speaker" in editor.identify_text.text()
    assert editor.identify_button.isEnabled()
    assert world.log.count("borrow") == 1 and world.log.count("release") == 1
    editor.transducer_table.selectRow(2)                                  # the microphone cannot play
    editor.identify()
    wait(lambda: editor.worker is None)
    assert "Could not play" in editor.identify_text.text() and "not an output" in editor.identify_text.text()


def test_new_rigs_come_from_a_layout_or_the_laptop_template_and_delete_cleanly(window):
    ws = window.ws
    editor = window.edit_rigs()
    assert "No rig yet" in editor.message.text()
    editor.layout_box.setCurrentIndex(editor.layout_box.findData("stereo_dongle"))
    editor.new_rig()
    assert editor.rig_id == "stereo_dongle_rig"
    assert "not placed on a device" in editor.message.text()
    editor.laptop_template()
    assert editor.rig_id == rigs.LAPTOP_RIG and ws.exists("scenes", rigs.LAPTOP_DEMO)
    editor.delete_rig()
    assert not ws.exists("rigs", rigs.LAPTOP_RIG)
    assert not ws.exists("scenes", "laptop_speaker_and_mic_as_built")
    assert ws.exists("scenes", rigs.LAPTOP_DEMO)                           # the demo is not the rig's


def test_a_workspace_from_step_1_is_migrated_and_the_window_says_so(tmp_path, world):
    path = tmp_path / "old"
    (path / "designs").mkdir(parents=True)
    (path / "workspace.json").write_text(json.dumps(dict(name="old", version=1)))
    (path / "designs" / "a.json").write_text(json.dumps(
        dict(name="a", events=[], receivers=[], listen=0.3, roles=["bench"])))
    ws = Workspace(path)
    settings = QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.Format.IniFormat)
    window = MainWindow(ws, settings, environment=environment(world))
    assert "Moved 1 ping design file(s)" in window.statusBar().currentMessage()
    assert ws.ids("ping_designs") == ["a"]
    window.close()
