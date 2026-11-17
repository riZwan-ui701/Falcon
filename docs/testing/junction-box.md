# Junction Box — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a lighting plan with detail-line routing between fixtures giving 1-, 2-
(straight and 90°), 3- (T and Y) and 4-way junctions; a box family with types
Terminal (1-way), Through (2-way 180), Angle (2-way 90), Tee (3-way),
Branch_Y, Cross (4-way); one fixture no line touches.

| # | Do this | Expect |
|---|---|---|
| 1 | Run from a 3D view | "Open the plan view with the routing lines first." |
| 2 | Dialog: Elevation 3700 mm, "Millimeters above the level: <level>" | Start → "Select lighting fixtures, then click Finish" |
| 3 | Select all fixtures, Finish | A box at each fixture insertion point at 3700 mm; types match the line pattern |
| 4 | Look at Angle / Tee / Branch_Y boxes | Turned so their outlets face the lines |
| 5 | Report | Placed N new / updated 0; elevation; family; types; the lonely fixture skipped with "no route line intersects the fixture outline; nearest line … mm …" |
| 6 | Plan view | Zoomed to the placement points, same plan kept |
| 7 | Change a line (a 2-way becomes a T), run again at 3650 | Existing boxes updated (type, turn, 3650), none doubled; "updated N existing box(es)" |
| 8 | Routing drawn as wires or in a linked CAD | Same result |
| 9 | Ctrl+Z | Whole run undone |

## Shift+click (original tool)

| # | Do this | Expect |
|---|---|---|
| 1 | Run with no box family (empty project) | "Load a junction box family first." |
| 2 | Run, choose the 2-way box, click the middle of a conduit | Box at the click, lined up, conduit cut and connected both sides |
| 3 | Click within 300 mm of a free conduit end with the end box | Box on the end, its connector joined to the conduit |
| 4 | Click several conduits, then Esc | All placed; message counts placed / connected |
| 5 | Ctrl+Z once | Every box from the run removed, conduits whole again |
| 6 | Run again | Last box type is listed first |
| 7 | Use a box whose connectors run along Y in the family | Still lines up (turned by its connectors), or reported as "could not be connected" — never a diagonal stub |
| 8 | Click near an end that already has an elbow | Box is placed inline near that end, not on the end |
