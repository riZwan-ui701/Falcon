# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Connect Conduit
# Purpose        : Draw a new conduit between two electrical elements, or
#                  carry existing conduits on into a device or panel and
#                  connect them.
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
# Input          : Dialog - Draw New Conduit (diameter + type) or Connect
#                  Conduit. Draw: click the exit point on the first element,
#                  then the second element. Connect: select conduits
#                  (Finish), then the device / panel. Repeats until Esc.
# Output         : New conduit legs with elbows, connected to free conduit
#                  connectors where the elements have them.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_route.py, falcon_geom.py, falcon_conduit.py,
#     falcon_settings.py
#
# Features       :
#   - Draw: 90-degree legs at the exit height, then a drop onto the target
#   - Connect: along each conduit's own line, then up/down to the device;
#     into a panel straight down to the middle of its top, never sideways
#   - One conduit + another conduit as target: coupling or elbow (as v1)
#   - Each conduit all-or-nothing; the whole session is one undo step
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Dialog with Draw New Conduit / Connect Conduit; many conduits at once;
#   panel drop; repeats until Esc
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

TITLE = "Falcon - Connect Conduit"
SECTION = "falcon_connectconduit"
DEFAULTS = {"mode": "connect", "type_name": "", "diameter_mm": 20.0}
FALLBACK_SIZES_MM = [16.0, 20.0, 21.0, 25.0, 27.0, 32.0, 35.0, 41.0, 50.0, 63.0]
TOL_MM = 5.0
EXIT_SNAP_MM = 100.0     # a free connector this close to the exit click is used
APPROACH_MM = 300.0      # straight run into a side connector

doc = revit.doc
uidoc = revit.uidoc
tup = falcon_conduit.tup
xyz = falcon_conduit.xyz


# ------------------------------------------------------------------ UI

class ConnectDialog(forms.WPFWindow):
    def __init__(self, settings, types):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "ConnectConduit.xaml"))
        self.types = types
        self.sizes = []
        self.last_diameter = settings["diameter_mm"]
        self.result = None
        names = [n for n, _t in types]
        for name in names:
            self.ctype.Items.Add(name)
        if names:
            self.ctype.SelectedIndex = (names.index(settings["type_name"])
                                        if settings["type_name"] in names else 0)
        (self.mode_draw if settings["mode"] == "draw" else self.mode_connect).IsChecked = True
        self.mode_changed(None, None)

    def mode_changed(self, sender, args):
        draw = bool(self.mode_draw.IsChecked)
        self.card_diameter.IsEnabled = draw
        self.card_type.IsEnabled = draw
        self.card_diameter.Opacity = 1.0 if draw else 0.5
        self.card_type.Opacity = 1.0 if draw else 0.5
        self.note.Visibility = Visibility.Collapsed if draw else Visibility.Visible

    def type_changed(self, sender, args):
        index = self.ctype.SelectedIndex
        if index < 0:
            return
        sizes = falcon_conduit.conduit_sizes_mm(doc, self.types[index][1]) or FALLBACK_SIZES_MM
        self.sizes = sizes
        self.diameter.Items.Clear()
        for mm in sizes:
            self.diameter.Items.Add(u"{:g} mm".format(mm))
        self.diameter.SelectedIndex = min(range(len(sizes)),
                                          key=lambda i: abs(sizes[i] - self.last_diameter))

    def ok_click(self, sender, args):
        draw = bool(self.mode_draw.IsChecked)
        if draw and not self.types:
            return
        result = {"mode": "draw" if draw else "connect",
                  "type_name": "", "type": None, "diameter_mm": self.last_diameter}
        if self.types and self.ctype.SelectedIndex >= 0:
            result["type_name"], result["type"] = self.types[self.ctype.SelectedIndex]
        if self.sizes and self.diameter.SelectedIndex >= 0:
            result["diameter_mm"] = self.sizes[self.diameter.SelectedIndex]
        self.result = result
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


class TargetFilter(ISelectionFilter):
    """Anything with a body: family instances and conduits."""

    def AllowElement(self, element):
        return isinstance(element, DB.FamilyInstance) or falcon_conduit.is_conduit(element)

    def AllowReference(self, reference, position):
        return True


# ------------------------------------------------------------- helpers

def tol():
    return falcon_geom.mm_to_ft(TOL_MM)


def set_end(conduit, index, point):
    p0, p1 = falcon_conduit.ends(conduit)
    if index == 0:
        falcon_conduit.set_ends(conduit, point, p1)
    else:
        falcon_conduit.set_ends(conduit, p0, point)


def end_index(conduit, point):
    p0, p1 = falcon_conduit.ends(conduit)
    return 0 if p0.DistanceTo(point) <= p1.DistanceTo(point) else 1


def is_panel(element):
    return falcon_conduit.is_panel(element)


def box_of(element):
    box = element.get_BoundingBox(None)
    if box is None:
        raise ValueError("element {} has no size in the model".format(element.Id))
    return box


def level_below(z):
    levels = sorted(DB.FilteredElementCollector(doc).OfClass(DB.Level),
                    key=lambda lv: lv.ProjectElevation)
    below = [lv for lv in levels if lv.ProjectElevation <= z + 1e-6]
    return (below[-1] if below else levels[0]).Id


def device_target(element, near):
    """(point, connector or None) where a conduit should land on element:
    its free conduit connector nearest `near`, else the middle of its top
    (or bottom, when the device is above the conduit)."""
    conn = falcon_conduit.free_conduit_connector(element, xyz(near))
    if conn is not None:
        return tup(conn.Origin), conn
    box = box_of(element)
    cx, cy = (box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0
    z = box.Min.Z if box.Min.Z > near[2] else box.Max.Z
    return (cx, cy, z), None


def build_legs(points, first, make_leg):
    """Create the route through points. `first` is an existing conduit whose
    free end is points[0] (it is extended when the first leg runs straight
    on), or None. Returns the last conduit."""
    points = falcon_route.unique_points(points, falcon_geom.mm_to_ft(1.0))
    if len(points) < 2:
        return first
    prev = first
    if first is not None:
        ia = end_index(first, xyz(points[0]))
        other = tup(falcon_conduit.ends(first)[1 - ia])
        out_dir = falcon_geom.vsub(points[0], other)
        leg = falcon_geom.vsub(points[1], points[0])
        if falcon_geom.angle_between_deg(out_dir, leg) < 1.0:
            set_end(first, ia, xyz(points[1]))
            points = points[1:]
    for p, q in zip(points, points[1:]):
        new = make_leg(xyz(p), xyz(q))
        doc.Regenerate()
        if prev is not None:
            if falcon_conduit.add_fitting(doc, "elbow", [
                    falcon_conduit.end_connector(prev, xyz(p)),
                    falcon_conduit.end_connector(new, xyz(p))]) is None:
                raise ValueError("Revit could not add an elbow (the legs are too short "
                                 "for the bend)")
        prev = new
    return prev


def connect_last(conduit, conn):
    if conn is None or conduit is None:
        return
    doc.Regenerate()
    end = falcon_conduit.end_connector(conduit, conn.Origin)
    if end is not None and end.Origin.DistanceTo(conn.Origin) <= tol():
        end.ConnectTo(conn)


# ------------------------------------------------- conduit -> conduit (v1)

def check_free(conduit, index):
    point = falcon_conduit.ends(conduit)[index]
    if falcon_conduit.end_connector(conduit, point).IsConnected:
        raise ValueError("conduit {} is already connected at that end".format(conduit.Id))


def connect_conduits(a, ia, b):
    t = tol()
    a0, a1 = [tup(p) for p in falcon_conduit.ends(a)]
    b0, b1 = [tup(p) for p in falcon_conduit.ends(b)]
    a_end, a_other = (a0, a1) if ia == 0 else (a1, a0)
    ib = end_index(b, xyz(a_end))
    check_free(a, ia)
    check_free(b, ib)
    da, db = falcon_geom.vsub(a1, a0), falcon_geom.vsub(b1, b0)
    if falcon_geom.is_vertical(da) or falcon_geom.is_vertical(db):
        raise ValueError("vertical conduits are not supported")
    if abs(a0[2] - a1[2]) > t or abs(b0[2] - b1[2]) > t or abs(a_end[2] - b0[2]) > t:
        raise ValueError("the conduits are not level at the same height")

    if falcon_geom.joint_kind(da, db) == "union":
        b_near = (b0, b1)[ib]
        flat = lambda p: (p[0], p[1], 0.0)
        d = falcon_geom.project_distance(flat(a_other), flat(a_end), flat(b_near))
        foot = falcon_geom.point_along(flat(a_other), flat(a_end), d)
        if falcon_geom.vlen(falcon_geom.vsub(foot, flat(b_near))) > t:
            raise ValueError("these conduits are parallel but not in line")
        set_end(a, ia, xyz(b_near))
        doc.Regenerate()
        if falcon_conduit.connect_union(doc, a, b) is None:
            raise ValueError("Revit could not add a coupling")
        return

    corner = falcon_geom.line_intersection_xy(a0, a1, b0, b1)
    corner = (corner[0], corner[1], a_end[2])
    b_near, b_other = ((b0, b1) if ib == 0 else (b1, b0))
    if (falcon_geom.vdot(falcon_geom.vsub(corner, a_other), falcon_geom.vsub(a_end, a_other)) <= 0
            or falcon_geom.vdot(falcon_geom.vsub(corner, b_other), falcon_geom.vsub(b_near, b_other)) <= 0):
        raise ValueError("the conduits point away from each other")
    set_end(a, ia, xyz(corner))
    set_end(b, ib, xyz(corner))
    doc.Regenerate()
    if falcon_conduit.connect_elbow(doc, a, b) is None:
        raise ValueError("Revit could not add an elbow (check bend radius / lengths)")


# ------------------------------------------------------- connect mode

def free_end_toward(conduit, point):
    """Index of the conduit's unconnected end nearest point (plan)."""
    p0, p1 = [tup(p) for p in falcon_conduit.ends(conduit)]
    order = sorted((0, 1), key=lambda i: falcon_geom.vlen(falcon_geom.vsub(
        ((p0, p1)[i][0], (p0, p1)[i][1], 0.0), (point[0], point[1], 0.0))))
    for i in order:
        if not falcon_conduit.end_connector(conduit, xyz((p0, p1)[i])).IsConnected:
            return i
    raise ValueError("both ends are already connected")


def connect_one(conduit, target):
    box = box_of(target)
    center = ((box.Min.X + box.Max.X) / 2.0, (box.Min.Y + box.Max.Y) / 2.0, box.Max.Z)
    ia = free_end_toward(conduit, center)
    ends = [tup(p) for p in falcon_conduit.ends(conduit)]
    end, other = ends[ia], ends[1 - ia]
    direction = falcon_geom.vsub(end, other)
    if falcon_geom.is_vertical(direction):
        raise ValueError("vertical conduit ends are not supported")
    make = lambda p, q: falcon_conduit.new_conduit_like(doc, conduit, p, q)
    if is_panel(target):
        pts = falcon_route.drop_into_panel(end, direction, center, box.Max.Z, tol())
        build_legs(pts, conduit, make)
        return
    point, conn = device_target(target, end)
    if conn is not None and abs(conn.CoordinateSystem.BasisZ.Z) < 0.7:
        # side connector: change height first, then run straight into it
        pts = falcon_geom.route_points(
            end, point, tup(conn.CoordinateSystem.BasisZ),
            approach=falcon_geom.mm_to_ft(APPROACH_MM))
    else:
        pts = falcon_route.continue_to(end, direction, point, tol())
    last = build_legs(pts, conduit, make)
    connect_last(last, conn)


def run_connect():
    """One round: conduits, then target. False when the user pressed Esc."""
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, falcon_conduit.ConduitFilter(),
            "Select the conduits to connect, then click Finish (Esc to exit)")
        if not refs:
            return False
        ref_t = uidoc.Selection.PickObject(
            ObjectType.Element, TargetFilter(),
            "Click the device or panel to connect them to (Esc to exit)")
    except OperationCanceledException:
        return False
    conduits = [doc.GetElement(r.ElementId) for r in refs]
    target = doc.GetElement(ref_t.ElementId)
    done, refused = 0, []
    with revit.Transaction("Falcon: Connect Conduit"):
        for conduit in conduits:
            if conduit.Id == target.Id:
                continue
            try:
                if falcon_conduit.is_conduit(target):
                    if len(conduits) != 1:
                        raise ValueError("pick one conduit to join to another conduit")
                    # join the end of the conduit that faces the target
                    t0, t1 = falcon_conduit.ends(target)
                    ia = end_index(conduit, t0.Add(t1).Multiply(0.5))
                    falcon_conduit.all_or_nothing(
                        doc, lambda: connect_conduits(conduit, ia, target))
                else:
                    falcon_conduit.all_or_nothing(doc, lambda: connect_one(conduit, target))
                done += 1
            except Exception as ex:
                refused.append(u"{}: {}".format(conduit.Id, ex))
    if refused:
        forms.alert(u"Connected {} conduit(s).\nNot connected:\n{}".format(
            done, u"\n".join(refused)), title=TITLE)
    return True


# ---------------------------------------------------------- draw mode

def run_draw(opts):
    try:
        ref_a = uidoc.Selection.PickObject(
            ObjectType.PointOnElement,
            "Click the exit point on the first element (Esc to exit)")
        ref_b = uidoc.Selection.PickObject(
            ObjectType.Element, TargetFilter(),
            "Click the second element (Esc to exit)")
    except OperationCanceledException:
        return False
    first = doc.GetElement(ref_a.ElementId)
    second = doc.GetElement(ref_b.ElementId)
    if first.Id == second.Id:
        forms.alert("Pick two different elements.", title=TITLE)
        return True
    start = tup(ref_a.GlobalPoint)
    start_conn = falcon_conduit.free_conduit_connector(first, ref_a.GlobalPoint)
    if (start_conn is not None
            and start_conn.Origin.DistanceTo(ref_a.GlobalPoint) <= falcon_geom.mm_to_ft(EXIT_SNAP_MM)):
        start = tup(start_conn.Origin)
    else:
        start_conn = None
    point, end_conn = device_target(second, start)
    pts = falcon_route.l_route(start, point, tol())
    diameter = falcon_geom.mm_to_ft(opts["diameter_mm"])
    level_id = level_below(start[2])
    type_id = opts["type"].Id

    def make(p, q):
        return falcon_conduit.new_conduit(doc, type_id, level_id, p, q, diameter)

    def route():
        if len(falcon_route.unique_points(pts, tol())) < 2:
            raise ValueError("the two points are the same")
        first_leg = make(xyz(pts[0]), xyz(pts[1]))
        doc.Regenerate()
        connect_last(first_leg, start_conn)
        last = build_legs(pts[1:], first_leg, make)
        connect_last(last, end_conn)

    with revit.Transaction("Falcon: Connect Conduit"):
        try:
            falcon_conduit.all_or_nothing(doc, route)
        except ValueError as ex:
            forms.alert(u"Not drawn: {}.\nNothing was changed.".format(ex), title=TITLE)
    return True


# ----------------------------------------------------------------- main

def main():
    if doc is None:
        forms.alert("Please open a Revit project first.", title=TITLE)
        return
    types = falcon_conduit.conduit_types(doc)
    dialog = ConnectDialog(falcon_settings.load(SECTION, DEFAULTS), types)
    dialog.show_dialog()
    opts = dialog.result
    if opts is None:
        return
    falcon_settings.save(SECTION, dict((k, opts[k]) for k in DEFAULTS))
    if opts["mode"] == "draw" and opts["type"] is None:
        forms.alert("This project has no conduit types.", title=TITLE)
        return
    with revit.TransactionGroup("Falcon: Connect Conduit"):
        while True:
            more = run_draw(opts) if opts["mode"] == "draw" else run_connect()
            if not more:
                break


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Connect Conduit stopped.**")
    output.print_code(traceback.format_exc())
