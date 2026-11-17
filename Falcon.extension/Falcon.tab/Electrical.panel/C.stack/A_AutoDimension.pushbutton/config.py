# Auto Dimension - Shift+click: the conduit-to-grid tool and the settings
# (Falcon, Rizwan Zahid, v2.0.0, Revit 2020-2027, IronPython 2.7)
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
