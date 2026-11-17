# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Auto Dimension
# Purpose        : Dimension lighting outlets in a plan: outlets that line
#                  up get one dimension chain through their centres, per
#                  row and per column.
# Author         : Rizwan Zahid
# Version        : 2.0.0
# Created Date   : 2026-11-12
# Updated Date   : 2026-11-17
# Status         : Production
#
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7
#
# Category       : BIM Automation
# Discipline     : Electrical
# Tool Type      : pyRevit Tool
#
# Input          : Linear dimension style (remembered); outlets (pick +
#                  Finish, pre-selection kept).
# Output         : Dimension chains to the outlets' centre references.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_layout.py, falcon_geom.py, falcon_view.py,
#     falcon_conduit.py, falcon_settings.py
#
# Features       :
#   - Rows and columns found automatically (100 mm alignment tolerance)
#   - Report: chains made, groups skipped, segment values, families with
#     no usable centre reference, dimension errors
#   - Shift+click: the conduit-to-grid tool (conduits.py) and settings
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Outlet dimension chains with a dimension style picker
# - The v1 conduit-to-grid tool moved to Shift+click (conduits.py)
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os
import traceback

from System.Collections.Generic import List

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_layout
import falcon_conduit
import falcon_view
import falcon_settings
from falcon_color import eid_int

TITLE = "Falcon - Auto Dimension"
SECTION = "falcon_autodimoutlets"
DEFAULTS = {"style_name": "", "show_all": False, "offset_mm": 450.0}
ALIGN_TOL_MM = 100.0
OUTLET_CATEGORIES = (
    DB.BuiltInCategory.OST_LightingFixtures,
    DB.BuiltInCategory.OST_LightingDevices,
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_CommunicationDevices,
    DB.BuiltInCategory.OST_DataDevices,
    DB.BuiltInCategory.OST_FireAlarmDevices,
    DB.BuiltInCategory.OST_SecurityDevices,
)

doc = revit.doc
uidoc = revit.uidoc


# ------------------------------------------------------------------ UI

def dimension_styles(show_all):
    out = []
    for dt in DB.FilteredElementCollector(doc).OfClass(DB.DimensionType):
        name = falcon_conduit.element_name(dt)
        if not name:
            continue
        if not show_all and dt.StyleType != DB.DimensionStyleType.Linear:
            continue
        out.append((name, dt))
    return sorted(out, key=lambda x: x[0])


class StyleDialog(forms.WPFWindow):
    def __init__(self, settings):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "DimStyle.xaml"))
        self.result = None
        self.styles = []
        self.wanted = settings["style_name"]
        self.show_all.IsChecked = settings["show_all"]
        self.fill()

    def fill(self):
        current = self.style.SelectedItem
        if current:
            self.wanted = current
        self.styles = dimension_styles(bool(self.show_all.IsChecked))
        names = [n for n, _t in self.styles]
        self.style.Items.Clear()
        for name in names:
            self.style.Items.Add(name)
        if names:
            self.style.SelectedIndex = names.index(self.wanted) if self.wanted in names else 0
        self.count.Text = u"{} styles".format(len(names))

    def show_all_changed(self, sender, args):
        self.fill()

    def ok_click(self, sender, args):
        if self.style.SelectedIndex < 0:
            return
        name, dim_type = self.styles[self.style.SelectedIndex]
        self.result = {"style_name": name, "type": dim_type,
                       "show_all": bool(self.show_all.IsChecked)}
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


class OutletFilter(ISelectionFilter):
    CATS = set(int(c) for c in OUTLET_CATEGORIES)

    def AllowElement(self, element):
        cat = element.Category
        return (isinstance(element, DB.FamilyInstance) and cat is not None
                and eid_int(cat.Id) in self.CATS)

    def AllowReference(self, reference, position):
        return False


def pick_outlets():
    flt = OutletFilter()
    pre = List[DB.Reference]()
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if flt.AllowElement(el):
            pre.Add(DB.Reference(el))
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, flt,
            "Select additional electrical outlets. Previous selections are kept; "
            "press Finish when done.", pre)
    except OperationCanceledException:
        return []
    return [doc.GetElement(r.ElementId) for r in refs]


# ------------------------------------------------------------ references

def center_reference(outlet, along):
    """The outlet's centre reference plane that cuts across a dimension
    running along `along` (DB.XYZ.BasisX / BasisY); None if it has none."""
    for ref_type, normal in (
            (DB.FamilyInstanceReferenceType.CenterLeftRight, outlet.HandOrientation),
            (DB.FamilyInstanceReferenceType.CenterFrontBack, outlet.FacingOrientation)):
        if abs(normal.DotProduct(along)) < 0.99:
            continue
        refs = outlet.GetReferences(ref_type)
        if refs is not None and refs.Count > 0:
            return refs[0]
    return None


# ----------------------------------------------------------------- main

def main():
    if doc is None:
        forms.alert("Please open a Revit project first.", title=TITLE)
        return
    view = doc.ActiveView
    if not falcon_view.is_plan(view):
        forms.alert("Open a plan view first.", title=TITLE)
        return
    settings = falcon_settings.load(SECTION, DEFAULTS)
    dialog = StyleDialog(settings)
    dialog.show_dialog()
    opts = dialog.result
    if opts is None:
        return
    falcon_settings.save(SECTION, {"style_name": opts["style_name"],
                                   "show_all": opts["show_all"]})

    outlets = [o for o in pick_outlets() if hasattr(o.Location, "Point")]
    if not outlets:
        return

    points = [(o.Location.Point.X, o.Location.Point.Y, 0.0) for o in outlets]
    rows, cols, singles = falcon_layout.rows_and_columns(
        points, falcon_geom.mm_to_ft(ALIGN_TOL_MM))
    offset = falcon_geom.mm_to_ft(settings["offset_mm"])
    z = falcon_view.plan_z(view)

    created, values, errors = 0, [], []
    missing = []
    skipped = singles
    with revit.Transaction("Falcon: Auto Dimension"):
        for label, groups, along, axis in (("Row", rows, DB.XYZ.BasisX, 0),
                                           ("Column", cols, DB.XYZ.BasisY, 1)):
            for number, group in enumerate(groups, 1):
                refs = DB.ReferenceArray()
                used = []
                for i in group:
                    ref = center_reference(outlets[i], along)
                    if ref is None:
                        name = outlets[i].Symbol.Family.Name
                        if name not in missing:
                            missing.append(name)
                        continue
                    refs.Append(ref)
                    used.append(i)
                if len(used) < 2:
                    skipped += 1
                    continue
                coords = [points[i][axis] for i in used]
                if axis == 0:
                    y = sum(points[i][1] for i in used) / len(used) + offset
                    line = DB.Line.CreateBound(DB.XYZ(min(coords), y, z),
                                               DB.XYZ(max(coords), y, z))
                else:
                    x = sum(points[i][0] for i in used) / len(used) + offset
                    line = DB.Line.CreateBound(DB.XYZ(x, min(coords), z),
                                               DB.XYZ(x, max(coords), z))
                try:
                    doc.Create.NewDimension(view, line, refs, opts["type"])
                except Exception as ex:
                    errors.append(u"{} {}: {}".format(label, number, ex))
                    continue
                created += 1
                values.append(u"{} {}: {}".format(label, number, u" / ".join(
                    u"{:.0f}".format(falcon_geom.ft_to_mm(g))
                    for g in falcon_layout.gaps(sorted(coords)))))

    lines = [u"Dimensions created: {}".format(created),
             u"Groups skipped: {}".format(skipped),
             u"Segment values (mm):"]
    lines.extend(values or [u"None"])
    lines.append(u"Families missing usable center references:")
    lines.append(u", ".join(missing) if missing else u"None")
    lines.append(u"Dimension errors:")
    lines.extend(errors or [u"None"])
    forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Auto Dimension stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
