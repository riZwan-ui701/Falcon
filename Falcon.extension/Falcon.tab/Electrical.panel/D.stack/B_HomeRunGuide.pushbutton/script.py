# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Home Run Guide
# Purpose        : Turn one drawn trunk route (detail lines) into offset
#                  home-run lanes: every branch line touching the trunk gets
#                  its own parallel lane back to the panel end, spaced apart
#                  and arranged so the lanes don't cross the branches.
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
# Input          : 3-step wizard - trunk detail lines (Finish), route
#                  spacing (mm, remembered), start marker (panel end).
# Output         : Detail lines for each lane (same line style as the
#                  trunk); branch ends moved onto their lanes; trunk removed.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_route.py, falcon_geom.py, falcon_settings.py
#
# Features       :
#   - Preview first: "Keep these lines?" No puts everything back
#   - Re-running on the same branches replaces the lanes made before
#   - The whole run is one undo step
#
# Notes          :
#   - Designed for production BIM workflows.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#   - Project only: exits with a message in the Family Editor.
#
# Changelog
# ------------------------------------------------------------
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import json
import os
import traceback

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import Visibility
from System.Windows.Media import SolidColorBrush, Color

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType, ISelectionFilter
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_route
import falcon_settings
import falcon_safety
from falcon_color import eid_int, eid_from

TITLE = "Falcon - Home Run Guide"
SECTION = "falcon_homerunguide"
DEFAULTS = {"spacing_mm": 50.0}
TOL_MM = 5.0
MARKER_PAPER_MM = 4.0      # marker square size on paper
MARKER_MIN_MM = 150.0

doc = revit.doc
uidoc = revit.uidoc


# ------------------------------------------------------------------ UI

class Wizard(forms.WPFWindow):
    BUTTONS = {1: "Continue to selection", 2: "OK", 3: "Pick start point"}

    def __init__(self, step, spacing_mm=None):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "HomeRunGuide.xaml"))
        self.go = False
        self.value = None
        self.step = step
        for n in (1, 2, 3):
            getattr(self, "step%d" % n).Visibility = (
                Visibility.Visible if n == step else Visibility.Collapsed)
            pill = getattr(self, "pill%d" % n)
            text = getattr(self, "pill%d_text" % n)
            if n == step:
                pill.Background = SolidColorBrush(Color.FromRgb(0x4F, 0xD1, 0xC5))
                text.Foreground = SolidColorBrush(Color.FromRgb(0x14, 0x1B, 0x2D))
        self.go_button.Content = self.BUTTONS[step]
        if step == 2:
            self.spacing.Text = "{:g}".format(spacing_mm)
            self.spacing.Focus()
            self.spacing.SelectAll()

    def go_click(self, sender, args):
        if self.step == 2:
            try:
                value = float(self.spacing.Text.replace(",", "."))
            except ValueError:
                value = 0
            if value <= 0:
                self.error.Text = "Enter a spacing above 0 mm."
                return
            self.value = value
        self.go = True
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


class LineFilter(ISelectionFilter):
    """Straight detail lines in the active view (optionally only some ids)."""

    def __init__(self, view_id, only=None):
        self.view_id = eid_int(view_id)
        self.only = only

    def AllowElement(self, element):
        if self.only is not None:
            return eid_int(element.Id) in self.only
        return is_detail_line(element) and eid_int(element.OwnerViewId) == self.view_id

    def AllowReference(self, reference, position):
        return False


# --------------------------------------------------------------- helpers

def is_detail_line(element):
    return (isinstance(element, DB.CurveElement)
            and element.CurveElementType == DB.CurveElementType.DetailCurve
            and isinstance(element.GeometryCurve, DB.Line))


def ends_of(line_el):
    c = line_el.GeometryCurve
    p, q = c.GetEndPoint(0), c.GetEndPoint(1)
    return (p.X, p.Y, p.Z), (q.X, q.Y, q.Z)


def xyz(t):
    return DB.XYZ(t[0], t[1], t[2])


def new_line(view, a, b, style):
    line = doc.Create.NewDetailCurve(view, DB.Line.CreateBound(xyz(a), xyz(b)))
    if style is not None:
        line.LineStyle = style
    return line


def draw_marker(view, center, size, style):
    h = size / 2.0
    c = center
    corners = [(c[0] - h, c[1] - h, c[2]), (c[0] + h, c[1] - h, c[2]),
               (c[0] + h, c[1] + h, c[2]), (c[0] - h, c[1] + h, c[2])]
    return [new_line(view, a, b, style) for a, b in zip(corners, corners[1:] + corners[:1])]


def view_key(view):
    return "routes_" + view.UniqueId.replace("-", "_")


def load_previous(view):
    raw = falcon_settings.load(SECTION, {view_key(view): ""})[view_key(view)]
    try:
        return json.loads(raw) if raw else {}
    except ValueError:
        return {}


def save_previous(view, mapping):
    falcon_settings.save(SECTION, {view_key(view): json.dumps(mapping)})


def chains_size(candidates, branch_ids, tol):
    """How many lines are in the branch chains (lines joined end to end
    with the branches)."""
    ends = dict((eid_int(c.Id), ends_of(c)) for c in candidates)
    seen = set(branch_ids)
    todo = list(branch_ids)
    while todo:
        cur = todo.pop()
        for p in ends[cur]:
            for other, (a, b) in ends.items():
                if other in seen:
                    continue
                if falcon_geom.vlen(falcon_geom.vsub(a, p)) <= tol or \
                        falcon_geom.vlen(falcon_geom.vsub(b, p)) <= tol:
                    seen.add(other)
                    todo.append(other)
    return len(seen)


# ----------------------------------------------------------------- main

def main():
    if not falcon_safety.project_only(doc, TITLE):
        return
    view = doc.ActiveView
    if view is None or view.ViewType not in (
            DB.ViewType.FloorPlan, DB.ViewType.CeilingPlan, DB.ViewType.EngineeringPlan,
            DB.ViewType.DraftingView, DB.ViewType.AreaPlan):
        forms.alert("Open the plan view where the route is drawn first.", title=TITLE)
        return
    tol = falcon_geom.mm_to_ft(TOL_MM)

    # 1 - select the trunk
    step = Wizard(1)
    step.show_dialog()
    if not step.go:
        return
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, LineFilter(view.Id),
            "Select Reference Line (click Finish when done)")
    except OperationCanceledException:
        return
    trunk_lines = [doc.GetElement(r.ElementId) for r in refs]
    if not trunk_lines:
        return
    try:
        trunk = falcon_route.chain_polyline([ends_of(l) for l in trunk_lines], tol)
    except ValueError as ex:
        forms.alert(u"{}.".format(ex), title=TITLE)
        return

    # 2 - spacing
    settings = falcon_settings.load(SECTION, DEFAULTS)
    step = Wizard(2, settings["spacing_mm"])
    step.show_dialog()
    if not step.go:
        return
    spacing_mm = step.value
    falcon_settings.save(SECTION, {"spacing_mm": spacing_mm})
    spacing = falcon_geom.mm_to_ft(spacing_mm)

    # 3 - start point (temporary markers), then preview
    style = trunk_lines[0].LineStyle
    style_id = eid_int(style.Id) if style is not None else None
    trunk_ids = set(eid_int(l.Id) for l in trunk_lines)
    size = max(falcon_geom.mm_to_ft(MARKER_MIN_MM),
               falcon_geom.mm_to_ft(MARKER_PAPER_MM) * max(view.Scale, 1))

    group = DB.TransactionGroup(doc, "Falcon: Home Run Guide")
    group.Start()
    try:
        kept, summary = run_in_group(view, trunk, trunk_lines, trunk_ids, style,
                                     style_id, spacing, spacing_mm, size, tol)
    except Exception:
        group.RollBack()
        raise
    if kept:
        group.Assimilate()
    else:
        group.RollBack()
    if summary:
        forms.alert(summary, title=TITLE)


def run_in_group(view, trunk, trunk_lines, trunk_ids, style, style_id,
                 spacing, spacing_mm, size, tol):
    """Markers -> pick -> preview -> ask. Returns (keep, closing message)."""
    with revit.Transaction("Falcon: Home Run Guide markers"):
        start_marks = draw_marker(view, trunk[0], size, style)
        end_marks = draw_marker(view, trunk[-1], size, style)
    step = Wizard(3)
    step.show_dialog()
    if not step.go:
        return False, None
    marker_ids = set(eid_int(m.Id) for m in start_marks + end_marks)
    try:
        ref = uidoc.Selection.PickObject(
            ObjectType.Element, LineFilter(view.Id, marker_ids),
            "Pick Start Point (click a square marker)")
    except OperationCanceledException:
        return False, None
    if eid_int(ref.ElementId) in set(eid_int(m.Id) for m in end_marks):
        trunk = list(reversed(trunk))

    # branches: same-style detail lines with exactly one end on the trunk
    candidates = [e for e in DB.FilteredElementCollector(doc, view.Id)
                  .OfClass(DB.CurveElement)
                  if is_detail_line(e) and eid_int(e.Id) not in trunk_ids
                  and eid_int(e.Id) not in marker_ids
                  and (style_id is None or (e.LineStyle is not None
                                            and eid_int(e.LineStyle.Id) == style_id))]
    branches = []
    for line in candidates:
        a, b = ends_of(line)
        on_a = falcon_route.locate_on_polyline(trunk, a, tol)
        on_b = falcon_route.locate_on_polyline(trunk, b, tol)
        if (on_a is None) == (on_b is None):
            continue
        touch_end, hit, other = (0, on_a, b) if on_a is not None else (1, on_b, a)
        if hit[1] <= tol:
            continue            # joins at the start itself - no lane needed
        seg, along = hit
        touch = falcon_route.point_at(trunk, seg, along)
        side = falcon_route.branch_side(trunk, seg, touch, other)
        branches.append({"line": line, "end": touch_end, "seg": seg,
                         "along": along, "side": side, "other": other})
    owned_trunk = [falcon_safety.owner_note(doc, l) for l in trunk_lines]
    owned_trunk = [n for n in owned_trunk if n]
    if owned_trunk:
        return False, (u"The reference line can't be removed: {}.\n"
                       u"Nothing was changed.".format(owned_trunk[0]))
    ws_skipped = [b for b in branches if falcon_safety.owner_note(doc, b["line"])]
    branches = [b for b in branches if b not in ws_skipped]
    if not branches:
        return False, (u"No branch lines touch the reference line.\n"
                       u"Draw the branches with the same line style as the "
                       u"reference line, ending on it.")

    lanes = falcon_route.assign_lanes([(b["along"], b["side"]) for b in branches])
    previous = load_previous(view)
    new_mapping = {}
    segments = []
    with revit.Transaction("Falcon: Home Run Guide preview"):
        for m in start_marks + end_marks:
            doc.Delete(m.Id)
        for br, (side, lane) in zip(branches, lanes):
            offset = falcon_route.lane_offset(side, lane, spacing)
            path = falcon_route.unique_points(
                falcon_route.lane_path(trunk, br["seg"], br["along"], offset), tol)
            made = [new_line(view, p, q, style) for p, q in zip(path, path[1:])]
            segments.extend(zip(path, path[1:]))
            # move the branch's end onto its lane
            other = br["other"]
            br["line"].SetGeometryCurve(
                DB.Line.CreateBound(xyz(other), xyz(path[0])) if br["end"] == 1
                else DB.Line.CreateBound(xyz(path[0]), xyz(other)), True)
            segments.append((other, path[0]))
            new_mapping[str(eid_int(br["line"].Id))] = [eid_int(l.Id) for l in made]

    crossing = falcon_route.count_crossings(segments, tol)
    per_side = {1: len([1 for s, _l in lanes if s == 1]),
                -1: len([1 for s, _l in lanes if s == -1])}
    unique = chains_size(candidates, [eid_int(b["line"].Id) for b in branches], tol) \
        + len(trunk_lines)
    msg = (u"Preview created for {} reference route(s).\n\n"
           u"Guide offset: {:g} mm\n"
           u"Unique detail-line segments: {}\n"
           u"Lanes assigned per side of the trunk: {} left, {} right. "
           u"Crossing score: {}.\n"
           u"Previous generated routes will be replaced, and the selected "
           u"reference guide removed, when you keep these routes.\n\n"
           u"Keep these lines?").format(len(branches), spacing_mm, unique,
                                        per_side[1], per_side[-1], crossing)
    if ws_skipped:
        msg = msg.replace(u"\n\nKeep these lines?", u"\n{} branch line(s) skipped: borrowed by "
                          u"another user.\n\nKeep these lines?".format(len(ws_skipped)))
    if not forms.alert(msg, title="Falcon - Home Run Guide Preview", yes=True, no=True):
        return False, None

    with revit.Transaction("Falcon: Home Run Guide"):
        for branch_id in new_mapping:
            for old in previous.get(branch_id, []):
                el = doc.GetElement(eid_from(old))
                if el is not None and is_detail_line(el):
                    doc.Delete(el.Id)
            previous[branch_id] = new_mapping[branch_id]
        for line in trunk_lines:
            doc.Delete(line.Id)
    save_previous(view, previous)
    return True, None


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Home Run Guide stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
