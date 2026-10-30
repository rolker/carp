#!/usr/bin/env python3
"""Beam patterns of candidate topside arrays (docs/topside-head.md).

Array factors only: ideal omnidirectional elements at half-wavelength pitch,
uniform weights, far field, one frequency, broadside. No element directivity,
mutual coupling or disc-to-disc variation, so real arrays will be worse.

Each row is a geometry plus the processing used on it:
  additive        delay-and-sum over all elements, wide transmit
  product         two receive sub-arrays beamformed separately and multiplied
                  (Mills cross processing; the "thick arm" variant includes
                  the core in each arm), wide transmit
  two-way         a transmit pattern multiplied by a receive pattern

"Leak beyond N deg" is the strongest response to a target more than N degrees
off the beam axis, relative to the beam peak: how much of an off-axis target
shows up in this beam.

    python3 array_patterns.py            # the table
    python3 array_patterns.py --plot X   # pattern image for row X (needs matplotlib)
"""
import argparse
import numpy as np

D = 0.5  # element pitch in wavelengths


def grid(nx, ny, x0=0.0, y0=0.0):
    xs = (np.arange(nx) - (nx - 1) / 2) * D + x0
    ys = (np.arange(ny) - (ny - 1) / 2) * D + y0
    return {(round(x, 3), round(y, 3)) for x in xs for y in ys}


def line(n, axis, offset=0.0):
    return grid(n, 1, y0=offset) if axis == "x" else grid(1, n, x0=offset)


def ring(n):
    return grid(n, n) - grid(n - 2, n - 2)


# --- geometries -------------------------------------------------------------
# Even-count crosses are offset by half a pitch so both arms sit on one grid
# and share one element.
ARM8_X, ARM8_Y = line(8, "x", +0.5 * D), line(8, "y", -0.5 * D)
CORE4 = grid(4, 4)
CORE5 = grid(5, 5)
ARM11_X = line(11, "x")
ARM5_Y = line(5, "y")
ARM9_X, ARM7_Y = line(9, "x"), line(7, "y")
RING9 = ring(9)
RING_TB = {p for p in RING9 if abs(p[1]) == max(q[1] for q in RING9)}
RING_LR = {p for p in RING9 if abs(p[0]) == max(q[0] for q in RING9)}
FULL8 = grid(8, 8)

# --- pattern maths ----------------------------------------------------------
N = 801
u = np.linspace(-1, 1, N)
U, V = np.meshgrid(u, u)
R = np.hypot(U, V)
VIS = R <= 1


def pattern(points):
    """Normalised array factor magnitude over direction cosines (u, v)."""
    af = sum(np.exp(2j * np.pi * (x * U + y * V)) for x, y in points)
    return np.where(VIS, np.abs(af) / len(points), 0.0)


def width_deg(db_row):
    on = np.where(db_row >= -3)[0]
    return float(np.degrees(np.arcsin(u[on[-1]]) - np.arcsin(u[on[0]])))


def summarise(af):
    db = 20 * np.log10(np.maximum(af, 1e-6))
    bw_u = width_deg(db[N // 2])
    bw_v = width_deg(db[:, N // 2])
    leak = {a: float(db[VIS & (R > np.sin(np.radians(a)))].max()) for a in (15, 20, 30)}
    return bw_u, bw_v, leak


ROWS = [
    # (label, channels, pings per 2D frame, pattern function)
    ("8x8 cross, arms multiplied, wide TX", 15, "1",
     lambda: pattern(ARM8_X) * pattern(ARM8_Y)),
    ("4x4 filled, TX and RX", 16, "steered",
     lambda: pattern(CORE4) ** 2),
    ("hybrid: 8x8 cross + 4x4 core, all added", 24, "1",
     lambda: pattern(ARM8_X | ARM8_Y | CORE4)),
    ("hybrid: thick arms multiplied, wide TX", 24, "1",
     lambda: pattern(ARM8_X | CORE4) * pattern(ARM8_Y | CORE4)),
    ("hybrid: core TX, thick arms multiplied", 24, "steered",
     lambda: pattern(CORE4) * pattern(ARM8_X | CORE4) * pattern(ARM8_Y | CORE4)),
    ("cored cross: 5x5 core, 11x5 arms, thick arms multiplied, wide TX", 31, "1",
     lambda: pattern(ARM11_X | CORE5) * pattern(ARM5_Y | CORE5)),
    ("cored cross: 5x5 core, 11x5 arms, core TX, thick arms multiplied", 31, "steered",
     lambda: pattern(CORE5) * pattern(ARM11_X | CORE5) * pattern(ARM5_Y | CORE5)),
    ("cored cross: 5x5 core, 9x7 arms, core TX, thick arms multiplied", 31, "steered",
     lambda: pattern(CORE5) * pattern(ARM9_X | CORE5) * pattern(ARM7_Y | CORE5)),
    ("square ring 9/side, all added", 32, "1",
     lambda: pattern(RING9)),
    ("square ring, opposite sides multiplied, wide TX", 32, "1",
     lambda: pattern(RING_TB) * pattern(RING_LR)),
    ("square ring, all TX, sides multiplied", 32, "steered",
     lambda: pattern(RING9) * pattern(RING_TB) * pattern(RING_LR)),
    ("filled rectangle 8x4, TX and RX", 32, "steered",
     lambda: pattern(grid(8, 4)) ** 2),
    ("8x8 filled, TX and RX", 64, "steered",
     lambda: pattern(FULL8) ** 2),
]


def main():
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--plot", type=int, metavar="ROW", help="show the pattern for one row (0-based)")
    args = ap.parse_args()

    if args.plot is not None:
        import matplotlib.pyplot as plt
        label, ch, _, fn = ROWS[args.plot]
        db = 20 * np.log10(np.maximum(fn(), 1e-6))
        plt.imshow(np.where(VIS, db, np.nan), extent=[-1, 1, -1, 1], origin="lower", vmin=-50, vmax=0, cmap="viridis")
        plt.colorbar(label="dB")
        plt.title(f"{label} ({ch} ch)")
        plt.xlabel("u = sin(angle) across")
        plt.ylabel("v = sin(angle) along")
        plt.show()
        return

    print(f"{'#':>2} {'array and processing':66s} {'ch':>3} {'pings':>7} | {'-3 dB width':>13} | leak beyond 15 / 20 / 30 deg")
    for i, (label, ch, pings, fn) in enumerate(ROWS):
        bw_u, bw_v, leak = summarise(fn())
        print(f"{i:>2} {label:66s} {ch:>3} {pings:>7} | {bw_u:5.1f} x {bw_v:5.1f} | {leak[15]:6.1f} {leak[20]:6.1f} {leak[30]:6.1f}")
    print("\nIdeal array factors at the design frequency; see the docstring for what is left out.")


if __name__ == "__main__":
    main()
