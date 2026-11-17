import pytest

from falcon_route import (chain_polyline, locate_on_polyline, point_at,
                          offset_polyline, lane_path, branch_side, assign_lanes,
                          lane_offset, count_crossings, split_at_touches,
                          joint_groups, merge_collinear, classify_joint,
                          continue_to, drop_into_panel, l_route, unique_points)

TOL = 0.01


def approx_pts(pts):
    return [pytest.approx(p) for p in pts]


# ------------------------------------------------------------ polylines

def test_chain_polyline_any_order_and_direction():
    segs = [((10, 0, 0), (10, 5, 0)), ((0, 0, 0), (10, 0, 0)), ((10, 5, 0), (20, 5, 0))]
    pts = chain_polyline(segs, TOL)
    assert pts in ([(0, 0, 0), (10, 0, 0), (10, 5, 0), (20, 5, 0)],
                   [(20, 5, 0), (10, 5, 0), (10, 0, 0), (0, 0, 0)])


def test_chain_polyline_refuses_gaps_and_loops():
    pytest.raises(ValueError, chain_polyline, [((0, 0, 0), (1, 0, 0)), ((5, 0, 0), (6, 0, 0))], TOL)
    square = [((0, 0, 0), (1, 0, 0)), ((1, 0, 0), (1, 1, 0)),
              ((1, 1, 0), (0, 1, 0)), ((0, 1, 0), (0, 0, 0))]
    pytest.raises(ValueError, chain_polyline, square, TOL)


def test_locate_and_point_at():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    assert locate_on_polyline(pts, (10.005, 4, 0), TOL) == (1, pytest.approx(14))
    assert locate_on_polyline(pts, (5, 3, 0), TOL) is None
    assert point_at(pts, 1, 14) == pytest.approx((10, 4, 0))


def test_offset_polyline_mitres_corner():
    pts = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    left = offset_polyline(pts, 1)          # inside of a left turn
    assert left == approx_pts([(0, 1, 0), (9, 1, 0), (9, 10, 0)])
    right = offset_polyline(pts, -1)
    assert right == approx_pts([(0, -1, 0), (11, -1, 0), (11, 10, 0)])


def test_lane_path_runs_from_touch_back_to_start():
    trunk = [(0, 0, 0), (10, 0, 0), (10, 10, 0)]
    lane = lane_path(trunk, 1, 14, -0.5)
    assert lane == approx_pts([(10.5, 4, 0), (10.5, -0.5, 0), (0, -0.5, 0)])


def test_branch_side():
    trunk = [(0, 0, 0), (10, 0, 0)]
    assert branch_side(trunk, 0, (5, 0, 0), (5, 3, 0)) == 1
    assert branch_side(trunk, 0, (5, 0, 0), (5, -3, 0)) == -1
    assert branch_side(trunk, 0, (10, 0, 0), (12, 0, 0)) == 0


def test_assign_lanes_far_branch_gets_inner_lane():
    # three branches on the left at 2, 8, 5; one on the right; one straight on
    touches = [(2, 1), (8, 1), (5, 1), (6, -1), (10, 0)]
    out = assign_lanes(touches)
    assert out[1] == (1, 0) and out[2] == (1, 1) and out[0] == (1, 2)
    assert out[4][0] == -1            # straight-on joins the emptier side
    assert sorted(l for s, l in out if s == -1) == [0, 1]
    assert out[4] == (-1, 0)          # farthest on that side -> inner


def test_lane_offset_spacing():
    assert lane_offset(1, 0, 50) == 25
    assert lane_offset(-1, 2, 50) == -125


def test_left_side_lanes_do_not_cross_branches():
    trunk = [(0, 0, 0), (100, 0, 0)]
    branches = [((20, 50, 0), (20, 0, 0)), ((60, 50, 0), (60, 0, 0)), ((40, 50, 0), (40, 0, 0))]
    touches = [(b[1][0], 1) for b in branches]
    segs = []
    for (side, lane), b in zip(assign_lanes(touches), branches):
        path = lane_path(trunk, 0, b[1][0], lane_offset(side, lane, 2))
        segs.append((b[0], path[0]))
        segs.extend(zip(path, path[1:]))
    assert count_crossings(segs, TOL) == 0


def test_count_crossings_ignores_touching_ends():
    segs = [((0, 0, 0), (10, 0, 0)), ((5, -5, 0), (5, 5, 0)), ((10, 0, 0), (10, 5, 0))]
    assert count_crossings(segs, TOL) == 1


# --------------------------------------------------------------- joints

def test_split_at_touches_makes_tee():
    segs = [((0, 0, 0), (10, 0, 0)), ((5, 0, 0), (5, 5, 0))]
    out = split_at_touches(segs, TOL)
    assert len(out) == 3
    groups = joint_groups(out, TOL)
    assert len(groups) == 1 and len(groups[0]) == 3


def test_merge_collinear_joins_straight_runs_only():
    segs = [((0, 0, 0), (5, 0, 0)), ((5, 0, 0), (10, 0, 0)), ((10, 0, 0), (10, 5, 0))]
    merged, sources = merge_collinear(segs, TOL)
    assert len(merged) == 2
    assert sorted(len(s) for s in sources) == [1, 2]
    long_seg = merged[[len(s) for s in sources].index(2)]
    assert sorted(long_seg) == [(0, 0, 0), (10, 0, 0)]


def test_merge_does_not_join_through_a_tee():
    segs = split_at_touches([((0, 0, 0), (10, 0, 0)), ((5, 0, 0), (5, 5, 0))], TOL)
    merged, _src = merge_collinear(segs, TOL)
    assert len(merged) == 3


def test_classify_joint():
    elbow = [((0, 0, 0), (5, 0, 0)), ((5, 0, 0), (5, 5, 0))]
    assert classify_joint(elbow, joint_groups(elbow, TOL)[0])[0] == "elbow"
    tee = split_at_touches([((0, 0, 0), (10, 0, 0)), ((5, 0, 0), (5, 5, 0))], TOL)
    kind, order = classify_joint(tee, joint_groups(tee, TOL)[0])
    assert kind == "tee"
    branch = tee[order[2][0]]
    assert (5, 5, 0) in branch
    cross = split_at_touches([((0, 0, 0), (10, 0, 0)), ((5, -5, 0), (5, 5, 0))], TOL)
    # a crossing (no end on the other) stays two lines - no joint
    assert joint_groups(cross, TOL) == []
    four = [((0, 0, 0), (5, 0, 0)), ((10, 0, 0), (5, 0, 0)),
            ((5, 5, 0), (5, 0, 0)), ((5, -5, 0), (5, 0, 0))]
    assert classify_joint(four, joint_groups(four, TOL)[0])[0] == "cross"


# ---------------------------------------------------- connect conduit

def test_continue_to_runs_along_then_drops():
    pts = continue_to((0, 0, 10), (1, 0, 0), (8, 0, 4), TOL)
    assert pts == approx_pts([(0, 0, 10), (8, 0, 10), (8, 0, 4)])


def test_continue_to_steps_across_when_off_line():
    pts = continue_to((0, 0, 10), (1, 0, 0), (8, 2, 4), TOL)
    assert pts == approx_pts([(0, 0, 10), (8, 0, 10), (8, 2, 10), (8, 2, 4)])


def test_continue_to_refuses_device_behind():
    pytest.raises(ValueError, continue_to, (0, 0, 10), (1, 0, 0), (-5, 0, 4), TOL)


def test_drop_into_panel_never_moves_sideways():
    pts = drop_into_panel((0, 3, 10), (1, 0, 0), (6, 0, 0), 2.0, TOL)
    assert pts == approx_pts([(0, 3, 10), (6, 3, 10), (6, 3, 2.0)])


def test_l_route_longer_leg_first_then_drop():
    pts = l_route((0, 0, 10), (10, 3, 2), TOL)
    assert pts == approx_pts([(0, 0, 10), (10, 0, 10), (10, 3, 10), (10, 3, 2)])


def test_unique_points():
    assert unique_points([(0, 0, 0), (0, 0, 0.001), (1, 0, 0)], TOL) == [(0, 0, 0), (1, 0, 0)]
