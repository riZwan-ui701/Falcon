# Auto Dimension — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: plan with a grid of ceiling fixtures (rows and columns, some rotated
90°), one fixture alone, one family with no centre reference planes.

| # | Do this | Expect |
|---|---|---|
| 1 | Run from a 3D view | "Open a plan view first." |
| 2 | Dialog "Select Dimension Style": Linear types only, "N styles" count | Tick **Show all styles** → every dimension style, count changes |
| 3 | Pick a style, **Use Style**, select a row of 5 and a column of 2 (Finish) | One chain along the row, one along the column, through the fixture centres |
| 4 | Read the report | "Dimensions created / Groups skipped / Segment values (mm): Row 1: 2406 / 1806 …" matching the chains |
| 5 | Pre-select fixtures, then run | They stay selected in the pick |
| 6 | Include the single fixture | Counted under Groups skipped |
| 7 | Include the family with no centre references | Named under "Families missing usable center references" |
| 8 | Rotated fixtures in a row | Still dimensioned (the other centre plane is used) |
| 9 | Ctrl+Z | All chains removed |
| 10 | Run again | Last style pre-selected |

## Shift+click (original tool)

| # | Do this | Expect |
|---|---|---|
| 1 | Run with nothing selected | One dimension string per bundle (not one spanning both) (Review Focus 4), from the nearest parallel grid through each conduit |
| 2 | Check the far conduit | Dimensioned to the wall face |
| 3 | Conduit with no grid/wall within 10 m | Listed "no parallel grid or wall within 10 m" |
| 4 | Select only one bundle and run | Only that bundle dimensioned |
| 5 | Shift+click, set 1500 | Dimension line sits 1500 mm along the run from the midpoint |
| 6 | Ctrl+Z | All dimensions from the run removed |
| 7 | **Important:** check the dimension really snaps to the conduit centreline | Witness line on each conduit centre. If Revit refuses conduit references, every bundle is listed as skipped - report this |
| 8 | A grid hidden in this view near the conduits | Not used; the next visible grid or a wall is used |
