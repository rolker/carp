#!/usr/bin/env bash
# Set up ~/ros2_ws for the camera pipeline and install its dependencies with
# rosdep. Run as yourself, not root: rosdep asks for sudo where it needs it.
#
# The workspace holds, pinned and with this repo's patches/<name> applied:
#   camera_ros             - shutdown-hang fix
#   ffmpeg_encoder_decoder - NV12/NV21 pass-through (no BGR round trip).
#                            Overlays the apt copy that the apt
#                            ffmpeg_image_transport loads; the patch touches
#                            no headers, so the two stay ABI-compatible.
# plus a symlink to this repo's ros/carp_camera, whose package.xml lists the
# runtime pieces (image_transport, ffmpeg_image_transport, rosbag2 MCAP).
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

# name repo commit
SOURCES=(
    "camera_ros https://github.com/christianrauch/camera_ros.git 8f792e27a6dbc81e4943a75765fc1b7b7d37b301"
    # tag 3.0.1, the version apt ships for Jazzy; keep them in step
    "ffmpeg_encoder_decoder https://github.com/ros-misc-utilities/ffmpeg_encoder_decoder.git bdbbe8b159a8a71a21a5fa81478c959e130a0be8"
)

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
for entry in "${SOURCES[@]}"; do
    read -r name url commit <<< "$entry"
    dir=$WS/src/$name
    if [[ ! -d $dir/.git ]]; then
        git clone -q "$url" "$dir"
    fi
    if [[ $(git -C "$dir" rev-parse HEAD) != "$commit" ]]; then
        git -C "$dir" fetch -q origin
        git -C "$dir" checkout -q --detach "$commit"
    fi
    for p in "$repo/patches/$name"/*.patch; do
        [[ -e $p ]] || continue
        if git -C "$dir" apply --reverse --check "$p" 2>/dev/null; then
            echo "Already applied: $name/$(basename "$p")"
        else
            git -C "$dir" apply "$p"
            echo "Applied: $name/$(basename "$p")"
        fi
    done
done
ln -sfn "$repo/ros/carp_camera" "$WS/src/carp_camera"

rosdep install --from-paths "$WS/src" --ignore-src -y \
    -t buildtool -t build -t build_export -t exec \
    --skip-keys "libcamera image_view"

echo
echo "Dependencies installed. Build with: ./scripts/build-ros-workspace.sh"
