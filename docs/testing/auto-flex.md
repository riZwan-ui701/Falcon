# Auto Flex — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a ceiling plan with conduit runs through junction boxes and light
fixtures below them. Load **two different** junction box families: one with
types Through / Tee (3-way) / Cross in one family, and one where each outlet
count is its own family (e.g. "JB 2-Way", "JB 3-Way"). The project needs a
flex pipe type and a piping system type (any MEP template has them).

| # | Do this | Expect |
|---|---|---|
| 1 | Run in a project with no light fixtures | "There are no light fixtures in the model." |
| 2 | Run; dialog shows **Flex Diameter (mm)** with 20 … 300 | Last diameter pre-selected (20 the first time) |
| 3 | Pick 20, **Select Ceiling Box**, pick two end boxes (one free outlet), **Finish** | One flex per box from the free outlet down onto the nearest fixture; result "Flex created: 2 / Boxes switched…: 0 / Skipped / failed: 0" |
| 4 | Pick a **Through** box with conduit on both outlets | Box becomes **Tee (3-way)**; both conduits still connected (select a conduit end — no free-end glyph); flex leaves from the new branch outlet; "switched: 1" |
| 5 | Pick a **Tee** box with all three outlets used | Becomes **Cross**; conduits connected; flex from the 4th outlet |
| 6 | Pick a **Cross** box with all four used | Skipped: "every outlet is taken and the family has no type with more outlets"; box unchanged |
| 7 | Repeat 4 with the second (one-family-per-type) box family | Switched to the 3-way family of the same conduit size; conduits connected |
| 8 | Pre-select boxes, then run | They are already ticked in the pick; Finish runs them |
| 9 | Run again on boxes that already got a flex | Skipped: "already has a flex"; no second flex |
| 10 | Pick a box whose family is not a junction box name but has conduit connectors | Allowed and handled like any box |
| 11 | Ctrl+Z once | Every flex and every type switch from the run undone, conduits back as before |
| 12 | Change diameter to 25 and run | Flex pipes are 25 mm |
