# Home Run Guide — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a lighting plan with a panel. With one line style (e.g. "normal")
draw a trunk from the panel (3–4 connected detail lines with corners) and
6+ branch lines from rooms, each ending on the trunk, from both sides.

| # | Do this | Expect |
|---|---|---|
| 1 | Run in a 3D view | "Open the plan view where the route is drawn first." |
| 2 | Run; step 1 shows **1 SELECT** highlighted, **Continue to selection** | Picking starts with "Select Reference Line (click Finish when done)" |
| 3 | Pick two trunk lines that don't touch, Finish | "the reference lines must touch end to end in one chain" |
| 4 | Pick the whole trunk, Finish | Step 2 **Set Offset**, ROUTE SPACING 50 mm |
| 5 | Type `0`, OK | "Enter a spacing above 0 mm." |
| 6 | 50, OK | Step 3 **Pick Start Point**; square markers appear at both trunk ends |
| 7 | Click the marker at the panel end | Preview: one lane per branch along the trunk to the panel, 50 mm apart; dialog lists routes, segments, lanes per side, crossing score 0 |
| 8 | Answer **No** | Everything back as before (markers gone, branches unchanged) |
| 9 | Run again, answer **Yes** | Trunk deleted, lanes kept, each branch end on its lane |
| 10 | Ctrl+Z once | Whole run undone |
| 11 | Move a branch, run again on a new trunk with **Yes** | Old lanes of those branches deleted and replaced |
| 12 | Click the far-end marker instead | Lanes run toward the far end |
| 13 | Draw branches in another line style | "No branch lines touch the reference line…" |
| 14 | Convert Line → Line Style on the result | Bundle of parallel conduits |
