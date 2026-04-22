# core/tools_handlers.py
#
# Python implementation of every tool exposed to the agent.
# Each handler receives plain arguments (str, int, dict...)
# and returns a structured dict the LLM can interpret.
#
# IMPORTANT: no qgis imports at module level — all QGIS imports are
# deferred inside functions to stay compatible with the embedded QGIS environment.

import traceback


# ══════════════════════════════════════════════════════════════
# INTERNAL HELPERS
# ══════════════════════════════════════════════════════════════

def _get_layer(layer_name: str):
    """Return the first layer whose name matches, or None if not found."""
    from qgis.core import QgsProject
    layers = QgsProject.instance().mapLayersByName(layer_name)
    return layers[0] if layers else None


def _ok(tool: str, **kwargs) -> dict:
    return {"success": True, "tool": tool, **kwargs}


def _err(tool: str, message: str) -> dict:
    return {"success": False, "tool": tool, "error": message}


# ══════════════════════════════════════════════════════════════
# CATEGORY: READ / PROJECT INSPECTION
# ══════════════════════════════════════════════════════════════

def get_project_info() -> dict:
    """List all layers and general project metadata."""
    from qgis.core import QgsProject, QgsVectorLayer, QgsRasterLayer
    prj = QgsProject.instance()
    layers = []
    for layer in prj.mapLayers().values():
        info = {
            "name": layer.name(),
            "type": "vector" if isinstance(layer, QgsVectorLayer)
                    else "raster" if isinstance(layer, QgsRasterLayer)
                    else "other",
            "crs": layer.crs().authid() if layer.crs().isValid() else "",
            "visible": True,
        }
        if isinstance(layer, QgsVectorLayer):
            info["geometry"] = layer.geometryType()  # 0=Point 1=Line 2=Polygon
            info["feature_count"] = layer.featureCount()
        layers.append(info)
    return _ok("get_project_info",
               project_crs=prj.crs().authid(),
               layer_count=len(layers),
               layers=layers)


def get_layer_info(layer_name: str) -> dict:
    """Return full details for a layer: CRS, geometry type, feature count, extent, source path."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_info", f"Couche introuvable : {layer_name}")
    info = {
        "name": layer.name(),
        "crs": layer.crs().authid(),
        "source": layer.source(),
    }
    if isinstance(layer, QgsVectorLayer):
        ext = layer.extent()
        info.update({
            "geometry_type": layer.geometryType(),
            "feature_count": layer.featureCount(),
            "field_count": len(layer.fields()),
            "extent": [ext.xMinimum(), ext.yMinimum(),
                       ext.xMaximum(), ext.yMaximum()],
        })
    return _ok("get_layer_info", **info)


def get_layer_fields(layer_name: str) -> dict:
    """List all fields of a vector layer with their name, type, and alias."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_fields", f"Couche introuvable : {layer_name}")
    if not isinstance(layer, QgsVectorLayer):
        return _err("get_layer_fields", f"{layer_name} n'est pas une couche vecteur")
    fields = [
        {"name": f.name(), "type": f.typeName(), "alias": f.alias()}
        for f in layer.fields()
    ]
    return _ok("get_layer_fields", layer=layer_name, fields=fields, count=len(fields))


def get_layer_features(layer_name: str,
                       filter_expression: str = "",
                       max_features: int = 50) -> dict:
    """Return feature attributes, optionally filtered by an expression."""
    from qgis.core import QgsVectorLayer, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_features", f"Couche introuvable : {layer_name}")
    if not isinstance(layer, QgsVectorLayer):
        return _err("get_layer_features", f"{layer_name} n'est pas une couche vecteur")

    req = QgsFeatureRequest()
    if filter_expression:
        req.setFilterExpression(filter_expression)
    req.setLimit(max_features)

    features = []
    field_names = [f.name() for f in layer.fields()]
    for feat in layer.getFeatures(req):
        features.append({name: feat[name] for name in field_names})

    return _ok("get_layer_features",
               layer=layer_name,
               filter=filter_expression or None,
               returned=len(features),
               total=layer.featureCount(),
               features=features)


def get_layer_statistics(layer_name: str, field_name: str) -> dict:
    """Compute basic statistics for a numeric field: min, max, mean, sum, count, stddev."""
    import processing
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_statistics", f"Couche introuvable : {layer_name}")
    try:
        result = processing.run("native:basicstatisticsforfields", {
            "INPUT": layer,
            "FIELD_NAME": field_name,
        })
        return _ok("get_layer_statistics",
                   layer=layer_name,
                   field=field_name,
                   min=result.get("MIN"),
                   max=result.get("MAX"),
                   mean=result.get("MEAN"),
                   sum=result.get("SUM"),
                   count=result.get("COUNT"),
                   stddev=result.get("STD_DEV"))
    except Exception as e:
        return _err("get_layer_statistics", str(e))


def get_unique_values(layer_name: str, field_name: str) -> dict:
    """Return the distinct values present in a field."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_unique_values", f"Couche vecteur introuvable : {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("get_unique_values", f"Champ introuvable : {field_name}")
    values = sorted([str(v) for v in layer.uniqueValues(idx)])
    return _ok("get_unique_values",
               layer=layer_name,
               field=field_name,
               values=values,
               count=len(values))


def get_selected_features(layer_name: str) -> dict:
    """Return the currently selected features with their attributes."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_selected_features", f"Couche vecteur introuvable : {layer_name}")
    field_names = [f.name() for f in layer.fields()]
    features = [
        {name: feat[name] for name in field_names}
        for feat in layer.selectedFeatures()
    ]
    return _ok("get_selected_features",
               layer=layer_name,
               selected_count=layer.selectedFeatureCount(),
               features=features)


def get_layer_extent(layer_name: str) -> dict:
    """Return the bounding box extent of a layer."""
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_extent", f"Couche introuvable : {layer_name}")
    ext = layer.extent()
    return _ok("get_layer_extent",
               layer=layer_name,
               crs=layer.crs().authid(),
               xmin=ext.xMinimum(), ymin=ext.yMinimum(),
               xmax=ext.xMaximum(), ymax=ext.yMaximum())


# ══════════════════════════════════════════════════════════════
# CATEGORY: GEOPROCESSING
# ══════════════════════════════════════════════════════════════

def _run_algo(tool_name: str, algorithm: str, params: dict,
              output_layer_name: str) -> dict:
    """Shared helper that runs a Processing algorithm and adds the result to the project."""
    import processing
    from qgis.core import QgsProject
    try:
        params["OUTPUT"] = "memory:"
        result = processing.run(algorithm, params)
        out = result.get("OUTPUT")
        if out is None:
            return _err(tool_name, "L'algorithme n'a retourné aucune couche OUTPUT")
        out.setName(output_layer_name)
        QgsProject.instance().addMapLayer(out)
        return _ok(tool_name,
                   algorithm=algorithm,
                   output_layer=output_layer_name,
                   feature_count_out=out.featureCount(),
                   crs=out.crs().authid(),
                   added_to_project=True)
    except Exception as e:
        return _err(tool_name, f"{algorithm} : {traceback.format_exc()}")


def buffer(layer_name: str, distance: float,
           dissolve: bool = False, segments: int = 5,
           output_layer_name: str = "buffer_result") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("buffer", f"Couche introuvable : {layer_name}")
    feature_count_in = layer.featureCount()
    result = _run_algo("buffer", "native:buffer", {
        "INPUT": layer,
        "DISTANCE": distance,
        "SEGMENTS": segments,
        "END_CAP_STYLE": 0,
        "JOIN_STYLE": 0,
        "MITER_LIMIT": 2,
        "DISSOLVE": dissolve,
    }, output_layer_name)
    if result["success"]:
        result["feature_count_in"] = feature_count_in
    return result


def clip(layer_name: str, overlay_layer_name: str,
         output_layer_name: str = "clip_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer:
        return _err("clip", f"Couche introuvable : {layer_name}")
    if not overlay:
        return _err("clip", f"Couche de découpe introuvable : {overlay_layer_name}")
    return _run_algo("clip", "native:clip",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def intersection(layer_name: str, overlay_layer_name: str,
                 output_layer_name: str = "intersection_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("intersection", "Couche(s) introuvable(s)")
    return _run_algo("intersection", "native:intersection",
                     {"INPUT": layer, "OVERLAY": overlay,
                      "INPUT_FIELDS": [], "OVERLAY_FIELDS": []},
                     output_layer_name)


def dissolve(layer_name: str, field: str = "",
             output_layer_name: str = "dissolve_result") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("dissolve", f"Couche introuvable : {layer_name}")
    return _run_algo("dissolve", "native:dissolve",
                     {"INPUT": layer, "FIELD": [field] if field else []},
                     output_layer_name)


def reproject_layer(layer_name: str, target_crs: str,
                    output_layer_name: str = "reprojected") -> dict:
    from qgis.core import QgsCoordinateReferenceSystem
    layer = _get_layer(layer_name)
    if not layer:
        return _err("reproject_layer", f"Couche introuvable : {layer_name}")
    crs = QgsCoordinateReferenceSystem(target_crs)
    if not crs.isValid():
        return _err("reproject_layer", f"CRS invalide : {target_crs}")
    return _run_algo("reproject_layer", "native:reprojectlayer",
                     {"INPUT": layer, "TARGET_CRS": crs},
                     output_layer_name)


def join_by_location(layer_name: str, join_layer_name: str,
                     predicates: list = None,
                     join_fields: list = None,
                     method: int = 0,
                     discard_nonmatching: bool = False,
                     prefix: str = "",
                     output_layer_name: str = "joined_result") -> dict:
    layer = _get_layer(layer_name)
    join_layer = _get_layer(join_layer_name)
    if not layer or not join_layer:
        return _err("join_by_location", "Couche(s) introuvable(s)")
    return _run_algo("join_by_location", "native:joinattributesbylocation", {
        "INPUT": layer,
        "JOIN": join_layer,
        "PREDICATE": predicates or [0],
        "JOIN_FIELDS": join_fields or [],
        "METHOD": method,
        "DISCARD_NONMATCHING": discard_nonmatching,
        "PREFIX": prefix,
    }, output_layer_name)


def centroids(layer_name: str,
              output_layer_name: str = "centroids_result") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("centroids", f"Couche introuvable : {layer_name}")
    return _run_algo("centroids", "native:centroids",
                     {"INPUT": layer, "ALL_PARTS": False},
                     output_layer_name)


def difference(layer_name: str, overlay_layer_name: str,
               output_layer_name: str = "difference_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("difference", "Couche(s) introuvable(s)")
    return _run_algo("difference", "native:difference",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def union(layer_name: str, overlay_layer_name: str,
          output_layer_name: str = "union_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("union", "Couche(s) introuvable(s)")
    return _run_algo("union", "native:union",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def fix_geometries(layer_name: str,
                   output_layer_name: str = "fixed_geometries") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("fix_geometries", f"Couche introuvable : {layer_name}")
    return _run_algo("fix_geometries", "native:fixgeometries",
                     {"INPUT": layer},
                     output_layer_name)


def run_processing_algorithm(algorithm: str, layer_name: str,
                             parameters: dict,
                             output_layer_name: str = "algo_result") -> dict:
    """Generic fallback: run any Processing algorithm by its string identifier."""
    import processing
    from qgis.core import QgsProject
    layer = _get_layer(layer_name)
    if not layer:
        return _err("run_processing_algorithm", f"Couche introuvable : {layer_name}")
    params = dict(parameters)
    params["INPUT"] = layer
    params["OUTPUT"] = "memory:"
    try:
        result = processing.run(algorithm, params)
        out = result.get("OUTPUT")
        if out is None:
            return _err("run_processing_algorithm",
                        f"Aucune couche OUTPUT retournée par {algorithm}")
        out.setName(output_layer_name)
        QgsProject.instance().addMapLayer(out)
        return _ok("run_processing_algorithm",
                   algorithm=algorithm,
                   output_layer=output_layer_name,
                   feature_count_out=out.featureCount(),
                   added_to_project=True)
    except Exception:
        return _err("run_processing_algorithm", traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# CATEGORY: SELECTION / FILTERING
# ══════════════════════════════════════════════════════════════

def select_by_expression(layer_name: str, expression: str) -> dict:
    """Select features using a QGIS expression string."""
    from qgis.core import QgsVectorLayer, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("select_by_expression", f"Couche vecteur introuvable : {layer_name}")
    layer.selectByExpression(expression)
    return _ok("select_by_expression",
               layer=layer_name,
               expression=expression,
               selected_count=layer.selectedFeatureCount(),
               total_count=layer.featureCount())


def select_by_location(layer_name: str, intersect_layer_name: str,
                       predicate: int = 0) -> dict:
    """
    Select features by spatial relationship with another layer.
    predicate: 0=intersects, 1=contains, 2=disjoint, 3=equals,
               4=touches, 5=overlaps, 6=within, 7=crosses
    """
    import processing
    layer = _get_layer(layer_name)
    intersect_layer = _get_layer(intersect_layer_name)
    if not layer:
        return _err("select_by_location", f"Couche introuvable : {layer_name}")
    if not intersect_layer:
        return _err("select_by_location",
                    f"Couche d'intersection introuvable : {intersect_layer_name}")
    try:
        processing.run("native:selectbylocation", {
            "INPUT": layer,
            "PREDICATE": [predicate],
            "INTERSECT": intersect_layer,
            "METHOD": 0,  # new selection (replace existing)
        })
        return _ok("select_by_location",
                   layer=layer_name,
                   intersect_layer=intersect_layer_name,
                   predicate=predicate,
                   selected_count=layer.selectedFeatureCount(),
                   total_count=layer.featureCount())
    except Exception as e:
        return _err("select_by_location", str(e))


def set_layer_filter(layer_name: str, expression: str) -> dict:
    """
    Apply a persistent subset filter to the layer (setSubsetString).
    Pass expression="" to remove the filter.
    """
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_layer_filter", f"Couche vecteur introuvable : {layer_name}")
    ok = layer.setSubsetString(expression)
    if not ok:
        return _err("set_layer_filter",
                    f"Expression invalide : {expression}")
    return _ok("set_layer_filter",
               layer=layer_name,
               filter=expression or "(aucun)",
               visible_count=layer.featureCount())


def zoom_to_layer(layer_name: str, iface=None) -> dict:
    """Zoom the map canvas to the full extent of the layer."""
    from qgis.core import QgsProject
    layer = _get_layer(layer_name)
    if not layer:
        return _err("zoom_to_layer", f"Couche introuvable : {layer_name}")
    if iface:
        iface.mapCanvas().setExtent(layer.extent())
        iface.mapCanvas().refresh()
    return _ok("zoom_to_layer", layer=layer_name)


def zoom_to_feature(layer_name: str, feature_id: int, iface=None) -> dict:
    """Zoom the map canvas to the bounding box of a specific feature by its FID."""
    from qgis.core import QgsVectorLayer, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("zoom_to_feature", f"Couche vecteur introuvable : {layer_name}")
    req = QgsFeatureRequest().setFilterFid(feature_id)
    feats = list(layer.getFeatures(req))
    if not feats:
        return _err("zoom_to_feature", f"Feature {feature_id} introuvable")
    if iface:
        iface.mapCanvas().setExtent(feats[0].geometry().boundingBox())
        iface.mapCanvas().refresh()
    return _ok("zoom_to_feature", layer=layer_name, feature_id=feature_id)


# ══════════════════════════════════════════════════════════════
# CATEGORY: STYLING / DISPLAY
# ══════════════════════════════════════════════════════════════

def get_layer_style(layer_name: str) -> dict:
    """Return the current renderer type and style information for a layer."""
    from qgis.core import (QgsVectorLayer, QgsSingleSymbolRenderer,
                           QgsCategorizedSymbolRenderer,
                           QgsGraduatedSymbolRenderer)
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_layer_style", f"Couche vecteur introuvable : {layer_name}")
    renderer = layer.renderer()
    if renderer is None:
        return _ok("get_layer_style", layer=layer_name, renderer_type="none")
    rtype = renderer.type()
    info = {"renderer_type": rtype}
    if isinstance(renderer, QgsSingleSymbolRenderer):
        sym = renderer.symbol()
        info["color"] = sym.color().name() if sym else None
        info["opacity"] = sym.opacity() if sym else None
    elif isinstance(renderer, QgsCategorizedSymbolRenderer):
        info["field"] = renderer.classAttribute()
        info["categories"] = [
            {"value": str(cat.value()), "label": cat.label(),
             "color": cat.symbol().color().name()}
            for cat in renderer.categories()
        ]
    elif isinstance(renderer, QgsGraduatedSymbolRenderer):
        info["field"] = renderer.classAttribute()
        info["range_count"] = len(renderer.ranges())
    return _ok("get_layer_style", layer=layer_name, **info)


def set_single_symbol(layer_name: str, color: str,
                      opacity: float = 1.0,
                      outline_color: str = "#000000",
                      size: float = None) -> dict:
    """Apply a single-symbol renderer with the given fill color, outline color, and opacity."""
    from qgis.core import QgsVectorLayer, QgsSingleSymbolRenderer, QgsSymbol
    from qgis.PyQt.QtGui import QColor
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_single_symbol", f"Couche vecteur introuvable : {layer_name}")
    try:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(color))
        symbol.setOpacity(opacity)
        if size is not None:
            symbol.setSize(size)
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_single_symbol",
                   layer=layer_name, color=color, opacity=opacity)
    except Exception as e:
        return _err("set_single_symbol", str(e))


def set_categorized_style(layer_name: str, field_name: str,
                          color_ramp: str = "Spectral") -> dict:
    """Apply a categorized renderer based on a field, with random per-category colors."""
    from qgis.core import (QgsVectorLayer, QgsCategorizedSymbolRenderer,
                           QgsStyle, QgsRendererCategory, QgsSymbol,
                           QgsApplication)
    from qgis.PyQt.QtGui import QColor
    import random
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_categorized_style",
                    f"Couche vecteur introuvable : {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("set_categorized_style",
                    f"Champ introuvable : {field_name}")
    try:
        unique_vals = list(layer.uniqueValues(idx))
        categories = []
        for val in unique_vals:
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            r, g, b = random.randint(30, 220), random.randint(30, 220), random.randint(30, 220)
            symbol.setColor(QColor(r, g, b))
            categories.append(QgsRendererCategory(val, symbol, str(val)))
        renderer = QgsCategorizedSymbolRenderer(field_name, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_categorized_style",
                   layer=layer_name,
                   field=field_name,
                   category_count=len(categories))
    except Exception as e:
        return _err("set_categorized_style", str(e))


def set_graduated_style(layer_name: str, field_name: str,
                        num_classes: int = 5,
                        color_ramp_name: str = "Blues",
                        mode: int = 0) -> dict:
    """
    Apply a graduated renderer on a numeric field using a color ramp.
    mode: 0=Quantile, 1=EqualInterval, 2=NaturalBreaks
    """
    from qgis.core import (QgsVectorLayer, QgsGraduatedSymbolRenderer,
                           QgsStyle, QgsApplication)
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_graduated_style",
                    f"Couche vecteur introuvable : {layer_name}")
    try:
        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp(color_ramp_name)
        if ramp is None:
            ramp = style.colorRamp("Blues")
        renderer = QgsGraduatedSymbolRenderer(field_name)
        renderer.updateClasses(layer, mode, num_classes)
        renderer.updateColorRamp(ramp)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_graduated_style",
                   layer=layer_name,
                   field=field_name,
                   num_classes=num_classes,
                   color_ramp=color_ramp_name)
    except Exception as e:
        return _err("set_graduated_style", str(e))


def _get_all_symbols(renderer):
    """Return all symbols from any renderer type (single, categorized, graduated, rule-based)."""
    from qgis.core import (QgsSingleSymbolRenderer, QgsCategorizedSymbolRenderer,
                           QgsGraduatedSymbolRenderer, QgsRuleBasedRenderer)
    if isinstance(renderer, QgsSingleSymbolRenderer):
        sym = renderer.symbol()
        return [sym] if sym else []
    if isinstance(renderer, QgsCategorizedSymbolRenderer):
        return [cat.symbol() for cat in renderer.categories() if cat.symbol()]
    if isinstance(renderer, QgsGraduatedSymbolRenderer):
        return [r.symbol() for r in renderer.ranges() if r.symbol()]
    if isinstance(renderer, QgsRuleBasedRenderer):
        syms = []
        def _collect(rule):
            if rule.symbol():
                syms.append(rule.symbol())
            for child in rule.children():
                _collect(child)
        _collect(renderer.rootRule())
        return syms
    return []


def set_symbol_properties(layer_name: str,
                           size: float = None,
                           stroke_color: str = None,
                           stroke_width: float = None,
                           stroke_style: str = None) -> dict:
    """Modify size, stroke color/width/style on the existing symbol(s) of a layer."""
    from qgis.core import (QgsVectorLayer, QgsSimpleMarkerSymbolLayer,
                           QgsSimpleLineSymbolLayer, QgsSimpleFillSymbolLayer)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import Qt

    STROKE_STYLE_MAP = {
        "solid":    Qt.SolidLine,
        "dash":     Qt.DashLine,
        "dot":      Qt.DotLine,
        "dash_dot": Qt.DashDotLine,
        "no_line":  Qt.NoPen,
    }

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_symbol_properties", f"Couche vecteur introuvable : {layer_name}")

    renderer = layer.renderer()
    if renderer is None:
        return _err("set_symbol_properties", "Aucun renderer sur cette couche")

    try:
        symbols = _get_all_symbols(renderer)
        if not symbols:
            return _err("set_symbol_properties", "Aucun symbole trouvable dans le renderer")

        applied_types = set()
        for sym in symbols:
            for i in range(sym.symbolLayerCount()):
                sl = sym.symbolLayer(i)

                if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                    if size is not None:
                        sl.setSize(size)
                    if stroke_color is not None:
                        sl.setStrokeColor(QColor(stroke_color))
                    if stroke_width is not None:
                        sl.setStrokeWidth(stroke_width)
                    if stroke_style is not None:
                        sl.setStrokeStyle(STROKE_STYLE_MAP.get(stroke_style, Qt.SolidLine))
                    applied_types.add("marker")

                elif isinstance(sl, QgsSimpleLineSymbolLayer):
                    if size is not None:
                        sl.setWidth(size)
                    if stroke_color is not None:
                        sl.setColor(QColor(stroke_color))
                    if stroke_style is not None:
                        sl.setPenStyle(STROKE_STYLE_MAP.get(stroke_style, Qt.SolidLine))
                    applied_types.add("line")

                elif isinstance(sl, QgsSimpleFillSymbolLayer):
                    if stroke_color is not None:
                        sl.setStrokeColor(QColor(stroke_color))
                    if stroke_width is not None:
                        sl.setStrokeWidth(stroke_width)
                    if stroke_style is not None:
                        sl.setStrokeStyle(STROKE_STYLE_MAP.get(stroke_style, Qt.SolidLine))
                    applied_types.add("fill")

        layer.triggerRepaint()
        return _ok("set_symbol_properties",
                   layer=layer_name,
                   applied_to=list(applied_types),
                   symbol_count=len(symbols))
    except Exception:
        return _err("set_symbol_properties", traceback.format_exc())


def set_marker_shape(layer_name: str, shape: str) -> dict:
    """Change the marker shape for a point layer (circle, square, diamond, etc.)."""
    from qgis.core import QgsVectorLayer, QgsSimpleMarkerSymbolLayer

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_marker_shape", f"Couche vecteur introuvable : {layer_name}")
    if layer.geometryType() != 0:
        return _err("set_marker_shape", "Cette couche n'est pas de type Point")

    SHAPE_NAME_MAP = {
        "circle":   "Circle",
        "square":   "Square",
        "diamond":  "Diamond",
        "triangle": "Triangle",
        "star":     "Star",
        "cross":    "Cross",
        "x":        "Cross2",
        "arrow":    "Arrow",
    }
    shape_attr = SHAPE_NAME_MAP.get(shape)
    if shape_attr is None:
        return _err("set_marker_shape", f"Forme inconnue : {shape}")

    try:
        try:
            target_shape = getattr(QgsSimpleMarkerSymbolLayer.Shape, shape_attr)
        except AttributeError:
            target_shape = getattr(QgsSimpleMarkerSymbolLayer, shape_attr)

        renderer = layer.renderer()
        symbols = _get_all_symbols(renderer)
        count = 0
        for sym in symbols:
            for i in range(sym.symbolLayerCount()):
                sl = sym.symbolLayer(i)
                if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                    sl.setShape(target_shape)
                    count += 1

        layer.triggerRepaint()
        return _ok("set_marker_shape",
                   layer=layer_name, shape=shape, updated_symbol_layers=count)
    except Exception:
        return _err("set_marker_shape", traceback.format_exc())


def set_rule_based_style(layer_name: str, rules: list) -> dict:
    """Apply a rule-based renderer with multiple expression-driven rules."""
    from qgis.core import (QgsVectorLayer, QgsRuleBasedRenderer, QgsSymbol,
                           QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
                           QgsSimpleFillSymbolLayer)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_rule_based_style", f"Couche vecteur introuvable : {layer_name}")
    if not rules:
        return _err("set_rule_based_style", "La liste de règles est vide")

    try:
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for r in rules:
            expression  = r.get("expression", "")
            color       = r.get("color", "#888888")
            label       = r.get("label", expression or "Défaut")
            size        = r.get("size")
            stroke_clr  = r.get("stroke_color")
            stroke_w    = r.get("stroke_width")

            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(color))

            for i in range(symbol.symbolLayerCount()):
                sl = symbol.symbolLayer(i)
                if size is not None:
                    if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                        sl.setSize(size)
                    elif isinstance(sl, QgsSimpleLineSymbolLayer):
                        sl.setWidth(size)
                if stroke_clr:
                    if hasattr(sl, "setStrokeColor"):
                        sl.setStrokeColor(QColor(stroke_clr))
                if stroke_w is not None:
                    if hasattr(sl, "setStrokeWidth"):
                        sl.setStrokeWidth(stroke_w)

            rule = QgsRuleBasedRenderer.Rule(symbol)
            if expression:
                rule.setFilterExpression(expression)
            rule.setLabel(label)
            root_rule.appendChild(rule)

        layer.setRenderer(QgsRuleBasedRenderer(root_rule))
        layer.triggerRepaint()
        return _ok("set_rule_based_style", layer=layer_name, rule_count=len(rules))
    except Exception:
        return _err("set_rule_based_style", traceback.format_exc())


def set_custom_categorized_colors(layer_name: str, field_name: str,
                                   color_map: dict,
                                   default_color: str = "#AAAAAA") -> dict:
    """Apply a categorized renderer with precise per-value color control."""
    from qgis.core import (QgsVectorLayer, QgsCategorizedSymbolRenderer,
                           QgsRendererCategory, QgsSymbol)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_custom_categorized_colors",
                    f"Couche vecteur introuvable : {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("set_custom_categorized_colors",
                    f"Champ introuvable : {field_name}")

    try:
        unique_vals = list(layer.uniqueValues(idx))
        categories = []
        for val in unique_vals:
            color = color_map.get(str(val), default_color)
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(QColor(color))
            label = str(val) if val is not None else "NULL"
            categories.append(QgsRendererCategory(val, symbol, label))

        layer.setRenderer(QgsCategorizedSymbolRenderer(field_name, categories))
        layer.triggerRepaint()
        return _ok("set_custom_categorized_colors",
                   layer=layer_name,
                   field=field_name,
                   category_count=len(categories))
    except Exception:
        return _err("set_custom_categorized_colors", traceback.format_exc())


def set_layer_opacity(layer_name: str, opacity: float) -> dict:
    """Set layer opacity from 0.0 (fully transparent) to 1.0 (fully opaque)."""
    layer = _get_layer(layer_name)
    if not layer:
        return _err("set_layer_opacity", f"Couche introuvable : {layer_name}")
    layer.setOpacity(max(0.0, min(1.0, opacity)))
    layer.triggerRepaint()
    return _ok("set_layer_opacity", layer=layer_name, opacity=opacity)


def set_layer_visibility(layer_name: str, visible: bool,
                         iface=None) -> dict:
    """Show or hide a layer in the layer panel."""
    from qgis.core import QgsProject, QgsLayerTree
    layer = _get_layer(layer_name)
    if not layer:
        return _err("set_layer_visibility", f"Couche introuvable : {layer_name}")
    root = QgsProject.instance().layerTreeRoot()
    node = root.findLayer(layer.id())
    if node:
        node.setItemVisibilityChecked(visible)
    if iface:
        iface.mapCanvas().refresh()
    return _ok("set_layer_visibility", layer=layer_name, visible=visible)


def refresh_canvas(iface=None) -> dict:
    """Force a repaint of the QGIS map canvas."""
    if iface:
        iface.mapCanvas().refresh()
    return _ok("refresh_canvas")


# ══════════════════════════════════════════════════════════════
# CATEGORY: DATA EDITING
# ══════════════════════════════════════════════════════════════

def add_field(layer_name: str, field_name: str,
              field_type: str = "string",
              length: int = 100) -> dict:
    """
    Add a new field to a vector layer.
    field_type: 'string', 'int', 'double', 'date'
    """
    from qgis.core import QgsVectorLayer, QgsField
    from qgis.PyQt.QtCore import QVariant
    TYPE_MAP = {
        "string": QVariant.String,
        "int":    QVariant.Int,
        "double": QVariant.Double,
        "date":   QVariant.Date,
    }
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("add_field", f"Couche vecteur introuvable : {layer_name}")
    if layer.fields().indexFromName(field_name) != -1:
        return _err("add_field", f"Le champ {field_name} existe déjà")
    qtype = TYPE_MAP.get(field_type.lower(), QVariant.String)
    field = QgsField(field_name, qtype, len=length)
    layer.startEditing()
    ok = layer.addAttribute(field)
    layer.commitChanges()
    if not ok:
        return _err("add_field", f"Impossible d'ajouter le champ {field_name}")
    return _ok("add_field",
               layer=layer_name,
               field=field_name,
               type=field_type)


def calculate_field(layer_name: str, field_name: str,
                    expression: str,
                    only_selected: bool = False) -> dict:
    """
    Compute or update a field using a QGIS expression.
    The field must already exist; use add_field first if needed.
    """
    from qgis.core import QgsVectorLayer, QgsExpression, QgsExpressionContext, \
                          QgsExpressionContextUtils, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("calculate_field", f"Couche vecteur introuvable : {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("calculate_field",
                    f"Champ introuvable : {field_name}. Créez-le d'abord avec add_field.")
    expr = QgsExpression(expression)
    if expr.hasParserError():
        return _err("calculate_field",
                    f"Expression invalide : {expr.parserErrorString()}")
    ctx = QgsExpressionContext()
    ctx.appendScopes(QgsExpressionContextUtils.globalProjectLayerScopes(layer))
    layer.startEditing()
    count = 0
    feats = layer.selectedFeatures() if only_selected else layer.getFeatures()
    for feat in feats:
        ctx.setFeature(feat)
        val = expr.evaluate(ctx)
        layer.changeAttributeValue(feat.id(), idx, val)
        count += 1
    layer.commitChanges()
    layer.triggerRepaint()
    return _ok("calculate_field",
               layer=layer_name,
               field=field_name,
               expression=expression,
               updated_count=count)


def load_layer(file_path: str, layer_name: str = "",
               layer_type: str = "auto") -> dict:
    """
    Load a layer into the project from a file path.
    layer_type: 'auto', 'vector', or 'raster'
    """
    from qgis.core import (QgsProject, QgsVectorLayer,
                           QgsRasterLayer, QgsWkbTypes)
    import os
    if not os.path.exists(file_path):
        return _err("load_layer", f"Fichier introuvable : {file_path}")
    name = layer_name or os.path.splitext(os.path.basename(file_path))[0]
    ext = os.path.splitext(file_path)[1].lower()
    raster_exts = {".tif", ".tiff", ".geotiff", ".img",
                   ".asc", ".nc", ".hdf", ".vrt"}
    is_raster = ext in raster_exts or layer_type == "raster"
    try:
        if is_raster:
            layer = QgsRasterLayer(file_path, name)
        else:
            layer = QgsVectorLayer(file_path, name, "ogr")
        if not layer.isValid():
            return _err("load_layer",
                        f"Couche invalide : {file_path}")
        QgsProject.instance().addMapLayer(layer)
        info = {"layer": name, "path": file_path,
                "crs": layer.crs().authid(), "added_to_project": True}
        if isinstance(layer, QgsVectorLayer):
            info["feature_count"] = layer.featureCount()
            info["geometry_type"] = layer.geometryType()
        return _ok("load_layer", **info)
    except Exception as e:
        return _err("load_layer", str(e))


def export_layer(layer_name: str, output_path: str,
                 format: str = "GeoJSON",
                 only_selected: bool = False) -> dict:
    """
    Export a vector layer to a file.
    format: 'GeoJSON', 'GPKG', 'ESRI Shapefile', 'CSV'
    """
    from qgis.core import QgsVectorLayer, QgsVectorFileWriter, QgsProject
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("export_layer", f"Couche vecteur introuvable : {layer_name}")
    options = QgsVectorFileWriter.SaveVectorOptions()
    options.driverName = format
    options.onlySelectedFeatures = only_selected
    options.fileEncoding = "UTF-8"
    error, msg, _, _ = QgsVectorFileWriter.writeAsVectorFormatV3(
        layer, output_path,
        QgsProject.instance().transformContext(),
        options
    )
    if error != QgsVectorFileWriter.NoError:
        return _err("export_layer", msg or "Erreur inconnue à l'export")
    return _ok("export_layer",
               layer=layer_name,
               output_path=output_path,
               format=format,
               only_selected=only_selected)


# ══════════════════════════════════════════════════════════════
# CATEGORY: ANALYSIS
# ══════════════════════════════════════════════════════════════

def calculate_geometry(layer_name: str,
                       output_layer_name: str = "geometry_calculated") -> dict:
    """Compute area, length, and perimeter and add them as new fields."""
    import processing
    layer = _get_layer(layer_name)
    if not layer:
        return _err("calculate_geometry", f"Couche introuvable : {layer_name}")
    return _run_algo("calculate_geometry", "native:addgeometryattributes",
                     {"INPUT": layer, "CALC_METHOD": 0},
                     output_layer_name)


def check_geometry_validity(layer_name: str) -> dict:
    """Check the validity of all geometries in a layer and report valid/invalid counts."""
    import processing
    layer = _get_layer(layer_name)
    if not layer:
        return _err("check_geometry_validity",
                    f"Couche introuvable : {layer_name}")
    try:
        result = processing.run("native:checkvalidity", {
            "INPUT": layer,
            "METHOD": 2,
            "IGNORE_RING_SELF_INTERSECTION": False,
            "VALID_OUTPUT": "memory:",
            "INVALID_OUTPUT": "memory:",
            "ERROR_OUTPUT": "memory:",
        })
        valid = result.get("VALID_OUTPUT")
        invalid = result.get("INVALID_OUTPUT")
        return _ok("check_geometry_validity",
                   layer=layer_name,
                   valid_count=valid.featureCount() if valid else 0,
                   invalid_count=invalid.featureCount() if invalid else 0)
    except Exception as e:
        return _err("check_geometry_validity", str(e))


# ══════════════════════════════════════════════════════════════
# CATEGORY: LABELING
# ══════════════════════════════════════════════════════════════

_PLACEMENT_STR_TO_INT = {
    "around_point": 0,
    "over_point":   1,
    "line":         2,
    "curved":       3,
    "horizontal":   4,
    "free":         5,
    "perimeter":    7,
}

_PLACEMENT_INT_TO_STR = {v: k for k, v in _PLACEMENT_STR_TO_INT.items()}


def _placement_enum(name: str):
    """Return the correct QGIS LabelPlacement enum value for a placement name.

    QGIS 3.26+ uses Qgis.LabelPlacement enum; older versions used int-backed
    QgsPalLayerSettings class attributes.  We try both.
    """
    from qgis.core import QgsPalLayerSettings

    _ATTR_MAP = {
        "around_point": "AroundPoint",
        "over_point":   "OverPoint",
        "line":         "Line",
        "curved":       "Curved",
        "horizontal":   "Horizontal",
        "free":         "Free",
        "perimeter":    "PerimeterCurved",
    }
    attr = _ATTR_MAP.get(name, "AroundPoint")

    # Try Qgis.LabelPlacement (QGIS 3.26+)
    try:
        from qgis.core import Qgis
        return getattr(Qgis.LabelPlacement, attr)
    except AttributeError:
        pass

    # Fall back to QgsPalLayerSettings class attributes (QGIS 3.22-3.25)
    return getattr(QgsPalLayerSettings, attr, 0)


def _placement_name(value) -> str:
    """Convert a placement enum/int back to its string name."""
    try:
        return _PLACEMENT_INT_TO_STR.get(int(value), str(value))
    except (TypeError, ValueError):
        return str(value)


def _get_pal_settings(layer):
    """Return a mutable copy of QgsPalLayerSettings from the layer's labeling, or a fresh one."""
    from qgis.core import QgsPalLayerSettings
    if layer.labeling() and hasattr(layer.labeling(), "settings"):
        return layer.labeling().settings()
    return QgsPalLayerSettings()


def _apply_pal_settings(layer, settings):
    """Wrap QgsPalLayerSettings back onto the layer and trigger repaint."""
    from qgis.core import QgsVectorLayerSimpleLabeling
    layer.setLabeling(QgsVectorLayerSimpleLabeling(settings))
    layer.triggerRepaint()


def get_label_settings(layer_name: str) -> dict:
    """Return the current labeling configuration of a vector layer."""
    from qgis.core import QgsVectorLayer

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_label_settings", f"Couche vecteur introuvable : {layer_name}")

    if not layer.labeling():
        return _ok("get_label_settings",
                   layer=layer_name,
                   enabled=False,
                   message="Aucun étiquetage configuré sur cette couche")

    try:
        settings = layer.labeling().settings()
        fmt = settings.format()
        buf = fmt.buffer()
        shadow = fmt.shadow()

        return _ok("get_label_settings",
                   layer=layer_name,
                   enabled=layer.labelsEnabled(),
                   field_name=settings.fieldName,
                   is_expression=settings.isExpression,
                   placement=_placement_name(settings.placement),
                   font_family=fmt.font().family(),
                   font_size=fmt.size(),
                   color=fmt.color().name(),
                   bold=fmt.font().bold(),
                   italic=fmt.font().italic(),
                   buffer_enabled=buf.enabled(),
                   buffer_size=buf.size(),
                   buffer_color=buf.color().name(),
                   shadow_enabled=shadow.enabled())
    except Exception:
        return _err("get_label_settings", traceback.format_exc())


def enable_labels(layer_name: str, field_name: str,
                  font_size: float = 10,
                  font_family: str = "Arial",
                  color: str = "#000000",
                  bold: bool = False,
                  italic: bool = False,
                  placement: str = None) -> dict:
    """Enable labeling on a vector layer with key formatting in a single call."""
    from qgis.core import (QgsVectorLayer, QgsPalLayerSettings,
                           QgsTextFormat, QgsUnitTypes)
    from qgis.PyQt.QtGui import QFont, QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("enable_labels", f"Couche vecteur introuvable : {layer_name}")

    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("enable_labels",
                    f"Champ introuvable : {field_name}. Utiliser get_layer_fields d'abord.")

    try:
        settings = QgsPalLayerSettings()
        settings.fieldName = field_name
        settings.isExpression = False
        settings.enabled = True

        if placement is None:
            geom = layer.geometryType()
            placement = "around_point" if geom == 0 else "curved" if geom == 1 else "horizontal"
        settings.placement = _placement_enum(placement)

        text_format = QgsTextFormat()
        font = QFont(font_family)
        font.setPointSizeF(font_size)
        font.setBold(bold)
        font.setItalic(italic)
        text_format.setFont(font)
        text_format.setSize(font_size)
        text_format.setSizeUnit(QgsUnitTypes.RenderPoints)
        text_format.setColor(QColor(color))
        settings.setFormat(text_format)

        _apply_pal_settings(layer, settings)
        layer.setLabelsEnabled(True)

        return _ok("enable_labels",
                   layer=layer_name,
                   field=field_name,
                   font=font_family,
                   size=font_size,
                   color=color,
                   placement=placement)
    except Exception:
        return _err("enable_labels", traceback.format_exc())


def disable_labels(layer_name: str) -> dict:
    """Disable labeling on a vector layer."""
    from qgis.core import QgsVectorLayer

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("disable_labels", f"Couche vecteur introuvable : {layer_name}")

    layer.setLabelsEnabled(False)
    layer.triggerRepaint()
    return _ok("disable_labels", layer=layer_name)


def set_label_text_format(layer_name: str,
                           font_family: str = None,
                           font_size: float = None,
                           color: str = None,
                           bold: bool = None,
                           italic: bool = None,
                           underline: bool = None,
                           opacity: float = None) -> dict:
    """Modify text formatting of existing layer labels."""
    from qgis.core import QgsVectorLayer
    from qgis.PyQt.QtGui import QFont, QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_text_format", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_text_format",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()
        font = text_format.font()

        if font_family is not None:
            font.setFamily(font_family)
        if font_size is not None:
            font.setPointSizeF(font_size)
            text_format.setSize(font_size)
        if bold is not None:
            font.setBold(bold)
        if italic is not None:
            font.setItalic(italic)
        if underline is not None:
            font.setUnderline(underline)
        if color is not None:
            text_format.setColor(QColor(color))
        if opacity is not None:
            text_format.setOpacity(max(0.0, min(1.0, opacity)))

        text_format.setFont(font)
        settings.setFormat(text_format)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_text_format",
                   layer=layer_name,
                   font=font.family(),
                   size=font.pointSizeF(),
                   color=text_format.color().name())
    except Exception:
        return _err("set_label_text_format", traceback.format_exc())


def set_label_buffer(layer_name: str,
                     enabled: bool = True,
                     size: float = 1.0,
                     color: str = "#FFFFFF",
                     opacity: float = 1.0) -> dict:
    """Configure the text halo/buffer around layer labels."""
    from qgis.core import (QgsVectorLayer, QgsTextBufferSettings, QgsUnitTypes)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_buffer", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_buffer",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        buf = QgsTextBufferSettings()
        buf.setEnabled(enabled)
        buf.setSize(size)
        buf.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        buf.setColor(QColor(color))
        buf.setOpacity(max(0.0, min(1.0, opacity)))

        text_format.setBuffer(buf)
        settings.setFormat(text_format)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_buffer",
                   layer=layer_name,
                   enabled=enabled, size=size, color=color, opacity=opacity)
    except Exception:
        return _err("set_label_buffer", traceback.format_exc())


def set_label_placement(layer_name: str,
                        placement: str,
                        offset_x: float = 0,
                        offset_y: float = 0,
                        min_scale: float = 0,
                        max_scale: float = 0) -> dict:
    """Change label placement mode, offset, and optional scale-based visibility."""
    from qgis.core import QgsVectorLayer, QgsUnitTypes

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_placement", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_placement",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    if placement not in _PLACEMENT_STR_TO_INT:
        return _err("set_label_placement", f"Placement inconnu : {placement}")

    try:
        settings = _get_pal_settings(layer)
        settings.placement = _placement_enum(placement)

        if offset_x != 0 or offset_y != 0:
            settings.offsetUnits = QgsUnitTypes.RenderMillimeters
            settings.xOffset = offset_x
            settings.yOffset = offset_y

        if min_scale > 0 or max_scale > 0:
            settings.scaleVisibility = True
            if min_scale > 0:
                settings.minimumScale = min_scale
            if max_scale > 0:
                settings.maximumScale = max_scale

        _apply_pal_settings(layer, settings)

        return _ok("set_label_placement",
                   layer=layer_name,
                   placement=placement,
                   offset_x=offset_x, offset_y=offset_y)
    except Exception:
        return _err("set_label_placement", traceback.format_exc())


def set_label_expression(layer_name: str, expression: str) -> dict:
    """Use a QGIS expression as the label text source instead of a plain field."""
    from qgis.core import QgsVectorLayer, QgsExpression

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_expression", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_expression",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    expr = QgsExpression(expression)
    if expr.hasParserError():
        return _err("set_label_expression",
                    f"Expression invalide : {expr.parserErrorString()}")

    try:
        settings = _get_pal_settings(layer)
        settings.fieldName = expression
        settings.isExpression = True
        _apply_pal_settings(layer, settings)

        return _ok("set_label_expression", layer=layer_name, expression=expression)
    except Exception:
        return _err("set_label_expression", traceback.format_exc())


def set_label_shadow(layer_name: str,
                     enabled: bool = True,
                     color: str = "#000000",
                     opacity: float = 0.7,
                     blur_radius: float = 1.5,
                     offset_distance: float = 1.0,
                     offset_angle: int = 315) -> dict:
    """Add or remove a drop shadow from layer labels."""
    from qgis.core import (QgsVectorLayer, QgsTextShadowSettings, QgsUnitTypes)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_shadow", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_shadow",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        shadow = QgsTextShadowSettings()
        shadow.setEnabled(enabled)
        shadow.setColor(QColor(color))
        shadow.setOpacity(max(0.0, min(1.0, opacity)))
        shadow.setBlurRadius(blur_radius)
        shadow.setBlurUnit(QgsUnitTypes.RenderMillimeters)
        shadow.setOffsetDistance(offset_distance)
        shadow.setOffsetUnit(QgsUnitTypes.RenderMillimeters)
        shadow.setOffsetAngle(offset_angle)

        text_format.setShadow(shadow)
        settings.setFormat(text_format)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_shadow",
                   layer=layer_name,
                   enabled=enabled, color=color,
                   blur_radius=blur_radius, offset_distance=offset_distance)
    except Exception:
        return _err("set_label_shadow", traceback.format_exc())


_BACKGROUND_SHAPES = {
    "rectangle": "ShapeRectangle",
    "square":    "ShapeSquare",
    "ellipse":   "ShapeEllipse",
    "circle":    "ShapeCircle",
}


def set_label_background(layer_name: str,
                         enabled: bool = True,
                         shape_type: str = "rectangle",
                         fill_color: str = "#FFFFFF",
                         stroke_color: str = "#000000",
                         stroke_width: float = 0.3,
                         size_x: float = 1.0,
                         size_y: float = 0.5,
                         opacity: float = 1.0) -> dict:
    """Add a filled shape background behind layer labels."""
    from qgis.core import (QgsVectorLayer, QgsTextBackgroundSettings, QgsUnitTypes)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QSizeF

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_background", f"Couche vecteur introuvable : {layer_name}")
    if not layer.labeling():
        return _err("set_label_background",
                    "Aucune étiquette configurée. Utiliser enable_labels d'abord.")

    shape_attr = _BACKGROUND_SHAPES.get(shape_type.lower())
    if shape_attr is None:
        return _err("set_label_background",
                    f"Forme inconnue : {shape_type}. Valeurs valides : {list(_BACKGROUND_SHAPES)}")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        bg = QgsTextBackgroundSettings()
        bg.setEnabled(bool(enabled))
        bg.setType(getattr(QgsTextBackgroundSettings, shape_attr))
        bg.setFillColor(QColor(fill_color))
        bg.setStrokeColor(QColor(stroke_color))
        bg.setStrokeWidth(float(stroke_width))
        bg.setStrokeWidthUnit(QgsUnitTypes.RenderMillimeters)
        bg.setSize(QSizeF(float(size_x), float(size_y)))
        bg.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        bg.setOpacity(max(0.0, min(1.0, float(opacity))))

        text_format.setBackground(bg)
        settings.setFormat(text_format)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_background",
                   layer=layer_name,
                   enabled=enabled, shape_type=shape_type,
                   fill_color=fill_color, stroke_color=stroke_color,
                   size_x=size_x, size_y=size_y, opacity=opacity)
    except Exception:
        return _err("set_label_background", traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# CAPTURE DU CANVAS QGIS
# ══════════════════════════════════════════════════════════════

def capture_map_canvas(iface=None) -> dict:
    if not iface:
        return _err("capture_map_canvas", "iface non disponible")
    try:
        import base64
        from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, Qt

        canvas = iface.mapCanvas()
        if not canvas:
            return _err("capture_map_canvas", "Canvas QGIS introuvable")

        pixmap = canvas.grab()

        # Resize to max 1280px on the longest side — preserves label/symbol readability.
        MAX_PX = 1280
        w, h = pixmap.width(), pixmap.height()
        if max(w, h) > MAX_PX:
            pixmap = pixmap.scaled(
                MAX_PX, MAX_PX,
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )

        # JPEG at 88% quality: ~10x smaller than PNG, colours and text still clean.
        byte_array = QByteArray()
        buf = QBuffer(byte_array)
        buf.open(QIODevice.WriteOnly)
        pixmap.save(buf, "JPEG", 88)
        buf.close()

        b64 = base64.b64encode(bytes(byte_array)).decode("utf-8")
        return _ok("capture_map_canvas",
                   width=pixmap.width(),
                   height=pixmap.height(),
                   image_base64=b64)
    except Exception:
        import traceback
        return _err("capture_map_canvas", traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# FALLBACK: FREE-FORM PYQGIS CODE EXECUTION
# ══════════════════════════════════════════════════════════════

def run_pyqgis_code(code: str, executor=None) -> dict:
    """
    Execute arbitrary PyQGIS code via the existing CodeExecutor.
    Used only when no native tool covers the requested operation.
    """
    if executor is None:
        return _err("run_pyqgis_code",
                    "executor non disponible (mode local uniquement)")
    success, error = executor.execute_code(code)
    if success:
        return _ok("run_pyqgis_code", code_executed=True,
                   warning=error)
    return _err("run_pyqgis_code", error or "Erreur d'exécution")
