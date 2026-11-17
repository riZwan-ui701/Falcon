# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Add Param
# Purpose        : Add a shared parameter to any loaded family (instance
#                  parameter) or to specific types (type parameter, with an
#                  optional value) without opening each family by hand.
# Author         : Rizwan Zahid
# Version        : 1.0.0
# Created Date   : 2026-11-17
# Updated Date   : 2026-11-17
# Status         : Production
#
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7
#
# Category       : BIM Automation
# Discipline     : All
# Tool Type      : pyRevit Tool
#
# Input          : Ticked families / types, parameter name, data type,
#                  Properties palette group, optional value.
# Output         : Families edited and reloaded with the shared parameter.
#
# Dependencies   :
#   - pyRevit, Revit API
#   - Falcon.extension/lib/falcon_params.py, falcon_settings.py
#
# Features       :
#   - Uses the shared parameter file set in Revit; the name is reused if it
#     is already in the file, otherwise it is created in a "Falcon" group.
#     With no file set, Falcon_SharedParameters.txt in %APPDATA%\Falcon is
#     used for this run and Revit's setting is put back afterwards.
#   - Reload keeps the project's existing parameter values.
#
# Changelog
# ------------------------------------------------------------
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os
import traceback

from System import Action
import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import FontWeights
from System.Windows.Controls import CheckBox, TextBlock, TreeViewItem
from System.Windows.Input import Cursors
from System.Windows.Threading import DispatcherPriority

from pyrevit import revit, DB, forms, script

import falcon_params
import falcon_settings
from falcon_color import eid_int

TITLE = "Falcon - Add Param"
SECTION = "falcon_addparam"
DEFAULTS = {"data_type": "Text", "group": "Identity Data"}
SP_GROUP = "Falcon"

doc = revit.doc


# --------------------------------------------------------- Revit helpers

def element_name(element):
    try:
        return element.Name
    except Exception:
        return DB.Element.Name.__get__(element)


class FamilyInfo(object):
    def __init__(self, family):
        self.family = family
        self.key = eid_int(family.Id)
        self.name = family.Name
        self.category = family.FamilyCategory.Name
        self.types = sorted(
            [(eid_int(sid), element_name(doc.GetElement(sid)))
             for sid in family.GetFamilySymbolIds()], key=lambda t: t[1])


def editable_families():
    out = []
    for family in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        try:
            if (not family.IsEditable or family.IsInPlace
                    or family.FamilyCategory is None):
                continue
            out.append(FamilyInfo(family))
        except Exception:
            continue
    return sorted(out, key=lambda f: (f.category, f.name))


def spec_for(kind):
    """Data type for the shared parameter on this Revit version."""
    spec = getattr(DB, "SpecTypeId", None)
    if spec is not None and hasattr(spec, "String"):      # Revit 2022+
        return {
            "text": spec.String.Text, "integer": spec.Int.Integer,
            "number": spec.Number, "length": spec.Length, "area": spec.Area,
            "volume": spec.Volume, "angle": spec.Angle,
            "yesno": spec.Boolean.YesNo, "url": spec.String.Url,
        }[kind]
    ptype = DB.ParameterType
    return {
        "text": ptype.Text, "integer": ptype.Integer, "number": ptype.Number,
        "length": ptype.Length, "area": ptype.Area, "volume": ptype.Volume,
        "angle": ptype.Angle, "yesno": ptype.YesNo, "url": ptype.URL,
    }[kind]


def group_for(group):
    """Properties palette group on this Revit version."""
    _label, forge_name, bip_name = group
    if hasattr(DB, "GroupTypeId"):                          # Revit 2022+
        return getattr(DB.GroupTypeId, forge_name) if forge_name else DB.ForgeTypeId()
    return getattr(DB.BuiltInParameterGroup, bip_name)


class SharedFile(object):
    """The shared parameter file for this run; put Revit's setting back
    with restore() when done."""

    def __init__(self):
        self.app = doc.Application
        self.original = self.app.SharedParametersFilename
        self.changed = False
        self.file = None
        try:
            self.file = self.app.OpenSharedParameterFile()
        except Exception:
            self.file = None
        if self.file is None:
            folder = os.path.join(os.getenv("APPDATA") or os.path.expanduser("~"), "Falcon")
            if not os.path.isdir(folder):
                os.makedirs(folder)
            path = os.path.join(folder, "Falcon_SharedParameters.txt")
            if not os.path.isfile(path):
                open(path, "w").close()
            self.app.SharedParametersFilename = path
            self.changed = True
            self.file = self.app.OpenSharedParameterFile()
        if self.file is None:
            raise ValueError("Revit could not open a shared parameter file.")
        self.path = self.app.SharedParametersFilename

    def definition(self, name, kind):
        """(ExternalDefinition, is_new). An existing name is reused."""
        for group in self.file.Groups:
            found = group.Definitions.get_Item(name)
            if found is not None:
                return found, False
        group = self.file.Groups.get_Item(SP_GROUP) or self.file.Groups.Create(SP_GROUP)
        opts = DB.ExternalDefinitionCreationOptions(name, spec_for(kind))
        return group.Definitions.Create(opts), True

    def restore(self):
        if self.changed:
            try:
                self.app.SharedParametersFilename = self.original or ""
            except Exception:
                pass


class KeepProjectValues(DB.IFamilyLoadOptions):
    """Reload over the old family; existing parameter values are kept."""

    def OnFamilyFound(self, familyInUse, overwriteParameterValues):
        overwriteParameterValues.Value = False
        return True

    def OnSharedFamilyFound(self, sharedFamily, familyInUse, source, overwriteParameterValues):
        source.Value = DB.FamilySource.Family
        overwriteParameterValues.Value = False
        return True


def add_to_family(family, definition, group, is_instance):
    """Edit family, add the parameter, load it back. Returns a short note."""
    family_doc = doc.EditFamily(family)
    try:
        manager = family_doc.FamilyManager
        if manager.get_Parameter(definition.Name) is not None:
            return u"already has it"
        t = DB.Transaction(family_doc, "Falcon: Add Param")
        t.Start()
        try:
            manager.AddParameter(definition, group_for(group), is_instance)
            t.Commit()
        except Exception:
            t.RollBack()
            raise
        family_doc.LoadFamily(doc, KeepProjectValues())
        return u"added ({})".format("instance" if is_instance else "type")
    finally:
        family_doc.Close(False)


def set_param(element, name, parsed):
    param = element.LookupParameter(name)
    if param is None or param.IsReadOnly:
        return False
    storage, value = parsed
    st = param.StorageType
    if storage == "string" and st == DB.StorageType.String:
        return param.Set(value)
    if storage == "integer" and st == DB.StorageType.Integer:
        return param.Set(int(value))
    if storage in ("integer", "double") and st == DB.StorageType.Double:
        return param.Set(float(value))
    return False


def set_values(name, parsed, jobs, by_key):
    """Put the optional value on the ticked types (type parameter) or on
    the placed instances of those types (instance parameter)."""
    done = failed = 0
    with revit.Transaction("Falcon: Add Param value"):
        for fam_key, job in jobs.items():
            type_ids = set(job["types"])
            if not type_ids:
                continue
            if job["instance"]:
                targets = [fi for fi in DB.FilteredElementCollector(doc)
                           .OfClass(DB.FamilyInstance)
                           if eid_int(fi.GetTypeId()) in type_ids]
            else:
                targets = [doc.GetElement(sid)
                           for sid in by_key[fam_key].family.GetFamilySymbolIds()
                           if eid_int(sid) in type_ids]
            for element in targets:
                if element is not None and set_param(element, name, parsed):
                    done += 1
                else:
                    failed += 1
    return done, failed


# ------------------------------------------------------------------- UI

class AddParamWindow(forms.WPFWindow):
    def __init__(self, families, settings):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "AddParam.xaml"))
        self.families = families
        self.by_key = dict((f.key, f) for f in families)
        self.family_of_type = {}
        for f in families:
            for tid, _name in f.types:
                self.family_of_type[tid] = f.key
        self.ticked_families = set()
        self.ticked_types = set()

        labels = [label for label, _k in falcon_params.DATA_TYPES]
        for label in labels:
            self.data_type.Items.Add(label)
        self.data_type.SelectedIndex = (labels.index(settings["data_type"])
                                        if settings["data_type"] in labels else 0)
        groups = [g[0] for g in falcon_params.GROUPS]
        for label in groups:
            self.group.Items.Add(label)
        self.group.SelectedIndex = (groups.index(settings["group"])
                                    if settings["group"] in groups else 0)
        self.rebuild()
        self.search.Focus()

    # ---- tree
    def _check(self, content, ticked, key, bold=False):
        box = CheckBox()
        text = TextBlock()
        text.Text = content
        if bold:
            text.FontWeight = FontWeights.SemiBold
        box.Content = text
        box.IsChecked = key in ticked
        handler = self._toggler(ticked, key)
        box.Checked += handler
        box.Unchecked += handler
        return box

    def _toggler(self, ticked, key):
        def on_change(sender, args):
            if sender.IsChecked:
                ticked.add(key)
            else:
                ticked.discard(key)
            self.update_counter()
        return on_change

    def rebuild(self):
        search = self.search.Text
        self.tree.Items.Clear()
        current = None
        cat_item = None
        for fam in self.families:
            fam_hit = falcon_params.matches(search, fam.category, fam.name)
            types = [(tid, name) for tid, name in fam.types
                     if fam_hit or falcon_params.matches(search, fam.category, fam.name, name)]
            if not fam_hit and not types:
                continue
            if fam.category != current:
                current = fam.category
                cat_item = TreeViewItem()
                header = TextBlock()
                header.Text = fam.category
                header.FontWeight = FontWeights.SemiBold
                cat_item.Header = header
                cat_item.IsExpanded = bool(search.strip())
                self.tree.Items.Add(cat_item)
            fam_item = TreeViewItem()
            fam_item.Header = self._check(u"{}  ({})".format(fam.name, len(fam.types)),
                                          self.ticked_families, fam.key)
            fam_item.IsExpanded = bool(search.strip()) and not fam_hit
            for tid, name in types:
                type_item = TreeViewItem()
                type_item.Header = self._check(name, self.ticked_types, tid)
                fam_item.Items.Add(type_item)
            cat_item.Items.Add(fam_item)
        self.update_counter()

    def update_counter(self):
        self.counter.Text = u"{} family(ies) ticked  |  {} type(s) ticked".format(
            len(self.ticked_families), len(self.ticked_types))

    def search_changed(self, sender, args):
        self.rebuild()

    # ---- log
    def write(self, line):
        self.log.AppendText(line + u"\n")
        self.log.ScrollToEnd()
        self.Dispatcher.Invoke(Action(lambda: None), DispatcherPriority.Background)

    # ---- buttons
    def close_click(self, sender, args):
        self.Close()

    def add_click(self, sender, args):
        self.log.Clear()
        name = (self.param_name.Text or u"").strip()
        error = falcon_params.name_error(name)
        if error:
            self.write(error)
            return
        if not self.ticked_families and not self.ticked_types:
            self.write(u"Tick at least one family or type.")
            return
        label, kind = falcon_params.DATA_TYPES[max(self.data_type.SelectedIndex, 0)]
        group = falcon_params.GROUPS[max(self.group.SelectedIndex, 0)]
        try:
            parsed = falcon_params.parse_value(kind, self.value.Text)
        except ValueError as ex:
            self.write(u"{}".format(ex))
            return
        falcon_settings.save(SECTION, {"data_type": label, "group": group[0]})

        jobs = falcon_params.plan_jobs(sorted(self.ticked_families),
                                       sorted(self.ticked_types), self.family_of_type)
        self.add_button.IsEnabled = False
        self.Cursor = Cursors.Wait
        try:
            self.run(name, kind, group, parsed, jobs)
        except Exception as ex:
            self.write(u"Stopped: {}".format(ex))
        finally:
            self.Cursor = None
            self.add_button.IsEnabled = True

    def run(self, name, kind, group, parsed, jobs):
        self.write(u"Working... Revit is editing and reloading {} family(ies). "
                   u"Please wait.".format(len(jobs)))
        shared = SharedFile()
        ok = 0
        try:
            definition, is_new = shared.definition(name, kind)
            if not is_new:
                self.write(u"Using '{}' already in the shared parameter file "
                           u"(its data type is kept).".format(name))
            for fam_key in sorted(jobs, key=lambda k: self.by_key[k].name):
                fam = self.by_key[fam_key]
                try:
                    note = add_to_family(fam.family, definition, group, jobs[fam_key]["instance"])
                    ok += 1
                    self.write(u"  OK    {} - {}".format(fam.name, note))
                except Exception as ex:
                    self.write(u"  FAIL  {} - {}".format(fam.name, ex))
        finally:
            shared.restore()

        if parsed is not None:
            if not any(job["types"] for job in jobs.values()):
                self.write(u"No type is ticked, so the value was not set.")
            else:
                done, failed = set_values(name, parsed, jobs, self.by_key)
                self.write(u"Value set on {} element(s){}.".format(
                    done, u", {} could not take it".format(failed) if failed else u""))
        self.write(u"Done. '{}' is in {} of {} family(ies). Shared parameter file: {}".format(
            name, ok, len(jobs), shared.path))


def main():
    if doc is None or doc.IsFamilyDocument:
        forms.alert("Open a Revit project (not a family) first.", title=TITLE)
        return
    families = editable_families()
    if not families:
        forms.alert("No editable families are loaded in this project.", title=TITLE)
        return
    AddParamWindow(families, falcon_settings.load(SECTION, DEFAULTS)).show_dialog()


try:
    main()
except Exception:
    output = script.get_output()
    output.print_md("**Falcon - Add Param stopped.**")
    output.print_code(traceback.format_exc())
