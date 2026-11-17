# Convert Line — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: plan view; detail lines in style "normal": an L, two lines end-to-end
in a straight line, a T (a line ending on the middle of another), a +, one
arc; a panel and some ceiling junction boxes/fixtures where lines end; a
linked DWG with lines.

| # | Do this | Expect |
|---|---|---|
| 1 | Run from a 3D view | "Open a plan view first…" |
| 2 | Dialog: 1 Selection / 2 Conduit Type / 3 Conduit Diameter / 4 Elevation, Delete original lines, Cancel / Start | As in the video; Line Style list holds the styles used in this view |
| 3 | Change Conduit Type | Diameter list changes to that type's sizes (e.g. 16, 20, 21, 25 … mm) |
| 4 | Select Line → pick the L + straight pair + arc, Elevation 3950 | Straight pair = **one** conduit; elbow at the L; "Skipped 1 arc…"; conduits 3950 mm above the level |
| 5 | Line Style "normal" → Start | Every "normal" line in the view converted; message "Converted N line(s) into M conduit(s)" with M < N when lines run straight on |
| 6 | The T and the + | Tee and cross fittings |
| 7 | Two lines meeting at a corner that is too short for an elbow | Counted in "joint(s) had not enough room for a fitting and were left disconnected" |
| 8 | Delete original lines ticked | Converted lines gone; unticked → lines stay |
| 9 | Circuit Elevation, run from a panel to fixtures | Run at the fixtures' height; a riser comes out of the panel top and joins with an elbow; ends on a box connector are connected |
| 10 | Circuit Elevation with a run touching nothing | Uses the typed elevation; message says how many runs did |
| 11 | CAD Lines → pick DWG lines | Conduits lie exactly on the DWG lines (no doubles from one polyline) |
| 12 | Ctrl+Z | Everything from the run undone (lines back if they were deleted) |
| 13 | Run again | Dialog shows last values |
