# ============================================================
# Shared Library
# ============================================================
# Module Name    : falcon_wiring
# Purpose        : Revit-free maths for Wiring Pro - the order to visit the
#                  outlets in, and clean horizontal / vertical wiring lines
#                  between them that never run over another fixture.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7 / CPython 3 (no Revit imports)
# ============================================================
"""Pure helpers, unit-tested offline (tests/test_falcon_wiring.py).

Points are (x, y) or (x, y, z) tuples - only x and y are used and
returned points keep the z of the first point given. A fixture outline
is a plan rectangle (min x, min y, max x, max y)."""

import math

SIDES = ("E", "W", "N", "S")
_FACING = {"E": (1, 0), "W": (-1, 0), "N": (0, 1), "S": (0, -1)}
PHASE_RGB = {"R": (255, 0, 0), "Y": (255, 200, 0), "B": (0, 90, 255)}


def _manhattan(a, b):
    return abs(a[0] - b[0]) + abs(a[1] - b[1])


# ----------------------------------------------------------- run order

def _path_length(points, order):
    return sum(_manhattan(points[a], points[b]) for a, b in zip(order, order[1:]))


def order_run(points, first, last=None):
    """Visit order (indices) for a run that starts at `first` and, when
    given, ends at `last`: nearest neighbour, then 2-opt until no swap
    makes the run shorter. Distances are Manhattan, as the wiring only
    runs horizontally and vertically."""
    n = len(points)
    if n == 0:
        return []
    left = set(range(n)) - set([first])
    if last is not None and last != first:
        left.discard(last)
    order = [first]
    while left:
        cur = points[order[-1]]
        nxt = min(sorted(left), key=lambda i: _manhattan(cur, points[i]))
        order.append(nxt)
        left.discard(nxt)
    if last is not None and last != first:
        order.append(last)
    improved = True
    end = len(order) - (1 if last is not None and last != first else 0)
    while improved:
        improved = False
        for i in range(1, end - 1):
            for j in range(i + 1, end):
                trial = order[:i] + order[i:j + 1][::-1] + order[j + 1:]
                if _path_length(points, trial) < _path_length(points, order) - 1e-9:
                    order = trial
                    improved = True
    return order


# ------------------------------------------------------------- outlines

def side_mid(rect, side):
    x0, y0, x1, y1 = rect
    cx, cy = (x0 + x1) / 2.0, (y0 + y1) / 2.0
    return {"E": (x1, cy), "W": (x0, cy), "N": (cx, y1), "S": (cx, y0)}[side]


def _seg_hits_rect(a, b, rect, shrink):
    """Does the horizontal / vertical segment a-b pass through the
    inside of rect (shrunk by `shrink`, so touching a side is fine)?"""
    x0, y0, x1, y1 = rect[0] + shrink, rect[1] + shrink, rect[2] - shrink, rect[3] - shrink
    if x0 >= x1 or y0 >= y1:
        return False
    if abs(a[1] - b[1]) < 1e-9:          # horizontal
        y = a[1]
        lo, hi = min(a[0], b[0]), max(a[0], b[0])
        return y0 < y < y1 and lo < x1 and hi > x0
    x = a[0]
    lo, hi = min(a[1], b[1]), max(a[1], b[1])
    return x0 < x < x1 and lo < y1 and hi > y0


def hits(path, rects, shrink=1e-6):
    """How many (segment, rectangle) overlaps the path has."""
    count = 0
    for a, b in zip(path, path[1:]):
        for r in rects:
            if _seg_hits_rect(a, b, r, shrink):
                count += 1
    return count


def _clean(path):
    out = []
    for p in path:
        if not out or abs(p[0] - out[-1][0]) > 1e-9 or abs(p[1] - out[-1][1]) > 1e-9:
            out.append(p)
    # drop middle points of straight runs
    i = 1
    while i < len(out) - 1:
        a, b, c = out[i - 1], out[i], out[i + 1]
        if (abs(a[0] - b[0]) < 1e-9 and abs(b[0] - c[0]) < 1e-9) or \
                (abs(a[1] - b[1]) < 1e-9 and abs(b[1] - c[1]) < 1e-9):
            out.pop(i)
        else:
            i += 1
    return out


def orthogonal_options(pa, pb):
    """Ways to go from pa to pb with horizontal / vertical legs only:
    straight (if lined up), the two L shapes and the two Z shapes."""
    if abs(pa[0] - pb[0]) < 1e-9 or abs(pa[1] - pb[1]) < 1e-9:
        return [[pa, pb]]
    mx, my = (pa[0] + pb[0]) / 2.0, (pa[1] + pb[1]) / 2.0
    return [
        [pa, (pb[0], pa[1]), pb],
        [pa, (pa[0], pb[1]), pb],
        [pa, (mx, pa[1]), (mx, pb[1]), pb],
        [pa, (pa[0], my), (pb[0], my), pb],
    ]


def _leaves(path, side):
    """First leg goes straight out of `side` (or the path is one point)."""
    if len(path) < 2:
        return True
    f = _FACING[side]
    d = (path[1][0] - path[0][0], path[1][1] - path[0][1])
    return d[0] * f[0] + d[1] * f[1] > 1e-9 and abs(d[0] * f[1] - d[1] * f[0]) < 1e-9


def _arrives(path, side):
    """Last leg comes straight into `side` from outside."""
    if len(path) < 2:
        return True
    f = _FACING[side]
    d = (path[-1][0] - path[-2][0], path[-1][1] - path[-2][1])
    return d[0] * f[0] + d[1] * f[1] < -1e-9 and abs(d[0] * f[1] - d[1] * f[0]) < 1e-9


def _score(path, obstacles):
    length = sum(_manhattan(a, b) for a, b in zip(path, path[1:]))
    return (hits(path, obstacles), len(path), length)


def _near(rects, box, pad):
    x0, y0, x1, y1 = box
    return [r for r in rects
            if r[2] > x0 - pad and r[0] < x1 + pad and r[3] > y0 - pad and r[1] < y1 + pad]


def _detours(pa, fa, pb, fb, rects, gap):
    """Paths that step `gap` straight out of each side, then run along a
    lane just clear of the nearby fixtures."""
    a1 = (pa[0] + fa[0] * gap, pa[1] + fa[1] * gap)
    b1 = (pb[0] + fb[0] * gap, pb[1] + fb[1] * gap)
    ys = set([a1[1], b1[1], (a1[1] + b1[1]) / 2.0])
    xs = set([a1[0], b1[0], (a1[0] + b1[0]) / 2.0])
    for r in rects:
        ys.update([r[1] - gap, r[3] + gap])
        xs.update([r[0] - gap, r[2] + gap])
    for y in ys:
        yield [pa, a1, (a1[0], y), (b1[0], y), b1, pb]
    for x in xs:
        yield [pa, a1, (x, a1[1]), (x, b1[1]), b1, pb]


def route_sides(rect_a, rect_b, obstacles, used_a=None):
    """Line from the middle of a side of fixture A to the middle of a side
    of fixture B, horizontal / vertical only.

    It leaves A straight out of a side and enters B straight into a side,
    never uses A's `used_a` side again (one line in, one line out), and
    avoids the other fixtures (`obstacles`) - going around them on a lane
    just clear of them when needed. Fewest fixtures crossed wins, then
    fewest bends, then shortest. Returns (points, side_a, side_b)."""
    size = max(rect_a[2] - rect_a[0], rect_a[3] - rect_a[1],
               rect_b[2] - rect_b[0], rect_b[3] - rect_b[1])
    gap = 0.3 * size
    box = (min(rect_a[0], rect_b[0]), min(rect_a[1], rect_b[1]),
           max(rect_a[2], rect_b[2]), max(rect_a[3], rect_b[3]))
    nearby = _near(obstacles, box, 2 * size)
    blockers = nearby + [rect_a, rect_b]
    best = None
    for sa in SIDES:
        if sa == used_a:
            continue
        pa = side_mid(rect_a, sa)
        for sb in SIDES:
            pb = side_mid(rect_b, sb)
            raws = list(orthogonal_options(pa, pb))
            raws.extend(_detours(pa, _FACING[sa], pb, _FACING[sb], blockers, gap))
            for raw in raws:
                path = _clean(raw)
                if not (_leaves(path, sa) and _arrives(path, sb)):
                    continue
                key = _score(path, blockers)
                if best is None or key < best[0]:
                    best = (key, path, sa, sb)
    if best is None:            # nothing clean: plain L between centres
        pa = side_mid(rect_a, "E" if used_a != "E" else "W")
        pb = side_mid(rect_b, "W")
        return _clean([pa, (pb[0], pa[1]), pb]), None, None
    return best[1], best[2], best[3]


def route_points(pa, pb, obstacles, first_axis=None):
    """Horizontal / vertical line between two fixed points (custom
    connection points, wall outlet ports). `first_axis` "x" or "y" breaks
    ties in favour of starting along that axis."""
    box = (min(pa[0], pb[0]), min(pa[1], pb[1]), max(pa[0], pb[0]), max(pa[1], pb[1]))
    span = max(box[2] - box[0], box[3] - box[1], 1e-6)
    nearby = _near(obstacles, box, 0.5 * span)
    raws = list(orthogonal_options(pa, pb))
    if hits(raws[0], nearby):
        gap = 0.1 * span
        for r in nearby:
            for y in (r[1] - gap, r[3] + gap):
                raws.append([pa, (pa[0], y), (pb[0], y), pb])
            for x in (r[0] - gap, r[2] + gap):
                raws.append([pa, (x, pa[1]), (x, pb[1]), pb])
    best = None
    for raw in raws:
        path = _clean(raw)
        key = list(_score(path, nearby))
        if first_axis and len(path) > 1:
            along_x = abs(path[1][1] - path[0][1]) < 1e-9
            key.insert(1, 0 if (first_axis == "x") == along_x else 1)
        key = tuple(key)
        if best is None or key < best[0]:
            best = (key, path)
    return best[1]


# ---------------------------------------------------------- wall outlets

def wall_ports(location, along, out, half_width, mode, front=0.0):
    """The two points where wiring meets a wall outlet.

    along: plan unit vector along the wall; out: unit vector into the room.
    "outlet": two points beside the outlet's stub, `front` into the room.
    "backbox": the two circles of the back box, on the wall face."""
    push = front if mode == "outlet" else 0.0
    base = (location[0] + out[0] * push, location[1] + out[1] * push)
    return ((base[0] + along[0] * half_width, base[1] + along[1] * half_width),
            (base[0] - along[0] * half_width, base[1] - along[1] * half_width))


def enter_leave(ports, came_from):
    """(entry port, exit port): enter at the port nearer where the wiring
    comes from, leave from the other one."""
    a, b = ports
    if came_from is None:
        return a, b
    if _manhattan(a, came_from) <= _manhattan(b, came_from):
        return a, b
    return b, a


def axis_of(vector):
    return "x" if abs(vector[0]) >= abs(vector[1]) else "y"


# ----------------------------------------------------------------- misc

def phase_letter(circuit_number, default="R"):
    """R / Y / B from a circuit number such as "R4" or "Y12"."""
    for ch in (circuit_number or ""):
        if ch.isalpha():
            ch = ch.upper()
            return ch if ch in PHASE_RGB else default
    return default


def lift(path, z):
    return [(p[0], p[1], z) for p in path]


def arc_points(start, toward, length, bulge=0.25):
    """Three points of a short home-run arc from start toward a point."""
    dx, dy = toward[0] - start[0], toward[1] - start[1]
    d = math.hypot(dx, dy) or 1.0
    ux, uy = dx / d, dy / d
    end = (start[0] + ux * length, start[1] + uy * length)
    mid = (start[0] + ux * length / 2.0 - uy * length * bulge,
           start[1] + uy * length / 2.0 + ux * length * bulge)
    return [start, mid, end]
