# Roadmap

## Direction

What must be true for CARP's current goal. Each line has the check that
says whether it is true today. The sit-rep (`/agent-workspace:sitrep`) runs
every check each time it is asked. This section holds no status and no
dates: progress is recorded in `docs/bringup-checklist.md`, which most
checks read.

**Acceptance case.** In the owner's words (2026-11-14): "have the power
system working on batteries and enough of a frame built to carry the
battery, pi, cameras, and pixhawk so I can test capturing video while
moving the frame around to simulate swimming, but not in water obviously!"

Along the way, the bench power supply can stand in for the batteries. In
the owner's words (2026-11-14): "we can also use the bench power supply as
needed instead of batteries."

The checks were proposed by the agent at onboarding (#3), and the owner can
change them. The two lines with no check have nothing to read yet: the
frame depends on the open frame question in `docs/open-questions.md`, and
how to record the moving-capture test is not decided.

| Line | Check |
|------|-------|
| The power module holds 5 V under load | `file-contains docs/bringup-checklist.md [x] Power module holds 5 V` |
| Battery voltage reads true in ArduSub | `file-contains docs/bringup-checklist.md [x] Calibrate` |
| The Pi 5 boots with the NVMe mounted | `file-contains docs/bringup-checklist.md [x] Pi 5 boots` |
| The cameras stream, encode and record to NVMe | `file-contains docs/bringup-checklist.md [x] Cameras stream, encode, and record to NVMe` |
| Recorded video plays back and can be scrubbed | `file-contains docs/bringup-checklist.md [x] rosbag records` |
| A frame carries the battery, Pi, cameras and Pixhawk | |
| A dry moving-frame capture test has been run | |
