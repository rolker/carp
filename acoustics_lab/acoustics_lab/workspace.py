"""The workspace: a folder of JSON objects, with undo and file watching.

    my_workspace/
      workspace.json
      signals/<id>.json  ping_designs/<id>.json  detection_designs/<id>.json
      layouts/<id>.json  scenes/<id>.json        rigs/<id>.json
      runs/               captures, git-ignored by default

Workspaces from before ping designs and detection designs were told apart
kept their ping designs in `designs/`; opening one moves them to
`ping_designs/` (see `notices`).

Every edit is written to its file at once, atomically (temporary file, then
rename), so a crash never leaves half a file. All edits go through one
QUndoStack, and undo rewrites the files too. IDs are short and readable,
made from the first name an object has and never changed; the display name
is inside the file. References between objects use IDs.

Files are laid out for version control: one object per file, indented JSON
with sorted keys, nothing that changes on every write.
"""
import contextlib
import copy
import json
import os
from pathlib import Path

from .objects import schema
from .objects.schema import KINDS, InUseError, WorkspaceError
from .qtcompat import QtCore, QUndoCommand, QUndoStack, Signal

FORMAT_VERSION = 1
GITIGNORE = "runs/\n"


def write_json(path, data):
    """Write `data` as JSON to `path` atomically: a temporary file in the
    same folder, then a rename over the target."""
    path = Path(path)
    temporary = path.with_name("." + path.name + ".tmp")
    with open(temporary, "w") as f:
        json.dump(data, f, indent=1, sort_keys=True)
        f.write("\n")
        f.flush()
        os.fsync(f.fileno())
    os.replace(temporary, path)


class _Edit(QUndoCommand):
    """One change to one object: before and after are its data, or None
    where it did not exist (a creation) or no longer does (a deletion)."""

    def __init__(self, workspace, kind, object_id, before, after, text):
        super().__init__(text)
        self.workspace, self.kind, self.id = workspace, kind, object_id
        self.before, self.after = before, after

    def redo(self):
        self.workspace._apply(self.kind, self.id, copy.deepcopy(self.after))

    def undo(self):
        self.workspace._apply(self.kind, self.id, copy.deepcopy(self.before))


class Workspace(QtCore.QObject):
    """Signals: `changed(kind, id)` after any object is created, edited or
    deleted (by an edit, undo or redo); `reloaded(message)` after files
    changed outside the program were read in, when the undo history is also
    cleared."""

    changed = Signal(str, str)
    reloaded = Signal(str)

    def __init__(self, path, parent=None):
        super().__init__(parent)
        self.path = Path(path).expanduser().resolve()
        self.is_new = not (self.path / "workspace.json").exists()
        self.path.mkdir(parents=True, exist_ok=True)
        self.notices = self._migrate() if not self.is_new else []
        self.new_kinds = []         # kinds whose folder was not there before this opening
        for kind in KINDS:
            if not (self.path / kind).exists():
                self.new_kinds.append(kind)
            (self.path / kind).mkdir(exist_ok=True)
        if self.is_new:
            write_json(self.path / "workspace.json",
                       dict(name=self.path.name, version=FORMAT_VERSION))
        if not (self.path / ".gitignore").exists():
            (self.path / ".gitignore").write_text(GITIGNORE)
        self.undo_stack = QUndoStack(self)
        self.problems = []
        self._objects, self.problems = self._read_all()
        self._watcher = None
        self._timer = None

    def _migrate(self):
        """Move ping designs from the folder step 1 called designs/ to
        ping_designs/. Files whose names are already taken in the new folder
        stay where they are, and the notice says so. Returns messages."""
        old, new = self.path / "designs", self.path / "ping_designs"
        if not old.is_dir():
            return []
        new.mkdir(exist_ok=True)
        moved, stayed = [], []
        for file in sorted(old.glob("*.json")):
            if (new / file.name).exists():
                stayed.append(file.name)
            else:
                os.replace(file, new / file.name)
                moved.append(file.name)
        with contextlib.suppress(OSError):      # only if empty
            old.rmdir()
        notices = []
        if moved:
            notices.append(f"Moved {len(moved)} ping design file(s) from designs/ "
                           "to ping_designs/")
        if stayed:
            notices.append("Left in designs/ because ping_designs/ already has a "
                           "file of the same name: " + ", ".join(stayed))
        return notices

    # ---- reading -------------------------------------------------------

    @property
    def name(self):
        try:
            with open(self.path / "workspace.json") as f:
                return json.load(f).get("name", self.path.name)
        except (OSError, ValueError):
            return self.path.name

    def _read_all(self):
        objects, problems = {k: {} for k in KINDS}, []
        for kind in KINDS:
            for file in sorted((self.path / kind).glob("*.json")):
                try:
                    with open(file) as f:
                        objects[kind][file.stem] = json.load(f)
                except (OSError, ValueError) as error:
                    problems.append(f"{kind}/{file.name}: {error}")
        return objects, problems

    def ids(self, kind):
        """IDs of a kind, sorted by display name."""
        items = self._objects[kind]
        return sorted(items, key=lambda i: (items[i].get("name", i).casefold(), i))

    def exists(self, kind, object_id):
        return object_id in self._objects[kind]

    def get(self, kind, object_id):
        """A copy of an object's data, or None."""
        data = self._objects[kind].get(object_id)
        return copy.deepcopy(data) if data is not None else None

    def get_signal(self, object_id):
        """A signal's data, or None; the callable the signal code wants."""
        return self.get("signals", object_id)

    def name_of(self, kind, object_id):
        data = self._objects[kind].get(object_id)
        return data["name"] if data else object_id

    def uses(self, kind, object_id):
        """Objects that refer to this one, as a sorted list of (kind, id)."""
        return sorted((k, i) for k in KINDS for i, data in self._objects[k].items()
                      if (kind, object_id) in schema.references(k, data))

    # ---- changing (all through the undo stack) -------------------------

    def new_id(self, kind, name):
        """The ID a new object of this name would get."""
        return schema.unique_id(name, self._objects[kind], schema.SINGULAR[kind])

    def _check(self, kind, object_id, data):
        schema.check(kind, data, self.exists, self.get_signal)
        if kind == "signals" and schema.derived_chain_has_cycle(
                lambda i: self._objects["signals"].get(i), object_id, data):
            raise WorkspaceError(
                f"'{data['name']}' would end up derived from itself")

    def create(self, kind, name, data=None, text=None):
        """Add an object. `data` is its contents (a copy is kept); its name is
        set to `name`. Returns the new ID."""
        data = copy.deepcopy(data) if data is not None else {}
        data["name"] = name
        object_id = self.new_id(kind, name)
        self._check(kind, object_id, data)
        self.undo_stack.push(_Edit(self, kind, object_id, None, data,
                                   text or f"add {schema.SINGULAR[kind]} {name}"))
        return object_id

    def update(self, kind, object_id, text=None, **changes):
        """Change top-level fields of an object. One call is one undo step.
        Does nothing if nothing would change."""
        before = self._objects[kind].get(object_id)
        if before is None:
            raise WorkspaceError(f"no {schema.SINGULAR[kind]} with ID '{object_id}'")
        after = copy.deepcopy(before)
        after.update(copy.deepcopy(changes))
        self.replace(kind, object_id, after, text)

    def replace(self, kind, object_id, data, text=None):
        """Replace an object's whole contents (one undo step)."""
        before = self._objects[kind].get(object_id)
        if before is None:
            raise WorkspaceError(f"no {schema.SINGULAR[kind]} with ID '{object_id}'")
        data = copy.deepcopy(data)
        if data == before:
            return
        self._check(kind, object_id, data)
        self.undo_stack.push(_Edit(
            self, kind, object_id, copy.deepcopy(before), data,
            text or f"edit {schema.SINGULAR[kind]} {before['name']}"))

    def delete(self, kind, object_id):
        """Delete an object, unless others use it (InUseError lists them)."""
        before = self._objects[kind].get(object_id)
        if before is None:
            return
        users = self.uses(kind, object_id)
        if users:
            raise InUseError(f"{schema.SINGULAR[kind]} '{before['name']}'", users)
        self.undo_stack.push(_Edit(
            self, kind, object_id, copy.deepcopy(before), None,
            f"delete {schema.SINGULAR[kind]} {before['name']}"))

    @contextlib.contextmanager
    def macro(self, text):
        """Group the edits made inside the block into one undo step."""
        self.undo_stack.beginMacro(text)
        try:
            yield
        finally:
            self.undo_stack.endMacro()

    def _apply(self, kind, object_id, data):
        """Put an object's data (None: remove it) in memory and in its file."""
        file = self.path / kind / f"{object_id}.json"
        if data is None:
            self._objects[kind].pop(object_id, None)
            with contextlib.suppress(FileNotFoundError):
                file.unlink()
        else:
            self._objects[kind][object_id] = data
            write_json(file, data)
        self.changed.emit(kind, object_id)

    # ---- changes from outside ------------------------------------------

    def rescan(self):
        """Read the files again. If they differ from what is held (a git
        checkout, another editor), take them, clear the undo history and
        emit `reloaded`. Returns whether anything changed."""
        fresh, problems = self._read_all()
        if fresh == self._objects:
            self.problems = problems
            self._watch_files()     # a rename replaced the files we watched
            return False
        self._objects, self.problems = fresh, problems
        self.undo_stack.clear()
        message = "Files changed outside the program: reloaded, undo history cleared"
        if problems:
            message += " (unreadable: " + "; ".join(problems) + ")"
        self.reloaded.emit(message)
        self._watch_files()
        return True

    def start_watching(self, delay_ms=300):
        """Watch the folders for outside changes; needs a running event
        loop. Our own writes also trigger it, but they match what is held,
        so rescan finds nothing to do."""
        if self._watcher is not None:
            return
        self._watcher = QtCore.QFileSystemWatcher(self)
        self._timer = QtCore.QTimer(self)
        self._timer.setSingleShot(True)
        self._timer.setInterval(delay_ms)
        self._timer.timeout.connect(self.rescan)
        self._watcher.directoryChanged.connect(self._poke)
        self._watcher.fileChanged.connect(self._poke)
        self._watch_files()

    def _poke(self, _path=""):
        """A watched folder or file changed: look again shortly (unless
        watching has stopped meanwhile)."""
        if self._timer is not None:
            self._timer.start()

    def _watch_files(self):
        if self._watcher is None:
            return
        old = self._watcher.files() + self._watcher.directories()
        if old:
            self._watcher.removePaths(old)
        paths = [str(self.path)] + [str(self.path / k) for k in KINDS]
        paths += [str(f) for k in KINDS for f in (self.path / k).glob("*.json")]
        self._watcher.addPaths(paths)

    def stop_watching(self):
        if self._watcher is not None:
            self._watcher.deleteLater()
            self._timer.stop()
            self._watcher = self._timer = None
