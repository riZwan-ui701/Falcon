import pytest

from falcon_geom import (outlets_from_name, box_capacity, pick_bigger_type,
                         nearest_index, best_outlet, flex_points)


@pytest.mark.parametrize("name, count", [
    ("Tee (3-way)", 3),
    ("Cross", 4),
    ("Through", 2),
    ("2 Way", 2),
    ("JB_4-WAY", 4),
    ("Two Way", 2),
    ("JBCross 20mm", 4),
    ("End", 1),
    ("Thru 25mm", 2),
    ("3way", 3),
    ("Standard", None),
    ("Pendant 20mm", None),   # 'end' inside a word is not 'End'
    ("20mm", None),
    ("", None),
    (None, None),
])
def test_outlets_from_name(name, count):
    assert outlets_from_name(name) == count


def test_number_way_beats_word():
    assert outlets_from_name("Tee 4-way") == 4


def test_box_capacity_capped_by_name():
    assert box_capacity(4, "Tee (3-way)") == 3
    assert box_capacity(4, "Box A") == 4
    assert box_capacity(2, "Cross") == 2   # can't have more than its connectors


def test_pick_bigger_type_steps_one_at_a_time():
    types = [("through", 2), ("tee", 3), ("cross", 4)]
    assert pick_bigger_type(3, types) == "tee"
    assert pick_bigger_type(4, types) == "cross"
    assert pick_bigger_type(5, types) is None


def test_pick_bigger_type_first_wins_a_tie():
    assert pick_bigger_type(3, [("same_family", 3), ("other_family", 3)]) == "same_family"


def test_nearest_index_in_plan():
    box = (0, 0, 10)
    fixtures = [(5, 0, 8), (1, 1, 0), (0, 3, 9)]
    assert nearest_index(box, fixtures) == 1
    assert nearest_index(box, []) is None


def test_best_outlet_points_to_target():
    dirs = [(1, 0, 0), (-1, 0, 0), (0, -1, 0)]
    assert best_outlet(dirs, (0, -5, -3)) == 2
    assert best_outlet(dirs, (4, 0, -3)) == 0


def test_best_outlet_prefers_down_on_tie():
    dirs = [(1, 0, 0), (0, 0, -1)]
    assert best_outlet(dirs, (0, 0, 0)) == 1


def test_flex_points_leave_outlet_then_drop():
    pts, t0, t1 = flex_points((0, 0, 10), (1, 0, 0), (3, 0, 2), 1.0)
    assert pts[0] == (0, 0, 10)
    assert pts[1] == pytest.approx((1, 0, 10))
    assert pts[2] == pytest.approx((3, 0, 3))
    assert pts[-1] == (3, 0, 2)
    assert t0 == pytest.approx((1, 0, 0))
    assert t1 == (0.0, 0.0, -1.0)


def test_flex_points_straight_drop_never_goes_back_up():
    pts, _t0, _t1 = flex_points((0, 0, 10), (0, 0, -1), (0, 0, 8.6), 1.0)
    zs = [p[2] for p in pts]
    assert zs == sorted(zs, reverse=True)
    assert pts[-1] == (0, 0, 8.6)


def test_flex_points_short_drop_does_not_overshoot():
    pts, _t0, _t1 = flex_points((0, 0, 10), (0, 0, -1), (0, 0, 9.7), 1.0)
    assert min(p[2] for p in pts) == pytest.approx(9.7)
