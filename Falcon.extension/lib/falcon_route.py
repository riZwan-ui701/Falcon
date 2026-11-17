# ============================================================
# Shared Library
# ============================================================
# Module Name    : falcon_route
# Purpose        : Revit-free routing maths for Home Run Guide, Convert
#                  Line and Connect Conduit - polylines, offset lanes,
#                  joints between lines, and conduit legs to a device.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7 / CPython 3 (no Revit imports)
# ============================================================
"""Pure helpers, unit-tested offline (tests/test_falcon_route.py).

Points are (x, y, z) tuples; plan work ignores z. Units are whatever
the caller passes (the tools pass feet)."""

import math

from falcon_geom import vsub, vlen


def _pdist(a, b):
    return math.hypot(a[0] - b[0], a[1] - b[1])


def _cross2(a, b):
    return a[0] * b[1] - a[1] * b[0]


def _unit2(d):
    length = math.hypot(d[0], d[1])
    if length < 1e-12:
        raise ValueError("segment has no length in plan")
    return (d[0] / length, d[1] / length)


# ------------------------------------------------------------ polylines

def chain_polyline(segments, tol):
    """Order touching segments into one open polyline [p0, p1, ...].

    Raises ValueError if they branch, loop or do not touch."""
    if not segments:
        raise ValueError("no lines")
    left = [tuple(s) for s in segments]
    pts = [left[0][0], left[0][1]]
    left.pop(0)
    while left:
        grown = False
        for i, (a, b) in enumerate(left):
            if _pdist(a, pts[-1]) <= tol:
                pts.append(b)
            elif _pdist(b, pts[-1]) <= tol:
                pts.append(a)
            elif _pdist(b, pts[0]) <= tol:
                pts.insert(0, a)
            elif _pdist(a, pts[0]) <= tol:
                pts.insert(0, b)
            else:
                continue
            left.pop(i)
            grown = True
            break
        if not grown:
            raise ValueError("the reference lines must touch end to end in one chain")
    if _pdist(pts[0], pts[-1]) <= tol and len(pts) > 2:
        raise ValueError("the reference lines form a closed loop")
    return pts


def locate_on_polyline(points, p, tol):
    """(segment index, distance from the start along the polyline) of
    the point of the polyline nearest p, when within tol in plan; None."""
    best = None
    run = 0.0
    for i in range(len(points) - 1):
        a, b = points[i], points[i + 1]
        seg = _pdist(a, b)
        if seg < 1e-12:
            continue
        u = _unit2(vsub(b, a))
        t = max(0.0, min(seg, (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]))
        foot = (a[0] + u[0] * t, a[1] + u[1] * t)
        gap = math.hypot(p[0] - foot[0], p[1] - foot[1])
        if gap <= tol and (best is None or gap < best[0]):
            best = (gap, i, run + t)
        run += seg
    return None if best is None else (best[1], best[2])


def point_at(points, seg_index, along):
    """Point on segment seg_index at total distance `along` from the start."""
    run = 0.0
    for i in range(seg_index):
        run += _pdist(points[i], points[i + 1])
    a, b = points[seg_index], points[seg_index + 1]
    u = _unit2(vsub(b, a))
    t = along - run
    return (a[0] + u[0] * t, a[1] + u[1] * t, a[2])


def offset_polyline(points, d):
    """Plan offset of a polyline by d (positive = left of travel), mitred
    at the corners; z is kept from the original points."""
    if len(points) < 2:
        return list(points)
    normals = []
    for a, b in zip(points, points[1:]):
        u = _unit2(vsub(b, a))
        normals.append((-u[1], u[0]))
    out = [(points[0][0] + normals[0][0] * d, points[0][1] + normals[0][1] * d, points[0][2])]
    for j in range(1, len(points) - 1):
        n0, n1 = normals[j - 1], normals[j]
        u0 = (n0[1], -n0[0])
        u1 = (n1[1], -n1[0])
        p = points[j]
        a0 = (p[0] + n0[0] * d, p[1] + n0[1] * d)
        a1 = (p[0] + n1[0] * d, p[1] + n1[1] * d)
        denom = _cross2(u0, u1)
        if abs(denom) < 1e-9:
            out.append((a1[0], a1[1], p[2]))
            continue
        t = _cross2((a1[0] - a0[0], a1[1] - a0[1]), u1) / denom
        out.append((a0[0] + u0[0] * t, a0[1] + u0[1] * t, p[2]))
    last = points[-1]
    out.append((last[0] + normals[-1][0] * d, last[1] + normals[-1][1] * d, last[2]))
    return out


def lane_path(points, seg_index, along, d):
    """Lane from a branch's touch point back to the start of the trunk,
    offset d. Returns points ordered touch -> start."""
    touch = point_at(points, seg_index, along)
    sub = list(points[:seg_index + 1])
    if _pdist(sub[-1], touch) > 1e-9:
        sub.append(touch)
    if len(sub) < 2:
        return []
    return list(reversed(offset_polyline(sub, d)))


def branch_side(points, seg_index, touch, other, tol=1e-9):
    """+1 when `other` (the branch's far end) is left of the trunk's
    travel at the touch point, -1 right, 0 straight on."""
    u = _unit2(vsub(points[seg_index + 1], points[seg_index]))
    c = _cross2(u, (other[0] - touch[0], other[1] - touch[1]))
    if c > tol:
        return 1
    if c < -tol:
        return -1
    return 0


def assign_lanes(touches):
    """touches: [(distance along trunk, side +1/-1/0)].

    Returns [(side, lane)] in the same order. Branches with no side go to
    the side with fewer lanes. On each side the branch farthest from the
    start gets the inner lane (0), so lanes never cross the branches."""
    sides = [s for _d, s in touches]
    count = {1: sides.count(1), -1: sides.count(-1)}
    resolved = []
    for _d, s in touches:
        if s == 0:
            s = 1 if count[1] <= count[-1] else -1
            count[s] += 1
        resolved.append(s)
    lanes = [None] * len(touches)
    for side in (1, -1):
        idx = [i for i, s in enumerate(resolved) if s == side]
        idx.sort(key=lambda i: -touches[i][0])
        for lane, i in enumerate(idx):
            lanes[i] = lane
    return list(zip(resolved, lanes))


def lane_offset(side, lane, spacing):
    """Signed offset of a lane: half a spacing off the trunk centre, then
    one spacing per lane, so all lanes are `spacing` apart."""
    return side * (lane + 0.5) * spacing


def _seg_cross(a, b, c, d, tol):
    r = (b[0] - a[0], b[1] - a[1])
    s = (d[0] - c[0], d[1] - c[1])
    denom = _cross2(r, s)
    if abs(denom) < 1e-12:
        return False
    q = (c[0] - a[0], c[1] - a[1])
    t = _cross2(q, s) / denom
    u = _cross2(q, r) / denom
    lr, ls = math.hypot(*r), math.hypot(*s)
    et, eu = tol / lr, tol / ls
    return et < t < 1 - et and eu < u < 1 - eu


def count_crossings(segments, tol):
    """Number of pairs of segments that cross in plan (touching ends do
    not count)."""
    n = 0
    for i in range(len(segments)):
        for j in range(i + 1, len(segments)):
            if _seg_cross(segments[i][0], segments[i][1],
                          segments[j][0], segments[j][1], tol):
                n += 1
    return n


# --------------------------------------------------------------- joints

def split_at_touches(segments, tol):
    """Split segments where another segment's end touches their middle
    (a T in the drawing), so every joint is at segment ends."""
    ends = [p for s in segments for p in s]
    out = []
    for a, b in segments:
        length = _pdist(a, b)
        if length < 1e-12:
            continue
        u = _unit2(vsub(b, a))
        cuts = []
        for p in ends:
            t = (p[0] - a[0]) * u[0] + (p[1] - a[1]) * u[1]
            if tol < t < length - tol:
                gap = abs(_cross2(u, (p[0] - a[0], p[1] - a[1])))
                if gap <= tol and all(abs(t - c) > tol for c in cuts):
                    cuts.append(t)
        pts = [a] + [(a[0] + u[0] * t, a[1] + u[1] * t,
                      a[2] + (b[2] - a[2]) * t / length) for t in sorted(cuts)] + [b]
        out.extend(zip(pts, pts[1:]))
    return out


def joint_groups(segments, tol):
    """Ends that meet: [[(segment index, end 0/1), ...]] with 2+ ends."""
    groups = []
    for i, seg in enumerate(segments):
        for e in (0, 1):
            p = seg[e]
            for g in groups:
                q = segments[g[0][0]][g[0][1]]
                if _pdist(p, q) <= tol:
                    g.append((i, e))
                    break
            else:
                groups.append([(i, e)])
    return [g for g in groups if len(g) > 1]


def _out_dir(seg, end):
    """Plan direction pointing away from the joint along the segment."""
    a, b = (seg[0], seg[1]) if end == 0 else (seg[1], seg[0])
    return _unit2(vsub(b, a))


def _opposite(d1, d2, tol_deg=1.0):
    return d1[0] * d2[0] + d1[1] * d2[1] <= -math.cos(math.radians(tol_deg))


def merge_collinear(segments, tol):
    """Join straight-on continuations (two lines meeting in line, nothing
    else at that point) into one segment. Returns (segments, sources)
    where sources[k] lists the input indices behind output k."""
    parent = list(range(len(segments)))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i

    for g in joint_groups(segments, tol):
        if len(g) != 2:
            continue
        (i, ei), (j, ej) = g
        if _opposite(_out_dir(segments[i], ei), _out_dir(segments[j], ej)):
            parent[find(i)] = find(j)
    clusters = {}
    for i in range(len(segments)):
        clusters.setdefault(find(i), []).append(i)
    out, sources = [], []
    for members in sorted(clusters.values()):
        pts = [p for m in members for p in segments[m]]
        a0 = segments[members[0]][0]
        u = _unit2(vsub(segments[members[0]][1], a0))
        key = lambda p: (p[0] - a0[0]) * u[0] + (p[1] - a0[1]) * u[1]
        out.append((min(pts, key=key), max(pts, key=key)))
        sources.append(members)
    return out, sources


def classify_joint(segments, group):
    """("elbow", [a, b]) / ("tee", [run1, run2, branch]) /
    ("cross", [run1, run2, other1, other2]) / ("union", [a, b]) /
    (None, ends) for what can't take a standard fitting. Items are
    (segment index, end) from the group."""
    dirs = [_out_dir(segments[i], e) for i, e in group]
    n = len(group)
    pairs = [(a, b) for a in range(n) for b in range(a + 1, n)
             if _opposite(dirs[a], dirs[b])]
    if n == 2:
        return ("union" if pairs else "elbow"), list(group)
    if n == 3 and len(pairs) == 1:
        a, b = pairs[0]
        c = [k for k in range(3) if k not in (a, b)][0]
        return "tee", [group[a], group[b], group[c]]
    if n == 4 and len(pairs) == 2:
        (a, b), (c, d) = pairs
        return "cross", [group[a], group[b], group[c], group[d]]
    return None, list(group)


# ---------------------------------------------------- connect conduit

def continue_to(end, direction, target, tol):
    """Conduit legs from a free conduit end to a device point.

    Runs on along the conduit's own line to the spot nearest the target,
    steps across only if the target is off that line, then goes up or
    down to the target height. Raises ValueError if the device is behind
    the conduit end."""
    u = _unit2(direction)
    t = (target[0] - end[0]) * u[0] + (target[1] - end[1]) * u[1]
    if t < -tol:
        raise ValueError("the device is behind the conduit end")
    foot = (end[0] + u[0] * max(t, 0.0), end[1] + u[1] * max(t, 0.0), end[2])
    pts = [end]
    if _pdist(foot, end) > tol:
        pts.append(foot)
    if _pdist(foot, target) > tol:
        pts.append((target[0], target[1], end[2]))
    if abs(target[2] - end[2]) > tol:
        pts.append((target[0], target[1], target[2]))
    elif len(pts) > 1 and _pdist(pts[-1], target) > tol:
        pts.append(target)
    return pts


def drop_into_panel(end, direction, panel_center, top_z, tol):
    """Conduit legs into a panel: along the conduit's own line to above the
    middle of the panel, then straight down to the panel top - never
    sideways, so a bundle keeps its spacing."""
    u = _unit2(direction)
    t = (panel_center[0] - end[0]) * u[0] + (panel_center[1] - end[1]) * u[1]
    if t < -tol:
        raise ValueError("the panel is behind the conduit end")
    foot = (end[0] + u[0] * max(t, 0.0), end[1] + u[1] * max(t, 0.0), end[2])
    pts = [end]
    if _pdist(foot, end) > tol:
        pts.append(foot)
    if abs(top_z - end[2]) > tol:
        pts.append((foot[0], foot[1], top_z))
    return pts


def l_route(start, target, tol):
    """New conduit from an exit point: 90-degree legs at the exit height
    (longer direction first), then straight up/down onto the target."""
    dx, dy = target[0] - start[0], target[1] - start[1]
    pts = [start]
    if abs(dx) > tol and abs(dy) > tol:
        if abs(dx) >= abs(dy):
            pts.append((target[0], start[1], start[2]))
        else:
            pts.append((start[0], target[1], start[2]))
    above = (target[0], target[1], start[2])
    if _pdist(pts[-1], above) > tol:
        pts.append(above)
    if abs(target[2] - start[2]) > tol:
        pts.append(target)
    return pts


def unique_points(points, tol):
    out = []
    for p in points:
        if not out or vlen(vsub(p, out[-1])) > tol:
            out.append(p)
    return out
