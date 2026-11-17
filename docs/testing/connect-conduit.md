# Connect Conduit — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a bundle of parallel conduits ending near a panel; a conduit ending
near a light switch below it; two junction boxes; two conduits in line with
a gap; two conduits at 90° (same height); a device with a side connector.

| # | Do this | Expect |
|---|---|---|
| 1 | Run; dialog shows Connection (Draw New Conduit / Connect Conduit), Conduit Diameter, Conduit Type | Connect mode greys out diameter/type with "In Connect mode the new segments use the diameter and type of the selected conduits." |
| 2 | Connect → select the bundle, Finish → click the panel | Each conduit runs on along its own line to above the middle of the panel, then straight down onto its top; spacing kept; elbows at the bends |
| 3 | Next round (still running): select the switch conduit, Finish → click the switch | Conduit runs on, then drops to the switch and connects if it has a conduit connector |
| 4 | Device behind the conduit end | That conduit refused: "the device is behind the conduit end"; others still done |
| 5 | Device with a side connector, lower | Goes down first, then a straight 300 mm run into the side |
| 6 | One conduit, then the in-line conduit as the target | Coupling |
| 7 | One conduit, then the 90° conduit as the target | Trimmed/extended to the corner, elbow |
| 8 | Esc | Tool ends; Ctrl+Z once undoes the whole session |
| 9 | Draw New → 20 mm, PVC → click a point on box A, then box B | 90° legs at the clicked height, longer direction first, then a drop onto B's free connector (connected) |
| 10 | Draw New with the click near A's free connector | Starts exactly at that connector and is connected |
| 11 | Draw New, two elements so close the legs are too short | "Not drawn: … Nothing was changed." |
| 12 | Run again | Last mode, type and diameter remembered |
