import json
from qgis.core import (
    QgsProject, QgsMapLayer, QgsVectorLayer, QgsRasterLayer
)

def _safe_int(x, default=0):
    try:
        return int(x)
    except Exception:
        return default

def _layer_basics(layer):
    crs = ""
    try:
        crs = layer.crs().authid() if layer.crs().isValid() else ""
    except Exception:
        pass

    ext = None
    try:
        r = layer.extent()
        ext = [r.xMinimum(), r.yMinimum(), r.xMaximum(), r.yMaximum()]
    except Exception:
        pass

    src = ""
    try:
        src = layer.source()
    except Exception:
        pass

    return {
        "id": layer.id(),
        "name": layer.name(),
        "type": layer.type(),  # 0=Vector, 1=Raster, 2=Plugin
        "provider": getattr(layer, "providerType", lambda: "")(),
        "crs": crs,
        "extent": ext,
        "source": src,
    }

def _vector_meta(vl: QgsVectorLayer):
    md = _layer_basics(vl)
    # Geometry type -- wrapped in try/except because WKB access can fail on some layer types.
    try:
        wkb = vl.wkbType()
        md["geometryType"] = int(QgsWkbTypes.geometryType(wkb))  # 0=Point,1=Line,2=Polygon,4=Unknown
        md["geometryTypeName"] = QgsWkbTypes.displayString(wkb)  # ex: 'Point', 'MultiPolygonZ', etc.
        md["isMultipart"] = QgsWkbTypes.isMultiType(wkb)
        md["hasZ"] = QgsWkbTypes.hasZ(wkb)
        md["hasM"] = QgsWkbTypes.hasM(wkb)
    except Exception:
        md["geometryType"] = None
        md["geometryTypeName"] = "Unknown"
        md["isMultipart"] = None
        md["hasZ"] = None
        md["hasM"] = None

    # featureCount can be slow on very large datasets but is acceptable for snapshot purposes.
    try:
        md["featureCount"] = _safe_int(vl.featureCount(), 0)
    except Exception:
        md["featureCount"] = None

    return md

def _raster_meta(rl: QgsRasterLayer):
    md = _layer_basics(rl)
    try:
        md["width"] = rl.width()
        md["height"] = rl.height()
        md["bandCount"] = rl.bandCount()
    except Exception:
        pass
    return md

def build_project_snapshot():
    """
    Return a lightweight project snapshot dict containing layers, layer-tree groups,
    and project custom variables. Used as LLM context for agent requests.
    Fields are intentionally excluded — use get_layer_fields tool to retrieve them on demand.
    """
    prj = QgsProject.instance()
    snapshot = {
        "project": {
            "title": prj.title(),
            "filePath": prj.fileName(),
            "ellipsoid": prj.ellipsoid(),
            "crs": prj.crs().authid() if prj.crs().isValid() else "",
        },
        "layers": [],
        "groups": [],
        "variables": {},
    }

    # Iterate over all loaded layers and collect type-specific metadata.
    for layer in prj.mapLayers().values():
        if isinstance(layer, QgsVectorLayer):
            snapshot["layers"].append(_vector_meta(layer))
        elif isinstance(layer, QgsRasterLayer):
            snapshot["layers"].append(_raster_meta(layer))
        elif isinstance(layer, QgsMapLayer):
            snapshot["layers"].append(_layer_basics(layer))

    # Collect layer group names as hierarchical paths (e.g. "Group/SubGroup").
    try:
        root = prj.layerTreeRoot()
        def walk(node, path=None):
            if path is None: path = []
            if node.name():
                snapshot["groups"].append("/".join(path + [node.name()]))
            for ch in node.children():
                if hasattr(ch, "children"):  # group node (not a layer leaf)
                    walk(ch, path + [node.name()] if node.name() else path)
        walk(root, [])
    except Exception:
        pass

    # Include QGIS project custom variables if any are defined.
    try:
        snapshot["variables"] = prj.customVariables()
    except Exception:
        pass

    return snapshot

def snapshot_to_json(snapshot: dict, max_bytes: int = 100*1024) -> str:
    """
    Serialize the snapshot to formatted JSON.
    Truncates the output at max_bytes to keep the LLM context size bounded.
    The truncation point is a character-count approximation for UTF-8 text.
    """
    txt = json.dumps(snapshot, ensure_ascii=False, indent=2)
    if max_bytes and len(txt.encode("utf-8")) > max_bytes:
        cut = max_bytes
        if cut < len(txt):
            txt = txt[:cut]
            # Ensure the truncated string ends with a newline before the marker.
            if not txt.endswith("\n"):
                txt += "\n"
            txt += "... (truncated)"
    return txt
