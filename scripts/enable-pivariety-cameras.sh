#!/usr/bin/env bash
# Enable both Arducam Pivariety (B0444) cameras on the Pi 5 CSI ports.
#
# camera_auto_detect only probes official Raspberry Pi sensors, so turn it off
# and load the arducam-pivariety overlay explicitly on cam0 and cam1.
# Safe to re-run: backs up config.txt and only adds lines that are missing.
#
# Usage: sudo ./scripts/enable-pivariety-cameras.sh   (then reboot)
set -euo pipefail

CONFIG=/boot/firmware/config.txt

if [[ $EUID -ne 0 ]]; then
    echo "Run with sudo: sudo $0" >&2
    exit 1
fi
[[ -f $CONFIG ]] || { echo "$CONFIG not found" >&2; exit 1; }
[[ -f /boot/firmware/overlays/arducam-pivariety.dtbo ]] \
    || { echo "arducam-pivariety.dtbo overlay missing" >&2; exit 1; }

backup="$CONFIG.$(date +%Y%m%d-%H%M%S).bak"
cp -a "$CONFIG" "$backup"
echo "Backup: $backup"

# Disable auto-detect wherever it is set.
sed -i -E 's/^(\s*)camera_auto_detect=1\s*$/\1camera_auto_detect=0/' "$CONFIG"

# Append to a trailing [all] section so the overlays apply on every model.
if [[ $(grep -E '^\s*\[' "$CONFIG" | tail -1 | tr -d '[:space:]') != "[all]" ]]; then
    printf '\n[all]\n' >> "$CONFIG"
fi
for port in cam0 cam1; do
    line="dtoverlay=arducam-pivariety,$port"
    grep -qxF "$line" "$CONFIG" || echo "$line" >> "$CONFIG"
done

echo "Changes:"
diff -u "$backup" "$CONFIG" || true
echo
echo "Reboot to apply. Undo with: sudo cp -a $backup $CONFIG"
