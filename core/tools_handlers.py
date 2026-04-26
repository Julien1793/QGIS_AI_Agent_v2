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


def _to_bool(v) -> bool:
    """Coerce any value to bool, handling string representations safely."""
    if isinstance(v, bool):
        return v
    return str(v).strip().lower() in ("true", "1", "yes")


def _ok(tool: str, **kwargs) -> dict:
    return {"success": True, "tool": tool, **kwargs}


def _err(tool: str, message: str, **kwargs) -> dict:
    return {"success": False, "tool": tool, "error": message, **kwargs}


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
    from qgis.core import QgsVectorLayer, QgsUnitTypes
    layer = _get_layer(layer_name)
    if not layer:
        return _err("get_layer_info", f"Layer not found: {layer_name}")
    crs = layer.crs()
    info = {
        "name": layer.name(),
        "crs": crs.authid(),
        "is_geographic": crs.isGeographic(),
        "map_units": QgsUnitTypes.encodeUnit(crs.mapUnits()),
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
        return _err("get_layer_fields", f"Layer not found: {layer_name}")
    if not isinstance(layer, QgsVectorLayer):
        return _err("get_layer_fields", f"{layer_name} is not a vector layer")
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
        return _err("get_layer_features", f"Layer not found: {layer_name}")
    if not isinstance(layer, QgsVectorLayer):
        return _err("get_layer_features", f"{layer_name} is not a vector layer")

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
        return _err("get_layer_statistics", f"Layer not found: {layer_name}")
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
        return _err("get_unique_values", f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("get_unique_values", f"Field not found: {field_name}")
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
        return _err("get_selected_features", f"Vector layer not found: {layer_name}")
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
        return _err("get_layer_extent", f"Layer not found: {layer_name}")
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
            return _err(tool_name, "The algorithm returned no OUTPUT layer")
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
           end_cap_style: int = 0,
           output_layer_name: str = "buffer_result") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("buffer", f"Layer not found: {layer_name}")
    feature_count_in = layer.featureCount()
    result = _run_algo("buffer", "native:buffer", {
        "INPUT": layer,
        "DISTANCE": distance,
        "SEGMENTS": segments,
        "END_CAP_STYLE": end_cap_style,
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
        return _err("clip", f"Layer not found: {layer_name}")
    if not overlay:
        return _err("clip", f"Clip layer not found: {overlay_layer_name}")
    return _run_algo("clip", "native:clip",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def intersection(layer_name: str, overlay_layer_name: str,
                 output_layer_name: str = "intersection_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("intersection", "Layer(s) not found")
    return _run_algo("intersection", "native:intersection",
                     {"INPUT": layer, "OVERLAY": overlay,
                      "INPUT_FIELDS": [], "OVERLAY_FIELDS": []},
                     output_layer_name)


def dissolve(layer_name: str, field: str = "",
             output_layer_name: str = "dissolve_result") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("dissolve", f"Layer not found: {layer_name}")
    return _run_algo("dissolve", "native:dissolve",
                     {"INPUT": layer, "FIELD": [field] if field else []},
                     output_layer_name)


def reproject_layer(layer_name: str, target_crs: str,
                    output_layer_name: str = "reprojected") -> dict:
    from qgis.core import QgsCoordinateReferenceSystem
    layer = _get_layer(layer_name)
    if not layer:
        return _err("reproject_layer", f"Layer not found: {layer_name}")
    crs = QgsCoordinateReferenceSystem(target_crs)
    if not crs.isValid():
        return _err("reproject_layer", f"Invalid CRS: {target_crs}")
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
        return _err("join_by_location", "Layer(s) not found")
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
        return _err("centroids", f"Layer not found: {layer_name}")
    return _run_algo("centroids", "native:centroids",
                     {"INPUT": layer, "ALL_PARTS": False},
                     output_layer_name)


def difference(layer_name: str, overlay_layer_name: str,
               output_layer_name: str = "difference_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("difference", "Layer(s) not found")
    return _run_algo("difference", "native:difference",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def union(layer_name: str, overlay_layer_name: str,
          output_layer_name: str = "union_result") -> dict:
    layer = _get_layer(layer_name)
    overlay = _get_layer(overlay_layer_name)
    if not layer or not overlay:
        return _err("union", "Layer(s) not found")
    return _run_algo("union", "native:union",
                     {"INPUT": layer, "OVERLAY": overlay},
                     output_layer_name)


def fix_geometries(layer_name: str,
                   output_layer_name: str = "fixed_geometries") -> dict:
    layer = _get_layer(layer_name)
    if not layer:
        return _err("fix_geometries", f"Layer not found: {layer_name}")
    return _run_algo("fix_geometries", "native:fixgeometries",
                     {"INPUT": layer},
                     output_layer_name)


def extract_by_expression(layer_name: str, expression: str,
                          output_layer_name: str = "extract_result") -> dict:
    """Create a new layer with features matching a QGIS expression."""
    from qgis.core import QgsExpression
    layer = _get_layer(layer_name)
    if not layer:
        return _err("extract_by_expression", f"Layer not found: {layer_name}")
    expr = QgsExpression(expression)
    if expr.hasParserError():
        return _err("extract_by_expression",
                    f"Invalid expression: {expr.parserErrorString()}")
    return _run_algo("extract_by_expression", "native:extractbyexpression", {
        "INPUT": layer,
        "EXPRESSION": expression,
    }, output_layer_name)


def extract_by_location(layer_name: str, intersect_layer_name: str,
                        predicate: int = 0,
                        output_layer_name: str = "extract_location_result") -> dict:
    """Create a new layer with features that spatially match another layer."""
    layer = _get_layer(layer_name)
    intersect_layer = _get_layer(intersect_layer_name)
    if not layer:
        return _err("extract_by_location", f"Layer not found: {layer_name}")
    if not intersect_layer:
        return _err("extract_by_location",
                    f"Intersection layer not found: {intersect_layer_name}")
    return _run_algo("extract_by_location", "native:extractbylocation", {
        "INPUT": layer,
        "PREDICATE": [predicate],
        "INTERSECT": intersect_layer,
    }, output_layer_name)


def merge_layers(layer_names: list,
                 output_layer_name: str = "merged_result") -> dict:
    """Merge multiple vector layers of the same geometry type into one."""
    import processing
    from qgis.core import QgsProject
    layers = []
    missing = []
    for name in layer_names:
        lyr = _get_layer(name)
        if lyr:
            layers.append(lyr)
        else:
            missing.append(name)
    if missing:
        return _err("merge_layers", f"Layer(s) not found: {', '.join(missing)}")
    if len(layers) < 2:
        return _err("merge_layers", "At least 2 layers are required to merge")
    try:
        result = processing.run("native:mergevectorlayers", {
            "LAYERS": layers,
            "CRS": layers[0].crs(),
            "OUTPUT": "memory:",
        })
        out = result.get("OUTPUT")
        if out is None:
            return _err("merge_layers", "Algorithm returned no OUTPUT layer")
        out.setName(output_layer_name)
        QgsProject.instance().addMapLayer(out)
        return _ok("merge_layers",
                   merged_layers=layer_names,
                   output_layer=output_layer_name,
                   feature_count_out=out.featureCount(),
                   added_to_project=True)
    except Exception:
        return _err("merge_layers", traceback.format_exc())


def join_by_field(layer_name: str, join_layer_name: str,
                  layer_field: str, join_field: str,
                  join_fields: list = None,
                  discard_nonmatching: bool = False,
                  prefix: str = "",
                  output_layer_name: str = "joined_result") -> dict:
    """Attribute join between two layers based on a common field value."""
    layer = _get_layer(layer_name)
    join_layer = _get_layer(join_layer_name)
    if not layer:
        return _err("join_by_field", f"Layer not found: {layer_name}")
    if not join_layer:
        return _err("join_by_field", f"Join layer not found: {join_layer_name}")
    return _run_algo("join_by_field", "native:joinattributestable", {
        "INPUT": layer,
        "FIELD": layer_field,
        "INPUT_2": join_layer,
        "FIELD_2": join_field,
        "FIELDS_TO_COPY": join_fields or [],
        "METHOD": 1,
        "DISCARD_NONMATCHING": discard_nonmatching,
        "PREFIX": prefix,
    }, output_layer_name)


def count_points_in_polygon(polygon_layer_name: str, point_layer_name: str,
                             count_field_name: str = "NUMPOINTS",
                             output_layer_name: str = "count_result") -> dict:
    """Count points inside each polygon and store the count as a new field."""
    poly_layer = _get_layer(polygon_layer_name)
    point_layer = _get_layer(point_layer_name)
    if not poly_layer:
        return _err("count_points_in_polygon",
                    f"Polygon layer not found: {polygon_layer_name}")
    if not point_layer:
        return _err("count_points_in_polygon",
                    f"Point layer not found: {point_layer_name}")
    return _run_algo("count_points_in_polygon", "native:countpointsinpolygon", {
        "POLYGONS": poly_layer,
        "POINTS": point_layer,
        "FIELD": count_field_name,
    }, output_layer_name)


def list_algorithms(keyword: str = "", max_results: int = 50) -> dict:
    """Search available QGIS Processing algorithms by keyword."""
    from qgis.core import QgsApplication
    all_algos = QgsApplication.processingRegistry().algorithms()

    if not keyword.strip():
        summary = {}
        for algo in all_algos:
            pid = algo.provider().id()
            summary[pid] = summary.get(pid, 0) + 1
        return _ok("list_algorithms",
                   message="Provide a keyword to search. Available providers:",
                   providers=summary,
                   total_algorithms=len(all_algos))

    keyword_lower = keyword.lower()
    results = [
        {"id": a.id(), "name": a.displayName(), "group": a.group(), "provider": a.provider().id()}
        for a in all_algos
        if keyword_lower in a.id().lower()
        or keyword_lower in a.displayName().lower()
        or keyword_lower in a.group().lower()
    ]
    results.sort(key=lambda a: a["id"])
    truncated = len(results) > max_results
    return _ok("list_algorithms",
               keyword=keyword,
               count=len(results),
               truncated=truncated,
               hint="Refine your keyword to narrow results." if truncated else None,
               algorithms=results[:max_results])


def get_algorithm_info(algorithm: str) -> dict:
    """Return parameter schema of a QGIS Processing algorithm (call before run_processing_algorithm)."""
    from qgis.core import QgsApplication, QgsProcessingParameterDefinition
    algo = QgsApplication.processingRegistry().algorithmById(algorithm)
    if not algo:
        return _err("get_algorithm_info", f"Algorithm not found: '{algorithm}'")

    params = []
    for p in algo.parameterDefinitions():
        if p.name() == "OUTPUT":
            continue
        is_optional = bool(p.flags() & QgsProcessingParameterDefinition.FlagOptional)
        params.append({
            "name": p.name(),
            "type": p.type(),
            "description": p.description(),
            "required": not is_optional,
            "default": p.defaultValue(),
        })

    outputs = [{"name": o.name(), "description": o.description()}
               for o in algo.outputDefinitions()]

    return _ok("get_algorithm_info",
               algorithm=algorithm,
               display_name=algo.displayName(),
               group=algo.group(),
               parameters=params,
               outputs=outputs)


def run_processing_algorithm(algorithm: str,
                             parameters: dict,
                             output_layer_name: str = "algo_result") -> dict:
    """Generic fallback: run any Processing algorithm. Call get_algorithm_info first."""
    import processing
    from qgis.core import QgsProject

    # Auto-resolve string values that match a project layer name to layer objects.
    resolved = {}
    for key, value in parameters.items():
        if isinstance(value, str):
            layers = QgsProject.instance().mapLayersByName(value)
            resolved[key] = layers[0] if layers else value
        else:
            resolved[key] = value

    resolved["OUTPUT"] = "memory:"
    try:
        result = processing.run(algorithm, resolved)
        from qgis.core import QgsMapLayer
        out = result.get("OUTPUT")
        if out is None:
            for v in result.values():
                if isinstance(v, QgsMapLayer):
                    out = v
                    break
        if out is None:
            raw = {
                k: (str(v) if not isinstance(v, (str, int, float, bool, list, dict)) else v)
                for k, v in result.items()
                if v is not None and not isinstance(v, QgsMapLayer)
            }
            return _ok("run_processing_algorithm",
                       algorithm=algorithm,
                       note="Algorithm produced no output layer.",
                       results=raw)
        out.setName(output_layer_name)
        QgsProject.instance().addMapLayer(out)
        return _ok("run_processing_algorithm",
                   algorithm=algorithm,
                   output_layer=output_layer_name,
                   feature_count_out=out.featureCount(),
                   added_to_project=True)
    except Exception as e:
        msg = str(e).strip() or traceback.format_exc().strip().splitlines()[-1]
        return _err("run_processing_algorithm", f"{algorithm}: {msg}")


# ══════════════════════════════════════════════════════════════
# CATEGORY: SELECTION / FILTERING
# ══════════════════════════════════════════════════════════════

def select_by_expression(layer_name: str, expression: str) -> dict:
    """Select features using a QGIS expression string."""
    from qgis.core import QgsVectorLayer, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("select_by_expression", f"Vector layer not found: {layer_name}")
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
        return _err("select_by_location", f"Layer not found: {layer_name}")
    if not intersect_layer:
        return _err("select_by_location",
                    f"Intersection layer not found: {intersect_layer_name}")
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
        return _err("set_layer_filter", f"Vector layer not found: {layer_name}")
    ok = layer.setSubsetString(expression)
    if not ok:
        return _err("set_layer_filter",
                    f"Invalid expression: {expression}")
    return _ok("set_layer_filter",
               layer=layer_name,
               filter=expression or "(none)",
               visible_count=layer.featureCount())


def clear_selection(layer_name: str) -> dict:
    """Remove all selected features on a layer."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("clear_selection", f"Vector layer not found: {layer_name}")
    layer.removeSelection()
    return _ok("clear_selection", layer=layer_name)


def invert_selection(layer_name: str) -> dict:
    """Invert the current selection on a layer."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("invert_selection", f"Vector layer not found: {layer_name}")
    layer.invertSelection()
    return _ok("invert_selection",
               layer=layer_name,
               selected_count=layer.selectedFeatureCount(),
               total_count=layer.featureCount())


def zoom_to_layer(layer_name: str, iface=None) -> dict:
    """Zoom the map canvas to the full extent of the layer."""
    from qgis.core import QgsProject
    layer = _get_layer(layer_name)
    if not layer:
        return _err("zoom_to_layer", f"Layer not found: {layer_name}")
    if iface:
        iface.mapCanvas().setExtent(layer.extent())
        iface.mapCanvas().refresh()
    return _ok("zoom_to_layer", layer=layer_name)


def zoom_to_feature(layer_name: str, feature_id: int, iface=None) -> dict:
    """Zoom the map canvas to the bounding box of a specific feature by its FID."""
    from qgis.core import QgsVectorLayer, QgsFeatureRequest
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("zoom_to_feature", f"Vector layer not found: {layer_name}")
    req = QgsFeatureRequest().setFilterFid(feature_id)
    feats = list(layer.getFeatures(req))
    if not feats:
        return _err("zoom_to_feature", f"Feature {feature_id} not found")
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
        return _err("get_layer_style", f"Vector layer not found: {layer_name}")
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
                      size: float = None,
                      stroke_color: str = None,
                      stroke_width: float = None) -> dict:
    """Apply a single-symbol renderer with fill color, optional border and opacity."""
    from qgis.core import (QgsVectorLayer, QgsSingleSymbolRenderer, QgsSymbol,
                           QgsSimpleMarkerSymbolLayer, QgsSimpleLineSymbolLayer,
                           QgsSimpleFillSymbolLayer)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import Qt
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_single_symbol", f"Vector layer not found: {layer_name}")
    try:
        symbol = QgsSymbol.defaultSymbol(layer.geometryType())
        symbol.setColor(QColor(color))
        symbol.setOpacity(opacity)
        if size is not None:
            symbol.setSize(size)
        for i in range(symbol.symbolLayerCount()):
            sl = symbol.symbolLayer(i)
            if stroke_color is not None:
                no_border = stroke_color.lower() == "none"
                if isinstance(sl, (QgsSimpleMarkerSymbolLayer, QgsSimpleFillSymbolLayer)):
                    if no_border:
                        sl.setStrokeStyle(Qt.NoPen)
                    else:
                        sl.setStrokeColor(QColor(stroke_color))
                elif isinstance(sl, QgsSimpleLineSymbolLayer):
                    sl.setColor(QColor(stroke_color))
            if stroke_width is not None:
                if hasattr(sl, "setStrokeWidth"):
                    sl.setStrokeWidth(stroke_width)
                elif isinstance(sl, QgsSimpleLineSymbolLayer):
                    sl.setWidth(stroke_width)
        renderer = QgsSingleSymbolRenderer(symbol)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_single_symbol",
                   layer=layer_name, color=color, opacity=opacity)
    except Exception as e:
        return _err("set_single_symbol", str(e))


def set_categorized_style(layer_name: str, field_name: str,
                          color_ramp_name: str = "Spectral") -> dict:
    """Apply a categorized renderer based on a field, colours distributed across a ramp."""
    from qgis.core import (QgsVectorLayer, QgsCategorizedSymbolRenderer,
                           QgsStyle, QgsRendererCategory, QgsSymbol)
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_categorized_style",
                    f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("set_categorized_style",
                    f"Field not found: {field_name}")
    try:
        unique_vals = sorted(
            [v for v in layer.uniqueValues(idx) if v is not None],
            key=lambda x: str(x)
        )
        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp(color_ramp_name)
        if ramp is None:
            ramp = style.colorRamp("Spectral")
        n = len(unique_vals)
        categories = []
        for i, val in enumerate(unique_vals):
            t = i / max(n - 1, 1)
            color = ramp.color(t)
            symbol = QgsSymbol.defaultSymbol(layer.geometryType())
            symbol.setColor(color)
            categories.append(QgsRendererCategory(val, symbol, str(val)))
        renderer = QgsCategorizedSymbolRenderer(field_name, categories)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_categorized_style",
                   layer=layer_name,
                   field=field_name,
                   color_ramp=color_ramp_name,
                   category_count=len(categories))
    except Exception as e:
        return _err("set_categorized_style", str(e))


def set_graduated_style(layer_name: str, field_name: str,
                        num_classes: int = 5,
                        color_ramp_name: str = "Blues",
                        mode: int = 0,
                        invert_ramp: bool = False) -> dict:
    """
    Apply a graduated renderer on a numeric field using a color ramp.
    mode: 0=Quantile, 1=EqualInterval, 2=NaturalBreaks
    """
    from qgis.core import (QgsVectorLayer, QgsGraduatedSymbolRenderer,
                           QgsStyle, QgsApplication)
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_graduated_style",
                    f"Vector layer not found: {layer_name}")
    try:
        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp(color_ramp_name)
        if ramp is None:
            ramp = style.colorRamp("Blues")
        if invert_ramp:
            ramp.invert()
        renderer = QgsGraduatedSymbolRenderer(field_name)
        try:
            from qgis.core import (QgsClassificationEqualInterval,
                                   QgsClassificationQuantile, QgsClassificationJenks)
            _cls = {0: QgsClassificationQuantile,
                    1: QgsClassificationEqualInterval,
                    2: QgsClassificationJenks}
            renderer.setClassificationMethod(_cls.get(mode, QgsClassificationEqualInterval)())
            renderer.updateClasses(layer, num_classes)
        except (ImportError, AttributeError, TypeError):
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


def set_proportional_symbols(layer_name: str, field_name: str,
                             min_size: float = 1.0,
                             max_size: float = 10.0,
                             color: str = "#3498DB",
                             min_value: float = None,
                             max_value: float = None,
                             stroke_color: str = "#ffffff",
                             stroke_width: float = 0.2) -> dict:
    """Apply a proportional symbol renderer: point size scales continuously with a numeric field."""
    from qgis.core import (QgsVectorLayer, QgsMarkerSymbol,
                           QgsSingleSymbolRenderer, QgsProperty, QgsUnitTypes)

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_proportional_symbols", f"Vector layer not found: {layer_name}")
    if layer.geometryType() != 0:
        return _err("set_proportional_symbols", "Proportional symbols require a Point layer")
    if layer.fields().indexFromName(field_name) == -1:
        return _err("set_proportional_symbols", f"Field not found: {field_name}")

    try:
        if min_value is None or max_value is None:
            vals = []
            for f in layer.getFeatures():
                v = f[field_name]
                if v is not None:
                    try:
                        vals.append(float(v))
                    except (TypeError, ValueError):
                        pass
            if not vals:
                return _err("set_proportional_symbols",
                            f"No numeric values found in field '{field_name}'")
            if min_value is None:
                min_value = min(vals)
            if max_value is None:
                max_value = max(vals)

        expr = (
            f'scale_linear("{field_name}", {min_value}, {max_value}, '
            f'{min_size}, {max_size})'
        )

        symbol = QgsMarkerSymbol.createSimple({
            "name": "circle",
            "color": color,
            "outline_color": stroke_color,
            "outline_width": str(stroke_width),
        })
        symbol.setSizeUnit(QgsUnitTypes.RenderMillimeters)
        sl = symbol.symbolLayer(0)
        sl.setDataDefinedProperty(
            sl.PropertySize,
            QgsProperty.fromExpression(expr)
        )

        layer.setRenderer(QgsSingleSymbolRenderer(symbol))
        layer.triggerRepaint()
        return _ok("set_proportional_symbols",
                   layer=layer_name,
                   field=field_name,
                   min_value=min_value,
                   max_value=max_value,
                   min_size=min_size,
                   max_size=max_size)
    except Exception:
        return _err("set_proportional_symbols", traceback.format_exc())


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
                           color: str = None,
                           size: float = None,
                           stroke_color: str = None,
                           stroke_width: float = None,
                           stroke_style: str = None,
                           fill_style: str = None) -> dict:
    """Modify fill color, size, stroke and fill pattern on the existing symbol(s) of a layer."""
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

    FILL_STYLE_MAP = {
        "solid":      Qt.SolidPattern,
        "no_fill":    Qt.NoBrush,
        "horizontal": Qt.HorPattern,
        "vertical":   Qt.VerPattern,
        "cross":      Qt.CrossPattern,
        "b_diagonal": Qt.BDiagPattern,
        "f_diagonal": Qt.FDiagPattern,
        "diagonal_x": Qt.DiagCrossPattern,
    }

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_symbol_properties", f"Vector layer not found: {layer_name}")

    renderer = layer.renderer()
    if renderer is None:
        return _err("set_symbol_properties", "No renderer on this layer")

    try:
        symbols = _get_all_symbols(renderer)
        if not symbols:
            return _err("set_symbol_properties", "No symbol found in renderer")

        applied_types = set()
        for sym in symbols:
            for i in range(sym.symbolLayerCount()):
                sl = sym.symbolLayer(i)

                if isinstance(sl, QgsSimpleMarkerSymbolLayer):
                    if color is not None:
                        sl.setColor(QColor(color))
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
                    if color is not None:
                        sl.setColor(QColor(color))
                    if size is not None:
                        sl.setWidth(size)
                    if stroke_color is not None:
                        sl.setColor(QColor(stroke_color))
                    if stroke_style is not None:
                        sl.setPenStyle(STROKE_STYLE_MAP.get(stroke_style, Qt.SolidLine))
                    applied_types.add("line")

                elif isinstance(sl, QgsSimpleFillSymbolLayer):
                    if color is not None:
                        sl.setColor(QColor(color))
                    if stroke_color is not None:
                        sl.setStrokeColor(QColor(stroke_color))
                    if stroke_width is not None:
                        sl.setStrokeWidth(stroke_width)
                    if stroke_style is not None:
                        sl.setStrokeStyle(STROKE_STYLE_MAP.get(stroke_style, Qt.SolidLine))
                    if fill_style is not None:
                        sl.setBrushStyle(FILL_STYLE_MAP.get(fill_style, Qt.SolidPattern))
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
        return _err("set_marker_shape", f"Vector layer not found: {layer_name}")
    if layer.geometryType() != 0:
        return _err("set_marker_shape", "This layer is not a Point layer")

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
        return _err("set_marker_shape", f"Unknown shape: {shape}")

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
        return _err("set_rule_based_style", f"Vector layer not found: {layer_name}")
    if not rules:
        return _err("set_rule_based_style", "The rules list is empty")

    try:
        root_rule = QgsRuleBasedRenderer.Rule(None)

        for r in rules:
            expression  = r.get("expression", "")
            color       = r.get("color", "#888888")
            label       = r.get("label", expression or "Default")
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
                    f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("set_custom_categorized_colors",
                    f"Field not found: {field_name}")

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
        return _err("set_layer_opacity", f"Layer not found: {layer_name}")
    layer.setOpacity(max(0.0, min(1.0, opacity)))
    layer.triggerRepaint()
    return _ok("set_layer_opacity", layer=layer_name, opacity=opacity)


def set_layer_blending_mode(layer_name: str, mode: str = "normal") -> dict:
    """Set the compositing/blending mode of a layer (multiply, screen, overlay, etc.)."""
    from qgis.PyQt.QtGui import QPainter

    BLEND_MAP = {
        "normal":     QPainter.CompositionMode_SourceOver,
        "multiply":   QPainter.CompositionMode_Multiply,
        "screen":     QPainter.CompositionMode_Screen,
        "overlay":    QPainter.CompositionMode_Overlay,
        "darken":     QPainter.CompositionMode_Darken,
        "lighten":    QPainter.CompositionMode_Lighten,
        "dodge":      QPainter.CompositionMode_ColorDodge,
        "burn":       QPainter.CompositionMode_ColorBurn,
        "hard_light": QPainter.CompositionMode_HardLight,
        "soft_light": QPainter.CompositionMode_SoftLight,
        "difference": QPainter.CompositionMode_Difference,
        "exclusion":  QPainter.CompositionMode_Exclusion,
    }
    layer = _get_layer(layer_name)
    if not layer:
        return _err("set_layer_blending_mode", f"Layer not found: {layer_name}")
    blend = BLEND_MAP.get(mode)
    if blend is None:
        return _err("set_layer_blending_mode", f"Unknown blending mode: {mode}")
    layer.setBlendMode(blend)
    layer.triggerRepaint()
    return _ok("set_layer_blending_mode", layer=layer_name, mode=mode)


def set_scale_based_visibility(layer_name: str,
                               min_scale: float = 0,
                               max_scale: float = 0) -> dict:
    """Set minimum and maximum display scale for a layer. 0 disables a limit."""
    layer = _get_layer(layer_name)
    if not layer:
        return _err("set_scale_based_visibility", f"Layer not found: {layer_name}")
    try:
        has_limit = min_scale > 0 or max_scale > 0
        layer.setScaleBasedVisibility(has_limit)
        if min_scale > 0:
            layer.setMinimumScale(min_scale)
        if max_scale > 0:
            layer.setMaximumScale(max_scale)
        if not has_limit:
            layer.setMinimumScale(0)
            layer.setMaximumScale(0)
        layer.triggerRepaint()
        return _ok("set_scale_based_visibility",
                   layer=layer_name,
                   min_scale=min_scale,
                   max_scale=max_scale)
    except Exception:
        return _err("set_scale_based_visibility", traceback.format_exc())


def set_layer_visibility(layer_name: str, visible: bool,
                         iface=None) -> dict:
    """Show or hide a layer in the layer panel."""
    from qgis.core import QgsProject, QgsLayerTree
    layer = _get_layer(layer_name)
    if not layer:
        return _err("set_layer_visibility", f"Layer not found: {layer_name}")
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
        return _err("add_field", f"Vector layer not found: {layer_name}")
    if layer.fields().indexFromName(field_name) != -1:
        return _err("add_field", f"Field {field_name} already exists")
    qtype = TYPE_MAP.get(field_type.lower(), QVariant.String)
    field = QgsField(field_name, qtype, len=length)
    layer.startEditing()
    ok = layer.addAttribute(field)
    layer.commitChanges()
    if not ok:
        return _err("add_field", f"Cannot add field {field_name}")
    return _ok("add_field",
               layer=layer_name,
               field=field_name,
               type=field_type)


def delete_field(layer_name: str, field_name: str) -> dict:
    """Permanently delete a field from a vector layer."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("delete_field", f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("delete_field", f"Field not found: {field_name}")
    layer.startEditing()
    ok = layer.deleteAttribute(idx)
    layer.commitChanges()
    if not ok:
        return _err("delete_field", f"Cannot delete field: {field_name}")
    return _ok("delete_field", layer=layer_name, field=field_name)


def rename_field(layer_name: str, field_name: str, new_name: str) -> dict:
    """Rename an existing field in a vector layer."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("rename_field", f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("rename_field", f"Field not found: {field_name}")
    if layer.fields().indexFromName(new_name) != -1:
        return _err("rename_field", f"Field already exists: {new_name}")
    layer.startEditing()
    ok = layer.renameAttribute(idx, new_name)
    layer.commitChanges()
    if not ok:
        return _err("rename_field", f"Cannot rename field: {field_name}")
    return _ok("rename_field", layer=layer_name, old_name=field_name, new_name=new_name)


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
        return _err("calculate_field", f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("calculate_field",
                    f"Field not found: {field_name}. Create it first with add_field.")
    expr = QgsExpression(expression)
    if expr.hasParserError():
        return _err("calculate_field",
                    f"Invalid expression: {expr.parserErrorString()}")
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
        return _err("load_layer", f"File not found: {file_path}")
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
                        f"Invalid layer: {file_path}")
        QgsProject.instance().addMapLayer(layer)
        info = {"layer": name, "path": file_path,
                "crs": layer.crs().authid(), "added_to_project": True}
        if isinstance(layer, QgsVectorLayer):
            info["feature_count"] = layer.featureCount()
            info["geometry_type"] = layer.geometryType()
        return _ok("load_layer", **info)
    except Exception as e:
        return _err("load_layer", str(e))


def rename_layer(layer_name: str, new_name: str) -> dict:
    """Rename a layer in the QGIS project (display name only, source file untouched)."""
    layer = _get_layer(layer_name)
    if not layer:
        return _err("rename_layer", f"Layer not found: {layer_name}")
    layer.setName(new_name)
    return _ok("rename_layer", old_name=layer_name, new_name=new_name)


def remove_layer(layer_name: str) -> dict:
    """Remove a layer from the QGIS project without deleting the source file."""
    from qgis.core import QgsProject
    layer = _get_layer(layer_name)
    if not layer:
        return _err("remove_layer", f"Layer not found: {layer_name}")
    QgsProject.instance().removeMapLayer(layer.id())
    return _ok("remove_layer", layer=layer_name)


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
        return _err("export_layer", f"Vector layer not found: {layer_name}")
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
        return _err("export_layer", msg or "Unknown export error")
    return _ok("export_layer",
               layer=layer_name,
               output_path=output_path,
               format=format,
               only_selected=only_selected)


# ══════════════════════════════════════════════════════════════
# CATEGORY: ANALYSIS
# ══════════════════════════════════════════════════════════════

def get_field_value_counts(layer_name: str, field_name: str,
                           sort_by: str = "count_desc") -> dict:
    """Frequency table for a field: count and percentage per unique value."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_field_value_counts", f"Vector layer not found: {layer_name}")
    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("get_field_value_counts", f"Field not found: {field_name}")

    counts: dict = {}
    total = 0
    for feat in layer.getFeatures():
        val = feat[field_name]
        key = str(val) if val is not None else "NULL"
        counts[key] = counts.get(key, 0) + 1
        total += 1

    if sort_by == "count_asc":
        rows = sorted(counts.items(), key=lambda x: x[1])
    elif sort_by == "value":
        rows = sorted(counts.items(), key=lambda x: x[0])
    else:
        rows = sorted(counts.items(), key=lambda x: -x[1])

    table = [
        {"value": v, "count": c, "percent": round(c / total * 100, 2) if total else 0}
        for v, c in rows
    ]
    return _ok("get_field_value_counts",
               layer=layer_name,
               field=field_name,
               total_features=total,
               unique_values=len(counts),
               frequencies=table)


def get_statistics_by_group(layer_name: str, group_field: str,
                             value_field: str) -> dict:
    """Group-by statistics: min, max, mean, sum, count per group."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_statistics_by_group", f"Vector layer not found: {layer_name}")
    if layer.fields().indexFromName(group_field) == -1:
        return _err("get_statistics_by_group", f"Group field not found: {group_field}")
    if layer.fields().indexFromName(value_field) == -1:
        return _err("get_statistics_by_group", f"Value field not found: {value_field}")

    groups: dict = {}
    for feat in layer.getFeatures():
        grp = str(feat[group_field]) if feat[group_field] is not None else "NULL"
        val = feat[value_field]
        try:
            val = float(val)
        except (TypeError, ValueError):
            continue
        if grp not in groups:
            groups[grp] = []
        groups[grp].append(val)

    results = []
    for grp, vals in sorted(groups.items()):
        n = len(vals)
        s = sum(vals)
        results.append({
            "group": grp,
            "count": n,
            "sum": round(s, 6),
            "mean": round(s / n, 6) if n else None,
            "min": round(min(vals), 6),
            "max": round(max(vals), 6),
        })

    return _ok("get_statistics_by_group",
               layer=layer_name,
               group_field=group_field,
               value_field=value_field,
               groups=results)


def get_field_percentiles(layer_name: str, field_name: str,
                          custom_percentile: float = None) -> dict:
    """Compute median, Q1, Q3, IQR, and an optional custom percentile for a numeric field."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_field_percentiles", f"Vector layer not found: {layer_name}")
    if layer.fields().indexFromName(field_name) == -1:
        return _err("get_field_percentiles", f"Field not found: {field_name}")

    values = []
    for feat in layer.getFeatures():
        val = feat[field_name]
        try:
            values.append(float(val))
        except (TypeError, ValueError):
            pass

    if not values:
        return _err("get_field_percentiles", "No numeric values found in field.")

    values.sort()
    n = len(values)

    def _percentile(p: float) -> float:
        idx = (p / 100) * (n - 1)
        lo, hi = int(idx), min(int(idx) + 1, n - 1)
        return round(values[lo] + (idx - lo) * (values[hi] - values[lo]), 6)

    result = {
        "count": n,
        "p25_q1": _percentile(25),
        "p50_median": _percentile(50),
        "p75_q3": _percentile(75),
        "iqr": round(_percentile(75) - _percentile(25), 6),
    }
    if custom_percentile is not None:
        p = max(0.0, min(100.0, float(custom_percentile)))
        result[f"p{int(p)}"] = _percentile(p)

    return _ok("get_field_percentiles",
               layer=layer_name,
               field=field_name,
               **result)


def get_field_correlation(layer_name: str, field_a: str, field_b: str) -> dict:
    """Pearson correlation coefficient between two numeric fields."""
    from qgis.core import QgsVectorLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("get_field_correlation", f"Vector layer not found: {layer_name}")
    for f in (field_a, field_b):
        if layer.fields().indexFromName(f) == -1:
            return _err("get_field_correlation", f"Field not found: {f}")

    xs, ys = [], []
    for feat in layer.getFeatures():
        try:
            x = float(feat[field_a])
            y = float(feat[field_b])
            xs.append(x)
            ys.append(y)
        except (TypeError, ValueError):
            pass

    n = len(xs)
    if n < 2:
        return _err("get_field_correlation", f"Not enough valid pairs ({n}) to compute correlation.")

    mean_x = sum(xs) / n
    mean_y = sum(ys) / n
    cov = sum((xs[i] - mean_x) * (ys[i] - mean_y) for i in range(n))
    std_x = (sum((v - mean_x) ** 2 for v in xs)) ** 0.5
    std_y = (sum((v - mean_y) ** 2 for v in ys)) ** 0.5

    if std_x == 0 or std_y == 0:
        return _err("get_field_correlation", "One of the fields has zero variance — correlation is undefined.")

    r = round(cov / (std_x * std_y), 6)
    return _ok("get_field_correlation",
               layer=layer_name,
               field_a=field_a,
               field_b=field_b,
               pearson_r=r,
               valid_pairs=n,
               interpretation=(
                   "strong positive" if r > 0.7 else
                   "moderate positive" if r > 0.3 else
                   "weak positive" if r > 0 else
                   "weak negative" if r > -0.3 else
                   "moderate negative" if r > -0.7 else
                   "strong negative"
               ))


def check_geometry_validity(layer_name: str) -> dict:
    """Check the validity of all geometries in a layer and report valid/invalid counts."""
    import processing
    layer = _get_layer(layer_name)
    if not layer:
        return _err("check_geometry_validity",
                    f"Layer not found: {layer_name}")
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
        return _err("get_label_settings", f"Vector layer not found: {layer_name}")

    if not layer.labeling():
        return _ok("get_label_settings",
                   layer=layer_name,
                   enabled=False,
                   message="No labeling configured on this layer")

    try:
        settings = layer.labeling().settings()
        fmt = settings.format()
        buf = fmt.buffer()
        shadow = fmt.shadow()

        callout_enabled = False
        callout_type = ""
        if hasattr(settings, "callout") and settings.callout():
            callout_enabled = settings.callout().enabled()
            callout_type = type(settings.callout()).__name__

        return _ok("get_label_settings",
                   layer=layer_name,
                   enabled=layer.labelsEnabled(),
                   field_name=settings.fieldName,
                   is_expression=settings.isExpression,
                   placement=_placement_name(settings.placement),
                   distance=settings.dist,
                   offset_x=settings.xOffset,
                   offset_y=settings.yOffset,
                   font_family=fmt.font().family(),
                   font_size=fmt.size(),
                   color=fmt.color().name(),
                   bold=fmt.font().bold(),
                   italic=fmt.font().italic(),
                   buffer_enabled=buf.enabled(),
                   buffer_size=buf.size(),
                   buffer_color=buf.color().name(),
                   shadow_enabled=shadow.enabled(),
                   callout_enabled=callout_enabled,
                   callout_type=callout_type)
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
    from qgis.core import (QgsVectorLayer, QgsPalLayerSettings, QgsTextFormat)
    from qgis.PyQt.QtGui import QFont, QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("enable_labels", f"Vector layer not found: {layer_name}")

    idx = layer.fields().indexFromName(field_name)
    if idx == -1:
        return _err("enable_labels",
                    f"Field not found: {field_name}. Use get_layer_fields first.")

    try:
        settings = QgsPalLayerSettings()
        settings.fieldName = field_name
        settings.isExpression = False
        settings.enabled = True

        if placement is None:
            geom = layer.geometryType()
            placement = "around_point" if geom == 0 else "curved" if geom == 1 else "horizontal"
        settings.placement = _placement_enum(placement)

        font_size = float(font_size)
        bold = _to_bool(bold)
        italic = _to_bool(italic)
        text_format = QgsTextFormat()
        font = QFont(font_family)
        font.setPointSizeF(font_size)
        font.setBold(bold)
        font.setItalic(italic)
        text_format.setFont(font)
        text_format.setSize(font_size)
        text_format.setSizeUnit(_render_unit("pt"))
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
        return _err("disable_labels", f"Vector layer not found: {layer_name}")

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
        return _err("set_label_text_format", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_text_format",
                    "No labels configured. Use enable_labels first.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()
        font = text_format.font()

        if font_family is not None:
            font.setFamily(font_family)
        if font_size is not None:
            font.setPointSizeF(float(font_size))
            text_format.setSize(float(font_size))
        if bold is not None:
            font.setBold(_to_bool(bold))
        if italic is not None:
            font.setItalic(_to_bool(italic))
        if underline is not None:
            font.setUnderline(_to_bool(underline))
        if color is not None:
            text_format.setColor(QColor(color))
        if opacity is not None:
            text_format.setOpacity(max(0.0, min(1.0, float(opacity))))

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
    from qgis.core import (QgsVectorLayer, QgsTextBufferSettings)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_buffer", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_buffer",
                    "No labels configured. Use enable_labels first.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        buf = QgsTextBufferSettings()
        buf.setEnabled(_to_bool(enabled))
        buf.setSize(float(size))
        buf.setSizeUnit(_render_unit("mm"))
        buf.setColor(QColor(color))
        buf.setOpacity(max(0.0, min(1.0, float(opacity))))

        text_format.setBuffer(buf)
        settings.setFormat(text_format)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_buffer",
                   layer=layer_name,
                   enabled=enabled, size=size, color=color, opacity=opacity)
    except Exception:
        return _err("set_label_buffer", traceback.format_exc())


_OFFSET_UNIT_MAP = {
    "mm":  ("RenderMillimeters", "Millimeters"),
    "pt":  ("RenderPoints",      "Points"),
    "px":  ("RenderPixels",      "Pixels"),
    "map": ("RenderMapUnits",    "MapUnits"),
}


def _render_unit(unit_str: str):
    """Return a render unit enum compatible with QGIS 3.22+ (Qgis.RenderUnit) and 3.36+ fallback."""
    old_attr, new_attr = _OFFSET_UNIT_MAP.get(unit_str.lower(), ("RenderMillimeters", "Millimeters"))
    try:
        from qgis.core import Qgis
        return getattr(Qgis.RenderUnit, new_attr)
    except AttributeError:
        from qgis.core import QgsUnitTypes
        return getattr(QgsUnitTypes, old_attr, QgsUnitTypes.RenderMillimeters)


def set_label_placement(layer_name: str,
                        placement: str = None,
                        distance: float = None,
                        distance_units: str = "mm",
                        offset_x: float = None,
                        offset_y: float = None,
                        offset_units: str = "mm",
                        min_scale: float = 0,
                        max_scale: float = 0) -> dict:
    """Change label placement mode, radial distance, cartesian offset, and scale visibility."""
    from qgis.core import QgsVectorLayer

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_placement", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_placement",
                    "No labels configured. Use enable_labels first.")

    if placement is not None and placement not in _PLACEMENT_STR_TO_INT:
        return _err("set_label_placement", f"Unknown placement: {placement}")

    try:
        settings = _get_pal_settings(layer)

        if placement is not None:
            settings.placement = _placement_enum(placement)

        # dist = radial distance from feature (Around Point / Line / Curved / Perimeter)
        if distance is not None:
            settings.dist = float(distance)
            settings.distUnits = _render_unit(distance_units)

        # xOffset/yOffset = Cartesian shift applied after placement
        if offset_x is not None:
            settings.xOffset = float(offset_x)
            settings.offsetUnits = _render_unit(offset_units)
        if offset_y is not None:
            settings.yOffset = float(offset_y)
            settings.offsetUnits = _render_unit(offset_units)

        min_scale = float(min_scale)
        max_scale = float(max_scale)
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
                   distance=distance, distance_units=distance_units,
                   offset_x=offset_x, offset_y=offset_y,
                   offset_units=offset_units)
    except Exception:
        return _err("set_label_placement", traceback.format_exc())


def set_label_expression(layer_name: str, expression: str) -> dict:
    """Use a QGIS expression as the label text source instead of a plain field."""
    from qgis.core import QgsVectorLayer, QgsExpression

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_expression", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_expression",
                    "No labels configured. Use enable_labels first.")

    expr = QgsExpression(expression)
    if expr.hasParserError():
        return _err("set_label_expression",
                    f"Invalid expression: {expr.parserErrorString()}")

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
    from qgis.core import (QgsVectorLayer, QgsTextShadowSettings)
    from qgis.PyQt.QtGui import QColor

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_shadow", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_shadow",
                    "No labels configured. Use enable_labels first.")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        shadow = QgsTextShadowSettings()
        shadow.setEnabled(_to_bool(enabled))
        shadow.setColor(QColor(color))
        shadow.setOpacity(max(0.0, min(1.0, float(opacity))))
        shadow.setBlurRadius(float(blur_radius))
        shadow.setBlurUnit(_render_unit("mm"))
        shadow.setOffsetDistance(float(offset_distance))
        shadow.setOffsetUnit(_render_unit("mm"))
        shadow.setOffsetAngle(int(offset_angle))

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
    from qgis.core import (QgsVectorLayer, QgsTextBackgroundSettings)
    from qgis.PyQt.QtGui import QColor
    from qgis.PyQt.QtCore import QSizeF

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_background", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_background",
                    "No labels configured. Use enable_labels first.")

    shape_attr = _BACKGROUND_SHAPES.get(shape_type.lower())
    if shape_attr is None:
        return _err("set_label_background",
                    f"Unknown shape: {shape_type}. Valid values: {list(_BACKGROUND_SHAPES)}")

    try:
        settings = _get_pal_settings(layer)
        text_format = settings.format()

        bg = QgsTextBackgroundSettings()
        bg.setEnabled(_to_bool(enabled))
        bg.setType(getattr(QgsTextBackgroundSettings, shape_attr))
        bg.setFillColor(QColor(fill_color))
        bg.setStrokeColor(QColor(stroke_color))
        bg.setStrokeWidth(float(stroke_width))
        bg.setStrokeWidthUnit(_render_unit("mm"))
        bg.setSize(QSizeF(float(size_x), float(size_y)))
        bg.setSizeUnit(_render_unit("mm"))
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


_CALLOUT_STYLES = ("simple", "manhattan", "curved", "balloon")


def set_label_callout(layer_name: str,
                      enabled: bool = True,
                      style: str = "simple",
                      line_color: str = "#000000",
                      line_width: float = 0.3,
                      min_length: float = 0.0) -> dict:
    """Configure a callout line connecting a displaced label to its feature."""
    from qgis.core import (QgsVectorLayer, QgsSimpleLineCallout, QgsLineSymbol)

    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsVectorLayer):
        return _err("set_label_callout", f"Vector layer not found: {layer_name}")
    if not layer.labeling():
        return _err("set_label_callout",
                    "No labels configured. Use enable_labels first.")
    if style not in _CALLOUT_STYLES:
        return _err("set_label_callout",
                    f"Unknown style: {style}. Valid: {list(_CALLOUT_STYLES)}")

    try:
        settings = _get_pal_settings(layer)

        if not enabled:
            existing = settings.callout()
            callout = existing.clone() if existing else QgsSimpleLineCallout()
            callout.setEnabled(False)
            settings.setCallout(callout)
            _apply_pal_settings(layer, settings)
            return _ok("set_label_callout", layer=layer_name, enabled=False)

        if style == "manhattan":
            from qgis.core import QgsManhattanLineCallout
            callout = QgsManhattanLineCallout()
        elif style == "curved":
            try:
                from qgis.core import QgsCurvedLineCallout
                callout = QgsCurvedLineCallout()
            except ImportError:
                callout = QgsSimpleLineCallout()
        elif style == "balloon":
            try:
                from qgis.core import QgsBalloonCallout, QgsFillSymbol
                callout = QgsBalloonCallout()
                fill_sym = QgsFillSymbol.createSimple({
                    "color": "#ffffff80",
                    "outline_color": line_color,
                    "outline_width": str(line_width),
                })
                callout.setFillSymbol(fill_sym)
            except ImportError:
                callout = QgsSimpleLineCallout()
        else:
            callout = QgsSimpleLineCallout()

        if hasattr(callout, "lineSymbol"):
            line_sym = QgsLineSymbol.createSimple({
                "color": line_color,
                "width": str(line_width),
            })
            callout.setLineSymbol(line_sym)

        if min_length > 0:
            callout.setMinimumLength(min_length)
            callout.setMinimumLengthUnit(_render_unit("mm"))

        callout.setEnabled(True)
        settings.setCallout(callout)
        _apply_pal_settings(layer, settings)

        return _ok("set_label_callout",
                   layer=layer_name, enabled=True,
                   style=style, line_color=line_color, line_width=line_width)
    except Exception:
        return _err("set_label_callout", traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# CATEGORY: RASTER
# ══════════════════════════════════════════════════════════════

def get_raster_info(layer_name: str) -> dict:
    """Return metadata of a raster layer: bands, pixel size, extent, CRS, nodata."""
    from qgis.core import QgsRasterLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsRasterLayer):
        return _err("get_raster_info", f"Raster layer not found: {layer_name}")
    provider = layer.dataProvider()
    ext = layer.extent()
    nodata = None
    try:
        if provider.sourceHasNoDataValue(1):
            nodata = provider.sourceNoDataValue(1)
    except Exception:
        pass
    return _ok("get_raster_info",
               layer=layer_name,
               crs=layer.crs().authid(),
               band_count=layer.bandCount(),
               width_px=layer.width(),
               height_px=layer.height(),
               pixel_size_x=layer.rasterUnitsPerPixelX(),
               pixel_size_y=layer.rasterUnitsPerPixelY(),
               extent=[ext.xMinimum(), ext.yMinimum(),
                       ext.xMaximum(), ext.yMaximum()],
               nodata=nodata,
               source=layer.source())


def get_raster_statistics(layer_name: str, band: int = 1) -> dict:
    """Compute min, max, mean, stddev for a raster band."""
    from qgis.core import QgsRasterLayer
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsRasterLayer):
        return _err("get_raster_statistics", f"Raster layer not found: {layer_name}")
    if band < 1 or band > layer.bandCount():
        return _err("get_raster_statistics",
                    f"Invalid band {band}. Layer has {layer.bandCount()} band(s).")
    try:
        provider = layer.dataProvider()
        stats = provider.bandStatistics(band)
        return _ok("get_raster_statistics",
                   layer=layer_name,
                   band=band,
                   min=stats.minimumValue,
                   max=stats.maximumValue,
                   mean=stats.mean,
                   stddev=stats.stdDev)
    except Exception:
        return _err("get_raster_statistics", traceback.format_exc())


def set_raster_style(layer_name: str,
                     style_type: str = "pseudocolor",
                     band: int = 1,
                     color_ramp_name: str = "Spectral",
                     min_value: float = None,
                     max_value: float = None,
                     invert: bool = False) -> dict:
    """Apply a pseudocolor or grayscale renderer to a raster layer."""
    from qgis.core import (QgsRasterLayer, QgsSingleBandGrayRenderer,
                           QgsSingleBandPseudoColorRenderer,
                           QgsColorRampShader, QgsRasterShader, QgsStyle)
    layer = _get_layer(layer_name)
    if not layer or not isinstance(layer, QgsRasterLayer):
        return _err("set_raster_style", f"Raster layer not found: {layer_name}")
    if band < 1 or band > layer.bandCount():
        return _err("set_raster_style",
                    f"Invalid band {band}. Layer has {layer.bandCount()} band(s).")
    try:
        provider = layer.dataProvider()

        if style_type == "gray":
            renderer = QgsSingleBandGrayRenderer(provider, band)
            layer.setRenderer(renderer)
            layer.triggerRepaint()
            return _ok("set_raster_style", layer=layer_name,
                       style_type="gray", band=band)

        # pseudocolor — resolve min/max automatically if not provided
        if min_value is None or max_value is None:
            stats = provider.bandStatistics(band)
            if min_value is None:
                min_value = stats.minimumValue
            if max_value is None:
                max_value = stats.maximumValue

        style = QgsStyle.defaultStyle()
        ramp = style.colorRamp(color_ramp_name) or style.colorRamp("Spectral")
        if invert:
            ramp.invert()

        shader_fn = QgsColorRampShader(min_value, max_value, ramp)
        shader_fn.setColorRampType(QgsColorRampShader.Interpolated)
        shader_fn.classifyColorRamp(10)

        raster_shader = QgsRasterShader()
        raster_shader.setRasterShaderFunction(shader_fn)

        renderer = QgsSingleBandPseudoColorRenderer(provider, band, raster_shader)
        layer.setRenderer(renderer)
        layer.triggerRepaint()
        return _ok("set_raster_style",
                   layer=layer_name,
                   style_type="pseudocolor",
                   band=band,
                   color_ramp=color_ramp_name,
                   min=min_value,
                   max=max_value,
                   inverted=invert)
    except Exception:
        return _err("set_raster_style", traceback.format_exc())


# ══════════════════════════════════════════════════════════════
# CAPTURE DU CANVAS QGIS
# ══════════════════════════════════════════════════════════════

def capture_map_canvas(iface=None) -> dict:
    if not iface:
        return _err("capture_map_canvas", "iface not available")
    try:
        import base64
        from qgis.PyQt.QtCore import QBuffer, QByteArray, QIODevice, Qt

        canvas = iface.mapCanvas()
        if not canvas:
            return _err("capture_map_canvas", "QGIS canvas not found")

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
                    "executor not available (local mode only)")
    success, error, print_output = executor.execute_code(code)
    if success:
        return _ok("run_pyqgis_code", code_executed=True,
                   warning=error,
                   print_output=print_output or None)
    return _err("run_pyqgis_code", error or "Execution error",
                print_output=print_output or None)
