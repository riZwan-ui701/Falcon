# Add Param — test checklist

Tested on Revit version: ______  pyRevit version: ______

Setup: a project with a few loaded lighting fixture families (several types
each) and some placed instances. Note the path in Manage → Shared Parameters.

| # | Do this | Expect |
|---|---|---|
| 1 | Run in a family document | "Open a Revit project (not a family) first." |
| 2 | Run; type `eurs` in the search box | Tree filters to matching Category → Family (type count) → Types, expanded |
| 3 | Tick a family | Counter "1 family(ies) ticked \| 0 type(s) ticked" |
| 4 | Clear search | Tick is kept |
| 5 | Name `Vendor`, Text, group **Data**, **Add Parameter** | Log "Working… editing and reloading 1 family(ies)", then "OK … added (instance)"; an instance of that family shows **Vendor** under **Data** |
| 6 | Run again with the same family and name | "already has it"; nothing else changes |
| 7 | Untick the family, tick two types of another family, name `Lamp Code`, value `LC-01` | Type parameter added; those two types show `LC-01`, the other types are empty |
| 8 | Tick a family and one of its types, Length (mm), value `600` | Instance parameter; placed instances of that type show 600 mm |
| 9 | Name with `[` or empty name | Error in the log, nothing edited |
| 10 | Integer type with value `1.5` | "'1.5' is not a valid value for this data type." |
| 11 | Clear Revit's shared parameter file setting, add a parameter | Works; `%APPDATA%\Falcon\Falcon_SharedParameters.txt` holds it; Revit's setting is blank again afterwards |
| 12 | A name already in the shared file with a different data type | Log says the existing one is used and its data type kept |
| 13 | Type values changed in the project before the run | Still the same after the reload |
| 14 | Reopen the dialog | Last data type and group pre-selected |
