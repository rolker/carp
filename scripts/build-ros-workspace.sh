#!/usr/bin/env bash
# Build ~/ros2_ws (camera_ros + carp_camera) against the patched libcamera in
# ~/opt/libcamera, and check that camera_ros really linked that one.
#
# Needs: build-libcamera.sh and setup-ros-workspace.sh first.
# Usage: ./scripts/build-ros-workspace.sh
# Then:  source ~/opt/libcamera/env.sh && source ~/ros2_ws/install/setup.bash
set -euo pipefail

WS=${WS:-$HOME/ros2_ws}
PREFIX=${PREFIX:-$HOME/opt/libcamera}

set +u  # ROS setup scripts reference unset variables
# shellcheck source=/dev/null
source /opt/ros/jazzy/setup.bash
# shellcheck source=/dev/null
source "$PREFIX/env.sh"
set -u

cd "$WS"
colcon build --symlink-install --packages-up-to carp_camera \
    --cmake-args -DCMAKE_BUILD_TYPE=Release

lib=$(find "$WS/install/camera_ros" -name 'libcamera_component.so' | head -1)
linked=$(LD_LIBRARY_PATH=$PREFIX/lib ldd "$lib" | awk '/libcamera\.so/ {print $3}')
echo
echo "camera_ros links: $linked"
if [[ $linked != "$PREFIX"/* ]]; then
    echo "WARNING: not the patched libcamera in $PREFIX" >&2
    exit 1
fi
