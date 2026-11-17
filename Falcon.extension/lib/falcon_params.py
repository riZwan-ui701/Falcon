# ============================================================
# Shared Library
# ============================================================
# Module Name    : falcon_params
# Purpose        : Revit-free rules for the Add Param tool - data types,
#                  palette groups, name checks, value parsing and which
#                  families get an instance or a type parameter.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7 / CPython 3 (no Revit imports)
# ============================================================
"""Pure helpers for Add Param, unit-tested offline (tests/)."""

import math

MM_PER_FT = 304.8
SQM_PER_SQFT = 0.09290304
CUM_PER_CUFT = 0.028316846592

# (label in the dialog, key). The Revit spec for each key is picked in
# the tool, because that API changed in Revit 2022.
DATA_TYPES = [
    (u"Text", "text"),
    (u"Integer", "integer"),
    (u"Number", "number"),
    (u"Length (mm)", "length"),
    (u"Area (m²)", "area"),
    (u"Volume (m³)", "volume"),
    (u"Angle (°)", "angle"),
    (u"Yes/No", "yesno"),
    (u"URL", "url"),
]

# (label, GroupTypeId member for Revit 2024+, BuiltInParameterGroup before)
GROUPS = [
    (u"Identity Data", "IdentityData", "PG_IDENTITY_DATA"),
    (u"Data", "Data", "PG_DATA"),
    (u"General", "General", "PG_GENERAL"),
    (u"Text", "Text", "PG_TEXT"),
    (u"Constraints", "Constraints", "PG_CONSTRAINTS"),
    (u"Dimensions", "Geometry", "PG_GEOMETRY"),
    (u"Electrical", "Electrical", "PG_ELECTRICAL"),
    (u"Electrical - Lighting", "ElectricalLighting", "PG_ELECTRICAL_LIGHTING"),
    (u"Electrical - Loads", "ElectricalLoads", "PG_ELECTRICAL_LOADS"),
    (u"Electrical - Circuiting", "ElectricalCircuiting", "PG_ELECTRICAL_CIRCUITING"),
    (u"Mechanical", "Mechanical", "PG_MECHANICAL"),
    (u"Graphics", "Graphics", "PG_GRAPHICS"),
    (u"Materials and Finishes", "Materials", "PG_MATERIALS"),
    (u"Other", None, "INVALID"),
]

BAD_NAME_CHARS = u"\\:{}[]|;<>?`~"
YES = ("yes", "y", "true", "1", "on")
NO = ("no", "n", "false", "0", "off")


def name_error(name):
    """Why name can't be a shared parameter name, or None if it is fine."""
    name = (name or u"").strip()
    if not name:
        return u"Enter a parameter name."
    bad = sorted(set(ch for ch in name if ch in BAD_NAME_CHARS))
    if bad:
        return u"The name can't contain: " + u" ".join(bad)
    return None


def parse_value(kind, text):
    """Turn the typed value into (storage, value) in Revit internal units.

    storage is "string", "integer" or "double". Empty text -> None.
    Length is typed in mm, area in m2, volume in m3, angle in degrees.
    Raises ValueError with a message the user can read."""
    if text is None or not text.strip():
        return None
    text = text.strip()
    if kind in ("text", "url"):
        return ("string", text)
    bad = ValueError(u"'{}' is not a valid value for this data type.".format(text))
    if kind == "yesno":
        low = text.lower()
        if low in YES:
            return ("integer", 1)
        if low in NO:
            return ("integer", 0)
        raise bad
    try:
        if kind == "integer":
            return ("integer", int(text))
        value = float(text.replace(",", "."))
    except ValueError:
        raise bad
    if kind == "length":
        return ("double", value / MM_PER_FT)
    if kind == "area":
        return ("double", value / SQM_PER_SQFT)
    if kind == "volume":
        return ("double", value / CUM_PER_CUFT)
    if kind == "angle":
        return ("double", math.radians(value))
    return ("double", value)


def plan_jobs(ticked_families, ticked_types, family_of_type):
    """Which families to edit and how.

    A ticked family gets an instance parameter. A ticked type whose family
    is not ticked makes that family get a type parameter. Returns
    {family_key: {"instance": bool, "types": [type_key]}}; "types" are the
    ticked types of that family (the optional value goes on those)."""
    jobs = {}
    for fam in ticked_families:
        jobs[fam] = {"instance": True, "types": []}
    for typ in ticked_types:
        job = jobs.setdefault(family_of_type[typ], {"instance": False, "types": []})
        job["types"].append(typ)
    return jobs


def matches(search, *texts):
    """Case-insensitive: every word of search appears in one of texts."""
    words = (search or u"").lower().split()
    hay = u" ".join(t or u"" for t in texts).lower()
    return all(w in hay for w in words)
