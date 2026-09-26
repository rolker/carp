#!/usr/bin/env bash
# Build Raspberry Pi's libcamera with our Arducam Pivariety cam helper, plus
# rpicam-apps, into a private prefix (no sudo). Pi 5 pipeline only.
#
# Sources go in $SRC (default ~/src), the install in $PREFIX (default
# ~/opt/libcamera). Safe to re-run: reuses clones, skips an applied patch,
# and rebuilds only what changed. Afterwards: source $PREFIX/env.sh
#
# Needs: sudo ./scripts/install-libcamera-build-deps.sh (once)
# Usage: ./scripts/build-libcamera.sh
set -euo pipefail

SRC=${SRC:-$HOME/src}
PREFIX=${PREFIX:-$HOME/opt/libcamera}
here=$(dirname "$(readlink -f "$0")")
patches=$here/../patches/libcamera

# Pinned so rebuilds are reproducible. libcamera matches the base of
# Arducam's 0.7.2+rpt20260819 package.
LIBCAMERA_REPO=https://github.com/raspberrypi/libcamera.git
LIBCAMERA_COMMIT=6c1dd9d55573010f710c9e190a73e7e76f0d9432
RPICAM_REPO=https://github.com/raspberrypi/rpicam-apps.git
RPICAM_COMMIT=6ddd6ba738df3f2c97065899ed41fe6177b634c8

checkout() {  # repo commit dir
    if [[ ! -d $3/.git ]]; then
        git init -q "$3"
        git -C "$3" remote add origin "$1"
    fi
    if [[ $(git -C "$3" rev-parse HEAD 2>/dev/null) != "$2" ]]; then
        git -C "$3" fetch -q --depth 1 origin "$2"
        git -C "$3" checkout -q --detach "$2"
    fi
}

setup() {  # srcdir, then meson options
    local dir=$1; shift
    if [[ -f $dir/build/build.ninja ]]; then
        meson setup --reconfigure "$dir/build" "$dir" "$@"
    else
        meson setup "$dir/build" "$dir" "$@"
    fi
}

mkdir -p "$SRC" "$PREFIX"

# --- libcamera ---------------------------------------------------------------
lc=$SRC/libcamera
checkout "$LIBCAMERA_REPO" "$LIBCAMERA_COMMIT" "$lc"
for p in "$patches"/*.patch; do
    if git -C "$lc" apply --reverse --check "$p" 2>/dev/null; then
        echo "Already applied: $(basename "$p")"
    else
        git -C "$lc" apply "$p"
        echo "Applied: $(basename "$p")"
    fi
done

setup "$lc" --prefix="$PREFIX" --libdir=lib --buildtype=release \
    -Dpipelines=rpi/pisp -Dipas=rpi/pisp \
    -Dgstreamer=enabled -Dv4l2=false -Dcam=disabled -Dqcam=disabled \
    -Dlc-compliance=disabled -Dpycamera=disabled -Ddocumentation=disabled \
    -Dtest=false -Dtracing=disabled -Drpi-awb-nn=disabled
ninja -C "$lc/build" install

# Tuning is looked up by sensor model; ours reports "arducam-pivariety".
tuning=$PREFIX/share/libcamera/ipa/rpi/pisp
cp "$tuning/imx462.json" "$tuning/arducam-pivariety.json"

# --- environment -------------------------------------------------------------
cat > "$PREFIX/env.sh" <<EOF
# source this to use the libcamera in $PREFIX
export PATH=$PREFIX/bin\${PATH:+:\$PATH}
export LD_LIBRARY_PATH=$PREFIX/lib\${LD_LIBRARY_PATH:+:\$LD_LIBRARY_PATH}
export PKG_CONFIG_PATH=$PREFIX/lib/pkgconfig\${PKG_CONFIG_PATH:+:\$PKG_CONFIG_PATH}
export GST_PLUGIN_PATH=$PREFIX/lib/gstreamer-1.0\${GST_PLUGIN_PATH:+:\$GST_PLUGIN_PATH}
EOF
# shellcheck source=/dev/null
source "$PREFIX/env.sh"

# --- rpicam-apps -------------------------------------------------------------
ra=$SRC/rpicam-apps
checkout "$RPICAM_REPO" "$RPICAM_COMMIT" "$ra"
# libav is off: it needs libavcodec >= 61 (ffmpeg 7) and Ubuntu 24.04 has 60.
# rpicam-apps is only for camera checks; encoding goes through the ROS video
# transport or GStreamer x264enc.
setup "$ra" --prefix="$PREFIX" --libdir=lib --buildtype=release \
    -Denable_libav=disabled -Denable_drm=enabled -Denable_egl=disabled \
    -Denable_qt=disabled -Denable_opencv=disabled -Denable_tflite=disabled \
    -Denable_hailo=disabled -Denable_imx500=false
ninja -C "$ra/build" install

echo
echo "Installed to $PREFIX. Use it with: source $PREFIX/env.sh"
echo "Check: rpicam-hello --list-cameras"
