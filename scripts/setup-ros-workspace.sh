#!/usr/bin/env bash
# Set up ~/ros2_ws for the camera pipeline and install its dependencies with
# rosdep. Run as yourself, not root: rosdep asks for sudo where it needs it.
#
# The workspace holds camera_ros (source, pinned) and a symlink to this
# repo's ros/carp_camera, whose package.xml lists the runtime pieces
# (image_transport, ffmpeg_image_transport, rosbag2 MCAP storage).
#
# Skipped rosdep keys:
#   libcamera  - camera_ros must use our patched build (build-libcamera.sh),
#                not ROS's upstream package
#   image_view - GUI viewer; not wanted on the headless Pi
#
# Usage: ./scripts/setup-ros-workspace.sh    (then build-ros-workspace.sh)
set -euo pipefail

WS=${WS:-$HOME/ros2_ws}
here=$(dirname "$(readlink -f "$0")")
repo=$(readlink -f "$here/..")

CAMERA_ROS_REPO=https://github.com/christianrauch/camera_ros.git
CAMERA_ROS_COMMIT=8f792e27a6dbc81e4943a75765fc1b7b7d37b301

if [[ $EUID -eq 0 ]]; then
    echo "Run as your user, not with sudo" >&2
    exit 1
fi

set +u  # ROS setup scripts reference unset variables
# shellcheck source=/dev/null
source /opt/ros/jazzy/setup.bash
set -u

if [[ ! -e /etc/ros/rosdep/sources.list.d/20-default.list ]]; then
    sudo rosdep init
fi
rosdep update

mkdir -p "$WS/src"
cr=$WS/src/camera_ros
if [[ ! -d $cr/.git ]]; then
    git clone -q "$CAMERA_ROS_REPO" "$cr"
fi
if [[ $(git -C "$cr" rev-parse HEAD) != "$CAMERA_ROS_COMMIT" ]]; then
    git -C "$cr" fetch -q origin
    git -C "$cr" checkout -q --detach "$CAMERA_ROS_COMMIT"
fi
ln -sfn "$repo/ros/carp_camera" "$WS/src/carp_camera"

rosdep install --from-paths "$WS/src" --ignore-src -y \
    -t buildtool -t build -t build_export -t exec \
    --skip-keys "libcamera image_view"

echo
echo "Dependencies installed. Build with: ./scripts/build-ros-workspace.sh"
