"""The window, driven headlessly (Qt's offscreen platform): pinging, editing
in place with undo, refusals, replay and continuous mode."""
import time

import pytest

from acoustics_lab.qtcompat import Qt, QtCore, pg
from acoustics_lab.objects import starter
from acoustics_lab.ui.mainwindow import MainWindow
from acoustics_lab.workspace import Workspace
from acoustics_lab.pages import ranging as ranging_page
from acoustics_lab.pages.placeholder import PlaceholderPage

app = pg.mkQApp("test")


@pytest.fixture
def window(tmp_path):
    settings = QtCore.QSettings(str(tmp_path / "s.ini"), QtCore.QSettings.Format.IniFormat)
    ws = Workspace(tmp_path / "ws")
    starter.populate(ws)
    w = MainWindow(ws, settings)
    w.show()
    yield w
    w.close()


def wait(condition, seconds=15):
    start = time.time()
    while not condition() and time.time() - start < seconds:
        app.processEvents()
        time.sleep(0.005)
    app.processEvents()
    assert condition(), "timed out"


def ping(window):
    page = window.page("Ranging & positioning")
    before = page.count
    window.ping_action.trigger()
    wait(lambda: page.count > before and not page.busy)
    return page


def cell(table, row, column):
    return table.item(row, column)


def test_the_window_starts_on_the_ranging_page_and_pings(window):
    page = ping(window)
    assert window.current_page() is page
    rows = page.results["mic"].rows
    assert [r["transducer"] for r in rows] == ["left", "right"] and all(r["heard"] for r in rows)
    assert page.result_table.rowCount() == 2
    assert "all events heard" in page.headline.text()
    assert page.echogram.ci.items       # the echogram has plots


def test_other_pages_are_placeholders_with_the_run_controls_greyed_out(window):
    window.page_list.setCurrentRow(window._row_of("Beam patterns"))
    assert isinstance(window.current_page(), PlaceholderPage)
    assert not window.ping_action.isEnabled()
    assert "no experiment" in window.ping_action.toolTip()
    window.page_list.setCurrentRow(window._row_of("Ranging & positioning"))
    assert window.ping_action.isEnabled()


def test_a_cell_edit_is_one_undo_step_and_rewrites_the_file(window):
    page = ping(window)
    ws = window.ws
    table = page.signal_table
    row = next(r for r in range(table.rowCount()) if table.item(r, ranging_page.ID).text() == "chirp_up")
    count = ws.undo_stack.count()
    cell(table, row, ranging_page.F1).setText("18000")
    assert ws.get("signals", "chirp_up")["f1"] == 18000.0
    assert ws.undo_stack.count() == count + 1
    # The derived "16-20 down" shows its source's numbers; its gain updates.
    ws.undo_stack.undo()
    assert ws.get("signals", "chirp_up")["f1"] == 20000.0
    assert cell(table, row, ranging_page.F1).text() == "20000"
    cell(table, row, ranging_page.LENGTH).setText("30")
    assert abs(ws.get("signals", "chirp_up")["duration"] - 0.03) < 1e-12


def test_bad_edits_are_refused_with_a_message_and_the_old_value_returns(window):
    page = ping(window)
    table, ws = page.signal_table, window.ws
    row = next(r for r in range(table.rowCount()) if table.item(r, ranging_page.ID).text() == "chirp_up")
    cell(table, row, ranging_page.LEVEL).setText("7")
    assert ws.get("signals", "chirp_up")["amplitude"] == 0.5
    assert "level" in window.statusBar().currentMessage()
    assert cell(table, row, ranging_page.LEVEL).text() == "0.5"
    cell(table, row, ranging_page.F0).setText("abc")
    assert "must be a number" in window.statusBar().currentMessage()


def test_cycles_and_deleting_used_signals_are_refused_in_the_window(window):
    page = ping(window)
    table, ws = page.signal_table, window.ws
    row = next(r for r in range(table.rowCount())
               if table.item(r, ranging_page.ID).text() == "16_20_down")
    item = cell(table, row, ranging_page.SOURCE)
    item.setData(Qt.ItemDataRole.UserRole, "16_20_down")        # itself: refused
    assert "derived from itself" in window.statusBar().currentMessage()
    assert ws.get("signals", "16_20_down")["source"] == "16_20_up"
    table.selectRow(next(r for r in range(table.rowCount())
                         if table.item(r, ranging_page.ID).text() == "chirp_up"))
    page.delete_signal()
    assert ws.exists("signals", "chirp_up")
    assert "Not deleted" in window.statusBar().currentMessage()
    assert "left_then_right" in window.statusBar().currentMessage()


def test_events_edit_add_and_delete_through_the_table(window):
    page = ping(window)
    ws, t = window.ws, page.event_table
    cell(t, 1, 3).setText("200")
    assert ws.get("ping_designs", "left_then_right")["events"][1]["time"] == 0.2
    page.add_event()
    assert len(ws.get("ping_designs", "left_then_right")["events"]) == 3
    t.selectRow(2)
    page.delete_event()
    assert len(ws.get("ping_designs", "left_then_right")["events"]) == 2
    ws.undo_stack.undo()
    assert len(ws.get("ping_designs", "left_then_right")["events"]) == 3
    page.listen.setText("0.5")
    page.listen.editingFinished.emit()
    assert ws.get("ping_designs", "left_then_right")["listen"] == 0.5


def test_loopback_scene_gives_times_of_flight(window):
    window.session.set_scene("dongle_bench_loopback")
    page = ping(window)
    rows = page.results["mic"].rows
    assert all(r["mode"] == "loopback" for r in rows)
    assert abs(rows[0]["path_m"] - 1.5) < 0.002 and abs(rows[1]["path_m"] - 1.9) < 0.002
    assert abs(rows[0]["error_mm"]) < 2


def test_temperature_in_the_toolbar_is_an_undoable_scene_edit(window):
    window.temp.setValue(0.0)
    assert window.ws.get("scenes", "dongle_bench")["medium"]["temperature_c"] == 0.0
    assert window.speed_label.text().strip().startswith("331.3")
    window.ws.undo_stack.undo()
    assert window.ws.get("scenes", "dongle_bench")["medium"]["temperature_c"] == 20.0
    assert window.temp.value() == 20.0


def test_saved_recordings_replay_in_the_window(window):
    page = window.page("Ranging & positioning")
    page.save_check.setChecked(True)
    window.session.set_scene("dongle_bench_loopback")
    for _ in range(2):
        ping(window)
    runs = window.ws.path / "runs"
    assert len(list(runs.rglob("*.wav"))) == 2
    window.open_replay(str(runs))
    assert window.session.mode == "replay" and window.ping_action.text() == "Next"
    ping(window)
    assert "Recording 1 of 2" in page.headline.text()
    assert page.results["mic"].loopback == ["left", "right"]
    ping(window)
    ping(window)
    assert "Recording 1 of 2" in page.headline.text()
    window.open_replay(str(runs / "nothing"))       # a bad path is reported, not fatal
    assert "Cannot open" in window.statusBar().currentMessage()


def test_continuous_pings_until_stopped(window):
    page = window.page("Ranging & positioning")
    window.interval.setValue(0.0)
    window.continuous_action.setChecked(True)
    wait(lambda: page.count >= 3)
    window.continuous_action.setChecked(False)
    wait(lambda: not page.busy)
    stopped_at = page.count
    time.sleep(0.2)
    app.processEvents()
    assert page.count == stopped_at


def test_a_design_that_cannot_play_is_explained_not_crashed(window):
    page = window.page("Ranging & positioning")
    window.ws.update("ping_designs", "left_then_right",
                     events=[dict(transducer="mic", signal="chirp_up", time=0.0)])
    assert "cannot send" in page.design_warnings.text()
    window.ping_action.trigger()
    app.processEvents()
    assert "Check the ping design" in window.statusBar().currentMessage()


def test_outside_changes_reload_with_a_message(window):
    ws = window.ws
    ws.update("signals", "chirp_up", f1=15000.0)
    path = ws.path / "signals" / "chirp_up.json"
    import json
    data = json.loads(path.read_text())
    data["f1"] = 9000.0
    path.write_text(json.dumps(data))
    wait(lambda: ws.get("signals", "chirp_up")["f1"] == 9000.0)
    assert "outside" in window.statusBar().currentMessage()
    table = window.page("Ranging & positioning").signal_table
    row = next(r for r in range(table.rowCount()) if table.item(r, ranging_page.ID).text() == "chirp_up")
    assert table.item(row, ranging_page.F1).text() == "9000"
