# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Auto Flex
# Purpose        : Draw a flex from each selected ceiling junction box to
#                  its nearest light fixture. A box whose outlets are all
#                  taken by conduit is switched to a type with one more
#                  outlet (Through -> Tee -> Cross), keeps its conduits
#                  connected, and the flex leaves from the new outlet.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
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
# Input          : Flex diameter (remembered); ceiling boxes (pick + Finish,
#                  pre-selected boxes are kept in the pick).
# Output         : Flex pipes box -> fixture; boxes switched to bigger types.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_geom.py, falcon_conduit.py, falcon_settings.py
#
# Features       :
#   - Works with any junction box family: outlets are counted from the
#     family's conduit connectors, capped by the type name (Tee = 3 ...)
#   - Bigger type looked for in the same family first, then in other box
#     families of the same category and conduit size
#   - Each box all-or-nothing; the whole run is one undo step
#
# Changelog
# ------------------------------------------------------------
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
from Autodesk.Revit.DB.Plumbing import FlexPipe, FlexPipeType, PipingSystemType
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_conduit
import falcon_settings
from falcon_color import eid_int

TITLE = "Falcon - Auto Flex"
SECTION = "falcon_autoflex"
DIAMETERS_MM = [20, 25, 32, 40, 50, 65, 80, 90, 100, 125, 150, 200, 250, 300]
DEFAULTS = {"diameter_mm": 20}
LEAD_MM = 150.0        # flex runs straight out of the outlet this far
ON_OUTLET_MM = 5.0     # a flex end this close to an outlet = already has a flex

doc = revit.doc
uidoc = revit.uidoc


# ------------------------------------------------------------------ UI

class AutoFlexDialog(forms.WPFWindow):
    def __init__(self, settings):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "AutoFlex.xaml"))
        self.result = None
        for mm in DIAMETERS_MM:
            self.diameter.Items.Add(str(mm))
        last = settings["diameter_mm"]
        self.diameter.SelectedIndex = (DIAMETERS_MM.index(last)
                                       if last in DIAMETERS_MM else 0)

    def select_click(self, sender, args):
        self.result = DIAMETERS_MM[max(self.diameter.SelectedIndex, 0)]
        self.Close()


class BoxFilter(ISelectionFilter):
    """Ceiling boxes: box-like family instances with conduit outlets."""

    def AllowElement(self, element):
        return is_box(element)

    def AllowReference(self, reference, position):
        return False


def is_box(element):
    return (isinstance(element, DB.FamilyInstance)
            and falcon_conduit.is_box_like(element)
            and bool(falcon_conduit.conduit_connectors(element)))


def pick_boxes():
    """Boxes picked with Finish; boxes already selected stay selected."""
    pre = List[DB.Reference]()
    for eid in uidoc.Selection.GetElementIds():
        element = doc.GetElement(eid)
        if is_box(element):
            pre.Add(DB.Reference(element))
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, BoxFilter(),
            "Select ceiling box(es), then press Finish", pre)
    except OperationCanceledException:
        return []
    return [doc.GetElement(r.ElementId) for r in refs]


# --------------------------------------------------------- model lookups

def fixture_targets():
    """[(fixture, top-centre point)] of every light fixture."""
    out = []
    collector = (DB.FilteredElementCollector(doc)
                 .OfCategory(DB.BuiltInCategory.OST_LightingFixtures)
                 .WhereElementIsNotElementType())
    for fixture in collector:
        box = fixture.get_BoundingBox(None)
        if box is None:
            continue
        out.append((fixture, ((box.Min.X + box.Max.X) / 2.0,
                              (box.Min.Y + box.Max.Y) / 2.0, box.Max.Z)))
    return out


def existing_flex_ends():
    ends = []
    for flex in DB.FilteredElementCollector(doc).OfClass(FlexPipe):
        points = list(flex.Points)
        if points:
            ends.extend([points[0], points[-1]])
    return ends


def flex_type_and_system():
    types = sorted(DB.FilteredElementCollector(doc).OfClass(FlexPipeType),
                   key=lambda t: ("round" not in falcon_conduit.element_name(t).lower(),
                                  falcon_conduit.element_name(t)))
    systems = list(DB.FilteredElementCollector(doc).OfClass(PipingSystemType))
    return (types[0] if types else None), (systems[0] if systems else None)


def level_for(inst, z):
    """The box's level, else the highest level at or below z."""
    level_id = getattr(inst, "LevelId", DB.ElementId.InvalidElementId)
    if level_id is not None and level_id != DB.ElementId.InvalidElementId:
        return level_id
    for bip in (DB.BuiltInParameter.FAMILY_LEVEL_PARAM,
                DB.BuiltInParameter.SCHEDULE_LEVEL_PARAM):
        param = inst.get_Parameter(bip)
        if param is not None and param.AsElementId() != DB.ElementId.InvalidElementId:
            return param.AsElementId()
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level),
                    key=lambda lv: lv.Elevation)
    below = [lv for lv in levels if lv.Elevation <= z + 1e-6]
    chosen = below[-1] if below else levels[0]
    return chosen.Id


# ----------------------------------------------------- box type switching

def _radius(inst):
    radii = []
    for conn in falcon_conduit.conduit_connectors(inst):
        try:
            radii.append(round(conn.Radius, 4))
        except Exception:
            pass
    return max(radii) if radii else None


def _trial(inst, symbol, cache):
    """(conduit connectors, radius) inst would have as symbol; cached."""
    key = eid_int(symbol.Id)
    if key not in cache:
        sub = DB.SubTransaction(doc)
        sub.Start()
        try:
            if not symbol.IsActive:
                symbol.Activate()
            inst.ChangeTypeId(symbol.Id)
            doc.Regenerate()
            cache[key] = (len(falcon_conduit.conduit_connectors(inst)), _radius(inst))
        except Exception:
            cache[key] = (0, None)
        finally:
            sub.RollBack()
    return cache[key]


def bigger_type(inst, needed, cache):
    """A box type with at least `needed` outlets: same family first, then
    other box families of the same category and conduit size. None if
    there is none."""
    current = inst.Symbol
    radius = _radius(inst)
    same, other = [], []
    for sid in current.Family.GetFamilySymbolIds():
        if sid == current.Id:
            continue
        sym = doc.GetElement(sid)
        count, _r = _trial(inst, sym, cache)
        same.append((sym, falcon_geom.box_capacity(count, falcon_conduit.element_name(sym))))
    pick = falcon_geom.pick_bigger_type(needed, same)
    if pick is not None:
        return pick
    cat_id = eid_int(current.Category.Id)
    for _label, sym in falcon_conduit.box_symbols(doc):
        if (eid_int(sym.Family.Id) == eid_int(current.Family.Id)
                or eid_int(sym.Category.Id) != cat_id):
            continue
        count, r = _trial(inst, sym, cache)
        if radius is None or r == radius:
            other.append((sym, falcon_geom.box_capacity(count, falcon_conduit.element_name(sym))))
    return falcon_geom.pick_bigger_type(needed, other)


# ------------------------------------------------------------ per box

def has_flex(inst, flex_ends):
    tol = falcon_geom.mm_to_ft(ON_OUTLET_MM)
    for conn in falcon_conduit.conduit_connectors(inst):
        for p in flex_ends:
            if conn.Origin.DistanceTo(p) <= tol:
                return True
    return False


def free_outlets(inst):
    return [c for c in falcon_conduit.conduit_connectors(inst) if not c.IsConnected]


def do_box(inst, targets, opts, cache):
    """Flex one box to its nearest fixture. Returns True when the box was
    switched to a bigger type. Raises ValueError with the reason to skip."""
    origin = inst.Location.Point
    idx = falcon_geom.nearest_index(falcon_conduit.tup(origin), [p for _f, p in targets])
    if idx is None:
        raise ValueError("no light fixture in the model")
    target = targets[idx][1]

    used = len(falcon_conduit.used_conduit_connectors(inst))
    capacity = falcon_geom.box_capacity(
        len(falcon_conduit.conduit_connectors(inst)),
        falcon_conduit.element_name(inst.Symbol))
    switched = False
    if used >= capacity or not free_outlets(inst):
        symbol = bigger_type(inst, used + 1, cache)
        if symbol is None:
            raise ValueError("every outlet is taken and the family has no type "
                             "with more outlets")
        if not symbol.IsActive:
            symbol.Activate()
            doc.Regenerate()
        falcon_conduit.swap_box_type(doc, inst, symbol.Id)
        switched = True
        if not free_outlets(inst):
            raise ValueError("the new type has no free outlet")

    outlets = free_outlets(inst)
    toward = falcon_geom.vsub(target, falcon_conduit.tup(origin))
    outlet = outlets[falcon_geom.best_outlet(
        [falcon_conduit.tup(c.CoordinateSystem.BasisZ) for c in outlets], toward)]

    start = falcon_conduit.tup(outlet.Origin)
    points, t0, t1 = falcon_geom.flex_points(
        start, falcon_conduit.tup(outlet.CoordinateSystem.BasisZ), target,
        falcon_geom.mm_to_ft(LEAD_MM))
    flex = FlexPipe.Create(
        doc, opts["system"].Id, opts["flex_type"].Id, level_for(inst, start[2]),
        falcon_conduit.xyz(t0), falcon_conduit.xyz(t1),
        List[DB.XYZ]([falcon_conduit.xyz(p) for p in points]))
    diameter = flex.get_Parameter(DB.BuiltInParameter.RBS_PIPE_DIAMETER_PARAM)
    if diameter is not None and not diameter.IsReadOnly:
        diameter.Set(falcon_geom.mm_to_ft(opts["diameter_mm"]))
    return switched


# ----------------------------------------------------------------- main

def main():
    if doc is None:
        forms.alert("Please open a Revit project first.", title=TITLE)
        return
    flex_type, system = flex_type_and_system()
    if flex_type is None or system is None:
        forms.alert("This project has no flex pipe type or piping system type. "
                    "Load a template with flex pipes first.", title=TITLE)
        return
    targets = fixture_targets()
    if not targets:
        forms.alert("There are no light fixtures in the model.", title=TITLE)
        return

    dialog = AutoFlexDialog(falcon_settings.load(SECTION, DEFAULTS))
    dialog.show_dialog()
    if dialog.result is None:
        return
    falcon_settings.save(SECTION, {"diameter_mm": dialog.result})
    opts = {"diameter_mm": dialog.result, "flex_type": flex_type, "system": system}

    boxes = pick_boxes()
    if not boxes:
        return

    created = switched = 0
    skipped = []
    cache = {}
    flex_ends = existing_flex_ends()
    with revit.TransactionGroup("Falcon: Auto Flex"):
        with revit.Transaction("Falcon: Auto Flex"):
            for inst in boxes:
                if has_flex(inst, flex_ends):
                    skipped.append(u"{}: already has a flex".format(inst.Id))
                    continue
                try:
                    was_switched = falcon_conduit.all_or_nothing(
                        doc, lambda: do_box(inst, targets, opts, cache))
                except Exception as ex:
                    skipped.append(u"{}: {}".format(inst.Id, ex))
                    continue
                created += 1
                if was_switched:
                    switched += 1

    lines = [u"Flex created: {}".format(created),
             u"Boxes switched to a type with an extra outlet: {}".format(switched),
             u"Skipped / failed: {}".format(len(skipped))]
    if skipped:
        lines.append(u"")
        lines.extend(skipped)
    forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Auto Flex stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
