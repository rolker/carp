# Vendor CAD

Manufacturer models used as references in Onshape. The files themselves are
git-ignored (large, and the vendor's to distribute); this list says where to
get each one.

| File | Part | Source | Notes |
|---|---|---|---|
| `B0444.STEP` | Arducam B0444 — IMX462 color, 141° M12 lens, Pivariety (the stereo cameras) | STEP download on Arducam's product page: <https://www.arducam.com/2mp-imx462-color-ultra-low-light-starvis-camera-module-with-141h-wide-angle-m12-lens-for-raspberry-pi.html> (the site blocks scripted downloads — use a browser) | SolidWorks 2021 export, 2023-07-21, ~8 MB. Downloaded 2026-09-26. SHA-256 `089f9e1f994d83802558106c0e795b24fb683035b7f99777f9aaf918f616bde9` |
| `RP-010083-CA-1-rpi-5 3D STEP - No Graphics small file.zip` | Raspberry Pi 5 board | Raspberry Pi Product Information Portal, Raspberry Pi 5 category: <https://pip.raspberrypi.com/categories/892-raspberry-pi-5> — direct: <https://pip-assets.raspberrypi.com/categories/892-raspberry-pi-5/documents/RP-010083-CA-1-rpi-5%203D%20STEP%20-%20No%20Graphics%20small%20file.zip> | ~13 MB zip, updated 2026-06-11; the "With Graphics" variant (RP-010082, ~24 MB) adds silkscreen and isn't needed for fit. Same portal hosts the mechanical drawing in `../reference/`. The old `datasheets.raspberrypi.com/rpi5/…step.zip` links are dead or empty |

## B0444 key dimensions (read from the STEP, mm)

Checked against a real board with calipers on 2026-09-27 (`cad/README.md` §1):
board 25.1 × 24.4 × 1.7, holes 21.05 × 12.55 at ~Ø2.0, lens front 17.0 above
the board at the current focus, back-side parts 2.2, barrel Ø14.0. Use the
measured values where they differ.

- Board 25 × ~24, 1.6 thick, R2 corners — the Raspberry Pi Camera v2 footprint
- Mounting holes Ø2.2 (M2), **21 × 12.5** pattern — also the Pi Camera v2 pattern
- Back-side components ~2 proud of the board
- M12 lens holder, two screws 18 apart straddling the lens
- **Optical axis is off-centre:** centred across the 25 width, ~4.7 from the
  board centre toward the edge opposite the connector (1.3 from the centre of
  the hole pattern)
- Lens front ~16 above the board's front face; barrel ~Ø14, front element ~Ø13.4
- Connector plus ribbon stub reaches ~8 past the connector-end board edge
