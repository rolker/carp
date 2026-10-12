"""Finding the detection design to use, and what to record of it."""
from ..models import detection_design
from ..models.detection_design import DetectionDesign


def get(workspace, design_id):
    """The DetectionDesign stored under this ID. A missing or unreadable one
    gives the built-in default (so a workspace from before detection designs
    still analyses), and `design_id` then reads "" in `resolve`."""
    data = workspace.get("detection_designs", design_id or "")
    if data is None:
        return detection_design.DEFAULT
    try:
        return detection_design.from_dict(data)
    except ValueError:
        return detection_design.DEFAULT


def of_ping_design(workspace, ping_design_id):
    """The detection design ID a ping design names as its default, or None."""
    ping = workspace.get("ping_designs", ping_design_id or "") or {}
    return ping.get("detection_design") or None


def resolve(workspace, *candidates):
    """(ID, DetectionDesign) to use: the first candidate ID that exists
    (the page's choice, then the ping design's own default, and so on), else
    the first stored design, else the built-in default (ID ""). Candidates
    that are None or no longer exist are skipped."""
    for design_id in candidates:
        if design_id and workspace.exists("detection_designs", design_id):
            return design_id, get(workspace, design_id)
    ids = workspace.ids("detection_designs")
    if ids:
        return ids[0], get(workspace, ids[0])
    return "", detection_design.DEFAULT


def record(design_id, design: DetectionDesign):
    """What is kept with a capture or a result: the ID and a full copy of
    the settings, so the result can always be traced to what produced it."""
    return dict(design.to_dict(), id=design_id)
