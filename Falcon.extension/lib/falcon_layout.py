# ============================================================
# Shared Library
# ============================================================
# Module Name    : falcon_layout
# Purpose        : Revit-free maths for Junction Box (which box type and
#                  rotation a fixture's routing lines need) and Auto
#                  Dimension (outlets lined up in rows and columns).
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7 / CPython 3 (no Revit imports)
# ============================================================
"""Pure helpers, unit-tested offline (tests/test_falcon_layout.py).
Points are (x, y, z) tuples; directions are plan (x, y) unit vectors."""

import math


def _pdist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _unit2(a, b):
    dx, dy = b[0] - a[0], b[1] - a[1]
    length = math.hypot(dx, dy)
    return (dx / length, dy / length)


# ------------------------------------------------------- box type names

def _words(name):
    words, cur = [], ""
    for ch in (name or "").lower():
        if ch.isalnum():
            cur += ch
        elif cur:
            words.append(cur)
            cur = ""
    if cur:
        words.append(cur)
    return words


def type_kind(name):
    """What a junction box type is for, from its name: "terminal",
    "through", "angle", "tee", "y", "cross" or None.

    Reads names like "Terminal (1-way)", "Through (2-way 180)",
    "Angle (2-way 90)", "Tee (3-way)", "Branch_Y", "Cross (4-way)"."""
    w = _words(name)
    way = "way" in w
    if "y" in w or "wye" in w:
        return "y"
    if "cross" in w or (way and "4" in w):
        return "cross"
    if "tee" in w or (way and "3" in w):
        return "tee"
    if any(x in w for x in ("angle", "elbow", "corner", "90")):
        return "angle"
    if any(x in w for x in ("through", "thru", "straight", "inline", "180")):
        return "through"
    if any(x in w for x in ("terminal", "end", "dead")) or (way and "1" in w):
        return "terminal"
    if way and "2" in w:
        return "through"
    return None


def pattern_kind(directions, tol_deg=10.0):
    """Box needed for the route directions leaving a fixture:
    terminal / through / angle / tee / y / cross; None for none or 5+."""
    n = len(directions)
    opp = math.cos(math.radians(tol_deg))
    pairs = [(a, b) for a in range(n) for b in range(a + 1, n)
             if directions[a][0] * directions[b][0]
             + directions[a][1] * directions[b][1] <= -opp]
    if n == 1:
        return "terminal"
    if n == 2:
        return "through" if pairs else "angle"
    if n == 3:
        return "tee" if pairs else "y"
    if n == 4:
        return "cross"
    return None


# ------------------------------------------------ routing at a fixture

def _touches(a, b, rect):
    """Liang-Barsky: does segment a-b touch the plan rectangle?"""
    x0, y0, x1, y1 = rect
    dx, dy = b[0] - a[0], b[1] - a[1]
    t0, t1 = 0.0, 1.0
    for p, q in ((-dx, a[0] - x0), (dx, x1 - a[0]), (-dy, a[1] - y0), (dy, y1 - a[1])):
        if abs(p) < 1e-12:
            if q < 0:
                return False
            continue
        r = q / p
        if p < 0:
            t0 = max(t0, r)
        else:
            t1 = min(t1, r)
        if t0 > t1:
            return False
    return True


def _inside(p, rect):
    return rect[0] <= p[0] <= rect[2] and rect[1] <= p[1] <= rect[3]


def exit_directions(center, rect, segments, merge_deg=10.0):
    """Plan directions in which routing lines leave a fixture.

    rect = (min x, min y, max x, max y) of the fixture outline. Each
    segment touching the outline adds the direction toward each of its
    ends that lies outside the outline (a line passing straight through
    adds both). Directions within merge_deg are merged."""
    limit = math.cos(math.radians(merge_deg))
    dirs = []
    for a, b in segments:
        if _pdist(a, b) < 1e-9 or not _touches(a, b, rect):
            continue
        u = _unit2(a, b)
        for p in (a, b):
            if _inside(p, rect):
                continue
            side = (p[0] - center[0]) * u[0] + (p[1] - center[1]) * u[1]
            d = u if side > 0 else (-u[0], -u[1])
            if all(d[0] * e[0] + d[1] * e[1] < limit for e in dirs):
                dirs.append(d)
    return dirs


def nearest_segment_distance(point, segments):
    """Plan distance from point to the nearest segment (None if none)."""
    best = None
    for a, b in segments:
        length = _pdist(a, b)
        if length < 1e-12:
            d = _pdist(a, point)
        else:
            u = _unit2(a, b)
            t = max(0.0, min(length, (point[0] - a[0]) * u[0] + (point[1] - a[1]) * u[1]))
            d = math.hypot(point[0] - a[0] - u[0] * t, point[1] - a[1] - u[1] * t)
        best = d if best is None else min(best, d)
    return best


def best_rotation(conn_dirs, route_dirs):
    """Turn (radians, about vertical) that lines the box outlets up with
    the route directions best. Each candidate turns one outlet onto one
    route; the best coverage wins, the smallest turn breaks ties."""
    if not conn_dirs or not route_dirs:
        return 0.0
    best = None
    for c in conn_dirs:
        for r in route_dirs:
            ang = math.atan2(r[1], r[0]) - math.atan2(c[1], c[0])
            ang = math.atan2(math.sin(ang), math.cos(ang))
            ca, sa = math.cos(ang), math.sin(ang)
            turned = [(x * ca - y * sa, x * sa + y * ca) for x, y in conn_dirs]
            score = sum(max(t[0] * q[0] + t[1] * q[1] for t in turned) for q in route_dirs)
            key = (round(score, 6), -round(abs(ang), 6))
            if best is None or key > best[0]:
                best = (key, ang)
    return best[1]


def pick_family(families, needed):
    """Family (key) with types for the most of the `needed` kinds.

    families: {key: set of kinds its types cover}; first key wins a tie."""
    best = None
    for key, kinds in families.items():
        score = len(set(needed) & kinds)
        if best is None or score > best[0]:
            best = (score, key)
    return best[1] if best else None


# ---------------------------------------------------- outlet dimensions

def rows_and_columns(points, tol):
    """Group outlet centres that line up.

    Returns (rows, columns, singles): rows / columns are lists of point
    indices sorted along the line (2+ points each); singles counts the
    groups that had one point only."""
    def cluster(axis):
        groups = []
        for i in sorted(range(len(points)), key=lambda k: points[k][axis]):
            if groups and abs(points[i][axis] - points[groups[-1][-1]][axis]) <= tol:
                groups[-1].append(i)
            else:
                groups.append([i])
        return groups
    rows, cols = cluster(1), cluster(0)
    singles = len([g for g in rows + cols if len(g) < 2])
    rows = [sorted(g, key=lambda i: points[i][0]) for g in rows if len(g) >= 2]
    cols = [sorted(g, key=lambda i: points[i][1]) for g in cols if len(g) >= 2]
    return rows, cols, singles


def gaps(values):
    return [b - a for a, b in zip(values, values[1:])]
