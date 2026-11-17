# Wiring Pro — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a lighting plan with a grid of ceiling fixtures (some rotated 90°, one
row with a gap), a room with wall sockets on several walls, a panel with a
distribution system, a lighting-fixture circuit tag and a wire type loaded.

| # | Do this | Expect |
|---|---|---|
| 1 | Run from a 3D view | "Open the plan view of the outlets first." |
| 2 | Dialog | Outlet type, Wire color, Connection, Circuit, Tag sections as in the video; Wall shows Outlet to outlet / Back box, Ceiling shows Custom connection point |
| 3 | Ceiling, Line style, LAST ticked, circuit on the panel, ADD TAG → box-select 8 fixtures, Finish, click first, click last | Lines side-middle to side-middle, horizontal/vertical only, run starts and ends where clicked |
| 4 | Look at every fixture | One line in, one line out; no line crosses another fixture |
| 5 | Report | "N detail line(s) connecting 8 ceiling outlet(s). Line style: … Circuit R2 created on <panel> for 8 outlet(s). … Added an arc wire toward panel … and the circuit tag (R2) at the first outlet." |
| 6 | Open the panel schedule | The new circuit lists the 8 fixtures (schedule created if there was none) |
| 7 | Tag | Arc wire from the first fixture toward the panel, circuit tag showing the circuit |
| 8 | LAST unticked | Only the first is picked; the end is chosen for the shortest run |
| 9 | Phase color, fixtures on R/Y/B circuits | Lines red / yellow / blue by circuit; no circuit → the chosen default letter |
| 10 | Custom connection point → click a corner of one fixture | Every line starts/ends at that same corner of each fixture (rotated ones too) |
| 11 | Wall, Outlet to outlet → sockets round a room | Lines run along the walls, entering each socket at one side of the stub and leaving at the other |
| 12 | Wall, Back box | Lines join the back-box circles |
| 13 | Fixtures already on a circuit, circuit ticked | "every outlet is already on a circuit"; lines still drawn |
| 14 | Ctrl+Z | Whole run undone (lines, circuit, wire, tag) |
| 15 | Tag type = a Wire Tag | Home-run arc wire with an arrow from the first outlet toward the panel; tag on it reads Panel/Circuit, e.g. DB-GF-02/R2 |
| 16 | Tag type = a fixture tag | Tag at the first outlet; report suggests a Wire Tag |
| 17 | Tick "Draw the run as Revit wires" | Same square routing drawn as wires of the chosen type; report says "Revit wire(s) (XHHW)" |
