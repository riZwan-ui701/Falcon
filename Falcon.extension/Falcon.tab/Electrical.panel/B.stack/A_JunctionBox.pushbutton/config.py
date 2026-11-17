# Junction Box - Shift+click: the original tool - click conduits to place
# boxes on them (Falcon, Rizwan Zahid, v2.0.0, Revit 2020-2027, IronPython 2.7)
import os

_path = os.path.join(os.path.dirname(__file__), "on_conduit.py")
with open(_path) as _f:
    exec(compile(_f.read(), _path, "exec"), {"__name__": "__main__", "__file__": _path})
