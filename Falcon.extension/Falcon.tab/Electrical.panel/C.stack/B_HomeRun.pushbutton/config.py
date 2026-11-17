# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Home Run - Settings (Shift+click)
# Purpose        : Set the home-run arrow length.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-12
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
# Input          : Arrow length in mm.
# Output         : Saved setting used by Home Run.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - falcon_view.py
#
# Features       :
#   - Remembers the arrow length
#
# Notes          :
#   - Runs when the button is Shift+clicked; the normal click runs script.py.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#
# Changelog
# ------------------------------------------------------------
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import falcon_view

falcon_view.ask_setting("Falcon - Home Run Settings", "falcon_homerun", "length_mm",
                   600.0, "Home-run arrow length (mm)", 50, 5000)
