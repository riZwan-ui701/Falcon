# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Wiring Pro
# Purpose        : Wire a run of ceiling or wall outlets in a plan: clean
#                  horizontal / vertical detail lines in the shortest order,
#                  a power circuit on a panel (with its panel schedule), an
#                  arc home-run wire and a circuit tag at the first outlet.
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
# Input          : Dialog (outlet type, wire color, connection, circuit,
#                  tag - all remembered); outlets (box-select + Finish);
#                  the FIRST outlet (and the LAST, if ticked); a custom
#                  connection point on one fixture (if ticked).
# Output         : Detail lines, power circuit, panel schedule, arc wire and
#                  circuit tag.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_wiring.py, falcon_geom.py, falcon_view.py,
#     falcon_conduit.py, falcon_settings.py
#
# Features       :
#   - Shortest run through the outlets from the first one (2-opt)
#   - Ceiling: side middle to side middle, one line in and one out per
#     fixture, never across another fixture; or a custom point, picked on
#     one fixture and used on all (follows each fixture's rotation)
#   - Wall: outlet to outlet (beside the stub) or back box to back box
#   - Line style or R / Y / B phase colors from each outlet's circuit
#   - One undo step
#
# Changelog
# ------------------------------------------------------------
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
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import Visibility

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.DB.Electrical import (ElectricalSystem, ElectricalSystemType,
                                          PanelScheduleView, Wire, WireType, WiringType)
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_wiring
import falcon_conduit
import falcon_view
import falcon_settings
from falcon_color import eid_int

TITLE = "Falcon - Wiring Pro"
SECTION = "falcon_wiringpro"
DEFAULTS = {"outlet": "ceiling", "color_mode": "style", "style_name": "",
            "default_phase": "R", "custom_point": False, "wall_mode": "outlet",
            # "circuit_on" (not "make_circuit"): v1 saved False whenever the panel
            # list was empty, so that old saved value is ignored on purpose
            "pick_last": True, "circuit_on": True, "panel": "", "add_tag": True,
            "tag_type": "", "wire_type": ""}
HOME_RUN_MM = 1200.0
CEILING_CATEGORIES = (DB.BuiltInCategory.OST_LightingFixtures,)
WALL_CATEGORIES = (
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_LightingDevices,
    DB.BuiltInCategory.OST_CommunicationDevices,
    DB.BuiltInCategory.OST_DataDevices,
    DB.BuiltInCategory.OST_FireAlarmDevices,
    DB.BuiltInCategory.OST_SecurityDevices,
    DB.BuiltInCategory.OST_NurseCallDevices,
    DB.BuiltInCategory.OST_TelephoneDevices,
    DB.BuiltInCategory.OST_LightingFixtures,
)
TAG_CATEGORIES = (
    DB.BuiltInCategory.OST_LightingFixtureTags,
    DB.BuiltInCategory.OST_ElectricalFixtureTags,
    DB.BuiltInCategory.OST_LightingDeviceTags,
    DB.BuiltInCategory.OST_CommunicationDeviceTags,
    DB.BuiltInCategory.OST_DataDeviceTags,
    DB.BuiltInCategory.OST_FireAlarmDeviceTags,
    DB.BuiltInCategory.OST_WireTags,
)
PHASES = ["R", "Y", "B"]

doc = revit.doc
uidoc = revit.uidoc
name_of = falcon_conduit.element_name


# ------------------------------------------------------------ catalogues

def line_styles():
    lines = doc.Settings.Categories.get_Item(DB.BuiltInCategory.OST_Lines)
    out = []
    for sub in lines.SubCategories:
        gs = sub.GetGraphicsStyle(DB.GraphicsStyleType.Projection)
        if gs is not None:
            out.append((sub.Name, gs))
    return sorted(out, key=lambda x: x[0])


def panels():
    out = []
    for el in (DB.FilteredElementCollector(doc)
               .OfCategory(DB.BuiltInCategory.OST_ElectricalEquipment)
               .WhereElementIsNotElementType()):
        if not falcon_conduit.is_panel(el):
            continue
        p = el.get_Parameter(DB.BuiltInParameter.RBS_ELEC_PANEL_NAME)
        label = (p.AsString() if p is not None and p.AsString() else name_of(el))
        dist = el.get_Parameter(DB.BuiltInParameter.RBS_FAMILY_CONTENT_DISTRIBUTION_SYSTEM)
        system = dist.AsValueString() if dist is not None and dist.HasValue else ""
        if system:
            label = u"{}  ({})".format(label, system)
        out.append((label, el))
    return sorted(out, key=lambda x: x[0])


def tag_types():
    out = []
    for bic in TAG_CATEGORIES:
        for sym in (DB.FilteredElementCollector(doc).OfCategory(bic)
                    .WhereElementIsElementType()):
            if isinstance(sym, DB.FamilySymbol):
                out.append((u"{} : {}".format(sym.Family.Name, name_of(sym)), sym))
    return sorted(out, key=lambda x: ("circuit" not in x[0].lower(), x[0]))


def wire_types():
    return sorted([(name_of(t), t) for t in
                   DB.FilteredElementCollector(doc).OfClass(WireType)], key=lambda x: x[0])


# ------------------------------------------------------------------ UI

def _fill(combo, labels, wanted):
    combo.Items.Clear()
    for label in labels:
        combo.Items.Add(label)
    if labels:
        combo.SelectedIndex = labels.index(wanted) if wanted in labels else 0


class WiringDialog(forms.WPFWindow):
    def __init__(self, s, styles, boards, tags, wires):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "WiringPro.xaml"))
        self.styles, self.boards, self.tags, self.wires = styles, boards, tags, wires
        self.result = None
        _fill(self.line_style, [n for n, _x in styles], s["style_name"])
        _fill(self.default_phase, PHASES, s["default_phase"])
        _fill(self.panel, [n for n, _x in boards], s["panel"])
        _fill(self.tag_type, [n for n, _x in tags], s["tag_type"])
        _fill(self.wire_type, [n for n, _x in wires], s["wire_type"])
        (self.color_phase if s["color_mode"] == "phase" else self.color_style).IsChecked = True
        (self.conn_backbox if s["wall_mode"] == "backbox" else self.conn_outlet).IsChecked = True
        self.custom_point.IsChecked = s["custom_point"]
        self.pick_last.IsChecked = s["pick_last"]
        self.saved_circuit_on = s["circuit_on"]
        self.warned_no_circuit = False
        self.make_circuit.IsChecked = s["circuit_on"] and bool(boards)
        self.make_circuit.IsEnabled = bool(boards)
        self.add_tag.IsChecked = s["add_tag"]
        (self.out_wall if s["outlet"] == "wall" else self.out_ceiling).IsChecked = True
        self.outlet_changed(None, None)

    def outlet_changed(self, sender, args):
        wall = bool(self.out_wall.IsChecked)
        self.wall_conn.Visibility = Visibility.Visible if wall else Visibility.Collapsed
        self.ceiling_conn.Visibility = Visibility.Collapsed if wall else Visibility.Visible

    def _pick(self, combo, items):
        i = combo.SelectedIndex
        return items[i] if 0 <= i < len(items) else (u"", None)

    def ok_click(self, sender, args):
        style = self._pick(self.line_style, self.styles)
        board = self._pick(self.panel, self.boards)
        tag = self._pick(self.tag_type, self.tags)
        wire = self._pick(self.wire_type, self.wires)
        if self.color_style.IsChecked and style[1] is None:
            self.error.Text = "There are no line styles to use."
            return
        if self.add_tag.IsChecked and (tag[1] is None or wire[1] is None):
            self.error.Text = "Load a circuit tag and a wire type, or untick ADD TAG."
            return
        circuit_on = bool(self.make_circuit.IsChecked) and board[1] is not None
        if not circuit_on and self.boards and not self.warned_no_circuit:
            # one reminder; pressing Start again goes ahead without a circuit
            self.warned_no_circuit = True
            self.error.Text = (u"\"Create a power circuit\" is off, so no circuit is made "
                               u"and the tag only shows a circuit for outlets that are "
                               u"already on one. Tick it, or press Start again to "
                               u"draw the wiring only.")
            return
        self.result = {
            "outlet": "wall" if self.out_wall.IsChecked else "ceiling",
            "color_mode": "phase" if self.color_phase.IsChecked else "style",
            "style_name": style[0], "style": style[1],
            "default_phase": PHASES[max(self.default_phase.SelectedIndex, 0)],
            "custom_point": bool(self.custom_point.IsChecked),
            "wall_mode": "backbox" if self.conn_backbox.IsChecked else "outlet",
            "pick_last": bool(self.pick_last.IsChecked),
            "make_circuit": circuit_on,
            # remember the user's tick - but not a box forced off by an empty
            # panel list
            "circuit_on": (bool(self.make_circuit.IsChecked) if self.boards
                           else self.saved_circuit_on),
            "panel": board[0], "panel_el": board[1],
            "add_tag": bool(self.add_tag.IsChecked),
            "tag_type": tag[0], "tag": tag[1], "wire_type": wire[0], "wire": wire[1],
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


class OutletFilter(ISelectionFilter):
    def __init__(self, cats=None, only=None):
        self.cats = set(int(c) for c in cats) if cats else None
        self.only = only

    def AllowElement(self, element):
        if self.only is not None:
            return eid_int(element.Id) in self.only
        cat = element.Category
        return (isinstance(element, DB.FamilyInstance) and cat is not None
                and eid_int(cat.Id) in self.cats)

    def AllowReference(self, reference, position):
        return False


# --------------------------------------------------------------- picking

def pick_outlets(cats, word):
    flt = OutletFilter(cats)
    pre = List[DB.Reference]()
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if flt.AllowElement(el):
            pre.Add(DB.Reference(el))
    refs = uidoc.Selection.PickObjects(
        ObjectType.Element, flt,
        "Draw a box around the {} outlets, then click Finish. Repeat to add more "
        "(they turn orange).".format(word), pre)
    seen, out = set(), []
    for r in refs:
        el = doc.GetElement(r.ElementId)
        if eid_int(el.Id) not in seen and hasattr(el.Location, "Point"):
            seen.add(eid_int(el.Id))
            out.append(el)
    return out


def pick_one(outlets, prompt):
    ref = uidoc.Selection.PickObject(
        ObjectType.Element, OutletFilter(only=set(eid_int(o.Id) for o in outlets)), prompt)
    ids = [eid_int(o.Id) for o in outlets]
    return ids.index(eid_int(ref.ElementId))


# ------------------------------------------------------------- geometry

def plan_rect(el):
    box = el.get_BoundingBox(None)
    return (box.Min.X, box.Min.Y, box.Max.X, box.Max.Y)


def plan_unit(v):
    length = math.hypot(v.X, v.Y)
    return (v.X / length, v.Y / length) if length > 1e-9 else (1.0, 0.0)


def ceiling_paths(outlets, order, rects, local):
    paths = []
    entered = {}
    for a, b in zip(order, order[1:]):
        others = [rects[k] for k in order if k not in (a, b)]
        if local is not None:
            pa = outlets[a].GetTransform().OfPoint(local)
            pb = outlets[b].GetTransform().OfPoint(local)
            paths.append((a, falcon_wiring.route_points((pa.X, pa.Y), (pb.X, pb.Y), others)))
            continue
        path, _sa, sb = falcon_wiring.route_sides(rects[a], rects[b], others,
                                                  used_a=entered.get(a))
        entered[b] = sb
        paths.append((a, path))
    return paths


def wall_paths(outlets, order, rects, mode):
    ports = []
    for o, r in zip(outlets, rects):
        size = max(r[2] - r[0], r[3] - r[1])
        loc = o.Location.Point
        ports.append(falcon_wiring.wall_ports(
            (loc.X, loc.Y), plan_unit(o.HandOrientation), plan_unit(o.FacingOrientation),
            0.3 * size, mode, front=0.3 * size))
    paths = []
    came = None
    for n, (a, b) in enumerate(zip(order, order[1:])):
        nxt = outlets[b].Location.Point
        if n == 0:
            # the first outlet leaves from the port nearer the next outlet
            exit_a = falcon_wiring.enter_leave(ports[a], (nxt.X, nxt.Y))[0]
        else:
            exit_a = falcon_wiring.enter_leave(ports[a], came)[1]
        entry_b, _exit = falcon_wiring.enter_leave(ports[b], exit_a)
        others = [rects[k] for k in order if k not in (a, b)]
        axis = falcon_wiring.axis_of(plan_unit(outlets[a].HandOrientation))
        paths.append((a, falcon_wiring.route_points(exit_a, entry_b, others, first_axis=axis)))
        came = entry_b
    return paths


# ------------------------------------------------------------- circuits

def circuits_of(el):
    mep = getattr(el, "MEPModel", None)
    if mep is None:
        return []
    try:
        systems = mep.GetElectricalSystems()
    except Exception:
        systems = getattr(mep, "ElectricalSystems", None)
    return [s for s in (systems or [])
            if s.SystemType == ElectricalSystemType.PowerCircuit]


def make_circuit(outlets, panel):
    """(circuit or None, note)."""
    free = [o for o in outlets if not circuits_of(o)]
    if not free:
        return None, u"every outlet is already on a circuit"
    system = ElectricalSystem.Create(
        doc, List[DB.ElementId]([o.Id for o in free]), ElectricalSystemType.PowerCircuit)
    system.SelectPanel(panel)
    doc.Regenerate()
    note = u""
    if len(free) < len(outlets):
        note = u"{} outlet(s) were already on a circuit and kept it".format(
            len(outlets) - len(free))
    return system, note


def ensure_schedule(panel):
    for psv in DB.FilteredElementCollector(doc).OfClass(PanelScheduleView):
        try:
            if psv.GetPanel() == panel.Id:
                return False
        except Exception:
            continue
    PanelScheduleView.CreateInstanceView(doc, panel.Id)
    return True


def electrical_connector(el):
    mep = getattr(el, "MEPModel", None)
    if mep is None or mep.ConnectorManager is None:
        return None
    for c in mep.ConnectorManager.Connectors:
        if c.Domain == DB.Domain.DomainElectrical:
            return c
    return None


# ----------------------------------------------------------------- main

def main():
    if doc is None:
        forms.alert("Please open a Revit project first.", title=TITLE)
        return
    view = doc.ActiveView
    if not falcon_view.is_plan(view):
        forms.alert("Open the plan view of the outlets first.", title=TITLE)
        return
    styles, boards, tags, wires = line_styles(), panels(), tag_types(), wire_types()
    dialog = WiringDialog(falcon_settings.load(SECTION, DEFAULTS), styles, boards, tags, wires)
    dialog.show_dialog()
    o = dialog.result
    if o is None:
        return
    falcon_settings.save(SECTION, dict((k, o[k]) for k in DEFAULTS))

    wall = o["outlet"] == "wall"
    word = "wall" if wall else "ceiling"
    try:
        outlets = pick_outlets(WALL_CATEGORIES if wall else CEILING_CATEGORIES, word)
        if len(outlets) < 2:
            forms.alert("Select at least two outlets.", title=TITLE)
            return
        first = pick_one(outlets, "Click the FIRST outlet (start of the run)")
        last = (pick_one(outlets, "Click the LAST outlet (end of the run)")
                if o["pick_last"] else None)
        local = None
        if not wall and o["custom_point"]:
            pt = uidoc.Selection.PickPoint("Click the connection point on one of the fixtures")
            host = [x for x in outlets if _inside(plan_rect(x), pt)]
            if not host:
                forms.alert("That point is not on one of the selected fixtures.", title=TITLE)
                return
            local = host[0].GetTransform().Inverse.OfPoint(pt)
    except OperationCanceledException:
        return

    rects = [plan_rect(x) for x in outlets]
    centers = [(x.Location.Point.X, x.Location.Point.Y) for x in outlets]
    order = falcon_wiring.order_run(centers, first, last)
    if wall:
        paths = wall_paths(outlets, order, rects, o["wall_mode"])
    else:
        paths = ceiling_paths(outlets, order, rects, local)
    z = falcon_view.plan_z(view)

    lines_made = 0
    report = []
    circuit = None
    with revit.TransactionGroup("Falcon: Wiring Pro"):
        with revit.Transaction("Falcon: Wiring Pro"):
            if o["make_circuit"]:
                try:
                    circuit, note = make_circuit(outlets, o["panel_el"])
                    if circuit is not None:
                        report.append(u"Circuit {} created on {} for {} outlet(s).".format(
                            circuit.CircuitNumber, o["panel"], len(outlets)))
                        if ensure_schedule(o["panel_el"]):
                            report.append(u"Panel schedule created for {}.".format(o["panel"]))
                        else:
                            report.append(u"The panel schedule of {} now lists them.".format(
                                o["panel"]))
                    if note:
                        report.append(u"Circuit: {}.".format(note))
                except Exception as ex:
                    report.append(u"Circuit not created: {}".format(ex))

            for a, path in paths:
                pts = falcon_wiring.lift(path, z)
                color = None
                if o["color_mode"] == "phase":
                    systems = circuits_of(outlets[a])
                    number = systems[0].CircuitNumber if systems else ""
                    letter = falcon_wiring.phase_letter(number, o["default_phase"]) \
                        if number else o["default_phase"]
                    color = DB.Color(*falcon_wiring.PHASE_RGB[letter])
                for p, q in zip(pts, pts[1:]):
                    line = doc.Create.NewDetailCurve(
                        view, DB.Line.CreateBound(DB.XYZ(*p), DB.XYZ(*q)))
                    if o["color_mode"] == "style" and o["style"] is not None:
                        line.LineStyle = o["style"]
                    elif color is not None:
                        ogs = DB.OverrideGraphicSettings()
                        ogs.SetProjectionLineColor(color)
                        view.SetElementOverrides(line.Id, ogs)
                    lines_made += 1

            if o["add_tag"]:
                report.extend(add_tag(view, outlets[order[0]], o, z))

    head = [u"{} detail line(s) connecting {} {} outlet(s).".format(
        lines_made, len(outlets), word)]
    head.append(u"Phase color (R red, Y yellow, B blue)" if o["color_mode"] == "phase"
                else u"Line style: {}".format(o["style_name"]))
    forms.alert(u"\n".join(head + report), title=TITLE)


def _inside(rect, pt):
    return rect[0] <= pt.X <= rect[2] and rect[1] <= pt.Y <= rect[3]


def add_tag(view, first, o, z):
    systems = circuits_of(first)
    if not systems:
        return [u"No tag: the first outlet is not on a circuit (tick \"Create a power "
                u"circuit\")."]
    system = systems[0]
    panel = system.BaseEquipment
    loc = first.Location.Point
    conn = electrical_connector(first)
    start = (loc.X, loc.Y)
    if conn is not None:
        start = (conn.Origin.X, conn.Origin.Y)
    toward = ((panel.Location.Point.X, panel.Location.Point.Y)
              if panel is not None and hasattr(panel.Location, "Point")
              else (start[0] - 1.0, start[1] + 1.0))
    pts = falcon_wiring.arc_points(start, toward, falcon_geom.mm_to_ft(HOME_RUN_MM))
    out = []
    try:
        Wire.Create(doc, o["wire"].Id, view.Id, WiringType.Arc,
                    List[DB.XYZ]([DB.XYZ(p[0], p[1], z) for p in pts]), conn, None)
        out.append(u"Added an arc wire toward panel {}".format(system.PanelName))
    except Exception as ex:
        out.append(u"Arc wire not added: {}".format(ex))
    try:
        end = pts[-1]
        DB.IndependentTag.Create(doc, o["tag"].Id, view.Id, DB.Reference(first), False,
                                 DB.TagOrientation.Horizontal, DB.XYZ(end[0], end[1], z))
        if out and out[0].startswith(u"Added"):
            out[0] += u" and the circuit tag ({}) at the first outlet.".format(
                system.CircuitNumber)
        else:
            out.append(u"Added the circuit tag ({}) at the first outlet.".format(
                system.CircuitNumber))
    except Exception as ex:
        out.append(u"Tag not added: {}".format(ex))
    return out


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Wiring Pro stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
