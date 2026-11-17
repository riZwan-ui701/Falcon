import pytest

import falcon_wiring
from falcon_wiring import (order_run, order_ring, side_mid, hits, overlaps,
                           orthogonal_options, route_sides, route_points,
                           wall_ports, enter_leave, axis_of, phase_letter, lift,
                           arc_points, arc_between, chamfer_home_run, tag_spot,
                           arc_polyline, best_arc, estimate_tag_size)


def rect(cx, cy, half=0.5):
    return (cx - half, cy - half, cx + half, cy + half)


def is_orthogonal(path):
    return all(abs(a[0] - b[0]) < 1e-9 or abs(a[1] - b[1]) < 1e-9
               for a, b in zip(path, path[1:]))


# ------------------------------------------------------------ run order

def test_order_run_row_from_first():
    pts = [(0, 0), (3, 0), (1, 0), (2, 0)]
    assert order_run(pts, 0) == [0, 2, 3, 1]


def test_order_run_respects_last():
    pts = [(0, 0), (1, 0), (2, 0), (0, 1), (1, 1), (2, 1)]
    order = order_run(pts, 0, last=3)
    assert order[0] == 0 and order[-1] == 3 and sorted(order) == list(range(6))
    # a sensible U: along the bottom row, up, back along the top row
    assert order == [0, 1, 2, 5, 4, 3]


def test_order_run_two_opt_untangles():
    # nearest neighbour alone zig-zags here; 2-opt fixes it
    pts = [(0, 0), (10, 0), (1, 5), (9, 5), (5, 0), (5, 5)]
    order = order_run(pts, 0)
    length = sum(abs(pts[a][0] - pts[b][0]) + abs(pts[a][1] - pts[b][1])
                 for a, b in zip(order, order[1:]))
    assert length <= 25


# ------------------------------------------------------------ outlines

def test_side_mid():
    r = (0, 0, 2, 4)
    assert side_mid(r, "E") == (2, 2) and side_mid(r, "S") == (1, 0)


def test_hits_ignores_touching_sides():
    r = (0, 0, 1, 1)
    assert hits([(-1, 0.5), (2, 0.5)], [r]) == 1
    assert hits([(-1, 1), (2, 1)], [r]) == 0      # runs along the edge


def test_orthogonal_options():
    assert orthogonal_options((0, 0), (5, 0)) == [[(0, 0), (5, 0)]]
    assert len(orthogonal_options((0, 0), (5, 3))) == 4


def test_route_sides_straight_between_neighbours():
    path, sa, sb = route_sides(rect(0, 0), rect(3, 0), [])
    assert (sa, sb) == ("E", "W")
    assert path == [(0.5, 0), (2.5, 0)]


def test_route_sides_goes_around_a_fixture_in_between():
    # A and B in a row with C between them: the line must not cross C
    path, _sa, _sb = route_sides(rect(0, 0), rect(6, 0), [rect(3, 0)])
    assert hits(path, [rect(3, 0)]) == 0
    assert is_orthogonal(path)


def test_route_sides_one_line_in_one_line_out():
    # the line came into A on its west side: it must leave from another side
    path, sa, _sb = route_sides(rect(0, 0), rect(-3, 0), [], used_a="W")
    assert sa != "W"
    assert hits(path, [rect(0, 0), rect(-3, 0)]) == 0


def test_route_sides_offset_fixtures_are_orthogonal():
    path, sa, sb = route_sides(rect(0, 0), rect(4, 3), [])
    assert is_orthogonal(path)
    assert path[0] == side_mid(rect(0, 0), sa)
    assert path[-1] == side_mid(rect(4, 3), sb)


def test_route_points_prefers_first_axis_and_avoids():
    path = route_points((0, 0), (4, 3), [], first_axis="y")
    assert path[1] == (0, 3)
    blocked = route_points((0, 0), (4, 3), [(1, -1, 3, 1)])
    assert hits(blocked, [(1, -1, 3, 1)]) == 0


# ---------------------------------------------------------- wall outlets

def test_wall_ports_modes():
    a, b = wall_ports((0, 0), (1, 0), (0, 1), 0.2, "outlet", front=0.1)
    assert a == pytest.approx((0.2, 0.1)) and b == pytest.approx((-0.2, 0.1))
    a, b = wall_ports((0, 0), (1, 0), (0, 1), 0.2, "backbox", front=0.1)
    assert a == pytest.approx((0.2, 0.0))


def test_enter_leave_uses_the_near_port_first():
    ports = ((1, 0), (-1, 0))
    assert enter_leave(ports, (5, 0)) == ((1, 0), (-1, 0))
    assert enter_leave(ports, (-5, 0)) == ((-1, 0), (1, 0))
    assert enter_leave(ports, None) == ports


def test_axis_of():
    assert axis_of((0.9, 0.1)) == "x" and axis_of((0, -1)) == "y"


# ------------------------------------------------------------------ misc

@pytest.mark.parametrize("number, letter", [
    ("R4", "R"), ("Y12", "Y"), ("b3", "B"), ("12", "R"), ("L1", "R"), ("", "R"),
])
def test_phase_letter(number, letter):
    assert phase_letter(number) == letter


def test_order_ring_both_ways():
    # 2 x 4 ring like the user's room: top row y=1, bottom row y=0
    pts = [(0, 1), (1, 1), (2, 1), (3, 1), (0, 0), (1, 0), (2, 0), (3, 0)]
    cw = order_ring(pts, 0, clockwise=True)
    ccw = order_ring(pts, 0, clockwise=False)
    assert cw == [0, 1, 2, 3, 7, 6, 5, 4]
    assert ccw == [0, 4, 5, 6, 7, 3, 2, 1]


def test_overlaps_counts_running_along_not_crossing():
    drawn = [((0, 0), (10, 0))]
    assert overlaps([(2, 0), (5, 0)], drawn) == 1
    assert overlaps([(5, -3), (5, 3)], drawn) == 0
    assert overlaps([(10, 0), (12, 0)], drawn) == 0   # touching end only


def test_route_sides_avoids_lines_already_drawn():
    a, b = rect(0, 0), rect(4, 0)
    drawn = [((0.5, 0), (3.5, 0))]                     # straight E-W already used
    path, _sa, _sb = route_sides(a, b, [], drawn=drawn)
    assert overlaps(path, drawn) == 0


def test_user_layout_routes_are_clean():
    # the user's screenshot: 2 rows of 4 fixtures, run clockwise
    H = 26
    centres = [(x, -139) for x in (246, 455, 713, 921)] + \
              [(x, -346) for x in (246, 455, 713, 921)]
    rects = [(cx - H, cy - H, cx + H, cy + H) for cx, cy in centres]
    order = order_ring(centres, 0, clockwise=True)
    drawn, entered = [], {}
    for a, b in zip(order, order[1:]):
        others = [rects[k] for k in order if k not in (a, b)]
        path, _sa, sb = route_sides(rects[a], rects[b], others,
                                    used_a=entered.get(a), drawn=drawn)
        entered[b] = sb
        assert hits(path, others) == 0
        assert overlaps(path, drawn) == 0
        assert is_orthogonal(path)
        drawn.extend(zip(path, path[1:]))


def test_arc_between_bulges_away_from_centre():
    pts = arc_between((0, 0), (4, 0), away_from=(2, 5))
    assert pts[1][1] < 0          # centre is above, so the arc bows down
    pts = arc_between((0, 0), (4, 0), away_from=(2, -5))
    assert pts[1][1] > 0


def test_chamfer_home_run_square_corners():
    pts = chamfer_home_run((0, 0), (-10, 2), 1.0)
    assert len(pts) == 3 and is_orthogonal(pts)
    assert pts[1][0] < 0 and pts[2][1] > 0


def test_tag_spot_clear_past_the_arrow_tip():
    # arrow pointing left: tag centre sits left of the tip by gap + half width
    spot = tag_spot((0, 0), (-1, 0), width=4, height=1, gap=0.5)
    assert spot == pytest.approx((-3.5, 0))
    # pointing down: clear by gap + half height
    spot = tag_spot((0, 0), (0, -1), width=4, height=1, gap=0.5)
    assert spot == pytest.approx((0, -2))


def test_tag_spot_slanted_arrow_stays_close():
    # the screenshot: arrow pointing up-left, wide one-line tag. The tag
    # must not cover the tip, yet its nearest edge stays within the gap.
    w, h, gap = 10.0, 1.4, 0.2
    tip = (0.0, 0.0)
    cx, cy = tag_spot((3, -3), tip, w, h, gap)
    inside = abs(tip[0] - cx) <= w / 2 and abs(tip[1] - cy) <= h / 2
    assert not inside
    # distance from the tip to the box edge
    ex = max(abs(tip[0] - cx) - w / 2, 0.0)
    ey = max(abs(tip[1] - cy) - h / 2, 0.0)
    assert (ex * ex + ey * ey) ** 0.5 <= gap + 1e-9
    # and far closer than the old placement (centre about 4.5 away)
    assert ((cx - tip[0]) ** 2 + (cy - tip[1]) ** 2) ** 0.5 < 1.5


USER_ROOM = [(x, -139) for x in (318, 475, 672, 829)] + \
            [(x, -339) for x in (318, 475, 672, 829)]


def user_rects(h=20):
    return [(cx - h, cy - h, cx + h, cy + h) for cx, cy in USER_ROOM]


def test_order_run_never_jumps_over_a_fixture():
    # the screenshot: shortest order went T2 -> T1 -> T3, jumping over T2
    rects = user_rects()
    for first in range(8):
        order = order_run(USER_ROOM, first, rects=rects)
        for a, b in zip(order, order[1:]):
            others = [r for k, r in enumerate(rects) if k not in (a, b)]
            assert not any(falcon_wiring._crosses_rect(USER_ROOM[a], USER_ROOM[b], r)
                           for r in others), (first, order)


def test_best_arc_misses_fixtures_and_earlier_arcs():
    rects = user_rects()
    mid = (573, -239)
    order = order_run(USER_ROOM, 4, rects=rects)          # start bottom-left
    drawn = []
    for a, b in zip(order, order[1:]):
        others = [r for k, r in enumerate(rects) if k not in (a, b)]
        pts, poly = best_arc(USER_ROOM[a], USER_ROOM[b], mid, others, drawn, tol=8)
        assert not any(falcon_wiring._crosses_rect(p, q, r)
                       for r in others for p, q in zip(poly, poly[1:]))
        drawn.append(poly)


def test_arc_polyline_passes_through_mid():
    poly = arc_polyline((0, 0), (5, 2), (10, 0))
    assert poly[0] == pytest.approx((0, 0)) and poly[-1] == pytest.approx((10, 0))
    assert max(p[1] for p in poly) == pytest.approx(2, abs=0.1)


def test_tag_size_estimate():
    w, h = estimate_tag_size(u"DB-GF-02/R2", 50)
    assert w > h > 0 and w == pytest.approx(len("DB-GF-02/R2") * h * 0.85, rel=0.01)


def test_nearest_to_panel():
    from falcon_wiring import nearest_to
    assert nearest_to(USER_ROOM, (100, -400)) == 4      # bottom-left is nearest the DB


def test_phase_colors_red_goldenrod_blue():
    from falcon_wiring import PHASE_RGB
    assert PHASE_RGB == {"R": (255, 0, 0), "Y": (184, 134, 11), "B": (0, 0, 255)}


def test_circuit_phase_from_number_then_load_then_default():
    from falcon_wiring import circuit_phase
    assert circuit_phase("Y2", (0, 0, 120), "R") == ("Y", "number")   # number wins
    assert circuit_phase("2", (0, 0, 120), "R") == ("B", "load")      # phase C
    assert circuit_phase("2", (0, 80, 0), "R") == ("Y", "load")       # phase B
    assert circuit_phase("L2", (90, 0, 0), "Y") == ("R", "load")      # phase A
    assert circuit_phase("2", (0, 0, 0), "Y") == ("Y", "default")     # no load
    assert circuit_phase("2", (50, 50, 0), "B") == ("B", "default")   # 2-pole
    assert circuit_phase("2", None, "R") == ("R", "default")


def test_next_switch_id():
    from falcon_wiring import next_switch_id
    assert next_switch_id([]) == "a"
    assert next_switch_id(["a", "B", " c ", ""]) == "d"
    used = [chr(c) for c in range(ord("a"), ord("z") + 1)]
    assert next_switch_id(used) == "aa"
    assert next_switch_id(used + ["aa"]) == "ab"


def test_lift_and_arc():
    assert lift([(1, 2)], 5) == [(1, 2, 5)]
    pts = arc_points((0, 0), (10, 0), 2.0)
    assert pts[0] == (0, 0) and pts[-1] == pytest.approx((2, 0))
    assert pts[1][1] != 0
