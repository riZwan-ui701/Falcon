# Falcon — pyRevit Extension

A pyRevit extension for electrical BIM work: quick visual markup, coloring,
and conduit automation (pull boxes, crossing offsets).

- **Markup** and **Graphics** tools only change how things *look* in views.
- **Electrical** tools change the model (they place boxes and cut conduits).
  Every Electrical run is one undo step — a single **Ctrl+Z** reverses it.

## Ribbon layout

The **Falcon** tab uses compact small buttons, stacked three high. Panels run
**Parameters → Electrical → Graphics** (set by `Falcon.tab/bundle.yaml`).

| Panel | Column 1 | Column 2 | Column 3 | Column 4 |
|---|---|---|---|---|
| **Parameters** | Add Param (large) | | | |
| **Electrical** | Connect Conduit, Convert Line, Multi Fillet | Junction Box, Pull Box, Conduit Cutter | Auto Dimension, Home Run, Line Cutter | Auto Flex, Home Run Guide, Wiring Pro |
| **Graphics** | Coloring, **Markup ▾** (Redline Markup, Blue Markup, Clear) | | | |

## Markup (Graphics panel → Markup ▾)

Every Markup tool changes only a **view-specific graphic override**
(`View.SetElementOverrides`). Nothing about the element itself — its material,
type, or appearance in any other view — is ever changed. Overrides are easy
to reverse: undo one at a time with Ctrl+Z, or run **Clear** to remove them.

### Tools

All three are in the **Markup ▾** dropdown on the **Graphics** panel.

### Redline Markup
Turns elements red in the active view.

### Blue Markup
Turns elements blue in the active view.

### Clear
Removes the color override from elements in the active view (whichever
color they were set to).

### How to use any of the three

- **Pre-select first:** select one or more elements in Revit, *then* click
  the tool — they update immediately.
- **Or run first, then pick:** click the tool with nothing selected, then
  click elements one at a time in the view. Each one updates the instant
  it's picked. Press **Esc** to stop picking.

Both approaches can be combined in the same run, and each click commits
immediately so the color change is visible right away (no waiting for Esc).

### Groups

If a picked element belongs to a Revit **Group**, the whole group is
recolored together — not just the one member you clicked.

## Graphics panel

### Coloring
Click it and choose in the **What do you want to color?** window (it comes
back after each job until you press **Close**):

- **Color Family** — a list of families and their types (search box, and
  "Only families that are used in the project"). Tick a family or some types
  — or just click one row — press **Choose color…** and pick a color in
  Revit's color dialog. The status line says how many views were colored and
  how many elements match. The color
  is added as a view filter (named `FALCON_COLOR_…`) to every plan, section and
  elevation — on the view template where a view has one, so the color stays
  when templates are re-applied. 3D views are left alone unless you tick
  **Also apply in 3D views**. **Remove color from selected** and **Remove all
  Coloring colors** delete only the filters this tool made.
- **Color Element** — select the elements (Tab selects a connected run; any
  pre-selection is kept), **Finish**, untick the categories you don't want in
  the **Filter selection** list (Check all / Uncheck all), then pick the
  color. They are colored in the current view and in every 3D view.

## Parameters panel

### Add Param
Adds a shared parameter to any loaded family without opening and editing each
family by hand.

1. **Choose families / types** — type in the search box (e.g. `eurs`) to
   filter the Category → Family → Type tree.
   - Tick a **family** → **instance** parameter (Properties palette, tags,
     schedules).
   - Tick only some **types** → **type** parameter; the optional value is set
     on those types only.
   The counter shows how many families and types are ticked.
2. **Parameter** — name, data type (Text, Integer, Number, Length in mm, Area
   in m², Volume in m³, Angle in °, Yes/No, URL) and the group it shows under
   in the Properties palette (Identity Data, Data, Electrical - Lighting …).
   **Value for the ticked types** is optional.
3. **Add Parameter** — the log shows "Working… Revit is editing and reloading
   N family(ies)", then one line per family. Families that already have a
   parameter with that name are left alone.

The parameter is a true **shared** parameter. It comes from the shared
parameter file set in Revit (Manage → Shared Parameters); a name already in
the file is reused, a new one is created in a **Falcon** group. If Revit has
no file set, `%APPDATA%\Falcon\Falcon_SharedParameters.txt` is used for the run
and Revit's setting is put back afterwards. Reloading keeps all existing
parameter values in the project. The dialog remembers the last data type and
group.

## Electrical panel

### Wiring Pro (plan views)
Wires a run of outlets and does the paperwork. The dialog (remembered):

- **Outlet type** — Ceiling (lighting fixtures) or Wall (sockets, switches,
  data, fire alarm … devices).
- **Wire color** — a line style, or **phase color** (R red, Y yellow, B blue)
  taken from each outlet's circuit number; outlets without a circuit use the
  letter you choose.
- **Connection** — Ceiling: lines join the **middle of the fixtures' sides**,
  or tick **Custom connection point** and click it on one fixture — the same
  point is used on every fixture (it follows each fixture's rotation). Wall:
  **Outlet to outlet** (in at one point beside the stub, out at the other) or
  **Back box** (circle to circle of the back boxes). **Also pick the LAST
  outlet** lets you fix the end of the run.
- **Circuit** — create a power circuit on the chosen panel; Revit numbers it
  (e.g. R4) and the panel's schedule lists the fixtures (a panel schedule is
  made if the panel has none).
- **Tag** — an arc home-run wire toward the panel (with Revit's arrow) and a
  circuit tag. Pick a **Wire Tag** (listed first) and it goes on the home-run
  wire, reading Panel/Circuit (e.g. `DB-GF-02/R2`) like Revit's own home runs;
  any other tag type goes on the first outlet.
- **Draw the run as Revit wires** (optional) — the same square routing, drawn
  as wires of the chosen wire type instead of detail lines.

Then box-select the outlets (Finish; pre-selected ones are kept) and click the
**first** outlet (and the **last**, if ticked). The tool finds the shortest run
through the rest and draws horizontal/vertical detail lines only — each
fixture has one line in and one line out, and no line runs over another
fixture. The report gives lines drawn, colors, the circuit, schedule and tag.
One undo step.

### Home Run Guide (plan views)
Draw the main route (the trunk) from the panel with detail lines, and a
detail line from each circuit/room that ends on the trunk (same line style).
Then a three-step wizard:

1. **Select** — click **Continue to selection**, pick the trunk lines, Finish.
2. **Offset** — the route spacing (default 50 mm, remembered).
3. **Start** — click **Pick start point**, then the temporary square marker at
   the panel end.

Every branch gets its own lane along the trunk back to the panel, offset by
the spacing. Lanes go on the side the branch comes from, and the branch
farthest from the panel gets the inside lane, so nothing crosses. A preview
reports the routes, segments, lanes per side and crossing score and asks
**Keep these lines?** — **No** puts everything back; **Yes** removes the
trunk and replaces lanes made earlier for the same branches. Then use
**Convert Line** (Line Style) to turn the lanes into conduits.

### Auto Flex
Pick the **Flex Diameter (mm)** (20–300, remembered), press **Select Ceiling
Box**, select the ceiling junction boxes (boxes already selected stay in the
pick) and press **Finish**. For every box:

- a flex (Revit flex pipe) is drawn from the box to its **nearest light
  fixture** (nearest in plan): it leaves the free outlet that points most
  toward the fixture, then drops onto the top of the fixture;
- if **every outlet is already taken by conduit**, the box is switched to a
  type with **one more outlet** (Through → Tee → Cross). Its conduits stay
  connected — the box is turned/slid so each conduit meets an outlet and the
  conduit ends are trimmed onto them — and the flex leaves from the new outlet;
- a box that already has a flex on one of its outlets is skipped, so running
  it twice does not double up.

Works with **any junction box family**: outlets are counted from the family's
conduit connectors, capped by what the type name says (`Tee`, `Cross`,
`Through`, `3-way`, `4 Way` …). The bigger type is looked for in the same
family first, then in other box families of the same category and conduit
size. Each box is all-or-nothing; the result dialog shows **Flex created**,
**Boxes switched to a type with an extra outlet** and **Skipped / failed**
with the reason for each skipped box. The whole run is one undo step.

The flex uses the project's first flex pipe type (a "Round" one if there is
one) and first piping system type — Revit has no flex conduit, so a flex pipe
is the usual stand-in; it is drawn to the outlet but can't be "connected" to a
conduit connector.

### Pull Box
Fill in the dialog — distance between pull boxes (default 15 m), bends before
a pull box (default 2), whether the panel riser bend counts as the first bend,
and which junction box type to use — press **Start**, select the conduits
(a whole bundle of home runs at once; pre-selected conduits are used
straight away), **Finish**, then click the **start point at the panel side** —
distances are measured from there. Each run is followed through its elbows
from its end nearest that point, and gets a box every 15 m, or on the straight conduit 300 mm after every second 90° bend,
whichever comes first. An existing junction box on the run restarts the count;
a tee stops the walk. If the box family has two conduit connectors
(a "through / 2-way" box) the conduit is cut and connected to it. The dialog
remembers your last values. The report gives the boxes placed per run.

### Conduit Cutter
Select the straight conduits that cross (or pick them and click **Finish**),
then choose **Up** (go over) or **Down** (go under). The smaller group is moved
around the bigger one: each of its conduits is cut and rebuilt with 30°
offsets so it clears the other group by 50 mm. Crossings close together share
one offset. Conduits that can't fit (crossing too close to the end, already
clear) are listed at the end and left untouched. Elbows come from the conduit
type's fitting settings.

**Shift+click** Conduit Cutter to change the clearance (mm) and elbow angle.

### Junction Box
Type the **Elevation** (mm above the plan's level, remembered), press
**Start**, select the fixtures (pre-selected ones are kept) and **Finish**.
At each fixture the tool reads the routing lines in the view — detail and
model lines, wires and CAD lines — that cross the fixture outline, and from
the directions they leave in picks the box type and turns it to match:

| Lines leaving the fixture | Box type |
|---|---|
| 1 | Terminal (1-way) |
| 2 straight on | Through (2-way 180) |
| 2 at an angle | Angle (2-way 90) |
| 3 with two in line | Tee (3-way) |
| 3 otherwise | Branch_Y |
| 4 | Cross (4-way) |

Types are recognised by their names, so any box family named like this works;
the family that covers the most of the needed types is used. The box goes at
the fixture's insertion point; a box already there is updated (type, turn,
elevation) instead of doubled. The report lists boxes placed/updated, the
elevation, family and types used, and every skipped fixture with the reason
(e.g. no route line crosses its outline, nearest line 260.5 mm away). The plan
is zoomed to the placement points. One undo step.

**Shift+click** runs the original Junction Box: pick the box type, then click
conduits — mid-run a 2-way box cuts the conduit and connects; within 300 mm
of an end the box goes on the end. Esc to finish.

### Convert Line
Turns detail lines into conduits in one click. The dialog:

1. **Selection** — **Select Line** (pick lines, Finish; pre-selected lines are
   used straight away), **Line Style** (every line in the active view with the
   chosen style) or **CAD Lines** (pick lines inside a linked/imported DWG).
2. **Conduit Type**.
3. **Conduit Diameter** — the size list of that type's standard.
4. **Elevation** — a fixed height in mm above the view's level, or **Circuit
   Elevation**: each connected run takes the height of the fixtures its lines
   touch (a box's conduit connector, else the top of the fixture) and, where a
   line ends on a panel, a riser comes up out of the panel top to that height.
   Runs that touch no fixture use the typed elevation.

**Delete original lines after conversion** removes the converted lines.
Lines that continue straight on become **one** conduit; where lines meet you
get an elbow, a tee (a line ending on the middle of another) or a cross.
Conduit ends that land on a free connector of a box are connected. The result
says e.g. "Converted 191 line(s) into 130 conduit(s). 2 joint(s) had not
enough room for a fitting and were left disconnected." Arcs are skipped.

### Connect Conduit
Pick the connection in the dialog, then work in the view until **Esc**
(the whole session is one undo step):

- **Draw New Conduit** (choose diameter and type) — click the exit point on
  the first element (a free conduit connector within 100 mm is used), then the
  second element. The conduit runs in straight 90° legs at the exit height,
  then drops (or rises) onto the second element's free connector, or the
  middle of its top/bottom.
- **Connect Conduit** — select the conduits (Finish), then the device or
  panel. New pieces use each conduit's own type and size. Each conduit runs on
  along its own line, steps across only if it has to, then goes up/down to the
  device and connects to its free connector. Into a **panel** every conduit
  goes straight on to above the middle of the panel and drops onto its top,
  never sideways, so a bundle keeps its spacing. Pick **one** conduit and
  another **conduit** as the target to join them as before (coupling in line,
  elbow at a corner).

### Multi Fillet
Select the first group of parallel conduits (Finish), then the second group
(Finish). Each pair is trimmed/extended to its corner and joined with an
elbow — inner with inner, whatever order you picked them in. If the elbow
family has a writable **Bend Radius**, the bends are made concentric.

### Home Run (plan views)
Click circuited devices. For each one an arrow is drawn toward its panel with
a `Panel-Circuit` text note (e.g. `LP-1-3,5`). Devices with no circuit are
listed and skipped. **Shift+click** to set the arrow length (default 600 mm).

### Auto Dimension (plan views)
Choose the **linear dimension type** (tick **Show all styles** for every
dimension style), **Use Style**, then select the outlets (pre-selected ones
are kept) and **Finish**. Outlets whose centres line up (within 100 mm) get
one dimension chain through their centre references — one per row, one per
column — 450 mm from the outlets. The report gives dimensions created, groups
skipped (an outlet alone in its row/column), the segment values per chain,
families with no usable centre reference, and any dimension errors.

**Shift+click** offers: **Dimension conduits to grids** (the original tool —
selected conduits, or all in the view, to the nearest parallel grid or wall)
and the two distances.

### Line Cutter (plan views)
Where one conduit passes over another, a small white "Falcon Mask" region hides
the lower one so the crossing reads clearly. Only the view changes. Running it
again replaces the masks it made before in that view. **Shift+click** to set
the gap each side of the upper conduit (default 50 mm).

## Install

1. In Revit, open **pyRevit tab → Settings**.
2. Under **Custom Extension Directories**, add the folder that *contains*
   `Falcon.extension` (not the extension folder itself).
3. **Save Settings**, then fully close and reopen Revit (a plain
   **Reload** is not enough after adding a new extension directory for the
   first time).
4. The **Falcon** tab should appear with the **Parameters**, **Electrical**
   and **Graphics** panels.

## Structure

```
Falcon.extension/
  Falcon.tab/
    Electrical.panel/
      A.stack/                      (column 1 - stack folders keep paths short)
        A_ConnectConduit.pushbutton/
        B_ConvertLine.pushbutton/
        C_MultiFillet.pushbutton/
      B.stack/
        A_JunctionBox.pushbutton/   (config.py = old click-on-conduit tool)
        B_PullBox.pushbutton/
        C_ConduitCutter.pushbutton/ (config.py = Shift+click settings)
      C.stack/
        A_AutoDimension.pushbutton/ (config.py = conduits to grids + settings)
        B_HomeRun.pushbutton/       (config.py)
        C_LineCutter.pushbutton/    (config.py)
      D.stack/
        A_AutoFlex.pushbutton/
        B_HomeRunGuide.pushbutton/
        C_WiringPro.pushbutton/
    Graphics.panel/
      A.stack/
        A_Coloring.pushbutton/
        B_Markup.pulldown/
          A_RedlineMarkup.pushbutton/
          B_BlueMarkup.pushbutton/
          C_Clear.pushbutton/
    Parameters.panel/
      A_AddParam.pushbutton/        (large button)
    bundle.yaml                     (panel order)
  lib/
    falcon_markup.py               (Markup tools)
    falcon_geom.py, falcon_route.py, falcon_layout.py, falcon_wiring.py,
    falcon_naming.py, falcon_params.py
                                   (pure - tested offline)
    falcon_conduit.py, falcon_color.py        (Revit conduit and colour helpers)
    falcon_settings.py                   (remembered settings)
    falcon_view.py                       (plan-view / annotation helpers)
tests/                              (pytest: maths, naming, ribbon layout)
docs/testing/                       (manual test checklists for Revit)
```

The A_/B_/C_ prefixes set the order. Keep folder names short: Windows
can't open files whose full path is longer than 260 characters, and
`tests/test_ribbon_layout.py` checks for that.

## Offline tests

The maths behind Pull Box, Conduit Cutter, Auto Flex, Home Run Guide,
Junction Box, Auto Dimension, Wiring Pro,
Convert Line and Connect Conduit, and the Add Param rules, run without Revit:

```
python -m venv .venv
.venv/Scripts/python -m pip install -r requirements-dev.txt
.venv/Scripts/python -m pytest tests -q
```

The Revit side is checked by hand with the lists in `docs/testing/`.

## Compatibility

IronPython 2.7-safe. The Markup tools only use APIs unchanged across Revit
2020–2027. The Graphics and Electrical tools are built and checked for
**Revit 2025** and handle the 2022 filter-rule and 2024 ElementId API
changes, so they are expected to work on 2020–2027.
