# ============================================================
# Shared Library
# ============================================================
# Module Name    : falcon_safety
# Purpose        : Pre-write safety checks shared by every Falcon tool -
#                  project-document guard and worksharing editability.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7 / CPython 3
#
# Notes          :
#   - Never forces a checkout: an element another user owns is skipped
#     and reported, so the tool keeps going.
#   - In a non-workshared model every element is editable - no change in
#     behaviour there.
# ============================================================
"""Guards to run before a Falcon tool changes the model."""

from pyrevit import DB, forms


def project_only(doc, title):
    """True when doc is an open project. In the Family Editor (or with no
    document) tell the user what to do and return False."""
    if doc is None:
        forms.alert("Open a Revit project first, then run the tool again.", title=title)
        return False
    if doc.IsFamilyDocument:
        forms.alert("This tool works in a project, not in the Family Editor. "
                    "Open the project and run it again.", title=title)
        return False
    return True


def owner_note(doc, element):
    """Why element can't be edited in a workshared model, or None if it
    can. Never forces a checkout."""
    if element is None or not doc.IsWorkshared:
        return None
    try:
        status = DB.WorksharingUtils.GetCheckoutStatus(doc, element.Id)
    except Exception:
        return None
    if status == DB.CheckoutStatus.OwnedByOtherUser:
        try:
            who = DB.WorksharingUtils.GetWorksharingTooltipInfo(doc, element.Id).Owner
        except Exception:
            who = "another user"
        return "it is borrowed by {} - ask them to sync, then run again".format(who)
    return None


def split_editable(doc, elements):
    """(editable elements, [skip reason strings]) - elements another user
    owns are skipped with a reason."""
    keep, skipped = [], []
    for el in elements:
        note = owner_note(doc, el)
        if note:
            skipped.append(u"{}: {}".format(el.Id, note))
        else:
            keep.append(el)
    return keep, skipped
