import math

import pytest

from falcon_layout import (type_kind, pattern_kind, exit_directions,
                           nearest_segment_distance, best_rotation, pick_family,
                           rows_and_columns, gaps)


@pytest.mark.parametrize("name, kind", [
    ("Terminal (1-way)", "terminal"),
    ("Through (2-way 180)", "through"),
    ("Angle (2-way 90)", "angle"),
    ("Tee (3-way)", "tee"),
    ("Branch_Y", "y"),
    ("Cross (4-way)", "cross"),
    ("JB 2 Way", "through"),
    ("End Box", "terminal"),
    ("Standard", None),
])
def test_type_kind(name, kind):
    assert type_kind(name) == kind


def test_pattern_kind():
    E, W, N, S = (1, 0), (-1, 0), (0, 1), (0, -1)
    assert pattern_kind([E]) == "terminal"
    assert pattern_kind([E, W]) == "through"
    assert pattern_kind([E, N]) == "angle"
    assert pattern_kind([E, W, N]) == "tee"
    r = math.sqrt(0.5)
    assert pattern_kind([S, (r, r), (-r, r)]) == "y"
    assert pattern_kind([E, W, N, S]) == "cross"
    assert pattern_kind([]) is None


def test_exit_directions():
    rect = (-1, -1, 1, 1)
    through = [((-5, 0, 0), (5, 0, 0))]
    assert sorted(exit_directions((0, 0, 0), rect, through)) == [(-1.0, 0.0), (1.0, 0.0)]
    ending_inside = [((0, 0, 0), (0, 5, 0)), ((0.5, 0, 0), (6, 0, 0))]
    assert sorted(exit_directions((0, 0, 0), rect, ending_inside)) == [(0.0, 1.0), (1.0, 0.0)]
    assert exit_directions((0, 0, 0), rect, [((3, 3, 0), (6, 3, 0))]) == []
    # two lines leaving the same way count once
    twice = [((0, 0, 0), (5, 0, 0)), ((0, 0.1, 0), (5, 0.1, 0))]
    assert exit_directions((0, 0, 0), rect, twice) == [(1.0, 0.0)]


def test_nearest_segment_distance():
    assert nearest_segment_distance((0, 0, 0), [((2, -1, 0), (2, 1, 0))]) == pytest.approx(2)
    assert nearest_segment_distance((0, 0, 0), []) is None


def test_best_rotation():
    # angle box with outlets east + north; route goes north + west -> turn 90
    assert best_rotation([(1, 0), (0, 1)], [(0, 1), (-1, 0)]) == pytest.approx(math.pi / 2)
    assert best_rotation([(1, 0), (-1, 0)], [(-1, 0), (1, 0)]) == pytest.approx(0)
    assert best_rotation([], [(1, 0)]) == 0.0


def test_pick_family():
    fams = {"A": {"through", "tee"}, "B": {"terminal", "through", "angle", "tee"}}
    assert pick_family(fams, ["terminal", "angle"]) == "B"
    assert pick_family({}, ["tee"]) is None


def test_rows_and_columns():
    pts = [(0, 0, 0), (2.4, 0.02, 0), (4.2, 0, 0), (4.2, 1.8, 0), (9, 9, 0)]
    rows, cols, singles = rows_and_columns(pts, 0.1)
    assert rows == [[0, 1, 2]]
    assert cols == [[2, 3]]
    assert singles == 5     # rows at y=1.8 and 9; columns at x=0, 2.4 and 9
    assert gaps([0, 2.4, 4.2]) == pytest.approx([2.4, 1.8])
