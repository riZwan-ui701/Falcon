import pytest

from falcon_wiring import (order_run, side_mid, hits, orthogonal_options,
                           route_sides, route_points, wall_ports, enter_leave,
                           axis_of, phase_letter, lift, arc_points)


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


def test_lift_and_arc():
    assert lift([(1, 2)], 5) == [(1, 2, 5)]
    pts = arc_points((0, 0), (10, 0), 2.0)
    assert pts[0] == (0, 0) and pts[-1] == pytest.approx((2, 0))
    assert pts[1][1] != 0
