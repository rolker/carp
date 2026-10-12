"""The room sonar page with two speakers, driven headlessly (Qt's offscreen
platform), on simulation and a faked machine. No device is opened, no card
borrowed, no mixer written, no sound made."""
import time

import numpy as np
import pytest

from acoustics_lab.experiments import room
from acoustics_lab.objects import rigs, starter
from acoustics_lab.qtcompat import QtCore, pg
from acoustics_lab.ui.mainwindow import MainWindow
from acoustics_lab.ui.session import Session
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


def page_of(window):
    window.page_list.setCurrentRow(window._row_of("Room sonar"))
    page = window.page("Room sonar")
    page.make_laptop()
    return page


def ping(window, page, times=1):
    for _ in range(times):
        before = page.count
        window.ping_action.trigger()
        wait(lambda: page.count > before and not page.busy)


def scatter_points(plot):
    return [item for item in plot.items() if isinstance(item, pg.ScatterPlotItem)]


def test_two_speaker_pings_draw_the_targets_the_return_of_each_sound_and_an_echogram_each(window):
    page = page_of(window)
    window.interval.setValue(0.2)
    ping(window, page, 12)
    assert page.design_box.currentData() == rigs.SPLIT_BANDS
    assert len(page.last.channels) == 2 and len(page._image_plots) == 2
    assert page.last.fixes and "target(s) placed" in page.headline.text()
    assert "Left speaker" in page.headline.text() and "Right speaker" in page.headline.text()
    spots = sum(len(s.points()) for s in scatter_points(page.plan))
    assert spots > 2 + 1 + 4                                  # speakers, microphone, the targets
    assert any("not measured" in i.toPlainText() for i in page.plan.items()
               if isinstance(i, pg.TextItem))                   # the plan says the positions are a guess
    assert "Leak" in page.numbers.text() and "-102 dB" in page.numbers.text()
    assert "Microphone across" in page.numbers.text()
    assert "Speaker spacing" in page.numbers.text() and "not measured" in page.numbers.text()
    assert "Placing a target" in page.notes.toPlainText()
    # the same targets by bearing and range
    page.view_box.setCurrentIndex(1)
    assert page.stack.currentIndex() == 1 and scatter_points(page.bearing)
    # only what moved, after the background is known
    page.source_box.setCurrentIndex(page.source_box.findData("changed"))
    assert "changes" in page.place_text.text()
    assert page.changed and len(page.changed) == len(page.results)


def test_a_design_with_one_sound_has_one_return_and_says_it_cannot_place(window):
    page = page_of(window)
    page.design_box.setCurrentIndex(page.design_box.findData(rigs.SAME_CHIRP))
    page.steer_spin.setValue(15.0)
    ping(window, page, 3)
    assert len(page.last.channels) == 1 and page._image_plots and len(page._image_plots) == 1
    assert "same signal" in page.place_text.text() and not page.last.fixes
    assert "Same signal on left and right" in page.numbers.text()
    assert "steered to +15 deg" in page.numbers.text()
    assert page._zone(page.last)[2] == 15.0 and page._zone(page.last)[0] < 15.0 < page._zone(page.last)[1]
    page.design_box.setCurrentIndex(page.design_box.findData(rigs.UP_AND_DOWN))
    ping(window, page)
    assert len(page._image_plots) == 2 and page.results and len(page.results) == 1  # history restarted
    assert "17 dB" in page.headline.text() and "Leak" in page.numbers.text()


def test_the_positions_are_edited_on_the_page_and_stop_being_a_guess(window):
    page = page_of(window)
    ws = window.ws
    assert not rigs.is_measured(ws.get("layouts", "laptop")) and not page.measured_check.isChecked()
    assert "Not measured" in page.geometry_note.text()
    ping(window, page, 2)
    spin = page._geometry_spins["right"][0]                      # the right speaker's x, in cm
    assert spin.value() == pytest.approx(17.0)
    spin.setValue(20.0)
    layout = ws.get("layouts", "laptop")
    assert layout["transducers"][1]["position"][0] == pytest.approx(0.20)
    assert layout["measured"] is True and layout["note"] == ""
    assert page.measured_check.isChecked() and page.geometry_note.text() == ""
    assert page.levels == [] and page.count == 0                 # the history does not fit any more
    ping(window, page)
    assert page.last.geometry.spacing("left", "right") == pytest.approx(0.37)
    assert not page.last.geometry.assumed
    ws.undo_stack.undo()                                         # one undo step
    assert ws.get("layouts", "laptop")["transducers"][1]["position"][0] == pytest.approx(0.17)
    assert not rigs.is_measured(ws.get("layouts", "laptop"))
    page.measured_check.setChecked(True)
    assert rigs.is_measured(ws.get("layouts", "laptop"))


def test_the_page_offers_the_two_speaker_designs_and_two_laptop_templates(window):
    page = window.page("Room sonar")
    window.page_list.setCurrentRow(window._row_of("Room sonar"))
    labels = [page.needs_buttons.itemAt(i).widget().text() for i in range(page.needs_buttons.count())]
    assert any("17-inch Alienware" in t and "not measured" in t for t in labels)
    assert any("15-inch Alienware" in t for t in labels)
    page.make_laptop("15")
    layout = window.ws.get("layouts", "15_inch_alienware")
    pos = {t["id"]: t["position"] for t in layout["transducers"]}
    assert pos["right"][0] - pos["left"][0] == pytest.approx(0.30) and layout["measured"] is False
    assert window.session.rig_id == "15_inch_alienware_speakers_and_mic"
    assert window.session.scene_id == "15_inch_alienware_in_a_room"
    ping(window, page, 2)
    assert page.last.heard and page.last.geometry.spacing("left", "right") == pytest.approx(0.30)
    assert window.ws.get("rigs", window.session.rig_id)["machine"] == rigs.machine_name()
    # the designs are offered again when one is missing
    window.ws.delete("ping_designs", rigs.UP_AND_DOWN)
    page.add_two_speaker_designs()
    assert window.ws.exists("ping_designs", rigs.UP_AND_DOWN)


def test_on_wsl_a_staggered_design_is_warned_about_and_a_simultaneous_one_is_not(window, monkeypatch):
    monkeypatch.setattr(rigs, "on_wsl", lambda: True)
    page = page_of(window)
    window.backend_box.setCurrentIndex(window.backend_box.findData("hardware"))
    page.design_box.setCurrentIndex(page.design_box.findData("left_then_right"))
    assert "staggers its events" in page.numbers.text() and "WSL" in page.numbers.text()
    ping(window, page)
    assert "staggers its events in time" in page.headline.text()
    assert "split bands" in page.headline.text()
    page.design_box.setCurrentIndex(page.design_box.findData(rigs.SPLIT_BANDS))
    assert "sends at one instant" in page.numbers.text()
    ping(window, page)
    assert "staggers" not in page.headline.text()
    # elsewhere there is nothing to say
    monkeypatch.setattr(rigs, "on_wsl", lambda: False)
    page.design_box.setCurrentIndex(page.design_box.findData("left_then_right"))
    ping(window, page)
    assert "staggers" not in page.headline.text() and "WSL" not in page.numbers.text()


# ---- without Qt widgets: templates, machines, WSL ------------------------------------

def test_the_15_inch_template_is_a_second_laptop_next_to_the_first(tmp_path, monkeypatch):
    monkeypatch.setattr(rigs, "on_wsl", lambda: False)
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    a, b = rigs.laptop_template(w, "17"), rigs.laptop_template(w, "15")
    assert a["layout"] == "laptop" and b["layout"] == "15_inch_alienware" and a["rig"] != b["rig"]
    for ids, spacing in ((a, 0.34), (b, 0.30)):
        layout = w.get("layouts", ids["layout"])
        left, right, mic = (t["position"] for t in layout["transducers"])
        assert right[0] - left[0] == pytest.approx(spacing) and mic[0] == 0.0 and mic[2] > 0.2
        assert layout["measured"] is False and f"{100 * spacing:.0f} cm apart" in layout["note"]
        assert w.get("rigs", ids["rig"])["layout"] == ids["layout"]
        assert w.exists("scenes", ids["demo"])
    assert rigs.laptop_template(w, "15") == b                         # safe to repeat
    assert w.get("rigs", b["rig"])["devices"][0]["access"] == "exclusive"


def test_under_wsl_the_laptop_rig_is_shared_with_no_mixer(tmp_path, monkeypatch):
    monkeypatch.setattr(rigs, "on_wsl", lambda: True)
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    ids = rigs.laptop_template(w)
    device = w.get("rigs", ids["rig"])["devices"][0]
    assert device["access"] == "shared" and device["mixer"] == {}


def test_a_workspace_opens_on_this_machines_rig_and_says_which_it_is(tmp_path, monkeypatch):
    monkeypatch.setattr(rigs, "machine_name", lambda: "alien15")
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    rigs.laptop_template(w, "17")                                   # made on this machine
    other = w.get("rigs", rigs.LAPTOP_RIG)
    w.update("rigs", rigs.LAPTOP_RIG, machine="alien17")             # ... but say it is another's
    mine = rigs.laptop_template(w, "15")["rig"]
    assert w.get("rigs", mine)["machine"] == "alien15"
    session = Session(w)
    assert session.rig_id == mine                                    # not the first in the list
    assert "was made on this machine (alien15)" in session.machine_note()
    session.set_rig(rigs.LAPTOP_RIG)
    assert "was made on alien17, not on this machine (alien15)" in session.machine_note()
    assert "devices it names may not be here" in session.machine_note()
    w.update("rigs", rigs.LAPTOP_RIG, machine="")
    assert session.machine_note() == ""                              # old rigs say nothing


def test_the_ping_carries_the_wsl_warning_when_events_are_staggered(tmp_path, monkeypatch):
    w = Workspace(tmp_path / "w")
    starter.populate(w)
    rigs.laptop_template(w)
    backend = __import__("acoustics_lab.backends.simulation", fromlist=["x"]).SimulationBackend.from_workspace(
        w, rigs.LAPTOP_DEMO)
    layout = w.get("layouts", "laptop")
    infos = backend.transducers()
    quiet = room.build_ping(w, "left_then_right", "mic", infos, 5.0, 343.2, layout)
    assert quiet.meta["warnings"] == []
    staggered = room.build_ping(w, "left_then_right", "mic", infos, 5.0, 343.2, layout, wsl=True)
    assert "up and down chirps" in staggered.meta["warnings"][0]
    assert "5-25 ms" in staggered.meta["warnings"][0]
    assert room.build_ping(w, rigs.SPLIT_BANDS, "mic", infos, 5.0, 343.2, layout, wsl=True).meta["warnings"] == []
    steered = room.build_ping(w, rigs.SAME_CHIRP, "mic", infos, 5.0, 343.2, layout, 20.0, wsl=True)
    assert "steering" in steered.meta["warnings"][0]
    assert room.build_ping(w, rigs.SAME_CHIRP, "mic", infos, 5.0, 343.2, layout, 0.0,
                           wsl=True).meta["warnings"] == []
    # and the reading says so with the result
    capture = backend.fire(staggered)
    assert any("staggers" in x for x in room.read(capture, "mic").warnings)
