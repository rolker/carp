"""The workspace (files, IDs, undo, references) and the window driven
headlessly on Qt's offscreen platform."""
import json

import pytest

from camera_lab.qtcompat import QtCore, pg
from camera_lab.objects import schema, starter
from camera_lab.workspace import Workspace

app = pg.mkQApp("test")


@pytest.fixture
def ws(tmp_path):
    w = Workspace(tmp_path / "ws")
    starter.populate(w)
    w.undo_stack.clear()
    return w


def test_starter_objects_are_valid_and_written_one_file_each(ws):
    assert ws.ids("rigs")[:2] == ["carp_74", "carp_95"]
    for kind in schema.KINDS:
        for oid in ws.ids(kind):
            schema.check(kind, ws.get(kind, oid), ws.exists)
            assert (ws.path / kind / f"{oid}.json").exists()
    assert ws.get("rigs", "carp_95")["baseline_mm"] == 95.0
    assert ws.get("rigs", "carp_74")["baseline_mm"] == 74.0


def test_edit_undo_redo_rewrites_the_file(ws):
    path = ws.path / "rigs" / "carp_95.json"
    ws.update("rigs", "carp_95", baseline_mm=88.0)
    assert json.loads(path.read_text())["baseline_mm"] == 88.0
    ws.undo_stack.undo()
    assert json.loads(path.read_text())["baseline_mm"] == 95.0
    ws.undo_stack.redo()
    assert ws.get("rigs", "carp_95")["baseline_mm"] == 88.0


def test_invalid_edits_are_refused_and_change_nothing(ws):
    with pytest.raises(schema.WorkspaceError):
        ws.update("rigs", "carp_95", baseline_mm=-5)
    with pytest.raises(schema.WorkspaceError):
        ws.update("rigs", "carp_95", lens="nope")
    assert ws.get("rigs", "carp_95")["baseline_mm"] == 95.0
    assert ws.undo_stack.count() == 0


def test_objects_in_use_cannot_be_deleted_and_copies_get_new_ids(ws):
    with pytest.raises(schema.InUseError):
        ws.delete("ports", "dome_2in")
    new = ws.duplicate("rigs", "carp_95", "CARP 85 mm")
    assert new == "carp_85_mm" and ws.get("rigs", new)["baseline_mm"] == 95.0
    ws.delete("rigs", new)
    assert not ws.exists("rigs", new)
    ws.undo_stack.undo()
    assert ws.exists("rigs", new)


def test_outside_changes_are_picked_up_and_clear_undo(ws):
    ws.update("rigs", "carp_95", fps=12.0)
    path = ws.path / "rigs" / "carp_95.json"
    data = json.loads(path.read_text())
    data["fps"] = 5.0
    path.write_text(json.dumps(data))
    messages = []
    ws.reloaded.connect(messages.append)
    assert ws.rescan()
    assert ws.get("rigs", "carp_95")["fps"] == 5.0 and ws.undo_stack.count() == 0 and messages


def test_reopening_a_workspace_reads_the_same_objects(ws, tmp_path):
    again = Workspace(ws.path)
    assert not again.is_new and again.ids("rigs") == ws.ids("rigs")


# ---- the window ----------------------------------------------------------

@pytest.fixture
def window(ws, tmp_path):
    from camera_lab.ui.mainwindow import MainWindow
    w = MainWindow(ws)
    w.show()
    yield w
    w.close()


def settle():
    for _ in range(5):
        app.processEvents()


def test_every_page_draws_with_the_starter_rigs(window):
    for page in window.pages:
        window.show_page(page.title)
        settle()
    assert window.current_page().title == window.pages[-1].title


def test_fov_page_numbers_for_carps_rig(window):
    window.show_page("Field of view & coverage")
    settle()
    page = window.current_page()
    header = [page.table.horizontalHeaderItem(c).text() for c in range(page.table.columnCount())]
    col = next(i for i, h in enumerate(header) if h.startswith("CARP 95"))
    labels = [page.table.verticalHeaderItem(r).text() for r in range(page.table.rowCount())]
    value = lambda name: page.table.item(labels.index(name), col).text()
    assert float(value("Horizontal FOV, in the medium (deg)")) == pytest.approx(141.4, abs=0.1)
    assert value("Footprint width at 2 m").endswith("m")


def test_switching_medium_to_air_and_flat_port_changes_the_fov(window):
    window.session.set(primary_id="flat_port", shown={"flat_port"})
    window.show_page("Field of view & coverage")
    settle()
    page = window.current_page()
    labels = [page.table.verticalHeaderItem(r).text() for r in range(page.table.rowCount())]
    water = float(page.table.item(labels.index("Horizontal FOV, in the medium (deg)"), 0).text())
    assert 85 < water < 95                      # a flat port narrows 141 deg to about 90
    window.session.set(medium_override="air")
    settle()
    air = float(page.table.item(labels.index("Horizontal FOV, in the medium (deg)"), 0).text())
    assert air == pytest.approx(141.4, abs=0.1)


def test_editing_a_field_on_a_page_is_one_undo_step(window):
    window.show_page("Stereo performance")
    settle()
    page = window.current_page()
    box = page.rig_panel.widgets["baseline_mm"]
    count = window.ws.undo_stack.count()
    box.setValue(80.0)
    assert window.ws.get("rigs", "carp_95")["baseline_mm"] == 80.0
    assert window.ws.undo_stack.count() == count + 1
    window.ws.undo_stack.undo()
    settle()
    assert box.value() == 95.0


def test_stereo_page_has_both_baselines_in_its_table(window):
    window.show_page("Stereo performance")
    settle()
    page = window.current_page()
    header = [page.table.horizontalHeaderItem(c).text() for c in range(page.table.columnCount())]
    assert any(h.startswith("CARP 74") for h in header) and any(h.startswith("CARP 95") for h in header)
    assert "Baseline decision" in page.notes.toPlainText()
