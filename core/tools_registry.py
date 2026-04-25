# core/tools_registry.py
#
# Central registry of all tools exposed to the agent.
# Each entry contains:
#   - intents  : categories used by the intent router to select tools
#   - schema   : OpenAI function-call JSON schema sent to the LLM
#   - handler  : name of the implementation function in tools_handlers.py
#
# TOOLS_BY_INTENT is built automatically from this registry at module load.

REGISTRY = {

    # ══════════════════════════════════════════════════════════
    # READ / PROJECT INSPECTION
    # ══════════════════════════════════════════════════════════

    "get_project_info": {
        "intents": ["read"],
        "handler": "get_project_info",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_project_info",
                "description": (
                    "Returns the list of all layers in the QGIS project with "
                    "their types, CRS, and feature count. "
                    "USE FIRST to discover project contents. "
                    "DO NOT use to read attributes of a specific layer."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    },

    "get_layer_info": {
        "intents": ["read"],
        "handler": "get_layer_info",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_info",
                "description": (
                    "Returns full details for a layer: CRS, geometry type, "
                    "feature count, extent, source file path. "
                    "Use before a geoprocessing operation to check CRS compatibility."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Exact layer name as shown in the QGIS project.",
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_fields": {
        "intents": ["read", "label", "field", "style", "select", "stats"],
        "handler": "get_layer_fields",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_fields",
                "description": (
                    "Lists all fields of a vector layer with their name, type "
                    "(Integer, String, Double, Date...) and alias. "
                    "Use before calculate_field, set_categorized_style, or "
                    "any operation requiring an exact field name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_features": {
        "intents": ["read"],
        "handler": "get_layer_features",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_features",
                "description": (
                    "Returns the attributes of features in a vector layer. "
                    "Supports a QGIS expression filter and a limit. "
                    "Filter examples: '\"usage\" = \\'residential\\'' or '\"area\" > 100'. "
                    "DO NOT use for statistics (use get_layer_statistics)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "filter_expression": {
                            "type": "string",
                            "description": "Optional QGIS expression. Ex: '\"type\" = \\'road\\''. Leave empty to return all.",
                        },
                        "max_features": {
                            "type": "integer",
                            "description": "Maximum number of features to return. Default 50.",
                            "default": 50,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_statistics": {
        "intents": ["stats"],
        "handler": "get_layer_statistics",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_statistics",
                "description": (
                    "Computes statistics on a numeric field: min, max, mean, "
                    "sum, standard deviation, count. "
                    "Use for 'what is the average area', 'what is the max of...'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Name of the numeric field to analyse.",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "get_unique_values": {
        "intents": ["read"],
        "handler": "get_unique_values",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_unique_values",
                "description": (
                    "Returns all unique values of a field. "
                    "Useful before set_categorized_style to discover categories, "
                    "or before select_by_expression to know possible values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {"type": "string"},
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "get_selected_features": {
        "intents": ["read"],
        "handler": "get_selected_features",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_selected_features",
                "description": (
                    "Returns currently selected features on a layer. "
                    "Use after select_by_expression or select_by_location "
                    "to inspect the selection."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_extent": {
        "intents": ["read"],
        "handler": "get_layer_extent",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_extent",
                "description": "Returns the spatial extent of a layer (xmin, ymin, xmax, ymax) and its CRS.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # GEOPROCESSING
    # ══════════════════════════════════════════════════════════

    "buffer": {
        "intents": ["process"],
        "handler": "buffer",
        "schema": {
            "type": "function",
            "function": {
                "name": "buffer",
                "description": (
                    "Creates a buffer zone around layer geometries (native:buffer). "
                    "Use for 'buffer zone', 'perimeter of X metres around'. "
                    "Distance is in layer units (metres for EPSG:2154, EPSG:3857...)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "distance": {
                            "type": "number",
                            "description": "Buffer distance in layer units (e.g. 500 for 500 metres if EPSG:2154).",
                        },
                        "dissolve": {
                            "type": "boolean",
                            "description": "True = merge all buffers into a single polygon. Useful before a spatial selection.",
                            "default": False,
                        },
                        "segments": {
                            "type": "integer",
                            "description": "Segments per quarter circle. More = smoother. Default 5.",
                            "default": 5,
                        },
                        "output_layer_name": {
                            "type": "string",
                            "description": "Name of the result layer. Ex: 'buffer_roads_500m'.",
                        },
                    },
                    "required": ["layer_name", "distance", "output_layer_name"],
                },
            },
        },
    },

    "clip": {
        "intents": ["process"],
        "handler": "clip",
        "schema": {
            "type": "function",
            "function": {
                "name": "clip",
                "description": (
                    "Clips a layer by another (native:clip). "
                    "Use for 'clip', 'limit to the area of', 'extract the part within'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Layer to clip.",
                        },
                        "overlay_layer_name": {
                            "type": "string",
                            "description": "Layer used as the clip mask.",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "overlay_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "intersection": {
        "intents": ["process"],
        "handler": "intersection",
        "schema": {
            "type": "function",
            "function": {
                "name": "intersection",
                "description": (
                    "Spatial intersection between two layers (native:intersection). "
                    "Returns only overlapping parts with attributes from both layers. "
                    "Different from clip: intersection preserves attributes from both layers."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "overlay_layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "overlay_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "dissolve": {
        "intents": ["process"],
        "handler": "dissolve",
        "schema": {
            "type": "function",
            "function": {
                "name": "dissolve",
                "description": (
                    "Merges geometries of a layer (native:dissolve). "
                    "Without field = merge everything into one geometry. "
                    "With field = merge by field value (e.g. merge by 'municipality')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field": {
                            "type": "string",
                            "description": "Grouping field. Leave empty to merge everything.",
                            "default": "",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "output_layer_name"],
                },
            },
        },
    },

    "reproject_layer": {
        "intents": ["process"],
        "handler": "reproject_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "reproject_layer",
                "description": (
                    "Reprojects a layer to another CRS (native:reprojectlayer). "
                    "Use when two layers have different CRS before combining them. "
                    "CRS examples: 'EPSG:2154' (Lambert 93), 'EPSG:4326' (WGS84), 'EPSG:3857' (Web Mercator)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "target_crs": {
                            "type": "string",
                            "description": "Target CRS in EPSG format. Ex: 'EPSG:4326'.",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "target_crs", "output_layer_name"],
                },
            },
        },
    },

    "join_by_location": {
        "intents": ["join"],
        "handler": "join_by_location",
        "schema": {
            "type": "function",
            "function": {
                "name": "join_by_location",
                "description": (
                    "Spatial join between two layers (native:joinattributesbylocation). "
                    "Adds attributes from one layer to another based on their spatial relationship. "
                    "Ex: add municipality name to each building."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Layer that receives the attributes.",
                        },
                        "join_layer_name": {
                            "type": "string",
                            "description": "Layer from which attributes are taken.",
                        },
                        "predicates": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Spatial predicates: [0]=intersects, [1]=contains, [6]=within. Default [0].",
                            "default": [0],
                        },
                        "join_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Fields to join. [] = all.",
                            "default": [],
                        },
                        "discard_nonmatching": {
                            "type": "boolean",
                            "description": "True = remove features with no spatial match.",
                            "default": False,
                        },
                        "prefix": {
                            "type": "string",
                            "description": "Prefix for joined fields. Ex: 'mun_'.",
                            "default": "",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "join_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "centroids": {
        "intents": ["process"],
        "handler": "centroids",
        "schema": {
            "type": "function",
            "function": {
                "name": "centroids",
                "description": (
                    "Computes centroids of polygons or lines (native:centroids). "
                    "Returns a point layer at the centre of each geometry."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "output_layer_name"],
                },
            },
        },
    },

    "difference": {
        "intents": ["process"],
        "handler": "difference",
        "schema": {
            "type": "function",
            "function": {
                "name": "difference",
                "description": (
                    "Spatial difference: returns the part of layer_name "
                    "that does NOT intersect overlay_layer_name (native:difference). "
                    "Ex: parcels outside a flood zone."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "overlay_layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "overlay_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "union": {
        "intents": ["process"],
        "handler": "union",
        "schema": {
            "type": "function",
            "function": {
                "name": "union",
                "description": (
                    "Spatial union of two layers (native:union). "
                    "Returns all geometries from both layers combined."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "overlay_layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "overlay_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "fix_geometries": {
        "intents": ["process"],
        "handler": "fix_geometries",
        "schema": {
            "type": "function",
            "function": {
                "name": "fix_geometries",
                "description": (
                    "Fixes invalid geometries in a layer (native:fixgeometries). "
                    "Use if a Processing algorithm fails with an invalid geometry error."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "output_layer_name"],
                },
            },
        },
    },

    "extract_by_expression": {
        "intents": ["select"],
        "handler": "extract_by_expression",
        "schema": {
            "type": "function",
            "function": {
                "name": "extract_by_expression",
                "description": (
                    "Creates a new layer containing only features that match a QGIS expression "
                    "(native:extractbyexpression). "
                    "Use instead of select_by_expression when you need a permanent filtered layer. "
                    "Expression examples: '\"type\" = \\'road\\'' or '\"area\" > 1000'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "QGIS expression to filter features. Ex: '\"status\" = \\'active\\''.",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "expression", "output_layer_name"],
                },
            },
        },
    },

    "extract_by_location": {
        "intents": ["select"],
        "handler": "extract_by_location",
        "schema": {
            "type": "function",
            "function": {
                "name": "extract_by_location",
                "description": (
                    "Creates a new layer with features that have a given spatial relationship "
                    "with another layer (native:extractbylocation). "
                    "Use when you need a permanent layer, not just a selection. "
                    "predicate: 0=intersects (default), 1=contains, 6=within, 4=touches."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Layer from which features are extracted.",
                        },
                        "intersect_layer_name": {
                            "type": "string",
                            "description": "Reference spatial layer.",
                        },
                        "predicate": {
                            "type": "integer",
                            "description": "0=intersects, 1=contains, 6=within, 4=touches. Default 0.",
                            "default": 0,
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "intersect_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "merge_layers": {
        "intents": ["join"],
        "handler": "merge_layers",
        "schema": {
            "type": "function",
            "function": {
                "name": "merge_layers",
                "description": (
                    "Merges multiple vector layers of the same geometry type into a single layer "
                    "(native:mergevectorlayers). "
                    "Use for 'merge', 'combine', 'append all layers into one'. "
                    "All layers must have compatible geometry types (e.g. all polygons)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_names": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of layer names to merge. Minimum 2.",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_names", "output_layer_name"],
                },
            },
        },
    },

    "join_by_field": {
        "intents": ["join"],
        "handler": "join_by_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "join_by_field",
                "description": (
                    "Attribute join: adds fields from a second layer to a first layer based on "
                    "a common field value (native:joinattributestable). "
                    "Different from join_by_location: matching is done by field value, not geometry. "
                    "Ex: add population data to municipalities by joining on 'commune_code'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Layer that receives the joined fields.",
                        },
                        "join_layer_name": {
                            "type": "string",
                            "description": "Layer from which fields are taken.",
                        },
                        "layer_field": {
                            "type": "string",
                            "description": "Join key field in the main layer.",
                        },
                        "join_field": {
                            "type": "string",
                            "description": "Matching field in the join layer.",
                        },
                        "join_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Specific fields to copy from the join layer. [] = all fields.",
                            "default": [],
                        },
                        "discard_nonmatching": {
                            "type": "boolean",
                            "description": "True = keep only features with a match. Default false.",
                            "default": False,
                        },
                        "prefix": {
                            "type": "string",
                            "description": "Prefix added to joined field names to avoid conflicts. Ex: 'pop_'.",
                            "default": "",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "join_layer_name", "layer_field", "join_field", "output_layer_name"],
                },
            },
        },
    },

    "count_points_in_polygon": {
        "intents": ["join"],
        "handler": "count_points_in_polygon",
        "schema": {
            "type": "function",
            "function": {
                "name": "count_points_in_polygon",
                "description": (
                    "Counts the number of points inside each polygon and adds the count as a new field "
                    "(native:countpointsinpolygon). "
                    "Use for 'how many points per polygon', 'count incidents per zone', "
                    "'number of trees per parcel'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "polygon_layer_name": {
                            "type": "string",
                            "description": "Polygon layer that receives the count field.",
                        },
                        "point_layer_name": {
                            "type": "string",
                            "description": "Point layer to count.",
                        },
                        "count_field_name": {
                            "type": "string",
                            "description": "Name of the new count field. Default 'NUMPOINTS'.",
                            "default": "NUMPOINTS",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["polygon_layer_name", "point_layer_name", "output_layer_name"],
                },
            },
        },
    },

    "list_algorithms": {
        "intents": ["process"],
        "handler": "list_algorithms",
        "schema": {
            "type": "function",
            "function": {
                "name": "list_algorithms",
                "description": (
                    "Search all available QGIS Processing algorithms by keyword (operation type, name, or group). "
                    "Use this to discover which algorithms exist for a given GIS operation before running one. "
                    "Examples: search 'buffer' to find all buffer variants, 'dissolve' for dissolve tools, "
                    "'clip' for clip algorithms, 'simplify' for simplification tools. "
                    "The keyword is matched against algorithm id, name, and group — so searching by concept works. "
                    "Workflow: list_algorithms → pick the best id → get_algorithm_info → run_processing_algorithm."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "keyword": {
                            "type": "string",
                            "description": (
                                "GIS operation or concept to search for (e.g. 'buffer', 'dissolve', 'clip', 'join', 'simplify'). "
                                "Matched against algorithm id, name, and group. "
                                "Empty string returns a summary of available providers instead of the full list."
                            ),
                        },
                        "max_results": {
                            "type": "integer",
                            "description": "Maximum number of results to return. Defaults to 50.",
                        },
                    },
                    "required": ["keyword"],
                },
            },
        },
    },

    "get_algorithm_info": {
        "intents": ["process"],
        "handler": "get_algorithm_info",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_algorithm_info",
                "description": (
                    "Returns the full parameter schema (names, types, required/optional, defaults) "
                    "of any QGIS Processing algorithm given its id. "
                    "Use the 'id' field returned by list_algorithms as input. "
                    "ALWAYS call this BEFORE run_processing_algorithm so you know the exact "
                    "parameter names and types to pass. "
                    "OUTPUT is excluded from the returned parameters (it is handled automatically)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "algorithm": {
                            "type": "string",
                            "description": (
                                "Full algorithm identifier, either already known (e.g. 'native:buffer', "
                                "'gdal:buffervectors', 'grass:v.buffer') or taken from the 'id' field "
                                "returned by list_algorithms."
                            ),
                        },
                    },
                    "required": ["algorithm"],
                },
            },
        },
    },

    "run_processing_algorithm": {
        "intents": ["process"],
        "handler": "run_processing_algorithm",
        "schema": {
            "type": "function",
            "function": {
                "name": "run_processing_algorithm",
                "description": (
                    "Generic fallback: runs ANY QGIS Processing algorithm by its full identifier. "
                    "Use ONLY when no specific tool covers the need. "
                    "ALWAYS call get_algorithm_info first to get exact parameter names and types. "
                    "Pass layer names as plain strings in parameters — they are resolved to layer "
                    "objects automatically. OUTPUT is always injected automatically, do not include it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "algorithm": {
                            "type": "string",
                            "description": (
                                "Full algorithm identifier, either already known (e.g. 'native:buffer') "
                                "or taken from the 'id' field returned by list_algorithms."
                            ),
                        },
                        "parameters": {
                            "type": "object",
                            "description": (
                                "All algorithm parameters as reported by get_algorithm_info. "
                                "For parameters of type 'source', 'vector', or 'raster', pass the "
                                "layer name as a string — it will be resolved to a layer object automatically. "
                                "Ex: {\"INPUT\": \"communes\", \"OVERLAY\": \"zones\", \"DISTANCE\": 500}. "
                                "Do NOT include OUTPUT."
                            ),
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["algorithm", "parameters", "output_layer_name"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # SELECTION / FILTERING
    # ══════════════════════════════════════════════════════════

    "select_by_expression": {
        "intents": ["select"],
        "handler": "select_by_expression",
        "schema": {
            "type": "function",
            "function": {
                "name": "select_by_expression",
                "description": (
                    "Selects features by a QGIS expression. "
                    "Syntax: '\"field_name\" = \\'value\\'' or '\"area\" > 100'. "
                    "Use get_layer_fields first to get exact field names. "
                    "DO NOT use for spatial selection (use select_by_location)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "QGIS expression. Ex: '\"type\" = \\'highway\\'' or '\"population\" > 10000'.",
                        },
                    },
                    "required": ["layer_name", "expression"],
                },
            },
        },
    },

    "select_by_location": {
        "intents": ["select"],
        "handler": "select_by_location",
        "schema": {
            "type": "function",
            "function": {
                "name": "select_by_location",
                "description": (
                    "Selects features based on their spatial relationship with another layer. "
                    "Use for 'select buildings within the buffer', "
                    "'find points in the area', 'features that intersect'. "
                    "predicate: 0=intersects (default), 1=contains, 6=within, 4=touches."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Layer from which features are selected.",
                        },
                        "intersect_layer_name": {
                            "type": "string",
                            "description": "Reference spatial layer.",
                        },
                        "predicate": {
                            "type": "integer",
                            "description": "0=intersects, 1=contains, 6=within, 4=touches. Default 0.",
                            "default": 0,
                        },
                    },
                    "required": ["layer_name", "intersect_layer_name"],
                },
            },
        },
    },

    "set_layer_filter": {
        "intents": ["select"],
        "handler": "set_layer_filter",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_layer_filter",
                "description": (
                    "Applies a permanent filter on a layer without creating a new one. "
                    "The layer will only show features matching the expression. "
                    "Pass expression='' to remove the filter."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "QGIS expression. Ex: '\"year\" >= 2000'. Empty to remove the filter.",
                        },
                    },
                    "required": ["layer_name", "expression"],
                },
            },
        },
    },

    "clear_selection": {
        "intents": ["select"],
        "handler": "clear_selection",
        "schema": {
            "type": "function",
            "function": {
                "name": "clear_selection",
                "description": (
                    "Removes all selected features on a layer. "
                    "Use after a selection operation to reset the selection state."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "invert_selection": {
        "intents": ["select"],
        "handler": "invert_selection",
        "schema": {
            "type": "function",
            "function": {
                "name": "invert_selection",
                "description": (
                    "Inverts the current selection on a layer: selected features become "
                    "unselected and unselected features become selected. "
                    "Useful after select_by_expression to get the complement."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "zoom_to_layer": {
        "intents": ["view"],
        "handler": "zoom_to_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "zoom_to_layer",
                "description": "Zooms the QGIS canvas to the full extent of a layer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "zoom_to_feature": {
        "intents": ["view"],
        "handler": "zoom_to_feature",
        "schema": {
            "type": "function",
            "function": {
                "name": "zoom_to_feature",
                "description": "Zooms to a specific feature of a layer by its identifier (fid).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "feature_id": {
                            "type": "integer",
                            "description": "Feature identifier (fid).",
                        },
                    },
                    "required": ["layer_name", "feature_id"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # STYLING / DISPLAY
    # ══════════════════════════════════════════════════════════

    "get_layer_style": {
        "intents": ["style"],
        "handler": "get_layer_style",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_style",
                "description": (
                    "Returns the current renderer type and style parameters of a layer: "
                    "colour, opacity, categorisation field, number of classes... "
                    "Use before modifying a style to understand the existing setup."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_single_symbol": {
        "intents": ["style"],
        "handler": "set_single_symbol",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_single_symbol",
                "description": (
                    "Applies a single symbol to the entire layer. "
                    "Use for 'colour in red', 'make the layer blue', 'change the colour of'. "
                    "colour in hex format: '#FF0000' for red, '#0000FF' for blue."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "color": {
                            "type": "string",
                            "description": "Fill colour in hex. Ex: '#FF0000', '#3498DB', '#2ECC71'.",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Symbol opacity from 0.0 to 1.0. Default 1.0.",
                            "default": 1.0,
                        },
                        "size": {
                            "type": "number",
                            "description": "Size in mm (points). Leave null for the default value.",
                        },
                        "stroke_color": {
                            "type": "string",
                            "description": "Border/outline colour in hex. Default '#000000'. Pass 'none' to remove the border.",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": "Border width in mm. Default 0.26.",
                        },
                    },
                    "required": ["layer_name", "color"],
                },
            },
        },
    },

    "set_categorized_style": {
        "intents": ["style"],
        "handler": "set_categorized_style",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_categorized_style",
                "description": (
                    "Applies a categorised symbology: a different colour for each unique value of a field. "
                    "Use for 'colour by type', 'one colour per category', 'symbology by usage'. "
                    "Use get_unique_values first to see available values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Field to base the categorisation on.",
                        },
                        "color_ramp_name": {
                            "type": "string",
                            "description": "QGIS colour ramp to distribute across categories. Ex: 'Spectral', 'Set1', 'Pastel1', 'Dark2', 'Paired', 'tab10'. Default 'Spectral'.",
                            "default": "Spectral",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "set_graduated_style": {
        "intents": ["style"],
        "handler": "set_graduated_style",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_graduated_style",
                "description": (
                    "Applies a graduated symbology on a numeric field (colour ramp). "
                    "Use for 'colour by density', 'graduated by area', 'colour ramp on'. "
                    "color_ramp_name: 'Blues', 'Reds', 'Greens', 'RdYlGn', 'Spectral', 'Viridis'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Numeric field for the graduation.",
                        },
                        "num_classes": {
                            "type": "integer",
                            "description": "Number of classes. Default 5.",
                            "default": 5,
                        },
                        "color_ramp_name": {
                            "type": "string",
                            "description": "QGIS colour ramp. Ex: 'Blues', 'Reds', 'Viridis'.",
                            "default": "Blues",
                        },
                        "mode": {
                            "type": "integer",
                            "description": "0=Quantile, 1=Equal intervals, 2=Natural breaks. Default 0.",
                            "default": 0,
                        },
                        "invert_ramp": {
                            "type": "boolean",
                            "description": "Invert the colour ramp direction. Default false.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "set_proportional_symbols": {
        "intents": ["style"],
        "handler": "set_proportional_symbols",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_proportional_symbols",
                "description": (
                    "Applies a proportional symbol renderer on a point layer: each point is scaled "
                    "in size proportionally to the value of a numeric field. "
                    "Use for 'symbols proportional to population', 'size by volume', 'graduated size'. "
                    "The size varies continuously (not by class), unlike set_graduated_style which uses colour bands. "
                    "min_value/max_value are auto-computed from the data if omitted."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Numeric field driving the symbol size.",
                        },
                        "min_size": {
                            "type": "number",
                            "description": "Symbol size in mm for the smallest value. Default 1.0.",
                            "default": 1.0,
                        },
                        "max_size": {
                            "type": "number",
                            "description": "Symbol size in mm for the largest value. Default 10.0.",
                            "default": 10.0,
                        },
                        "color": {
                            "type": "string",
                            "description": "Fill colour in hex. Default '#3498DB'.",
                            "default": "#3498DB",
                        },
                        "min_value": {
                            "type": "number",
                            "description": "Field value mapped to min_size. Auto-computed if omitted.",
                        },
                        "max_value": {
                            "type": "number",
                            "description": "Field value mapped to max_size. Auto-computed if omitted.",
                        },
                        "stroke_color": {
                            "type": "string",
                            "description": "Border colour in hex. Default '#ffffff'.",
                            "default": "#ffffff",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": "Border width in mm. Default 0.2.",
                            "default": 0.2,
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "set_symbol_properties": {
        "intents": ["style"],
        "handler": "set_symbol_properties",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_symbol_properties",
                "description": (
                    "Modifies detailed symbol properties of the active layer: "
                    "point size, stroke/border width, stroke colour, line style. "
                    "Works on the current renderer without changing it (single symbol, categorised, graduated, rules). "
                    "For points: 'size' = size in mm. "
                    "For lines: 'size' = width in mm. "
                    "For polygons: 'stroke_width' = border width in mm. "
                    "stroke_style: 'solid', 'dash', 'dot', 'no_line'=no border."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "color": {
                            "type": "string",
                            "description": "Fill colour in hex. Changes the fill on the existing renderer without resetting it. Ex: '#3498DB'.",
                        },
                        "size": {
                            "type": "number",
                            "description": "Marker/point size or line width in mm.",
                        },
                        "stroke_color": {
                            "type": "string",
                            "description": "Border/outline colour in hex. Ex: '#000000'.",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": "Border width in mm (polygons and points). Ex: 0.5.",
                        },
                        "stroke_style": {
                            "type": "string",
                            "enum": ["solid", "dash", "dot", "dash_dot", "no_line"],
                            "description": "Line/border style.",
                        },
                        "fill_style": {
                            "type": "string",
                            "enum": ["solid", "no_fill", "horizontal", "vertical", "cross", "b_diagonal", "f_diagonal", "diagonal_x"],
                            "description": "Polygon fill pattern. 'solid'=plain fill, 'no_fill'=transparent, others=hatch patterns. Polygons only.",
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_marker_shape": {
        "intents": ["style"],
        "handler": "set_marker_shape",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_marker_shape",
                "description": (
                    "Changes the marker shape for a point layer. "
                    "Use after set_single_symbol to refine the point shape. "
                    "Available shapes: circle, square, diamond, triangle, star, cross, x, arrow."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "shape": {
                            "type": "string",
                            "enum": ["circle", "square", "diamond", "triangle", "star", "cross", "x", "arrow"],
                            "description": "Marker shape.",
                        },
                    },
                    "required": ["layer_name", "shape"],
                },
            },
        },
    },

    "set_rule_based_style": {
        "intents": ["style"],
        "handler": "set_rule_based_style",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_rule_based_style",
                "description": (
                    "Applies a rule-based symbology: each rule combines a QGIS expression and a colour. "
                    "Ideal for complex conditions or multiple categories with crossed criteria. "
                    "Use get_layer_fields and get_unique_values first. "
                    "Each rule can have an optional size (points/lines) and border. "
                    "Rules are evaluated in order — put the most specific cases first."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "rules": {
                            "type": "array",
                            "description": "Ordered list of rules.",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "expression": {
                                        "type": "string",
                                        "description": "QGIS expression. Ex: '\"type\" = \\'highway\\''. Leave '' for the default rule.",
                                    },
                                    "color": {
                                        "type": "string",
                                        "description": "Fill colour in hex. Ex: '#E74C3C'.",
                                    },
                                    "label": {
                                        "type": "string",
                                        "description": "Legend label. Ex: 'Highways'.",
                                    },
                                    "size": {
                                        "type": "number",
                                        "description": "Symbol size in mm (optional).",
                                    },
                                    "stroke_color": {
                                        "type": "string",
                                        "description": "Border colour in hex (optional).",
                                    },
                                    "stroke_width": {
                                        "type": "number",
                                        "description": "Border width in mm (optional).",
                                    },
                                },
                                "required": ["expression", "color", "label"],
                            },
                        },
                    },
                    "required": ["layer_name", "rules"],
                },
            },
        },
    },

    "set_custom_categorized_colors": {
        "intents": ["style"],
        "handler": "set_custom_categorized_colors",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_custom_categorized_colors",
                "description": (
                    "Applies a categorised symbology with exact colours per value. "
                    "Prefer over set_categorized_style when you want to control each colour. "
                    "Ex: red for 'urgent', green for 'normal', grey for 'closed'. "
                    "Use get_unique_values first to know possible values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Categorisation field.",
                        },
                        "color_map": {
                            "type": "object",
                            "description": "Value → hex colour mapping. Ex: {\"highway\": \"#E74C3C\", \"national\": \"#F39C12\"}.",
                            "additionalProperties": {"type": "string"},
                        },
                        "default_color": {
                            "type": "string",
                            "description": "Colour for values not in the color_map. Default '#AAAAAA'.",
                            "default": "#AAAAAA",
                        },
                    },
                    "required": ["layer_name", "field_name", "color_map"],
                },
            },
        },
    },

    "set_layer_opacity": {
        "intents": ["style"],
        "handler": "set_layer_opacity",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_layer_opacity",
                "description": "Sets the opacity of a layer from 0.0 (invisible) to 1.0 (opaque).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "opacity": {
                            "type": "number",
                            "description": "Opacity between 0.0 and 1.0.",
                        },
                    },
                    "required": ["layer_name", "opacity"],
                },
            },
        },
    },

    "set_layer_blending_mode": {
        "intents": ["style"],
        "handler": "set_layer_blending_mode",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_layer_blending_mode",
                "description": (
                    "Sets the blending/compositing mode of a layer. "
                    "Use for 'multiply', 'screen', 'overlay', 'darken effects'. "
                    "Modes: 'normal' (default), 'multiply' (darkens, good for overlays on imagery), "
                    "'screen' (brightens), 'overlay' (contrast), 'darken', 'lighten', "
                    "'dodge' (colour dodge), 'burn' (colour burn), 'hard_light', 'soft_light', "
                    "'difference', 'exclusion'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "mode": {
                            "type": "string",
                            "enum": [
                                "normal", "multiply", "screen", "overlay",
                                "darken", "lighten", "dodge", "burn",
                                "hard_light", "soft_light", "difference", "exclusion"
                            ],
                            "description": "Blending mode.",
                            "default": "normal",
                        },
                    },
                    "required": ["layer_name", "mode"],
                },
            },
        },
    },

    "set_scale_based_visibility": {
        "intents": ["view"],
        "handler": "set_scale_based_visibility",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_scale_based_visibility",
                "description": (
                    "Controls at which map scales a layer is visible. "
                    "Use for 'only show at zoom level X', 'hide when zoomed out beyond 1:100000', "
                    "'visible between 1:5000 and 1:50000'. "
                    "Pass 0 to disable a limit. Set both to 0 to remove all scale restrictions."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "min_scale": {
                            "type": "number",
                            "description": "Layer is hidden when zoomed out beyond this scale (e.g. 100000 = 1:100000). 0 = no limit.",
                            "default": 0,
                        },
                        "max_scale": {
                            "type": "number",
                            "description": "Layer is hidden when zoomed in beyond this scale (e.g. 5000 = 1:5000). 0 = no limit.",
                            "default": 0,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_layer_visibility": {
        "intents": ["view"],
        "handler": "set_layer_visibility",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_layer_visibility",
                "description": "Shows (true) or hides (false) a layer in the QGIS layer panel.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "visible": {"type": "boolean"},
                    },
                    "required": ["layer_name", "visible"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # LABELING
    # ══════════════════════════════════════════════════════════

    "get_label_settings": {
        "intents": ["label"],
        "handler": "get_label_settings",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_label_settings",
                "description": (
                    "Returns the full label configuration of a vector layer: "
                    "source field, font, size, colour, buffer, placement, shadow. "
                    "Use before modifying labels to understand the existing setup."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "enable_labels": {
        "intents": ["label"],
        "handler": "enable_labels",
        "schema": {
            "type": "function",
            "function": {
                "name": "enable_labels",
                "description": (
                    "Enables labels on a vector layer. "
                    "Configurable in a single call: source field, font, size, colour, bold, italic, placement. "
                    "Placement is auto-detected from geometry type if not specified "
                    "(around_point for points, curved for lines, horizontal for polygons). "
                    "Use get_layer_fields first to get the exact field name. "
                    "ALWAYS call capture_map_canvas afterwards to verify the result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Field displayed as the label. Must exist in the layer.",
                        },
                        "font_size": {
                            "type": "number",
                            "description": "Font size in points. Default 10.",
                            "default": 10,
                        },
                        "font_family": {
                            "type": "string",
                            "description": "Font family. Ex: 'Arial', 'Times New Roman', 'Open Sans'. Default 'Arial'.",
                            "default": "Arial",
                        },
                        "color": {
                            "type": "string",
                            "description": "Text colour in hex. Default '#000000' (black).",
                            "default": "#000000",
                        },
                        "bold": {
                            "type": "boolean",
                            "description": "Bold text. Default false.",
                            "default": False,
                        },
                        "italic": {
                            "type": "boolean",
                            "description": "Italic text. Default false.",
                            "default": False,
                        },
                        "placement": {
                            "type": "string",
                            "enum": ["around_point", "over_point", "line", "curved", "horizontal", "perimeter", "free"],
                            "description": "Label placement mode. Auto-detected if omitted.",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "disable_labels": {
        "intents": ["label"],
        "handler": "disable_labels",
        "schema": {
            "type": "function",
            "function": {
                "name": "disable_labels",
                "description": "Disables labels on a vector layer.",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_text_format": {
        "intents": ["label"],
        "handler": "set_label_text_format",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_text_format",
                "description": (
                    "Modifies label text formatting: font, size, colour, bold, italic, underline, opacity. "
                    "Labels must be enabled first with enable_labels. "
                    "All parameters are optional — only provided ones will be changed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "font_family": {
                            "type": "string",
                            "description": "Font family. Ex: 'Arial', 'Verdana'.",
                        },
                        "font_size": {
                            "type": "number",
                            "description": "Size in points.",
                        },
                        "color": {
                            "type": "string",
                            "description": "Hex colour. Ex: '#FF0000'.",
                        },
                        "bold": {"type": "boolean"},
                        "italic": {"type": "boolean"},
                        "underline": {"type": "boolean"},
                        "opacity": {
                            "type": "number",
                            "description": "Text opacity from 0.0 to 1.0.",
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_buffer": {
        "intents": ["label"],
        "handler": "set_label_buffer",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_buffer",
                "description": (
                    "Configures the halo/buffer around labels to improve readability. "
                    "A white buffer around black text is the standard setup. "
                    "Labels must be enabled first with enable_labels. "
                    "ALWAYS call capture_map_canvas afterwards to verify the result."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "enabled": {
                            "type": "boolean",
                            "description": "Enable (true) or disable (false) the buffer.",
                            "default": True,
                        },
                        "size": {
                            "type": "number",
                            "description": "Buffer size in mm. Typically 0.5 to 2.0. Default 1.0.",
                            "default": 1.0,
                        },
                        "color": {
                            "type": "string",
                            "description": "Buffer colour in hex. Default '#FFFFFF' (white).",
                            "default": "#FFFFFF",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Buffer opacity from 0.0 to 1.0. Default 1.0.",
                            "default": 1.0,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_placement": {
        "intents": ["label"],
        "handler": "set_label_placement",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_placement",
                "description": (
                    "Changes label placement mode, distance, cartesian offset, and scale-based visibility. "
                    "Points → 'around_point' (near feature) or 'over_point' (centred). "
                    "Lines → 'line' (along) or 'curved'. "
                    "Polygons → 'horizontal' (flat) or 'perimeter' (on border). "
                    "All parameters are optional — omit placement to keep the current mode. "
                    "distance = radial distance from the feature, used by around_point / line / curved / perimeter modes "
                    "(this is the 'Distance' field visible in the QGIS label placement UI). "
                    "offset_x/offset_y = Cartesian shift applied after placement (separate from distance). "
                    "Labels must be enabled first with enable_labels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "placement": {
                            "type": "string",
                            "enum": ["around_point", "over_point", "line", "curved", "horizontal", "perimeter", "free"],
                            "description": "Label placement mode. Omit to keep the current mode.",
                        },
                        "distance": {
                            "type": "number",
                            "description": (
                                "Radial distance between the label and the feature. "
                                "This is the main 'Distance' control for around_point, line, curved and perimeter modes. "
                                "E.g. 2.0 places the label 2 mm away from the point. Units set by distance_units."
                            ),
                        },
                        "distance_units": {
                            "type": "string",
                            "enum": ["mm", "pt", "px", "map"],
                            "description": "Unit for distance. Default 'mm'.",
                            "default": "mm",
                        },
                        "offset_x": {
                            "type": "number",
                            "description": "Cartesian horizontal shift after placement (positive = right). Units set by offset_units.",
                        },
                        "offset_y": {
                            "type": "number",
                            "description": "Cartesian vertical shift after placement (positive = up). Units set by offset_units.",
                        },
                        "offset_units": {
                            "type": "string",
                            "enum": ["mm", "pt", "px", "map"],
                            "description": "Unit for offset_x/offset_y. Default 'mm'.",
                            "default": "mm",
                        },
                        "min_scale": {
                            "type": "number",
                            "description": "Minimum display scale (e.g. 500000 = 1:500000). 0 = no limit.",
                            "default": 0,
                        },
                        "max_scale": {
                            "type": "number",
                            "description": "Maximum display scale (e.g. 5000 = 1:5000). 0 = no limit.",
                            "default": 0,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_expression": {
        "intents": ["label"],
        "handler": "set_label_expression",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_expression",
                "description": (
                    "Uses a QGIS expression as the label text instead of a plain field. "
                    "Allows combining fields, formatting values, or computing displayed text. "
                    "Examples: concat(\"name\", '\\n', \"code\") for two lines, "
                    "format_number(\"area\", 2) || ' m²' for a formatted value. "
                    "Labels must be enabled first with enable_labels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "Valid QGIS expression. Ex: 'concat(\"name\", \\' (\\', \"code\", \\')\\')'.",
                        },
                    },
                    "required": ["layer_name", "expression"],
                },
            },
        },
    },

    "set_label_shadow": {
        "intents": ["label"],
        "handler": "set_label_shadow",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_shadow",
                "description": (
                    "Adds or removes a drop shadow from layer labels. "
                    "The shadow improves readability on complex backgrounds or imagery. "
                    "Labels must be enabled first with enable_labels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "enabled": {
                            "type": "boolean",
                            "description": "Enable (true) or disable (false) the shadow.",
                            "default": True,
                        },
                        "color": {
                            "type": "string",
                            "description": "Shadow colour in hex. Default '#000000' (black).",
                            "default": "#000000",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Shadow opacity from 0.0 to 1.0. Default 0.7.",
                            "default": 0.7,
                        },
                        "blur_radius": {
                            "type": "number",
                            "description": "Blur radius in mm. Typically 0.5 to 3.0. Default 1.5.",
                            "default": 1.5,
                        },
                        "offset_distance": {
                            "type": "number",
                            "description": "Shadow offset distance in mm. Default 1.0.",
                            "default": 1.0,
                        },
                        "offset_angle": {
                            "type": "integer",
                            "description": "Shadow angle in degrees (0-360). 315 = bottom-right. Default 315.",
                            "default": 315,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_background": {
        "intents": ["label"],
        "handler": "set_label_background",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_background",
                "description": (
                    "Adds a filled shape background behind layer labels. "
                    "Improves readability on complex backgrounds. "
                    "Labels must be enabled first with enable_labels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "enabled": {
                            "type": "boolean",
                            "description": "Enable (true) or disable (false) the background.",
                            "default": True,
                        },
                        "shape_type": {
                            "type": "string",
                            "enum": ["rectangle", "square", "ellipse", "circle"],
                            "description": "Background shape. Default 'rectangle'.",
                            "default": "rectangle",
                        },
                        "fill_color": {
                            "type": "string",
                            "description": "Fill colour in hex. Default '#FFFFFF' (white).",
                            "default": "#FFFFFF",
                        },
                        "stroke_color": {
                            "type": "string",
                            "description": "Border colour in hex. Default '#000000' (black).",
                            "default": "#000000",
                        },
                        "stroke_width": {
                            "type": "number",
                            "description": "Border width in mm. Default 0.3.",
                            "default": 0.3,
                        },
                        "size_x": {
                            "type": "number",
                            "description": "Horizontal padding in mm around the text. Default 1.0.",
                            "default": 1.0,
                        },
                        "size_y": {
                            "type": "number",
                            "description": "Vertical padding in mm around the text. Default 0.5.",
                            "default": 0.5,
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Background opacity from 0.0 to 1.0. Default 1.0.",
                            "default": 1.0,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_label_callout": {
        "intents": ["label"],
        "handler": "set_label_callout",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_label_callout",
                "description": (
                    "Adds or removes a callout line connecting a displaced label to its feature. "
                    "Useful when labels are pushed far from their feature (e.g. on dense maps). "
                    "Styles: 'simple' (straight line), 'manhattan' (right-angle/orthogonal), "
                    "'curved' (smooth Bézier curve), 'balloon' (speech-bubble shape with fill). "
                    "Labels must be enabled first with enable_labels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "enabled": {
                            "type": "boolean",
                            "description": "Enable (true) or disable (false) the callout. Default true.",
                            "default": True,
                        },
                        "style": {
                            "type": "string",
                            "enum": ["simple", "manhattan", "curved", "balloon"],
                            "description": "Callout style. Default 'simple'.",
                            "default": "simple",
                        },
                        "line_color": {
                            "type": "string",
                            "description": "Line (or balloon border) colour in hex. Default '#000000' (black).",
                            "default": "#000000",
                        },
                        "line_width": {
                            "type": "number",
                            "description": "Line width in mm. Default 0.3.",
                            "default": 0.3,
                        },
                        "min_length": {
                            "type": "number",
                            "description": "Minimum callout length in mm. Callouts shorter than this are not drawn. Default 0 (always draw).",
                            "default": 0.0,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "refresh_canvas": {
        "intents": ["view"],
        "handler": "refresh_canvas",
        "schema": {
            "type": "function",
            "function": {
                "name": "refresh_canvas",
                "description": "Forces a refresh of the QGIS map canvas. Call after style modifications.",
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # DATA EDITING
    # ══════════════════════════════════════════════════════════

    "add_field": {
        "intents": ["field"],
        "handler": "add_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "add_field",
                "description": (
                    "Adds a new field to a vector layer. "
                    "field_type: 'string', 'int', 'double', 'date'. "
                    "Use before calculate_field if the field does not exist yet."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {"type": "string"},
                        "field_type": {
                            "type": "string",
                            "enum": ["string", "int", "double", "date"],
                            "default": "string",
                        },
                        "length": {
                            "type": "integer",
                            "description": "Maximum length for string fields. Default 100.",
                            "default": 100,
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "delete_field": {
        "intents": ["field"],
        "handler": "delete_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "delete_field",
                "description": (
                    "Permanently deletes a field from a vector layer. "
                    "Use get_layer_fields first to confirm the exact field name. "
                    "This operation cannot be undone."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Exact name of the field to delete.",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "rename_field": {
        "intents": ["field"],
        "handler": "rename_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "rename_field",
                "description": (
                    "Renames an existing field in a vector layer. "
                    "Use get_layer_fields first to confirm the exact current name."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Current exact name of the field.",
                        },
                        "new_name": {
                            "type": "string",
                            "description": "New name for the field.",
                        },
                    },
                    "required": ["layer_name", "field_name", "new_name"],
                },
            },
        },
    },

    "rename_layer": {
        "intents": ["layer"],
        "handler": "rename_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "rename_layer",
                "description": (
                    "Renames a layer in the QGIS project panel. "
                    "Only changes the display name — does not rename the source file."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Current layer name.",
                        },
                        "new_name": {
                            "type": "string",
                            "description": "New display name for the layer.",
                        },
                    },
                    "required": ["layer_name", "new_name"],
                },
            },
        },
    },

    "remove_layer": {
        "intents": ["layer"],
        "handler": "remove_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "remove_layer",
                "description": (
                    "Removes a layer from the QGIS project. "
                    "Does NOT delete the source file on disk. "
                    "This operation cannot be undone without reloading the layer."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "calculate_field": {
        "intents": ["field"],
        "handler": "calculate_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "calculate_field",
                "description": (
                    "Calculates or updates an existing field using a QGIS expression. "
                    "Possible expressions: '\"area\" * 2', 'length($geometry)', "
                    "'area($geometry)', 'concat(\"first\", \\' \\', \"last\")'. "
                    "The field must exist — use add_field first if needed."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Field to calculate (must exist).",
                        },
                        "expression": {
                            "type": "string",
                            "description": "QGIS expression. Ex: 'area($geometry)' or '\"pop\" / \"area\"'.",
                        },
                        "only_selected": {
                            "type": "boolean",
                            "description": "True = calculate only on selected features.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name", "field_name", "expression"],
                },
            },
        },
    },

    "load_layer": {
        "intents": ["layer"],
        "handler": "load_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "load_layer",
                "description": (
                    "Loads a layer into the QGIS project from a file path. "
                    "Supported formats: GeoJSON, Shapefile (.shp), GeoPackage (.gpkg), "
                    "CSV, GeoTIFF, and all GDAL/OGR formats."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Absolute path to the file.",
                        },
                        "layer_name": {
                            "type": "string",
                            "description": "Display name in QGIS. Uses the filename if empty.",
                            "default": "",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
    },

    "export_layer": {
        "intents": ["layer"],
        "handler": "export_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "export_layer",
                "description": (
                    "Exports a vector layer to a file. "
                    "format: 'GeoJSON', 'GPKG', 'ESRI Shapefile', 'CSV'. "
                    "Can export only selected features with only_selected=true."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "output_path": {
                            "type": "string",
                            "description": "Absolute output path with extension. Ex: '/tmp/result.geojson'.",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["GeoJSON", "GPKG", "ESRI Shapefile", "CSV"],
                            "default": "GeoJSON",
                        },
                        "only_selected": {
                            "type": "boolean",
                            "description": "True = export only selected features.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name", "output_path"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # RASTER
    # ══════════════════════════════════════════════════════════

    "get_raster_info": {
        "intents": ["raster", "read"],
        "handler": "get_raster_info",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_raster_info",
                "description": (
                    "Returns metadata of a raster layer: band count, pixel size, "
                    "width/height in pixels, CRS, spatial extent, source path, and nodata value. "
                    "Use first to inspect any raster layer before processing or styling it."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_raster_statistics": {
        "intents": ["raster", "stats"],
        "handler": "get_raster_statistics",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_raster_statistics",
                "description": (
                    "Computes statistics for a raster band: min, max, mean, standard deviation. "
                    "Use to determine value range before styling with set_raster_style. "
                    "band defaults to 1 (first band)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "band": {
                            "type": "integer",
                            "description": "Band number (1-based). Default 1.",
                            "default": 1,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "set_raster_style": {
        "intents": ["raster"],
        "handler": "set_raster_style",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_raster_style",
                "description": (
                    "Applies a visual style to a raster layer. "
                    "style_type: 'pseudocolor' (color ramp on values, default) or 'gray' (grayscale). "
                    "Use get_raster_statistics first to know min/max and set them explicitly — "
                    "otherwise they are computed automatically. "
                    "color_ramp_name examples: 'Spectral', 'RdYlGn', 'Viridis', 'Blues', 'Reds', 'Greys'. "
                    "Set invert=true to reverse the ramp direction (e.g. high values in blue)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "style_type": {
                            "type": "string",
                            "enum": ["pseudocolor", "gray"],
                            "description": "Renderer type. Default 'pseudocolor'.",
                            "default": "pseudocolor",
                        },
                        "band": {
                            "type": "integer",
                            "description": "Band to render (1-based). Default 1.",
                            "default": 1,
                        },
                        "color_ramp_name": {
                            "type": "string",
                            "description": "QGIS color ramp name for pseudocolor. Default 'Spectral'.",
                            "default": "Spectral",
                        },
                        "min_value": {
                            "type": "number",
                            "description": "Minimum value of the color ramp. Auto-computed if omitted.",
                        },
                        "max_value": {
                            "type": "number",
                            "description": "Maximum value of the color ramp. Auto-computed if omitted.",
                        },
                        "invert": {
                            "type": "boolean",
                            "description": "Invert the color ramp direction. Default false.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # ANALYSIS
    # ══════════════════════════════════════════════════════════

    "get_field_value_counts": {
        "intents": ["stats"],
        "handler": "get_field_value_counts",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_field_value_counts",
                "description": (
                    "Returns a frequency table for a field: count and percentage for each unique value. "
                    "Use for 'how many features per type', 'distribution of values', "
                    "'what is the most common category'. "
                    "Prefer over get_unique_values when you need counts, not just the list of values."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Field to compute the frequency table on.",
                        },
                        "sort_by": {
                            "type": "string",
                            "enum": ["count_desc", "count_asc", "value"],
                            "description": "Sort order: 'count_desc' (default), 'count_asc', or 'value' (alphabetical).",
                            "default": "count_desc",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "get_statistics_by_group": {
        "intents": ["stats"],
        "handler": "get_statistics_by_group",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_statistics_by_group",
                "description": (
                    "Computes statistics (min, max, mean, sum, count) on a numeric field "
                    "grouped by the unique values of another field. "
                    "Use for 'average area per type', 'total population per municipality', "
                    "'compare statistics between categories'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "group_field": {
                            "type": "string",
                            "description": "Field used to form groups (categorical). Ex: 'type', 'municipality'.",
                        },
                        "value_field": {
                            "type": "string",
                            "description": "Numeric field to compute statistics on. Ex: 'area', 'population'.",
                        },
                    },
                    "required": ["layer_name", "group_field", "value_field"],
                },
            },
        },
    },

    "get_field_percentiles": {
        "intents": ["stats"],
        "handler": "get_field_percentiles",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_field_percentiles",
                "description": (
                    "Computes percentiles for a numeric field: median (P50), Q1 (P25), Q3 (P75), "
                    "IQR, and any custom percentile. "
                    "Use for 'what is the median', 'interquartile range', 'give me the 90th percentile'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Numeric field to compute percentiles on.",
                        },
                        "custom_percentile": {
                            "type": "number",
                            "description": "Additional percentile to compute (0–100). Ex: 90 for P90. Optional.",
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "get_field_correlation": {
        "intents": ["stats"],
        "handler": "get_field_correlation",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_field_correlation",
                "description": (
                    "Computes the Pearson correlation coefficient between two numeric fields. "
                    "Returns r (−1 to 1) and the number of valid feature pairs. "
                    "Use for 'is X correlated with Y', 'relationship between area and population'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_a": {
                            "type": "string",
                            "description": "First numeric field.",
                        },
                        "field_b": {
                            "type": "string",
                            "description": "Second numeric field.",
                        },
                    },
                    "required": ["layer_name", "field_a", "field_b"],
                },
            },
        },
    },

    "calculate_geometry": {
        "intents": ["field"],
        "handler": "calculate_geometry",
        "schema": {
            "type": "function",
            "function": {
                "name": "calculate_geometry",
                "description": (
                    "Calculates geometric attributes (area, perimeter, length, coordinates) "
                    "and adds them as new fields in a layer. "
                    "Use for 'add the area', 'compute areas', 'add length'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "output_layer_name"],
                },
            },
        },
    },

    "check_geometry_validity": {
        "intents": ["stats"],
        "handler": "check_geometry_validity",
        "schema": {
            "type": "function",
            "function": {
                "name": "check_geometry_validity",
                "description": (
                    "Checks the validity of geometries in a layer. "
                    "Returns the count of valid and invalid geometries. "
                    "Use before fix_geometries if geometry errors appear."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # ULTIMATE FALLBACK
    # ══════════════════════════════════════════════════════════

    "request_additional_tools": {
        "intents": ["__always__"],
        "handler": None,
        "schema": {
            "type": "function",
            "function": {
                "name": "request_additional_tools",
                "description": (
                    "Requests access to additional tools if you realise mid-execution "
                    "that the available tools do not cover all needs. "
                    "Specify the missing intents from: read, stats, process, join, select, "
                    "style, label, field, layer, view, raster. "
                    "New tools will be immediately available for subsequent calls."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "List of intents needed, e.g. [\"style\", \"label\"].",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Why these additional tools are needed.",
                        },
                    },
                    "required": ["intents"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════

    "capture_map_canvas": {
        "intents": ["__always__"],
        "handler": "capture_map_canvas",
        "schema": {
            "type": "function",
            "function": {
                "name": "capture_map_canvas",
                "description": (
                    "Captures a screenshot of the QGIS map canvas and returns it as an image. "
                    "Use this tool in two cases: "
                    "(1) **mandatory after applying a style, symbology, labels, or any visual change to a layer**, "
                    "to verify the result before responding; "
                    "(2) **if the user asks to see the map, canvas, what is displayed, or "
                    "the visual state of the project**."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {},
                    "required": [],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════

    "run_pyqgis_code": {
        "intents": ["__fallback__"],
        "handler": "run_pyqgis_code",
        "schema": {
            "type": "function",
            "function": {
                "name": "run_pyqgis_code",
                "description": (
                    "ULTIMATE FALLBACK: executes arbitrary PyQGIS code. "
                    "Use ONLY if no other tool covers the need. "
                    "The code has access to: iface, QgsProject, QgsVectorLayer, processing, Qgis. "
                    "Always include a result log line in the code: "
                    "iface.messageBar().pushInfo('Agent', 'X features processed')"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Valid Python code using the PyQGIS API.",
                        },
                    },
                    "required": ["code"],
                },
            },
        },
    },
}


# ══════════════════════════════════════════════════════════════
# AUTO-BUILT INTENT INDEX
# ══════════════════════════════════════════════════════════════

# Maps intent → tool names, e.g. {"read": [...], "__always__": [...], "__fallback__": [...]}
TOOLS_BY_INTENT: dict = {}
for _name, _def in REGISTRY.items():
    for _intent in _def["intents"]:
        TOOLS_BY_INTENT.setdefault(_intent, []).append(_name)


def get_schemas_for_intent(intents: list) -> list:
    """
    Return OpenAI function-call schemas for the given intents.

    Ordering:
      1. Tools matched by the requested intents (deduplicated, insertion order).
      2. __always__ tools (request_additional_tools, capture_map_canvas, …).
      3. __fallback__ tools (run_pyqgis_code, …) — always last.
    """
    seen: set = set()
    tool_names: list = []

    def _add(name: str) -> None:
        if name not in seen:
            seen.add(name)
            tool_names.append(name)

    for intent in intents:
        for name in TOOLS_BY_INTENT.get(intent, []):
            _add(name)

    for name in TOOLS_BY_INTENT.get("__always__", []):
        _add(name)

    for name in TOOLS_BY_INTENT.get("__fallback__", []):
        _add(name)

    return [REGISTRY[name]["schema"] for name in tool_names]


def get_handler_name(tool_name: str) -> str:
    """Return the Python handler function name registered for a given tool."""
    return REGISTRY.get(tool_name, {}).get("handler", "")
