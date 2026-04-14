"""
Houdini Radial Menu – Viewport Display Toggles
================================================

This is a radial menu for Houdini to give a faster access to the variety of display options.
Install: Edit > Radial Menus > New

copyright 2026 Simon Trapp
"""


import hou


# ── Helper: get the DisplayModel display set from the pane ───────────

def _get_display_set(pane):
    """Return the DisplayModel GeometryViewportDisplaySet."""
    viewport = pane.curViewport()
    settings = viewport.settings()
    return settings.displaySet(hou.displaySetType.DisplayModel)


# ── Toggle functions ─────────────────────────────────────────────────
# Each receives **kwargs from the radial menu system.
# kwargs["pane"] is the SceneViewer pane tab.

def toggle_point_markers(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPointMarkers(not ds.isShowingPointMarkers())

def toggle_point_normals(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPointNormals(not ds.isShowingPointNormals())

def toggle_point_trails(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPointTrails(not ds.isShowingPointTrails())

def toggle_point_numbers(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPointNumbers(not ds.isShowingPointNumbers())

def toggle_prim_normals(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPrimNormals(not ds.isShowingPrimNormals())

def toggle_prim_numbers(**kwargs):
    ds = _get_display_set(kwargs["pane"])
    ds.showPrimNumbers(not ds.isShowingPrimNumbers())

# ── Check functions (return True if ON) ──────────────────────────────

def check_point_markers(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPointMarkers()

def check_point_normals(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPointNormals()

def check_point_trails(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPointTrails()

def check_point_numbers(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPointNumbers()

def check_prim_normals(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPrimNormals()

def check_prim_numbers(**kwargs):
    return _get_display_set(kwargs["pane"]).isShowingPrimNumbers()


# ── Visualizer submenu (dynamically lists node visualizers) ──────────

def _get_selected_node():
    selected = hou.selectedNodes()
    if selected:
        return selected[0]
    return None

def _make_viz_toggle(viz):
    def toggle(**kw):
        try:
            vp = kw["pane"].curViewport()
            viz.setIsActive(not viz.isActive(viewport=vp), viewport=vp)
        except TypeError:
            viz.setIsActive(not viz.isActive())
    return toggle

def _make_viz_check(viz):
    def check(**kw):
        try:
            vp = kw["pane"].curViewport()
            return viz.isActive(viewport=vp)
        except TypeError:
            return viz.isActive()
    return check

def _build_viz_page(vizs, page=0, **kwargs):
    """Create a submenu:

    Possible positions (n, ne, e, se, s, sw, nw).
    w for more, e for back if necessary
    """
    page_slots = ("n", "ne", "se", "s", "sw", "nw")
    items_per_page = len(page_slots)  # 6

    start = page * items_per_page
    page_vizs = vizs[start:start + items_per_page]
    remaining = vizs[start + items_per_page:]

    submenu = {}

    for slot, viz in zip(page_slots, page_vizs):
        submenu[slot] = {
            "type": "script_action",
            "label": viz.label(),
            "icon": viz.icon() if viz.icon() else "BUTTONS_visualize",
            "script": _make_viz_toggle(viz),
            "check": _make_viz_check(viz),
        }

    # If more than 7 visualiziers, add the more option
    if remaining:
        def make_next_page(next_page=page + 1, all_vizs=vizs):
            def build(**kw):
                _build_viz_page(all_vizs, page=next_page, **kw)
            return build

        submenu["w"] = {
            "type": "script_submenu",
            "label": "More... ({} left)".format(len(remaining)),
            "icon": "BUTTONS_resimulate",
            "script": make_next_page(),
        }

    radialmenu.setRadialMenu(submenu)

def build_visualizer_submenu(**kwargs):
    pane = kwargs["pane"]
    node = _get_selected_node()

    submenu = {}

    if node is None:
        submenu["n"] = {
            "type": "script_action",
            "label": "No node selected",
            "script": lambda **kw: None,
        }
        radialmenu.setRadialMenu(submenu)
        return

    vizs = []

    try:
        vizs.extend(hou.viewportVisualizers.visualizers(
            category=hou.viewportVisualizerCategory.Common
        ))
    except Exception:
        pass

    # Scene-level visualizers
    try:
        vizs.extend(hou.viewportVisualizers.visualizers(
            category=hou.viewportVisualizerCategory.Scene
        ))
    except Exception:
        pass

    # Node-level visualizers
    try:
        vizs.extend(hou.viewportVisualizers.visualizers(
            category=hou.viewportVisualizerCategory.Node, node=node
        ))
    except Exception:
        pass

    if not vizs:
        submenu["n"] = {
            "type": "script_action",
            "label": "No visualizers found",
            "script": lambda **kw: None,
        }
        radialmenu.setRadialMenu(submenu)
        return

    _build_viz_page(vizs, page=0, **kwargs)


# ── Build the radial menu ───────────────────────────────────────────

menu = {
    "n": {
        "type": "script_action",
        "label": "Points",
        "icon": "VIEW_display_points",
        "script": toggle_point_markers,
        "check": check_point_markers,
    },
    "ne": {
        "type": "script_action",
        "label": "Point Normals",
        "icon": "VIEW_display_point_normals",
        "script": toggle_point_normals,
        "check": check_point_normals,
    },
    "e": {
        "type": "script_action",
        "label": "Point Trails",
        "icon": "VIEW_display_point_velocities",
        "script": toggle_point_trails,
        "check": check_point_trails,
    },
    "se": {
        "type": "script_action",
        "label": "Point Numbers",
        "icon": "VIEW_display_point_numbers",
        "script": toggle_point_numbers,
        "check": check_point_numbers,
    },
    "s": {
        "type": "script_action",
        "label": "Prim Normals",
        "icon": "VIEW_display_primitive_normals",
        "script": toggle_prim_normals,
        "check": check_prim_normals,
    },
    "sw": {
        "type": "script_action",
        "label": "Prim Numbers",
        "icon": "VIEW_display_primitive_numbers",
        "script": toggle_prim_numbers,
        "check": check_prim_numbers,
    },
    "w": {
        "type": "script_submenu",
        "label": "Visualization",
        "icon": "VIEW_visualization",
        "script": build_visualizer_submenu,
    },
}

radialmenu.setRadialMenu(menu)