#!/usr/bin/env bash
# Install what it takes to build Raspberry Pi's libcamera (with our Pivariety
# cam helper) and rpicam-apps on Ubuntu 24.04. Compilers come from
# build-essential; this adds the build system and libraries.
#
# Usage: sudo ./scripts/install-libcamera-build-deps.sh
set -euo pipefail

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi

packages=(
    # build system
    build-essential meson ninja-build pkg-config cmake
    # libcamera
    libyaml-dev python3-yaml python3-ply python3-jinja2
    libgnutls28-dev openssl libudev-dev libdw-dev
    nlohmann-json3-dev  # libpisp
    # rpicam-apps (its libav encoder is off: Ubuntu 24.04's ffmpeg is too old)
    libboost-program-options-dev libdrm-dev libexif-dev
    libjpeg-dev libtiff-dev libpng-dev
    # GStreamer libcamerasrc, and x264enc for encode tests
    libgstreamer1.0-dev libgstreamer-plugins-base1.0-dev gstreamer1.0-plugins-ugly
)

apt-get update
apt-get install -y "${packages[@]}"
