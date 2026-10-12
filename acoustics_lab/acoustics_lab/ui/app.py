"""Starting the program: choose the workspace, open the window."""
import argparse
import sys
from pathlib import Path

from ..objects import starter
from ..qtcompat import QtCore, pg
from ..workspace import Workspace
from .mainwindow import MAX_RECENT, MainWindow

DEFAULT_WORKSPACE = Path.home() / "acoustics_lab_workspace"


def parse_args(argv=None):
    p = argparse.ArgumentParser(
        prog="python3 -m acoustics_lab",
        description="Workbench for underwater and in-air acoustics.")
    p.add_argument("--workspace", metavar="FOLDER",
                   help="workspace to open (created if it does not exist); "
                        "default: the last one used, else ~/acoustics_lab_workspace")
    p.add_argument("--import-designs", metavar="FOLDER",
                   help="import carp/acoustic ping designs (*.json) first")
    p.add_argument("--replay", metavar="PATH",
                   help="open a WAV file or a folder of recordings in replay")
    return p.parse_args(argv)


class Application:
    """Owns the one window; opening another workspace replaces it."""

    def __init__(self, args):
        self.app = pg.mkQApp("acoustics_lab")
        self.app.setOrganizationName("acoustics_lab")
        self.settings = QtCore.QSettings("acoustics_lab", "acoustics_lab")
        self.window = None
        path = args.workspace or self.settings.value("last_workspace") or str(DEFAULT_WORKSPACE)
        self.open_workspace(path, args.import_designs, args.replay)

    def open_workspace(self, path, import_designs=None, replay=None):
        workspace = Workspace(path)
        if workspace.is_new:
            starter.populate(workspace)
        self.settings.setValue("last_workspace", str(workspace.path))
        recent = [r for r in self.settings.value("recent", [], type=list)
                  if r != str(workspace.path)]
        self.settings.setValue("recent", ([str(workspace.path)] + recent)[:MAX_RECENT])
        old, self.window = self.window, MainWindow(workspace, self.settings, replay)
        self.window.workspace_requested.connect(self.open_workspace)
        if import_designs:
            self.window.run_import(import_designs)
        self.window.show()
        if old is not None:
            old.close()

    def run(self):
        return self.app.exec()


def main(argv=None):
    sys.exit(Application(parse_args(argv)).run())
