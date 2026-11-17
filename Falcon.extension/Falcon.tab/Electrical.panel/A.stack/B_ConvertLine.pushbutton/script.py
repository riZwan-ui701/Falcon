# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Convert Line
# Purpose        : Turn detail/model lines (picked, or every line of a
#                  line style in the view) or lines inside a linked/imported
#                  CAD file into connected conduits.
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
# Input          : Selection mode (Select Line / Line Style / CAD Lines),
#                  conduit type, diameter (from the type's size list),
#                  Elevation or Circuit Elevation, delete-lines option.
# Output         : Conduits on the active view's level; lines that continue
#                  straight on become one conduit; elbows, tees and crosses
#                  where lines meet; risers into panels (Circuit Elevation).
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_route.py, falcon_geom.py, falcon_conduit.py,
#     falcon_settings.py
#
# Features       :
#   - Arcs and other curves are skipped and counted
#   - Joints with no room for a fitting are left disconnected and counted
#   - Remembers last settings; one undo step
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - New dialog: Select Line / Line Style / CAD Lines, size list from the
#   conduit type, Circuit Elevation, delete original lines
# - Straight-on lines merged into one conduit; tees and crosses added
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import Visibility

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_route
import falcon_conduit
import falcon_settings

TITLE = "Falcon - Convert Line"
SECTION = "falcon_convertline"
DEFAULTS = {"mode": "pick", "style_name": "", "type_name": "", "diameter_mm": 20.0,
            "elevation_mm": 3000.0, "circuit": False, "delete_lines": True}
FALLBACK_SIZES_MM = [16.0, 20.0, 21.0, 25.0, 27.0, 32.0, 35.0, 41.0, 50.0, 63.0]
JOINT_TOL_MM = 5.0
TOUCH_TOL_MM = 25.0
MIN_LENGTH_MM = 10.0
DEVICE_CATEGORIES = (
    DB.BuiltInCategory.OST_LightingFixtures,
    DB.BuiltInCategory.OST_LightingDevices,
    DB.BuiltInCategory.OST_ElectricalFixtures,
    DB.BuiltInCategory.OST_ElectricalEquipment,
    DB.BuiltInCategory.OST_ConduitFitting,
    DB.BuiltInCategory.OST_CommunicationDevices,
    DB.BuiltInCategory.OST_DataDevices,
    DB.BuiltInCategory.OST_FireAlarmDevices,
    DB.BuiltInCategory.OST_SecurityDevices,
)

doc = revit.doc
uidoc = revit.uidoc


def _fmt_mm(mm):
    return u"{:g} mm".format(mm)


# ------------------------------------------------------------------ UI

class ConvertDialog(forms.WPFWindow):
    def __init__(self, settings, types, styles, level_name):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "ConvertLine.xaml"))
        self.types = types
        self.styles = styles
        self.sizes = []
        self.last_diameter = settings["diameter_mm"]
        self.result = None
        for name in styles:
            self.line_style.Items.Add(name)
        if styles:
            self.line_style.SelectedIndex = (styles.index(settings["style_name"])
                                             if settings["style_name"] in styles else 0)
        names = [n for n, _t in types]
        for name in names:
            self.ctype.Items.Add(name)
        self.ctype.SelectedIndex = (names.index(settings["type_name"])
                                    if settings["type_name"] in names else 0)
        self.elevation.Text = "{:g}".format(settings["elevation_mm"])
        self.level_note.Text = u"Millimeters above the level: {}".format(level_name)
        (self.elev_circuit if settings["circuit"] else self.elev_fixed).IsChecked = True
        self.delete_lines.IsChecked = settings["delete_lines"]
        mode = settings["mode"] if settings["mode"] in ("pick", "style", "cad") else "pick"
        if mode == "style" and not styles:
            mode = "pick"
        getattr(self, "mode_" + mode).IsChecked = True
        self.mode_changed(None, None)

    def mode(self):
        for m in ("pick", "style", "cad"):
            if getattr(self, "mode_" + m).IsChecked:
                return m
        return "pick"

    def mode_changed(self, sender, args):
        mode = self.mode()
        self.line_style.IsEnabled = mode == "style"
        self.delete_lines.Visibility = (Visibility.Collapsed if mode == "cad"
                                        else Visibility.Visible)

    def type_changed(self, sender, args):
        index = self.ctype.SelectedIndex
        if index < 0:
            return
        sizes = falcon_conduit.conduit_sizes_mm(doc, self.types[index][1]) or FALLBACK_SIZES_MM
        self.sizes = sizes
        self.diameter.Items.Clear()
        for mm in sizes:
            self.diameter.Items.Add(_fmt_mm(mm))
        nearest = min(range(len(sizes)), key=lambda i: abs(sizes[i] - self.last_diameter))
        self.diameter.SelectedIndex = nearest

    def ok_click(self, sender, args):
        mode = self.mode()
        if mode == "style" and self.line_style.SelectedIndex < 0:
            self.error.Text = "There are no lines in this view to pick a line style from."
            return
        circuit = bool(self.elev_circuit.IsChecked)
        try:
            elevation = float(self.elevation.Text.replace(",", "."))
        except ValueError:
            self.error.Text = "Enter the elevation in mm (it is also used for runs " \
                              "that touch no fixture)."
            return
        if self.diameter.SelectedIndex < 0:
            self.error.Text = "Pick a conduit diameter."
            return
        name, ctype = self.types[self.ctype.SelectedIndex]
        self.result = {
            "mode": mode,
            "style_name": self.styles[self.line_style.SelectedIndex] if self.styles else "",
            "type_name": name, "type": ctype,
            "diameter_mm": self.sizes[self.diameter.SelectedIndex],
            "elevation_mm": elevation, "circuit": circuit,
            "delete_lines": bool(self.delete_lines.IsChecked) and mode != "cad",
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


class CurveFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, DB.CurveElement)

    def AllowReference(self, reference, position):
        return False


class ImportFilter(ISelectionFilter):
    def AllowElement(self, element):
        return isinstance(element, DB.ImportInstance)

    def AllowReference(self, reference, position):
        return True


# ------------------------------------------------------------ collecting

def _segments_of(curve):
    """Straight (p0, p1) pieces of a Line or PolyLine; [] for anything else."""
    if isinstance(curve, DB.Line):
        return [(curve.GetEndPoint(0), curve.GetEndPoint(1))]
    if isinstance(curve, DB.PolyLine):
        pts = list(curve.GetCoordinates())
        return list(zip(pts, pts[1:]))
    return []


def _style_name(curve_el):
    style = curve_el.LineStyle
    return style.Name if style is not None else ""


def view_line_styles(view):
    names = set()
    for el in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement):
        names.add(_style_name(el))
    return sorted(n for n in names if n)


def lines_from_elements(elements):
    """(segments, source elements used, skipped count)."""
    segments, used, skipped = [], [], 0
    for el in elements:
        pieces = _segments_of(el.GeometryCurve)
        if pieces:
            segments.extend(pieces)
            used.append(el)
        else:
            skipped += 1
    return segments, used, skipped


def picked_lines():
    elements = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    elements = [e for e in elements if isinstance(e, DB.CurveElement)]
    if not elements:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, CurveFilter(), "Select the lines to convert, then click Finish")
        elements = [doc.GetElement(r.ElementId) for r in refs]
    return lines_from_elements(elements)


def style_lines(view, style_name):
    elements = [e for e in DB.FilteredElementCollector(doc, view.Id).OfClass(DB.CurveElement)
                if _style_name(e) == style_name]
    return lines_from_elements(elements)


def cad_lines():
    refs = uidoc.Selection.PickObjects(
        ObjectType.PointOnElement, ImportFilter(),
        "Pick the CAD lines to convert, then click Finish")
    segments, skipped = [], 0
    for ref in refs:
        imp = doc.GetElement(ref.ElementId)
        geo = imp.GetGeometryObjectFromReference(ref)
        pieces = _segments_of(geo)
        if not pieces:
            skipped += 1
            continue
        # The geometry may come back in the CAD file's own coordinates;
        # if it does not pass near the picked point, move it into the model.
        hit = falcon_conduit.tup(ref.GlobalPoint)
        near = min(_plan_gap(p, hit) for p in pieces)
        if near > falcon_geom.mm_to_ft(50):
            tf = imp.GetTotalTransform()
            pieces = [(tf.OfPoint(a), tf.OfPoint(b)) for a, b in pieces]
        segments.extend(pieces)
    return segments, [], skipped


def _plan_gap(piece, point):
    a, b = falcon_conduit.tup(piece[0]), falcon_conduit.tup(piece[1])
    flat_a, flat_b = (a[0], a[1], 0.0), (b[0], b[1], 0.0)
    flat_p = (point[0], point[1], 0.0)
    d = falcon_geom.project_distance(flat_a, flat_b, flat_p)
    on = falcon_geom.point_along(flat_a, flat_b, d)
    return falcon_geom.vlen(falcon_geom.vsub(on, flat_p))


# --------------------------------------------------- circuit elevation

class Device(object):
    def __init__(self, element):
        self.element = element
        box = element.get_BoundingBox(None)
        self.min, self.max = box.Min, box.Max
        self.is_panel = falcon_conduit.is_panel(element)

    def touches(self, p, tol):
        return (self.min.X - tol <= p[0] <= self.max.X + tol
                and self.min.Y - tol <= p[1] <= self.max.Y + tol)

    def height(self, p):
        """Where a conduit meets this device: its conduit connector nearest
        in plan, else the top of the device."""
        conns = falcon_conduit.conduit_connectors(self.element)
        if conns:
            best = min(conns, key=lambda c: (c.Origin.X - p[0]) ** 2 + (c.Origin.Y - p[1]) ** 2)
            return best.Origin.Z
        return self.max.Z


def collect_devices():
    out = []
    for bic in DEVICE_CATEGORIES:
        for el in (DB.FilteredElementCollector(doc).OfCategory(bic)
                   .WhereElementIsNotElementType()):
            if isinstance(el, DB.FamilyInstance) and el.get_BoundingBox(None) is not None:
                out.append(Device(el))
    return out


def components(n, groups):
    parent = list(range(n))

    def find(i):
        while parent[i] != i:
            parent[i] = parent[parent[i]]
            i = parent[i]
        return i
    for g in groups:
        for i, _e in g[1:]:
            parent[find(i)] = find(g[0][0])
    return [find(i) for i in range(n)]


def plan_heights(segments, groups, default_z, tol):
    """Height of every segment and the panel ends to rise into.

    Returns (heights, panel_ends, device_ends, runs_without_fixture) where
    panel_ends / device_ends are [(segment, end, Device)]."""
    joined = set((i, e) for g in groups for i, e in g)
    comp = components(len(segments), groups)
    devices = collect_devices()
    found = {}
    panel_ends, device_ends = [], []
    for i, seg in enumerate(segments):
        for e in (0, 1):
            if (i, e) in joined:
                continue
            p = seg[e]
            hits = [d for d in devices if d.touches(p, tol)]
            if not hits:
                continue
            panel = [d for d in hits if d.is_panel]
            others = [d for d in hits if not d.is_panel]
            if others:
                dev = others[0]
                found.setdefault(comp[i], []).append(dev.height(p))
                device_ends.append((i, e, dev))
            elif panel:
                panel_ends.append((i, e, panel[0]))
    heights = []
    for i in range(len(segments)):
        zs = found.get(comp[i])
        heights.append(max(zs) if zs else default_z)
    no_fixture = len(set(comp) - set(found))
    return heights, panel_ends, device_ends, no_fixture


# ----------------------------------------------------------------- main

def main():
    if doc is None:
        forms.alert("Please open a Revit project first.", title=TITLE)
        return
    view = doc.ActiveView
    level = getattr(view, "GenLevel", None)
    if level is None:
        forms.alert("Open a plan view first - the conduits go on its level.", title=TITLE)
        return
    types = falcon_conduit.conduit_types(doc)
    if not types:
        forms.alert("This project has no conduit types.", title=TITLE)
        return

    dialog = ConvertDialog(falcon_settings.load(SECTION, DEFAULTS), types,
                           view_line_styles(view), level.Name)
    dialog.show_dialog()
    opts = dialog.result
    if opts is None:
        return
    falcon_settings.save(SECTION, dict((k, opts[k]) for k in DEFAULTS))

    try:
        if opts["mode"] == "style":
            raw, used, skipped = style_lines(view, opts["style_name"])
        elif opts["mode"] == "cad":
            raw, used, skipped = cad_lines()
        else:
            raw, used, skipped = picked_lines()
    except OperationCanceledException:
        return

    tol = falcon_geom.mm_to_ft(JOINT_TOL_MM)
    min_len = falcon_geom.mm_to_ft(MIN_LENGTH_MM)
    flat = []
    for a, b in raw:
        p0, p1 = (a.X, a.Y, 0.0), (b.X, b.Y, 0.0)
        if falcon_geom.vlen(falcon_geom.vsub(p1, p0)) >= min_len:
            flat.append((p0, p1))
        else:
            skipped += 1
    flat = falcon_geom.dedupe_segments(flat, falcon_geom.mm_to_ft(1.0))
    if not flat:
        forms.alert("No straight lines to convert.", title=TITLE)
        return
    line_count = len(used) if used else len(flat)

    segments, _src = falcon_route.merge_collinear(
        falcon_route.split_at_touches(flat, tol), tol)
    groups = falcon_route.joint_groups(segments, tol)
    default_z = level.ProjectElevation + falcon_geom.mm_to_ft(opts["elevation_mm"])
    panel_ends, device_ends, no_fixture = [], [], 0
    if opts["circuit"]:
        heights, panel_ends, device_ends, no_fixture = plan_heights(
            segments, groups, default_z, falcon_geom.mm_to_ft(TOUCH_TOL_MM))
    else:
        heights = [default_z] * len(segments)

    diameter = falcon_geom.mm_to_ft(opts["diameter_mm"])
    type_id = opts["type"].Id
    conduits, problems = [], []
    fittings = left_open = risers = 0
    with revit.TransactionGroup("Falcon: Convert Line"):
        with revit.Transaction("Falcon: Convert Line"):
            for (p0, p1), z in zip(segments, heights):
                try:
                    conduits.append(falcon_conduit.new_conduit(
                        doc, type_id, level.Id, falcon_conduit.xyz((p0[0], p0[1], z)),
                        falcon_conduit.xyz((p1[0], p1[1], z)), diameter))
                except Exception as ex:
                    conduits.append(None)
                    problems.append(u"line at ({:.1f}, {:.1f}): {}".format(p0[0], p0[1], ex))
            doc.Regenerate()

            for group in groups:
                kind, order = falcon_route.classify_joint(segments, group)
                members = [(conduits[i], segments[i][e], heights[i]) for i, e in order]
                if kind is None or any(c is None for c, _p, _z in members):
                    left_open += 1
                    continue
                conns = [falcon_conduit.end_connector(c, falcon_conduit.xyz((p[0], p[1], z)))
                         for c, p, z in members]
                if falcon_conduit.add_fitting(doc, kind, conns) is None:
                    left_open += 1
                else:
                    fittings += 1

            for i, e, panel in panel_ends:
                conduit = conduits[i]
                if conduit is None:
                    continue
                p = segments[i][e]
                top = (p[0], p[1], heights[i])
                bottom = (p[0], p[1], panel.max.Z)
                if abs(top[2] - bottom[2]) < tol:
                    continue
                try:
                    riser = falcon_conduit.new_conduit(
                        doc, type_id, level.Id, falcon_conduit.xyz(bottom),
                        falcon_conduit.xyz(top), diameter)
                    doc.Regenerate()
                    made = falcon_conduit.add_fitting(doc, "elbow", [
                        falcon_conduit.end_connector(conduit, falcon_conduit.xyz(top)),
                        falcon_conduit.end_connector(riser, falcon_conduit.xyz(top))])
                    risers += 1
                    if made is None:
                        left_open += 1
                except Exception as ex:
                    problems.append(u"riser into panel {}: {}".format(panel.element.Id, ex))

            near = falcon_geom.mm_to_ft(TOUCH_TOL_MM)
            for i, e, dev in device_ends:
                conduit = conduits[i]
                if conduit is None:
                    continue
                p = segments[i][e]
                end = falcon_conduit.xyz((p[0], p[1], heights[i]))
                target = falcon_conduit.free_conduit_connector(dev.element, end)
                if target is not None and target.Origin.DistanceTo(end) <= near:
                    try:
                        falcon_conduit.end_connector(conduit, end).ConnectTo(target)
                    except Exception:
                        pass

            if opts["delete_lines"] and used:
                made_any = any(c is not None for c in conduits)
                if made_any:
                    for el in used:
                        doc.Delete(el.Id)

    made = len([c for c in conduits if c is not None])
    lines = [u"Converted {} line(s) into {} conduit(s).".format(line_count, made + risers)]
    if fittings:
        lines.append(u"{} fitting(s) added where lines meet.".format(fittings))
    if left_open:
        lines.append(u"{} joint(s) had not enough room for a fitting and were left "
                     u"disconnected.".format(left_open))
    if opts["circuit"] and no_fixture:
        lines.append(u"{} run(s) touched no fixture and used the typed elevation.".format(
            no_fixture))
    if skipped:
        lines.append(u"Skipped {} arc / other / very short line(s).".format(skipped))
    if problems:
        lines.append(u"Problems:\n" + u"\n".join(problems))
    forms.alert(u"\n".join(lines), title=TITLE)


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Convert Line stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
