# Coloring — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup (any Revit 2020-2027): a project with lighting fixtures of 2+ types, conduits, a few floor
plans (some with a view template, one without) and a 3D view.

| # | Do this | Expect |
|---|---|---|
| 0 | Click **Coloring** | "What do you want to color?" with Color Family / Color Element cards and Close; it comes back after each job until Close |
| 1 | **Color Family** | Window opens; tree lists families with their category in grey brackets |
| 2 | Untick "Only families that are used" | Unused families appear; tick again → they disappear |
| 3 | Type part of a family name in the search box | Only matching families/types are listed, expanded |
| 4 | Click (don't tick) one **type** row, press **Choose color…**, pick cyan, OK | "Selected: Type: …"; status `Colored type "Family : Type" in N view(s). 3D views were left out. M element(s) match.` Swatch shows cyan |
| 5 | Look at plans with and without a template | That type is cyan in both; other types unchanged; 3D view unchanged |
| 6 | Open the template's V/G → Filters | `FALCON_COLOR_Family__Type` is there with the colour |
| 7 | Tick a **family** (no types), tick **Also apply in 3D views**, choose red | Whole family red in plans **and** 3D |
| 8 | Tick a family whose name has `:` or `[ ]` in it, choose a colour | Works; filter name has `_` in place of those characters |
| 9 | Tick the type from step 4, **Remove color from selected** | Cyan gone everywhere; swatch cleared |
| 10 | **Remove all Coloring colors** → Yes | Every FALCON_COLOR filter removed; other filters untouched |
| 11 | Ctrl+Z after step 4 | Colour from step 4 removed in one undo |
| 12 | **Color Element**, select 2 conduits and an elbow (Finish) | Filter selection: "3 elements selected…", Conduits (2), Conduit Fittings (1), Check all / Uncheck all |
| 13 | Untick Conduit Fittings, OK, pick a colour | Only the 2 conduits coloured, in this view and all 3D views; message gives counts |
