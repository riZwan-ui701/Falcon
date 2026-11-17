# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Conduit Cutter - Settings (Shift+click)
# Purpose        : Change the clearance and elbow angle used by
#                  Conduit Cutter.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-12
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7
#
# Category       : BIM Automation
# Discipline     : Electrical
# Tool Type      : pyRevit Tool (Shift+click of the button)
#
# Input          : Clearance (mm) and elbow angle (degrees).
# Output         : Saved settings used by Conduit Cutter.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - falcon_settings.py
#
# Features       :
#   - Remembers clearance and offset angle
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

from pyrevit import forms

import falcon_settings

TITLE = "Falcon - Conduit Cutter Settings"
SECTION = "falcon_cutter"
DEFAULTS = {"clearance_mm": 50.0, "angle_deg": 30.0}


def ask_number(prompt, default, low, high):
    text = forms.ask_for_string(default=str(default), prompt=prompt, title=TITLE)
    if text is None:
        return None
    try:
        value = float(text.replace(",", "."))
    except ValueError:
        value = None
    if value is None or not (low <= value <= high):
        forms.alert(u"Enter a number from {:g} to {:g}.".format(low, high), title=TITLE)
        return None
    return value


settings = falcon_settings.load(SECTION, DEFAULTS)
clearance = ask_number("Clear gap between the two conduit groups (mm)",
                       settings["clearance_mm"], 0, 1000)
if clearance is not None:
    angle = ask_number("Offset elbow angle (degrees)", settings["angle_deg"], 15, 60)
    if angle is not None:
        falcon_settings.save(SECTION, {"clearance_mm": clearance, "angle_deg": angle})
        forms.alert(u"Saved: {:g} mm clearance, {:g}-degree elbows.".format(clearance, angle),
                    title=TITLE)
