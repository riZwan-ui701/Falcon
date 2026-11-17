# Falcon — skills audit (2026-11-17)

The whole Falcon extension — all 17 ribbon buttons, their Shift+click files
and the shared `lib/` modules — checked against three of Rizwan's skills:

| Skill | What it checks |
|---|---|
| **revit-tool-pyrevit** | How a pyRevit tool must be built: metadata, safety, undo, ESC, worksharing, performance, reports |
| **revit-version-matrix** | Revit API differences 2020 → 2027 |
| **electrical-bim-standards** | Electrical BIM practice (Qatar: Kahramaa / Ashghal first, then ISO 19650, Uniclass, COBie) |

Nothing here was tested inside Revit. Each fix has a line in the Revit
Testing Checklist at the end — please mark Pass / Fail.

Status key: **Fixed** (changed in this audit) · **OK** (already met the
rule) · **Decision** (your call, recorded) · **Note** (practice point for
you, no code change).

---

## 1. revit-tool-pyrevit

| # | Rule | Finding | Status |
|---|---|---|---|
| P1 | Metadata block on every `.py` | 10 new tools lacked **Notes**; 6 older tools lacked **Notes**; 4 Shift+click `config.py` files had a one-line header; Conduit Cutter's `config.py` was incomplete | **Fixed** — full block everywhere; a test checks every `.py` in the ribbon |
| P2 | Project-only tools exit cleanly in the Family Editor | 16 of 17 model tools had no check (only Add Param did) | **Fixed** — `falcon_safety.project_only` in every model tool; tested |
| P3 | Worksharing: never force a checkout, skip and report | No check anywhere | **Fixed** — elements borrowed by another user are skipped with "borrowed by \<user\> – ask them to sync" in Auto Flex, Pull Box, Connect Conduit, Junction Box (update), Convert Line (delete lines), Home Run Guide |
| P4 | Confirm before delete / bulk edit, with the count | Convert Line deleted lines and Add Param reloaded families without asking | **Fixed** — both ask, with the count |
| P5 | No element search inside a loop | Add Param searched the model once per family | **Fixed** — searched once |
| P6 | IronPython 2.7-safe (no f-strings / Py3-only syntax) | None found | **OK** — tested |
| P7 | ESC during a pick exits silently | Every pick handles it | **OK** |
| P8 | One undo step per run | Every model tool uses one Transaction / TransactionGroup | **OK** — see exception E1 |
| P9 | Linked-model elements never modified | Pick filters and collectors only reach host elements | **OK** |
| P10 | No silent failures; skipped items reported with a reason | All tools list skipped items and why | **OK** |
| P11 | Final report as a pop-up vs the output window | Skill says output window; the demo videos use pop-ups | **Decision** — keep pop-ups (Rizwan, 2026-11-17) |

**Exception E1 — Markup tools (Redline / Blue / Clear).** These commit one
transaction per picked element on purpose, so the colour shows the moment
you click (one Transaction for the whole run would only repaint at Esc).
Ctrl+Z undoes one element at a time. Kept as designed.

## 2. revit-version-matrix (Revit 2020 → 2027)

| # | API change (version) | Finding | Status |
|---|---|---|---|
| V1 | Units: `DisplayUnitType` → `UnitTypeId` (2021) | Not used; units converted directly (mm ↔ feet) | **OK** |
| V2 | `ParameterType` → `SpecTypeId` (2022) | Add Param branches on feature detection | **OK** |
| V3 | Parameter groups → `GroupTypeId` (2022; `BuiltInParameterGroup` deprecated 2024) | Add Param uses `GroupTypeId` when present, the old enum only before 2022 | **OK** |
| V4 | ElementId 64-bit, `IntegerValue` deprecated (2024) | Reads go through `eid_int` (`.Value` first). One place rebuilt ids with `ElementId(number)` (Home Run Guide) | **Fixed** — new `eid_from` helper (feature detection, `Int64` on 2024+); a test blocks `ElementId(number)` in tools |
| V5 | Tag members `TaggedElementId` / `LeaderEnd` / `HasElbow` (2022) | Not used | **OK** |
| V6 | Dimension child classes (2025) | Dimensions are created only, never type-checked | **OK** |
| V7 | Electrical systems: `ElectricalSystems` → `GetElectricalSystems()` (2021) | Both handled | **OK** |
| V8 | .NET 10 runtime, all-user add-in path in Program Files (2027) | pyRevit extension, per-user path — not affected | **OK** — confirm your pyRevit build supports 2027 |
| V9 | Removed in 2027 (AXM, `Mechanical.Zone`, legacy rebar, energy settings) | Not used | **OK** |

### Version / engine install matrix

| Revit | pyRevit loader | Engine | Status |
|---|---|---|---|
| 2020 | .NET Framework 4.7.2 | IronPython 2.7 | Built — awaiting Revit test |
| 2021 – 2024 | .NET Framework 4.8 | IronPython 2.7 | Built — awaiting Revit test |
| 2025 – 2026 | .NET 8 | IronPython 2.7 | Built — awaiting Revit test |
| 2027 | .NET 10 | IronPython 2.7 | Built — confirm pyRevit 2027 support first |

## 3. electrical-bim-standards

| # | Topic | Finding | Status |
|---|---|---|---|
| E1 | Flex to light fixtures (Auto Flex) | Revit has no flex conduit, so flex is drawn as a **flex pipe**. It went into the first piping system (e.g. Hydronic Supply) unlabelled, so it could appear in plumbing / HVAC schedules and clash sets | **Fixed** — prefers a piping system type named with conduit / flex / elec, and labels each flex "Flexible conduit - Falcon Auto Flex" in Comments. **Note:** create a system type such as "ELEC - Flexible Conduit" once in your template so it is always used |
| E2 | Phase colours (Wiring Pro) | R / Y / B for L1 / L2 / L3, from the circuit number or its phase load; Y drawn dark goldenrod for white backgrounds | **OK** — graphics only. **Note:** R/Y/B matches your circuit naming; confirm the phase colour convention with the Kahramaa regulations / project spec |
| E3 | Pull boxes every 15 m and every two 90° bends | Values are settings (default 15 m / 2 bends) | **Note** — confirm spacing and bend limit against QCS / the project spec; change them in the Pull Box dialog |
| E4 | Circuit numbering and panel schedules | Wiring Pro lets Revit number circuits and makes a panel schedule only if the panel has none | **OK** — numbering follows your Electrical Settings, so set the circuit naming scheme there |
| E5 | Home runs and circuit tags | Home-run arrow wire + Wire Tag reading Panel/Circuit, as Revit does | **OK** |
| E6 | Shared parameters (Add Param) | True shared parameters; new names go into a "Falcon" group of your shared parameter file | **Note** — name parameters to your BEP / COBie naming (e.g. COBie or Uniclass fields) so they map at handover |
| E7 | Worksets | Tools create elements on the active workset | **Note** — set the electrical workset active before running |
| E8 | Junction box types | Recognised by type name (Terminal / Through / Angle / Tee / Branch_Y / Cross) | **Note** — keep these words in box type names in your family library |

*Confirm Qatar-specific rules (Kahramaa / Ashghal QCS) against the current official documents or the project BEP.*

---

## Revit Testing Checklist — this audit

Tested on Revit version: ______  pyRevit version: ______

| # | Do this | Expect | Pass / Fail |
|---|---|---|---|
| 1 | Open a family and click Multi Fillet, Conduit Cutter, Home Run, Line Cutter, Junction Box (Shift+click) and Auto Dimension (Shift+click → conduits to grids) | "This tool works in a project, not in the Family Editor…" — nothing changes | |
| 2 | Same for the 10 tools of the first audit | Same message | |
| 3 | Workshared: another user borrows an element each tool would edit | Skipped and listed as borrowed; the rest runs; no checkout forced | |
| 4 | Convert Line, Delete original lines ticked | Asks first, with the number of lines | |
| 5 | Add Param → Add Parameter | Asks first, with the number of families | |
| 6 | Home Run Guide twice on the same branches (2024+ model) | Second run replaces the first run's lanes (ids rebuilt correctly) | |
| 7 | Auto Flex in a project with a piping system type named "ELEC - Flexible Conduit" | Flex uses that system; Comments = "Flexible conduit - Falcon Auto Flex" | |
| 8 | Auto Flex in a project without such a system type | Flex uses the first system type, Comments still filled | |
| 9 | Shift+click Home Run, Line Cutter, Conduit Cutter, Junction Box, Auto Dimension | Each opens as before | |
| 10 | Any tool, non-workshared model | Same result as before the audit | |
