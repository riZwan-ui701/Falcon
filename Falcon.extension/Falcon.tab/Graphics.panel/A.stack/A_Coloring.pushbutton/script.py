# ============================================================
# Tool Metadata
# ============================================================
# Tool Name      : Coloring
# Purpose        : Color a whole family, one of its types, or picked
#                  elements, so systems read clearly in plans and 3D.
# Author         : Rizwan Zahid
# Version        : 2.0.0
# Created Date   : 2026-11-12
# Updated Date   : 2026-11-17
# Status         : Production
#
# Target Revit   : Revit 2020 - 2027
# Platform       : pyRevit
# Python Version : IronPython 2.7
#
# Category       : BIM Automation
# Discipline     : All Disciplines (built for Electrical)
# Tool Type      : pyRevit Tool
#
# Input          : Menu (comes back until Close). Color Family - families /
#                  types ticked or clicked in a list. Color Element -
#                  elements picked with Finish, filtered by category, then
#                  a color.
# Output         : Color Family - FALCON_COLOR_* view filters on project views
#                  and their templates (3D optional).
#                  Color Element - view overrides in the active view and
#                  every 3D view.
#
# Dependencies   :
#   - pyRevit
#   - Revit API
#   - Falcon.extension/lib/falcon_color.py, falcon_naming.py, falcon_markup.py
#
# Features       :
#   - Search, "only used" filter, swatches showing current colors
#   - Remove color from selected / remove all Coloring colors
#   - Never changes the elements themselves - graphics only
#
# Notes          :
#   - Designed for production BIM workflows.
#   - IronPython 2.7-safe, so it runs on every supported Revit version.
#   - Project only: exits with a message in the Family Editor.
#
# Changelog
# ------------------------------------------------------------
# v2.0.0
# - Menu window that comes back after each action until Close
# - Click a family/type row to color it; status says how many elements match
# - Color Element: pick (Finish), filter by category, then the color
# v1.0.0
# - Initial Release
#
# License        : Proprietary
# Copyright      : (c) Rizwan Zahid. All Rights Reserved
# ============================================================

import os

import clr
clr.AddReference("PresentationFramework")
clr.AddReference("PresentationCore")
clr.AddReference("WindowsBase")

from System.Windows import Thickness, VerticalAlignment
from System.Windows.Controls import (TreeViewItem, StackPanel, CheckBox,
                                     TextBlock, Orientation)
from System.Windows.Shapes import Rectangle
from System.Windows.Media import SolidColorBrush, Color as WColor, Brushes

from System.Collections.Generic import List

from pyrevit import revit, DB, forms, script
from Autodesk.Revit.UI.Selection import ObjectType
from Autodesk.Revit.Exceptions import OperationCanceledException

import falcon_color
import falcon_naming
import falcon_safety

TITLE = "Falcon - Coloring"
SYSTEM_CATEGORIES = (
    DB.BuiltInCategory.OST_Conduit,
    DB.BuiltInCategory.OST_CableTray,
    DB.BuiltInCategory.OST_PipeCurves,
    DB.BuiltInCategory.OST_DuctCurves,
)

doc = revit.doc
uidoc = revit.uidoc


def _name(element):
    try:
        return element.Name
    except Exception:
        return DB.Element.Name.__get__(element)


# ------------------------------------------------------------ data

class FamilyEntry(object):
    def __init__(self, name, category):
        self.name = name
        self.category_name = category.Name
        self.category_id = category.Id
        self.types = []          # [(type name, type id int)]

    def add_type(self, type_name, type_id):
        self.types.append((type_name, falcon_color.eid_int(type_id)))


def used_type_counts():
    """{type id int: number of placed elements of that type}."""
    used = {}
    for el in DB.FilteredElementCollector(doc).WhereElementIsNotElementType():
        try:
            tid = el.GetTypeId()
        except Exception:
            continue
        if tid is not None and tid != DB.ElementId.InvalidElementId:
            key = falcon_color.eid_int(tid)
            used[key] = used.get(key, 0) + 1
    return used


def collect_families():
    entries = {}
    for fam in DB.FilteredElementCollector(doc).OfClass(DB.Family):
        cat = fam.FamilyCategory
        if cat is None or cat.CategoryType != DB.CategoryType.Model:
            continue
        entry = FamilyEntry(fam.Name, cat)
        for sid in fam.GetFamilySymbolIds():
            entry.add_type(_name(doc.GetElement(sid)), sid)
        entries[(fam.Name, falcon_color.eid_int(cat.Id))] = entry

    for bic in SYSTEM_CATEGORIES:
        types = DB.FilteredElementCollector(doc).OfCategory(bic).WhereElementIsElementType()
        for etype in types:
            cat = etype.Category
            if cat is None:
                continue
            key = (etype.FamilyName, falcon_color.eid_int(cat.Id))
            if key not in entries:
                entries[key] = FamilyEntry(etype.FamilyName, cat)
            entries[key].add_type(_name(etype), etype.Id)

    return sorted(entries.values(), key=lambda e: e.name.lower())


# ------------------------------------------------------------ window

def _brush(color):
    return SolidColorBrush(WColor.FromRgb(color.Red, color.Green, color.Blue))


class ColorFamilyWindow(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "ColorFamily.xaml"))
        self.families = collect_families()
        self.used = used_type_counts()
        self.checked = set()       # keys: (family, type or None)
        self.category_of = dict((f.name, f.category_name) for f in self.families)
        self.clicked = None        # key of the row clicked in the tree
        self.nodes = []
        self.colors = falcon_color.filter_colors(doc)
        self.tree.SelectedItemChanged += self.row_clicked
        self.build_tree()

    # ---------- tree
    def _header(self, key, label, filter_key):
        panel = StackPanel()
        panel.Orientation = Orientation.Horizontal
        box = CheckBox()
        box.IsChecked = key in self.checked
        box.Tag = key
        box.Click += self.node_click
        box.VerticalAlignment = VerticalAlignment.Center
        swatch = Rectangle()
        swatch.Width = swatch.Height = 12
        swatch.Margin = Thickness(4, 0, 4, 0)
        swatch.Stroke = Brushes.Gray
        color = self.colors.get(filter_key)
        swatch.Fill = _brush(color) if color is not None else Brushes.Transparent
        text = TextBlock()
        text.Text = label
        panel.Children.Add(box)
        panel.Children.Add(swatch)
        panel.Children.Add(text)
        if key[1] is None:
            cat = TextBlock()
            cat.Text = u"   ({})".format(self.category_of.get(key[0], u""))
            cat.Foreground = Brushes.Gray
            panel.Children.Add(cat)
        return panel

    def build_tree(self):
        self.tree.Items.Clear()
        needle = (self.search.Text or "").strip().lower()
        only_used = bool(self.only_used.IsChecked)
        for fam in self.families:
            types = fam.types
            if only_used:
                types = [t for t in types if t[1] in self.used]
                if not types:
                    continue
            fam_match = needle in fam.name.lower()
            if needle and not fam_match:
                types = [t for t in types if needle in t[0].lower()]
                if not types:
                    continue
            item = TreeViewItem()
            item.Tag = (fam.name, None)
            item.Header = self._header(
                (fam.name, None), fam.name, falcon_naming.filter_name(fam.name))
            for type_name, _tid in sorted(types):
                child = TreeViewItem()
                child.Tag = (fam.name, type_name)
                child.Header = self._header(
                    (fam.name, type_name), type_name,
                    falcon_naming.filter_name(fam.name, type_name))
                item.Items.Add(child)
            item.IsExpanded = bool(needle)
            self.tree.Items.Add(item)

    def node_click(self, sender, args):
        if sender.IsChecked:
            self.checked.add(sender.Tag)
        else:
            self.checked.discard(sender.Tag)
        self.show_selected()

    def row_clicked(self, sender, args):
        item = self.tree.SelectedItem
        self.clicked = getattr(item, "Tag", None) if item is not None else None
        self.show_selected()

    def chosen(self):
        """Ticked rows, or the clicked row when nothing is ticked."""
        if self.checked:
            return set(self.checked)
        return set([self.clicked]) if self.clicked else set()

    def show_selected(self):
        chosen = self.chosen()
        if not chosen:
            self.selected_text.Text = "Nothing selected"
            return
        lines = []
        for fam, typ in sorted(chosen, key=lambda k: (k[0], k[1] or "")):
            lines.append(u"Type: {} : {}".format(fam, typ) if typ else u"Family: {}".format(fam))
        self.selected_text.Text = "\n".join(lines)

    def targets(self):
        """[(FamilyEntry, type name or None)] - a ticked family only counts
        when none of its types are ticked."""
        by_name = dict((f.name, f) for f in self.families)
        chosen = self.chosen()
        typed = set(k[0] for k in chosen if k[1] is not None)
        result = []
        for fam, typ in chosen:
            entry = by_name.get(fam)
            if entry is None or (typ is None and fam in typed):
                continue
            result.append((entry, typ))
        return result

    def matching(self, targets):
        count = 0
        for entry, typ in targets:
            for type_name, tid in entry.types:
                if typ is None or type_name == typ:
                    count += self.used.get(tid, 0)
        return count

    def refresh(self, message):
        self.colors = falcon_color.filter_colors(doc)
        self.build_tree()
        self.status.Text = message

    # ---------- events
    def search_changed(self, sender, args):
        if hasattr(self, "families"):   # events can fire while XAML loads
            self.build_tree()

    def filter_changed(self, sender, args):
        if hasattr(self, "families"):
            self.build_tree()

    def choose_click(self, sender, args):
        targets = self.targets()
        if not targets:
            self.status.Text = "Tick a family or a type first."
            return
        color = falcon_color.pick_color()
        if color is None:
            return
        include_3d = bool(self.also_3d.IsChecked)
        failures = []
        views_done = 0
        with revit.TransactionGroup("Falcon: Color Family"):
            with revit.Transaction("Falcon: Color Family"):
                views = falcon_color.target_views(doc, include_3d)
                ogs = falcon_color.color_override(doc, color)
                for entry, typ in targets:
                    try:
                        filt = falcon_color.ensure_filter(doc, entry.name, entry.category_id, typ)
                        views_done = max(views_done, falcon_color.apply_filter(views, filt, ogs))
                    except Exception as ex:
                        failures.append(u"{}: {}".format(entry.name, ex))
        if len(targets) == 1:
            entry, typ = targets[0]
            what = u'type "{} : {}"'.format(entry.name, typ) if typ else u'family "{}"'.format(entry.name)
        else:
            what = u"{} item(s)".format(len(targets))
        msg = u"Colored {} in {} view(s).".format(what, views_done)
        if not include_3d:
            msg += u" 3D views were left out."
        msg += u" {} element(s) match.".format(self.matching(targets))
        if failures:
            msg += u" Skipped: " + u"; ".join(failures)
        self.refresh(msg)

    def remove_click(self, sender, args):
        targets = self.targets()
        if not targets:
            self.status.Text = "Tick a family or a type first."
            return
        existing = falcon_color.falcon_filters(doc)
        filters = [existing[n] for n in
                   (falcon_naming.filter_name(e.name, t) for e, t in targets) if n in existing]
        with revit.Transaction("Falcon: Remove Color"):
            count = falcon_color.delete_filters(doc, filters)
        self.refresh(u"Removed color from {} item(s).".format(count))

    def remove_all_click(self, sender, args):
        filters = list(falcon_color.falcon_filters(doc).values())
        if not filters:
            self.status.Text = "There are no Coloring colors in this project."
            return
        if not forms.alert(u"Remove all {} Coloring color(s) from every view?".format(len(filters)),
                           title=TITLE, yes=True, no=True):
            return
        with revit.Transaction("Falcon: Remove All Colors"):
            count = falcon_color.delete_filters(doc, filters)
        self.refresh(u"Removed {} Coloring color(s).".format(count))

    def close_click(self, sender, args):
        self.Close()


# ------------------------------------------------------------ element mode

class CategoryFilter(forms.WPFWindow):
    """Untick the categories you do not want to color."""

    def __init__(self, elements):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "FilterSelection.xaml"))
        self.result = None
        self.by_cat = {}
        for el in elements:
            cat = el.Category
            name = cat.Name if cat is not None else u"(no category)"
            self.by_cat.setdefault(name, []).append(el)
        self.intro.Text = (u"{} elements selected. Untick the categories you do not "
                           u"want to color.".format(len(elements)))
        self.checks = []
        for name in sorted(self.by_cat):
            box = CheckBox()
            box.Content = u"{}  ({})".format(name, len(self.by_cat[name]))
            box.Tag = name
            box.IsChecked = True
            box.Margin = Thickness(0, 2, 0, 2)
            self.boxes.Children.Add(box)
            self.checks.append(box)

    def check_all(self, sender, args):
        for box in self.checks:
            box.IsChecked = True

    def uncheck_all(self, sender, args):
        for box in self.checks:
            box.IsChecked = False

    def ok_click(self, sender, args):
        self.result = [el for box in self.checks if box.IsChecked
                       for el in self.by_cat[box.Tag]]
        self.Close()

    def cancel_click(self, sender, args):
        self.Close()


def color_element_mode():
    pre = List[DB.Reference]()
    for eid in uidoc.Selection.GetElementIds():
        el = doc.GetElement(eid)
        if el is not None and el.Category is not None:
            pre.Add(DB.Reference(el))
    try:
        refs = uidoc.Selection.PickObjects(
            ObjectType.Element,
            "Select the elements to color (Tab selects a connected run), then click "
            "Finish. Linked models are ignored.", pre)
    except OperationCanceledException:
        return
    elements = [doc.GetElement(r.ElementId) for r in refs]
    elements = [e for e in elements if e is not None
                and not isinstance(e, DB.RevitLinkInstance)]
    if not elements:
        return
    picker = CategoryFilter(elements)
    picker.show_dialog()
    if not picker.result:
        return
    color = falcon_color.pick_color()
    if color is None:
        return
    with revit.Transaction("Falcon: Color Element"):
        total, views_3d = falcon_color.color_elements(
            doc, [el.Id for el in picker.result], color)
    forms.alert(u'Colored {} element(s) in view "{}" and in {} 3D view(s).'.format(
        total, doc.ActiveView.Name, views_3d), title=TITLE)


# ------------------------------------------------------------ main

class ColoringMenu(forms.WPFWindow):
    def __init__(self):
        forms.WPFWindow.__init__(
            self, os.path.join(os.path.dirname(__file__), "ColoringMenu.xaml"))
        self.choice = None
        self.element_text.Text = (
            u"Pick elements in the model (a conduit, a tray, anything) and give them a "
            u"color. Shows in the current view ({}) and in the 3D views.".format(
                doc.ActiveView.Name))

    def family_click(self, sender, args):
        self.choice = "family"
        self.Close()

    def element_click(self, sender, args):
        self.choice = "element"
        self.Close()

    def close_click(self, sender, args):
        self.Close()


if not falcon_safety.project_only(doc, TITLE):
    script.exit()

while True:
    menu = ColoringMenu()
    menu.show_dialog()
    if menu.choice == "family":
        ColorFamilyWindow().show_dialog()
    elif menu.choice == "element":
        color_element_mode()
    else:
        break
