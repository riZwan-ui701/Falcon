# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Junction Box
# Purpose        : Place (or update) a junction box at every selected
#                  fixture. The routing lines that run into the fixture
#                  decide the box type (Terminal / Through / Angle / Tee /
#                  Branch_Y / Cross) and its rotation; the box goes at the
#                  elevation you type.
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
# Input          : Elevation (mm above the plan's level, remembered);
#                  fixtures (pick + Finish, pre-selection kept).
# Output         : Junction boxes at the fixtures' insertion points, typed
#                  and turned to match the routing lines.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_layout.py, falcon_conduit.py,
#     falcon_geom.py, falcon_settings.py
#
# Features       :
#   - Routing lines = detail/model lines, wires and CAD lines in the view
#   - Box family chosen automatically (the one covering most needed types)
#   - A box already at a fixture is updated (type, turn, elevation)
#   - Skipped fixtures listed with the reason; one undo step
#   - Shift+click: the original click-on-conduit Junction Box
#
# Notes          :
#   - Designed for production BIM workflows.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#   - Project only: exits with a message in the Family Editor.
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Places boxes at fixtures from the routing lines (type + rotation)
# - The v1 click-on-conduit tool moved to Shift+click (on_conduit.py)
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import math
import os
import traceback

from System.Collections.Generic import List

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.DB.Electrical import Wire
from Autodesk.Revit.DB.Structure import StructuralType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_layout
import falcon_conduit
import falcon_settings
import falcon_safety
from falcon_color import eid_int

TITLE = "Falcon - Junction Box"
SECTION = "falcon_junctionbox"
DEFAULTS = {"elevation_mm": 3700.0}
OUTLINE_PAD_MM = 10.0       # routing line counts if within this of the outline
SAME_SPOT_MM = 50.0         # an existing box this close (plan) is updated
ZOOM_PAD_MM = 2000.0
KIND_LABELS = {"terminal": "Terminal", "through": "Through", "angle": "Angle",
               "tee": "Tee", "y": "Branch_Y", "cross": "Cross"}
FIXTURE_CATEGORIES = (
    DB.BuiltInCategory.OST_LightingFixtures,
    DB.BuiltInCategory.OST_LightingDevices,
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_CommunicationDevices,
    DB.BuiltInCategory.OST_DataDevices,
    DB.BuiltInCategory.OST_FireAlarmDevices,
    DB.BuiltInCategory.OST_SecurityDevices,
    DB.BuiltInCategory.OST_NurseCallDevices,
)

doc = revit.doc
uidoc = revit.uidoc


# ------------------------------------------------------------------ UI

class ElevationDialog(forms.WPFWindow):
    def __init__(self, settings, level_name):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "JunctionBox.xaml"))
        self.result = None
        self.elevation.Text = "{:g}".format(settings["elevation_mm"])
        self.level_note.Text = u"Millimeters above the level: {}".format(level_name)
        self.elevation.Focus()
        self.elevation.SelectAll()

    def ok_click(self, sender, args):
        try:
            self.result = float(self.elevation.Text.replace(",", "."))
        except ValueError:
            self.error.Text = "Enter the elevation in mm."
            return
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


def _cat_int(element):
    cat = element.Category
    return eid_int(cat.Id) if cat is not None else None


class FixtureFilter(ISelectionFilter):
    CATS = set(int(c) for c in FIXTURE_CATEGORIES)

    def AllowElement(self, element):
        return isinstance(element, DB.FamilyInstance) and _cat_int(element) in self.CATS

    def AllowReference(self, reference, position):
        return False


def pick_fixtures():
    flt = FixtureFilter()
    pre = List[DB.Reference]()
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if flt.AllowElement(el):
            pre.Add(DB.Reference(el))
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, flt, "Select lighting fixtures, then click Finish", pre)
    except OperationCanceledException:
        return []
    return [doc.GetElement(r.ElementId) for r in refs]


# ----------------------------------------------------- routing lines

def _pieces(curve, transform=None):
    pts = None
    if isinstance(curve, DB.Line):
        pts = [curve.GetEndPoint(0), curve.GetEndPoint(1)]
    elif isinstance(curve, DB.PolyLine):
        pts = list(curve.GetCoordinates())
    if not pts:
        return []
    if transform is not None:
        pts = [transform.OfPoint(p) for p in pts]
    return [((a.X, a.Y, 0.0), (b.X, b.Y, 0.0)) for a, b in zip(pts, pts[1:])]


def routing_lines(view):
    """All straight routing segments in the view, with counts per source."""
    segs = []
    counts = {"detail": 0, "model": 0, "wire": 0, "cad": 0}
    for el in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
        pieces = _pieces(el.GeometryCurve)
        if not pieces:
            continue
        key = "detail" if el.CurveElementType == DB.CurveElementType.DetailCurve else "model"
        counts[key] += len(pieces)
        segs.extend(pieces)
    for wire in DB.FilteredElementCollector(doc, view.Id).OfClass(Wire):
        try:
            pts = [wire.GetVertex(i) for i in range(wire.NumberOfVertices)]
        except Exception:
            continue
        pieces = [((a.X, a.Y, 0.0), (b.X, b.Y, 0.0)) for a, b in zip(pts, pts[1:])]
        counts["wire"] += len(pieces)
        segs.extend(pieces)
    opts = DB.Options()
    opts.View = view
    for imp in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.ImportInstance):
        geo = imp.get_Geometry(opts)
        if geo is None:
            continue
        for g in geo:
            if not isinstance(g, DB.GeometryInstance):
                continue
            for obj in g.GetInstanceGeometry():
                pieces = _pieces(obj)
                counts["cad"] += len(pieces)
                segs.extend(pieces)
    return segs, counts


# ------------------------------------------------------------ boxes

def box_catalogue():
    """{family name: {kind: FamilySymbol}} for junction box families whose
    type names say what they are for."""
    out = {}
    for _label, sym in falcon_conduit.box_symbols(doc):
        kind = falcon_layout.type_kind(falcon_conduit.element_name(sym))
        if kind is None:
            continue
        out.setdefault(sym.Family.Name, {}).setdefault(kind, sym)
    return out


def existing_boxes():
    found = []
    for bic in falcon_conduit.BOX_CATEGORIES:
        for el in (DB.FilteredElementCollector(doc).OfCategory(bic)
                   .WhereElementIsNotElementType()):
            if (isinstance(el, DB.FamilyInstance) and falcon_conduit.is_box_like(el)
                    and hasattr(el.Location, "Point")):
                found.append(el)
    return found


def box_at(boxes, point, tol):
    for box in boxes:
        p = box.Location.Point
        if math.hypot(p.X - point.X, p.Y - point.Y) <= tol:
            return box
    return None


def outlet_dirs(inst):
    dirs = []
    for conn in falcon_conduit.conduit_connectors(inst):
        z = conn.CoordinateSystem.BasisZ
        if math.hypot(z.X, z.Y) > 0.7:
            length = math.hypot(z.X, z.Y)
            dirs.append((z.X / length, z.Y / length))
    return dirs


def turn_to(inst, route_dirs):
    """Rotate inst about its own vertical axis so its outlets face the
    routing lines (the box's X axis follows the first line when it has no
    side outlets)."""
    doc.Regenerate()
    dirs = outlet_dirs(inst)
    if dirs:
        angle = falcon_layout.best_rotation(dirs, route_dirs)
    else:
        facing = inst.HandOrientation
        first = route_dirs[0]
        angle = math.atan2(first[1], first[0]) - math.atan2(facing.Y, facing.X)
    if abs(math.sin(angle)) > 1e-6 or math.cos(angle) < 0:
        p = inst.Location.Point
        DB.ElementTransformUtils.RotateElement(
            doc, inst.Id, DB.Line.CreateBound(p, p + DB.XYZ.BasisZ), angle)


def fixture_outline(fixture, pad):
    box = fixture.get_BoundingBox(None)
    if box is None:
        return None
    return (box.Min.X - pad, box.Min.Y - pad, box.Max.X + pad, box.Max.Y + pad)


def zoom_to(points):
    if not points:
        return
    pad = falcon_geom.mm_to_ft(ZOOM_PAD_MM)
    lo = DB.XYZ(min(p.X for p in points) - pad, min(p.Y for p in points) - pad,
                min(p.Z for p in points))
    hi = DB.XYZ(max(p.X for p in points) + pad, max(p.Y for p in points) + pad,
                max(p.Z for p in points))
    for ui_view in uidoc.GetOpenUIViews():
        if ui_view.ViewId == doc.ActiveView.Id:
            ui_view.ZoomAndCenterRectangle(lo, hi)


# ----------------------------------------------------------------- main

def main():
    if not falcon_safety.project_only(doc, TITLE):
        return
    view = doc.ActiveView
    level = getattr(view, "GenLevel", None)
    if level is None:
        forms.alert("Open the plan view with the routing lines first.", title=TITLE)
        return
    catalogue = box_catalogue()
    if not catalogue:
        forms.alert("Load a junction box family whose type names say what they are "
                    "for (Terminal, Through, Angle, Tee, Branch_Y, Cross).", title=TITLE)
        return

    dialog = ElevationDialog(falcon_settings.load(SECTION, DEFAULTS), level.Name)
    dialog.show_dialog()
    if dialog.result is None:
        return
    elevation_mm = dialog.result
    falcon_settings.save(SECTION, {"elevation_mm": elevation_mm})

    fixtures = pick_fixtures()
    if not fixtures:
        return

    segments, counts = routing_lines(view)
    pad = falcon_geom.mm_to_ft(OUTLINE_PAD_MM)
    plans, skipped = [], []
    for fx in fixtures:
        loc = getattr(fx.Location, "Point", None)
        rect = fixture_outline(fx, pad)
        if loc is None or rect is None:
            skipped.append(u"Fixture {}: it has no insertion point".format(fx.Id))
            continue
        center = (loc.X, loc.Y, 0.0)
        dirs = falcon_layout.exit_directions(center, rect, segments)
        if not dirs:
            near = falcon_layout.nearest_segment_distance(center, segments)
            skipped.append(
                u"Fixture {}: no route line intersects the fixture outline; nearest line "
                u"{} from insertion point and no line crosses the fixture outline (view has "
                u"{} detail, {} model, {} wire, {} CAD segments)".format(
                    fx.Id, u"{:.1f} mm".format(falcon_geom.ft_to_mm(near)) if near is not None
                    else u"(none)", counts["detail"], counts["model"], counts["wire"],
                    counts["cad"]))
            continue
        kind = falcon_layout.pattern_kind(dirs)
        if kind is None:
            skipped.append(u"Fixture {}: {} route lines leave it - more than a cross "
                           u"box takes".format(fx.Id, len(dirs)))
            continue
        plans.append((fx, loc, dirs, kind))
    family_name = falcon_layout.pick_family(
        dict((name, set(kinds)) for name, kinds in catalogue.items()),
        [k for _f, _l, _d, k in plans])
    preferred = catalogue.get(family_name, {})

    z = level.ProjectElevation + falcon_geom.mm_to_ft(elevation_mm)
    boxes = existing_boxes()
    same_spot = falcon_geom.mm_to_ft(SAME_SPOT_MM)
    placed = updated = 0
    used_types, used_families, points = [], [], []
    with revit.TransactionGroup("Falcon: Junction Box"):
        with revit.Transaction("Falcon: Junction Box"):
            for fx, loc, dirs, kind in plans:
                symbol = preferred.get(kind)
                if symbol is None:
                    others = [fam[kind] for fam in catalogue.values() if kind in fam]
                    symbol = others[0] if others else None
                if symbol is None:
                    skipped.append(u"Fixture {}: no junction box type for a {} "
                                   u"({})".format(fx.Id, KIND_LABELS[kind], kind))
                    continue
                point = DB.XYZ(loc.X, loc.Y, z)

                def place(symbol=symbol, point=point, dirs=dirs):
                    if not symbol.IsActive:
                        symbol.Activate()
                        doc.Regenerate()
                    inst = box_at(boxes, point, same_spot)
                    is_new = inst is None
                    if is_new:
                        inst = doc.Create.NewFamilyInstance(
                            point, symbol, level, StructuralType.NonStructural)
                    else:
                        note = falcon_safety.owner_note(doc, inst)
                        if note:
                            raise ValueError(u"existing box {}: {}".format(inst.Id, note))
                    if not is_new and inst.GetTypeId() != symbol.Id:
                        inst.ChangeTypeId(symbol.Id)
                    falcon_conduit.set_height(doc, inst, z)
                    turn_to(inst, dirs)
                    return is_new, inst
                try:
                    is_new, inst = falcon_conduit.all_or_nothing(doc, place)
                    if is_new:
                        boxes.append(inst)
                        placed += 1
                    else:
                        updated += 1
                except Exception as ex:
                    skipped.append(u"Fixture {}: {}".format(fx.Id, ex))
                    continue
                points.append(point)
                label = falcon_conduit.element_name(symbol)
                if label not in used_types:
                    used_types.append(label)
                if symbol.Family.Name not in used_families:
                    used_families.append(symbol.Family.Name)
    zoom_to(points)

    lines = [u"Placed {} new junction box(es) and updated {} existing box(es).".format(
        placed, updated),
        u"Elevation: {:g} mm above {}".format(elevation_mm, level.Name)]
    if used_families:
        lines.append(u"Family used: {}".format(u", ".join(used_families)))
        lines.append(u"Type(s): {}".format(u", ".join(used_types)))
    if skipped:
        lines.append(u"")
        lines.append(u"Skipped {} fixture(s):".format(len(skipped)))
        lines.extend(skipped)
    lines.append(u"")
    lines.append(u"Active plan kept: {}. The plan was zoomed to the placement "
                 u"points.".format(view.Name))
    forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Junction Box stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
