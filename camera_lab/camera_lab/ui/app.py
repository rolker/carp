"""Starting the program: choose the workspace, open the window."""
import argparse
import sys
from pathlib import Path

from ..objects import starter
from ..qtcompat import QtCore, pg
from ..workspace import Workspace
from .mainwindow import MainWindow

DEFAULT_WORKSPACE = Path.home() / "camera_lab_workspace"


def parse_args(argv=None):
    p = argparse.ArgumentParser(prog="python3 camera_lab/run.py",
                                description="Workbench for choosing cameras for an underwater vehicle.")
    p.add_argument("--workspace", metavar="FOLDER",
                   help="workspace to open (created with CARP's cameras if it does not exist); "
                        "default: the last one used, else ~/camera_lab_workspace")
    p.add_argument("--page", metavar="TITLE", help="open on this page")
    p.add_argument("--screenshot", metavar="FILE", help="save the window to a PNG and exit "
                                                         "(for documentation and tests)")
    return p.parse_args(argv)


def open_workspace(path):
    ws = Workspace(path)
    if ws.is_new:
        starter.populate(ws)
        ws.undo_stack.clear()
    return ws


def main(argv=None):
    args = parse_args(argv)
    app = pg.mkQApp("camera_lab")
    app.setOrganizationName("camera_lab")
    settings = QtCore.QSettings("camera_lab", "camera_lab")
    path = args.workspace or settings.value("last_workspace") or str(DEFAULT_WORKSPACE)
    ws = open_workspace(path)
    settings.setValue("last_workspace", str(ws.path))
    window = MainWindow(ws, settings)
    if args.page:
        window.show_page(args.page)
    window.show()
    if args.screenshot:
        def grab():
            window.grab().save(args.screenshot)
            app.quit()
        QtCore.QTimer.singleShot(2500, grab)
    sys.exit(app.exec())
