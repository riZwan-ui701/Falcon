# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Junction Box - Shift+click (place on conduit)
# Purpose        : Run the original Junction Box tool: click conduits to place boxes on them.
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
# Input          : Selection - box type, then clicks on conduits (Esc to finish).
# Output         : Junction boxes on the conduits, cut and connected for 2-way boxes.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - on_conduit.py in this button folder
#
# Features       :
#   - Keeps the v1 click-on-conduit tool one Shift+click away
#
# Notes          :
#   - Runs when the button is Shift+clicked; the normal click runs script.py.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Shift+click runs the v1 tool (on_conduit.py)
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os

_path = os.path.join(os.path.dirname(__file__), "on_conduit.py")
with open(_path) as _f:
    exec(compile(_f.read(), _path, "exec"), {"__name__": "__main__", "__file__": _path})
