# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Auto Dimension - Shift+click (more options)
# Purpose        : Dimension conduits to grids, or set the outlet / conduit dimension distances.
# Author         : Rizwan Zahid
# Version        : 2.0.0
# Created Date   : 2026-11-17
# Updated Date   : 2026-11-17
# Status         : Production
#
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7
#
# Category       : BIM Automation
# Discipline     : Electrical
# Tool Type      : pyRevit Tool (Shift+click of the button)
#
# Input          : Active View - a choice from a short menu.
# Output         : Conduit dimensions, or a saved distance setting.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - conduits.py in this button folder, falcon_view.py
#
# Features       :
#   - Conduits-to-grids tool and both distance settings
#
# Notes          :
#   - Runs when the button is Shift+clicked; the normal click runs script.py.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Menu: conduits to grids, outlet distance, conduit distance
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os

from pyrevit import forms

import falcon_view

CONDUITS = "Dimension conduits to grids"
OUTLET_GAP = "Outlet chains: distance from the outlets (mm)"
CONDUIT_GAP = "Conduits: distance from the conduit midpoint (mm)"

choice = forms.CommandSwitchWindow.show(
    [CONDUITS, OUTLET_GAP, CONDUIT_GAP], message="Auto Dimension - more options")
if choice == CONDUITS:
    _path = os.path.join(os.path.dirname(__file__), "conduits.py")
    with open(_path) as _f:
        exec(compile(_f.read(), _path, "exec"), {"__name__": "__main__", "__file__": _path})
elif choice == OUTLET_GAP:
    falcon_view.ask_setting("Falcon - Auto Dimension Settings", "falcon_autodimoutlets",
                            "offset_mm", 450.0,
                            "Distance from the outlet centres to the dimension line (mm)",
                            -100000, 100000)
elif choice == CONDUIT_GAP:
    falcon_view.ask_setting("Falcon - Auto Dimension Settings", "falcon_autodim", "offset_mm",
                            500.0, "Distance from the conduit midpoint to the dimension line (mm)",
                            -100000, 100000)
