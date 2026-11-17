# Safety audit (revit-tool-pyrevit skill) — Revit Testing Checklist

Tested on Revit version: ______  pyRevit version: ______

Audit of Wiring Pro, Auto Flex, Add Param, Home Run Guide, Convert Line,
Connect Conduit, Junction Box, Auto Dimension, Pull Box and Coloring against
the revit-tool-pyrevit skill. What each tool does in a normal model is
unchanged; these checks cover the new safety behaviour. Not tested in Revit
yet — please mark Pass / Fail.

| # | Do this | Expect | Pass / Fail |
|---|---|---|---|
| 1 | Open a family (.rfa) and click any of the 10 tools | "This tool works in a project, not in the Family Editor. Open the project and run it again." Nothing changes | |
| 2 | Convert Line with "Delete original lines" ticked | Asks "After converting, N original line(s) will be deleted… Continue?" — No stops with nothing changed, Yes converts and deletes | |
| 3 | Add Param → Add Parameter | Asks "This will add '<name>' to N family(ies)… Continue?" — No stops, Yes edits and reloads | |
| 4 | Add Param with a value on ticked types of an instance parameter, in a big project | Value set on the placed instances; noticeably no slower than before | |
| 5 | Workshared model: another user borrows a conduit / box / line, then run Pull Box, Connect Conduit, Auto Flex, Junction Box (update), Convert Line (delete lines) | That element is skipped and listed with "borrowed by <user> – ask them to sync"; the rest still runs; no checkout is forced | |
| 6 | Workshared model: the Home Run Guide trunk line is borrowed by another user | "The reference line can't be removed: … Nothing was changed." | |
| 7 | Workshared model: one branch line borrowed | Preview lists "1 branch line(s) skipped: borrowed by another user" | |
| 8 | Non-workshared model, run each tool as before | Same result as before the audit | |

## Version / engine install matrix

| Revit version | pyRevit loader | Engine target | Bundle path | Status |
|---|---|---|---|---|
| 2020 – 2024 | .NET Framework 4.8 | IronPython 2.7 (default) | `Falcon.extension\Falcon.tab\<panel>.panel\…\<tool>.pushbutton\` | Built — awaiting Revit test |
| 2025 – 2026 | .NET 8 | IronPython 2.7 (default) | same | Built — awaiting Revit test |
| 2027 | .NET 10 | IronPython 2.7 (default) | same | Built — verify pyRevit support for 2027 first |

All scripts are IronPython 2.7-safe (checked by `tests/test_ribbon_layout.py`),
so no CPython 3 engine is needed.
