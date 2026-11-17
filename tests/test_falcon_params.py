import math

import pytest

from falcon_params import (DATA_TYPES, GROUPS, name_error, parse_value,
                           plan_jobs, matches)


def test_lists_have_unique_labels():
    assert len(set(l for l, _k in DATA_TYPES)) == len(DATA_TYPES)
    assert len(set(g[0] for g in GROUPS)) == len(GROUPS)
    assert GROUPS[0][0] == "Identity Data"   # the dialog default


def test_name_error():
    assert name_error("Vendor") is None
    assert name_error("  ") == "Enter a parameter name."
    assert "[" in name_error("Vendor [x]")


@pytest.mark.parametrize("kind, text, expected", [
    ("text", " Philips ", ("string", "Philips")),
    ("url", "https://x.y", ("string", "https://x.y")),
    ("integer", "12", ("integer", 12)),
    ("yesno", "Yes", ("integer", 1)),
    ("yesno", "0", ("integer", 0)),
    ("number", "2,5", ("double", 2.5)),
    ("length", "304.8", ("double", 1.0)),
])
def test_parse_value(kind, text, expected):
    storage, value = parse_value(kind, text)
    assert storage == expected[0]
    assert value == pytest.approx(expected[1])


def test_parse_value_units():
    assert parse_value("area", "0.09290304")[1] == pytest.approx(1.0)
    assert parse_value("volume", "0.028316846592")[1] == pytest.approx(1.0)
    assert parse_value("angle", "90")[1] == pytest.approx(math.pi / 2)


def test_parse_value_empty_and_bad():
    assert parse_value("integer", "  ") is None
    pytest.raises(ValueError, parse_value, "integer", "1.5")
    pytest.raises(ValueError, parse_value, "yesno", "maybe")
    pytest.raises(ValueError, parse_value, "length", "abc")


def test_plan_jobs_family_tick_is_instance_type_tick_is_type():
    family_of = {"t1": "F1", "t2": "F1", "t3": "F2"}
    jobs = plan_jobs(["F1"], ["t2", "t3"], family_of)
    assert jobs == {
        "F1": {"instance": True, "types": ["t2"]},
        "F2": {"instance": False, "types": ["t3"]},
    }


def test_matches():
    assert matches("eurs lux", "Lighting Fixtures", "EURS63_LF_FB_LuxSpace")
    assert not matches("eurs power", "EURS63_LF_FB_LuxSpace")
    assert matches("", "anything")
