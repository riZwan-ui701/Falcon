# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Pull Box
# Purpose        : Place pull boxes along a conduit run automatically -
#                  every N metres and after every N 90-degree bends.
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
# Input          : Spacing (m), bends limit, riser option, box type;
#                  the conduits (a whole bundle at once, Finish), then a
#                  click on the start point at the panel side.
# Output         : Junction/pull box instances on the run. 2-way boxes
#                  cut the conduit and are connected to both sides.
#
# Dependencies   :
#   - pyRevit
#   - Revit API
#   - Falcon.extension/lib/falcon_geom.py, falcon_conduit.py, falcon_settings.py
#
# Features       :
#   - Follows the run through elbows and fittings
#   - Existing junction boxes restart the count
#   - Remembers the last values used
#   - Every selected run gets its own boxes; one undo step
#
# Notes          :
#   - Designed for production BIM workflows.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#   - Project only: exits with a message in the Family Editor.
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Select many conduits (a bundle) and click the panel-side start
#   point; each run is measured from there
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os
import traceback

from pyrevit import revit, forms, script
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_geom
import falcon_conduit
import falcon_settings
import falcon_safety
from falcon_color import eid_int

TITLE = "Falcon - Pull Box"
SECTION = "falcon_pullbox"
DEFAULTS = {"distance_m": 15.0, "bends": 2, "riser": False, "box_label": ""}
AFTER_BEND_MM = 300.0
END_MARGIN_MM = 150.0   # keep boxes this far from conduit joints

doc = revit.doc
uidoc = revit.uidoc


class PullBoxDialog(forms.WPFWindow):
    def __init__(self, settings, symbols):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "PullBox.xaml"))
        self.symbols = symbols
        self.result = None
        self.distance.Text = str(settings["distance_m"])
        self.bends.Text = str(settings["bends"])
        self.riser.IsChecked = settings["riser"]
        labels = [label for label, _sym in symbols]
        for label in labels:
            self.box.Items.Add(label)
        self.box.SelectedIndex = (labels.index(settings["box_label"])
                                  if settings["box_label"] in labels else 0)
        self.distance.Focus()
        self.distance.SelectAll()

    def start_click(self, sender, args):
        try:
            distance = float(self.distance.Text.replace(",", "."))
            bends = int(self.bends.Text)
        except ValueError:
            self.error.Text = "Enter a number for distance and a whole number for bends."
            return
        if distance <= 0 or bends < 1:
            self.error.Text = "Distance must be more than 0 and bends at least 1."
            return
        index = self.box.SelectedIndex
        self.result = {
            "distance_m": distance,
            "bends": bends,
            "riser": bool(self.riser.IsChecked),
            "box_label": self.symbols[index][0],
            "symbol": self.symbols[index][1],
        }
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


def place_all(run, boxes, symbol):
    """Place boxes last-to-first.

    Each box is all-or-nothing: if cutting/connecting fails, that box is
    rolled back and listed with the real reason.
    Returns (placed, connected, not_cut_reasons, skipped)."""
    pieces = {}
    placed = connected = 0
    not_cut = {}
    skipped = []
    for seg_index, dist in reversed(boxes):
        seg = run[seg_index]
        point = falcon_conduit.xyz(falcon_geom.point_along(
            falcon_conduit.tup(seg["p_start"]), falcon_conduit.tup(seg["p_end"]), dist))
        candidates = pieces.setdefault(seg_index, [seg["element"]])
        host = None
        for piece in candidates:
            if falcon_conduit.conduit_contains(piece, point):
                host = piece
                break
        if host is None:
            skipped.append(u"{}: box point is not on the conduit any more".format(
                seg["element"].Id))
            continue
        try:
            _inst, new_piece, note = falcon_conduit.all_or_nothing(
                doc, lambda: falcon_conduit.place_box(doc, symbol, host, point))
        except Exception as ex:
            skipped.append(u"{}: {}".format(host.Id, ex))
            continue
        placed += 1
        if new_piece is not None:
            connected += 1
            candidates.append(new_piece)
        elif note:
            not_cut[note] = not_cut.get(note, 0) + 1
    return placed, connected, not_cut, skipped


def main():
    if not falcon_safety.project_only(doc, TITLE):
        return
    symbols = falcon_conduit.box_symbols(doc)
    if not symbols:
        forms.alert("Load a junction box family first.", title=TITLE)
        return

    dialog = PullBoxDialog(falcon_settings.load(SECTION, DEFAULTS), symbols)
    dialog.show_dialog()
    opts = dialog.result
    if opts is None:
        return
    falcon_settings.save(SECTION, dict((k, opts[k]) for k in DEFAULTS))

    selected, owned = falcon_safety.split_editable(doc, pick_conduits())
    if not selected:
        return
    try:
        start = uidoc.Selection.PickPoint(
            "Click the start point (panel side). Distances are measured from here.")
    except OperationCanceledException:
        return

    runs = runs_from(selected, start)
    total_placed = 0
    report, skipped = [], list(owned)
    with revit.TransactionGroup("Falcon: Pull Box"):
        with revit.Transaction("Falcon: Pull Box"):
            for n, run in enumerate(runs, 1):
                walked = []
                for item in run:
                    if item["kind"] == "branch":
                        break
                    walked.append(item)
                length_m = sum(i["length"] for i in walked) * falcon_geom.MM_PER_FT / 1000.0
                bend_count = len([i for i in walked if i["kind"] == "bend"])
                boxes = falcon_geom.plan_pull_boxes(
                    run, falcon_geom.m_to_ft(opts["distance_m"]), opts["bends"],
                    falcon_geom.mm_to_ft(AFTER_BEND_MM), 1 if opts["riser"] else 0,
                    end_margin=falcon_geom.mm_to_ft(END_MARGIN_MM))
                if not boxes:
                    report.append(u"Run {}: no pull box needed ({:.1f} m, {} bend(s)).".format(
                        n, length_m, bend_count))
                    continue
                placed, _joined, not_cut, run_skipped = place_all(run, boxes, opts["symbol"])
                total_placed += placed
                skipped.extend(run_skipped)
                report.append(u"Run {}: {} pull box(es) along {:.1f} m with {} bend(s).".format(
                    n, placed, length_m, bend_count))
                for reason, count in sorted(not_cut.items()):
                    report.append(u"   {} placed without cutting the conduit: {}.".format(
                        count, reason))
                if run and run[-1]["kind"] == "branch":
                    report.append(u"   Run branches at {}; stopped there.".format(
                        run[-1]["element"].Id))

    lines = [u"Placed {} pull box(es) on {} run(s).".format(total_placed, len(runs))]
    lines.extend(report)
    if skipped:
        lines.append(u"Skipped:\n" + u"\n".join(skipped))
    forms.alert(u"\n".join(lines), title=TITLE)


def pick_conduits():
    picked = [doc.GetElement(i) for i in uidoc.Selection.GetElementIds()]
    picked = [e for e in picked if falcon_conduit.is_conduit(e)]
    if picked:
        return picked
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element, falcon_conduit.ConduitFilter(),
            "Select the conduits to place pull boxes on, then click Finish")
    except OperationCanceledException:
        return []
    return [doc.GetElement(r.ElementId) for r in refs]


def runs_from(conduits, start):
    """Split the selected conduits into runs, each traced from its end
    nearest the start point. A run stops where it leaves the selection."""
    left = dict((eid_int(c.Id), c) for c in conduits)
    runs = []

    def gap(c):
        return min(falcon_geom.vlen(falcon_geom.vsub(
            (p.X, p.Y, 0.0), (start.X, start.Y, 0.0))) for p in falcon_conduit.ends(c))
    while left:
        first = min(left.values(), key=gap)
        p0, p1 = falcon_conduit.ends(first)
        entry = min((p0, p1), key=lambda p: (p.X - start.X) ** 2 + (p.Y - start.Y) ** 2)
        run = []
        for item in falcon_conduit.trace_run(doc, first, entry):
            el = item["element"]
            if falcon_conduit.is_conduit(el) and eid_int(el.Id) not in left:
                break
            run.append(item)
            left.pop(eid_int(el.Id), None)
        left.pop(eid_int(first.Id), None)
        if run:
            runs.append(run)
    return runs


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Pull Box stopped. Nothing was changed.**")
    output.print_code(traceback.format_exc())
