#!/usr/bin/env bash
# Capture raw 1080p frames from both Pivariety cameras at once, then write a
# side-by-side preview PNG. Bench check that the kernel path streams; no
# libcamera, no ISP, no white balance (the preview is green-tinted by design).
#
# Media and video node numbers change between boots, so each camera is found
# by its sensor's I2C bus: bus 10 is CAM/DISP 0, bus 11 is CAM/DISP 1.
#
# Usage: ./scripts/capture-raw-pair.sh [outdir] [frames] [exposure] [gain]
#   exposure is in lines (~14.8 us each), gain 100 = 1x. Needs the video group.
set -euo pipefail

outdir=${1:-.}
frames=${2:-30}
exposure=${3:-1000}
gain=${4:-200}
here=$(dirname "$(readlink -f "$0")")
mkdir -p "$outdir"

declare -A video=()
for m in /dev/media*; do
    sensor=$(media-ctl -d "$m" -p 2>/dev/null \
        | grep -oE 'arducam-pivariety 1[01]-000c' | head -1) || true
    [[ -n $sensor ]] || continue
    port=$(( ${sensor:18:2} - 10 ))
    media-ctl -d "$m" -l '"csi2":4 -> "rp1-cfe-csi2_ch0":0 [1]'
    media-ctl -d "$m" -V '"csi2":0 [fmt:SRGGB10_1X10/1920x1080 field:none]'
    media-ctl -d "$m" -V '"csi2":4 [fmt:SRGGB10_1X10/1920x1080 field:none]'
    v4l2-ctl -d "$(media-ctl -d "$m" -e "$sensor")" \
        -c exposure="$exposure",analogue_gain="$gain"
    video[$port]=$(media-ctl -d "$m" -e rp1-cfe-csi2_ch0)
    v4l2-ctl -d "${video[$port]}" \
        --set-fmt-video=width=1920,height=1080,pixelformat=pRAA
    echo "cam$port: $m ${video[$port]}"
done

(( ${#video[@]} > 0 )) || { echo "No Pivariety sensor bound; check dmesg" >&2; exit 1; }

for port in "${!video[@]}"; do
    timeout 20 v4l2-ctl -d "${video[$port]}" --stream-mmap \
        --stream-count="$frames" --stream-to="$outdir/cam$port.raw" &
done
wait
echo

if [[ -n ${video[0]:-} && -n ${video[1]:-} ]]; then
    python3 "$here/raw10-preview.py" "$outdir/cam0.raw" "$outdir/cam1.raw" "$outdir/pair.png"
    echo "Preview: $outdir/pair.png (left cam0, right cam1)"
else
    echo "Only one camera found; preview needs both" >&2
fi
