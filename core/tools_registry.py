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
                    "Retourne la liste de toutes les couches du projet QGIS avec "
                    "leurs types, CRS et nombre de features. "
                    "UTILISER EN PREMIER pour connaître le contenu du projet. "
                    "NE PAS utiliser pour lire les attributs d'une couche spécifique."
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
                    "Retourne les détails complets d'une couche : CRS, type de géométrie, "
                    "nombre de features, emprise, source fichier. "
                    "À utiliser avant un géotraitement pour vérifier la compatibilité CRS."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Nom exact de la couche dans le projet QGIS.",
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_fields": {
        "intents": ["read"],
        "handler": "get_layer_fields",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_fields",
                "description": (
                    "Liste tous les champs d'une couche vecteur avec leur nom, type "
                    "(Integer, String, Double, Date...) et alias. "
                    "À utiliser avant calculate_field, set_categorized_style ou "
                    "toute opération nécessitant un nom de champ exact."
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
                    "Retourne les attributs des features d'une couche vecteur. "
                    "Supporte un filtre par expression QGIS et une limite. "
                    "Exemples de filtre : '\"usage\" = \\'résidentiel\\'' ou '\"surface\" > 100'. "
                    "NE PAS utiliser pour des statistiques (utiliser get_layer_statistics)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "filter_expression": {
                            "type": "string",
                            "description": "Expression QGIS optionnelle. Ex: '\"type\" = \\'route\\''. Laisser vide pour tout retourner.",
                        },
                        "max_features": {
                            "type": "integer",
                            "description": "Nombre max de features retournées. Défaut 50.",
                            "default": 50,
                        },
                    },
                    "required": ["layer_name"],
                },
            },
        },
    },

    "get_layer_statistics": {
        "intents": ["read", "analyse"],
        "handler": "get_layer_statistics",
        "schema": {
            "type": "function",
            "function": {
                "name": "get_layer_statistics",
                "description": (
                    "Calcule les statistiques d'un champ numérique : min, max, moyenne, "
                    "somme, écart-type, count. "
                    "À utiliser pour 'quelle est la surface moyenne', 'quel est le max de...'"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Nom du champ numérique à analyser.",
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
                    "Retourne toutes les valeurs uniques d'un champ. "
                    "Utile avant set_categorized_style pour connaître les catégories, "
                    "ou avant select_by_expression pour connaître les valeurs possibles."
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
                    "Retourne les features actuellement sélectionnées sur une couche. "
                    "À utiliser après select_by_expression ou select_by_location "
                    "pour inspecter ce qui est sélectionné."
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
                "description": "Retourne l'emprise spatiale d'une couche (xmin, ymin, xmax, ymax) et son CRS.",
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
                    "Crée une zone tampon autour des géométries d'une couche (native:buffer). "
                    "Utiliser pour 'zone tampon', 'buffer', 'périmètre de X mètres autour de'. "
                    "La distance est en unités de la couche (mètres pour EPSG:2154, EPSG:3857...)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "distance": {
                            "type": "number",
                            "description": "Distance du buffer en unités de la couche (ex: 500 pour 500 mètres si EPSG:2154).",
                        },
                        "dissolve": {
                            "type": "boolean",
                            "description": "True = fusionne tous les buffers en un seul polygone. Utile avant une sélection spatiale.",
                            "default": False,
                        },
                        "segments": {
                            "type": "integer",
                            "description": "Segments par quart de cercle. Plus = plus lisse. Défaut 5.",
                            "default": 5,
                        },
                        "output_layer_name": {
                            "type": "string",
                            "description": "Nom de la couche résultat. Ex: 'buffer_routes_500m'.",
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
                    "Découpe une couche par une autre (native:clip). "
                    "Utiliser pour 'découper', 'clip', 'limiter à la zone de', 'extraire la partie dans'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Couche à découper.",
                        },
                        "overlay_layer_name": {
                            "type": "string",
                            "description": "Couche servant de masque de découpe.",
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
                    "Intersection spatiale entre deux couches (native:intersection). "
                    "Retourne uniquement les parties communes avec les attributs des deux couches. "
                    "Différent de clip : intersection conserve les attributs des deux couches."
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
                    "Fusionne les géométries d'une couche (native:dissolve). "
                    "Sans field = tout fusionner en une géométrie. "
                    "Avec field = fusionner par valeur de ce champ (ex: fusionner par 'commune')."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field": {
                            "type": "string",
                            "description": "Champ de regroupement. Laisser vide pour tout fusionner.",
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
                    "Reprojette une couche dans un autre CRS (native:reprojectlayer). "
                    "Utiliser quand deux couches ont des CRS différents avant de les combiner. "
                    "Exemples CRS : 'EPSG:2154' (Lambert 93), 'EPSG:4326' (WGS84), 'EPSG:3857' (Web Mercator)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "target_crs": {
                            "type": "string",
                            "description": "CRS cible au format EPSG. Ex: 'EPSG:4326'.",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["layer_name", "target_crs", "output_layer_name"],
                },
            },
        },
    },

    "join_by_location": {
        "intents": ["process", "analyse"],
        "handler": "join_by_location",
        "schema": {
            "type": "function",
            "function": {
                "name": "join_by_location",
                "description": (
                    "Jointure spatiale entre deux couches (native:joinattributesbylocation). "
                    "Ajoute les attributs d'une couche à une autre selon leur relation spatiale. "
                    "Ex: ajouter le nom de la commune à chaque bâtiment."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Couche qui reçoit les attributs.",
                        },
                        "join_layer_name": {
                            "type": "string",
                            "description": "Couche dont on prend les attributs.",
                        },
                        "predicates": {
                            "type": "array",
                            "items": {"type": "integer"},
                            "description": "Relations spatiales : [0]=intersects, [1]=contains, [6]=within. Défaut [0].",
                            "default": [0],
                        },
                        "join_fields": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Champs à joindre. [] = tous.",
                            "default": [],
                        },
                        "discard_nonmatching": {
                            "type": "boolean",
                            "description": "True = supprimer les features sans correspondance.",
                            "default": False,
                        },
                        "prefix": {
                            "type": "string",
                            "description": "Préfixe pour les champs joints. Ex: 'com_'.",
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
                    "Calcule les centroïdes de polygones ou lignes (native:centroids). "
                    "Retourne une couche de points au centre de chaque géométrie."
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
                    "Différence spatiale : retourne la partie de layer_name "
                    "qui n'intersecte PAS overlay_layer_name (native:difference). "
                    "Ex: parcelles hors zone inondable."
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
                    "Union spatiale de deux couches (native:union). "
                    "Retourne toutes les géométries des deux couches combinées."
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
                    "Corrige les géométries invalides d'une couche (native:fixgeometries). "
                    "À utiliser si un algo Processing échoue avec une erreur de géométrie invalide."
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

    "run_processing_algorithm": {
        "intents": ["process"],
        "handler": "run_processing_algorithm",
        "schema": {
            "type": "function",
            "function": {
                "name": "run_processing_algorithm",
                "description": (
                    "Fallback générique : lance N'IMPORTE QUEL algorithme QGIS Processing "
                    "par son identifiant complet. "
                    "À utiliser UNIQUEMENT si aucun tool spécifique ne couvre le besoin. "
                    "Exemples : 'native:simplifygeometries', 'qgis:advancedpythonfieldcalculator', "
                    "'native:extractbyattribute', 'native:splitvectorlayer'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "algorithm": {
                            "type": "string",
                            "description": "Identifiant complet de l'algo. Ex: 'native:simplifygeometries'.",
                        },
                        "layer_name": {"type": "string"},
                        "parameters": {
                            "type": "object",
                            "description": "Paramètres spécifiques à l'algorithme (sans INPUT ni OUTPUT qui sont gérés automatiquement).",
                        },
                        "output_layer_name": {"type": "string"},
                    },
                    "required": ["algorithm", "layer_name", "parameters", "output_layer_name"],
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
                    "Sélectionne des features par une expression QGIS. "
                    "Syntaxe : '\"nom_champ\" = \\'valeur\\'' ou '\"surface\" > 100'. "
                    "Utiliser get_layer_fields d'abord pour connaître les noms exacts des champs. "
                    "NE PAS utiliser pour une sélection spatiale (utiliser select_by_location)."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "Expression QGIS. Ex: '\"type\" = \\'autoroute\\'' ou '\"population\" > 10000'.",
                        },
                    },
                    "required": ["layer_name", "expression"],
                },
            },
        },
    },

    "select_by_location": {
        "intents": ["select", "process"],
        "handler": "select_by_location",
        "schema": {
            "type": "function",
            "function": {
                "name": "select_by_location",
                "description": (
                    "Sélectionne des features selon leur relation spatiale avec une autre couche. "
                    "Utiliser pour 'sélectionner les bâtiments dans le buffer', "
                    "'trouver les points dans la zone', 'features qui intersectent'. "
                    "predicate : 0=intersects (défaut), 1=contains, 6=within, 4=touches."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {
                            "type": "string",
                            "description": "Couche dont on sélectionne les features.",
                        },
                        "intersect_layer_name": {
                            "type": "string",
                            "description": "Couche de référence spatiale.",
                        },
                        "predicate": {
                            "type": "integer",
                            "description": "0=intersects, 1=contains, 6=within, 4=touches. Défaut 0.",
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
                    "Applique un filtre permanent sur une couche sans créer de nouvelle couche. "
                    "La couche n'affichera que les features correspondant à l'expression. "
                    "Passer expression='' pour supprimer le filtre."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "expression": {
                            "type": "string",
                            "description": "Expression QGIS. Ex: '\"annee\" >= 2000'. Vide pour supprimer le filtre.",
                        },
                    },
                    "required": ["layer_name", "expression"],
                },
            },
        },
    },

    "zoom_to_layer": {
        "intents": ["select", "view"],
        "handler": "zoom_to_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "zoom_to_layer",
                "description": "Zoome le canvas QGIS sur l'emprise complète d'une couche.",
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
        "intents": ["select", "view"],
        "handler": "zoom_to_feature",
        "schema": {
            "type": "function",
            "function": {
                "name": "zoom_to_feature",
                "description": "Zoome sur une feature spécifique d'une couche par son identifiant (fid).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "feature_id": {
                            "type": "integer",
                            "description": "Identifiant (fid) de la feature.",
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
                    "Retourne le type de renderer actuel d'une couche et ses paramètres de style : "
                    "couleur, opacité, champ de catégorisation, nombre de classes... "
                    "À utiliser avant de modifier un style pour comprendre l'existant."
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
                    "Applique un symbole unique à toute la couche. "
                    "Utiliser pour 'colorie en rouge', 'rends la couche bleue', "
                    "'change la couleur de'. "
                    "color au format hex : '#FF0000' pour rouge, '#0000FF' pour bleu."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "color": {
                            "type": "string",
                            "description": "Couleur de remplissage en hex. Ex: '#FF0000', '#3498DB', '#2ECC71'.",
                        },
                        "opacity": {
                            "type": "number",
                            "description": "Opacité du symbole de 0.0 à 1.0. Défaut 1.0.",
                            "default": 1.0,
                        },
                        "size": {
                            "type": "number",
                            "description": "Taille (pour les points). Laisser null pour la valeur par défaut.",
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
                    "Applique une symbologie catégorisée : une couleur différente par valeur unique d'un champ. "
                    "Utiliser pour 'colorie par type', 'une couleur par catégorie', 'symbologie par usage'. "
                    "Utiliser get_unique_values d'abord pour voir les valeurs disponibles."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Champ sur lequel baser la catégorisation.",
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
                    "Applique une symbologie graduée sur un champ numérique (rampe de couleur). "
                    "Utiliser pour 'colorie par densité', 'graduation par surface', 'rampe de couleur sur'. "
                    "color_ramp_name : 'Blues', 'Reds', 'Greens', 'RdYlGn', 'Spectral', 'Viridis'."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Champ numérique pour la graduation.",
                        },
                        "num_classes": {
                            "type": "integer",
                            "description": "Nombre de classes. Défaut 5.",
                            "default": 5,
                        },
                        "color_ramp_name": {
                            "type": "string",
                            "description": "Rampe de couleur QGIS. Ex: 'Blues', 'Reds', 'Viridis'.",
                            "default": "Blues",
                        },
                        "mode": {
                            "type": "integer",
                            "description": "0=Quantile, 1=Intervalles égaux, 2=Ruptures naturelles. Défaut 0.",
                            "default": 0,
                        },
                    },
                    "required": ["layer_name", "field_name"],
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
                "description": "Règle l'opacité d'une couche de 0.0 (invisible) à 1.0 (opaque).",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "opacity": {
                            "type": "number",
                            "description": "Opacité entre 0.0 et 1.0.",
                        },
                    },
                    "required": ["layer_name", "opacity"],
                },
            },
        },
    },

    "set_layer_visibility": {
        "intents": ["style", "view"],
        "handler": "set_layer_visibility",
        "schema": {
            "type": "function",
            "function": {
                "name": "set_layer_visibility",
                "description": "Affiche (true) ou masque (false) une couche dans le panneau des couches QGIS.",
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

    "refresh_canvas": {
        "intents": ["style", "view"],
        "handler": "refresh_canvas",
        "schema": {
            "type": "function",
            "function": {
                "name": "refresh_canvas",
                "description": "Force le rafraîchissement du canvas QGIS. Appeler après des modifications de style.",
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
        "intents": ["edit"],
        "handler": "add_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "add_field",
                "description": (
                    "Ajoute un nouveau champ à une couche vecteur. "
                    "field_type : 'string', 'int', 'double', 'date'. "
                    "À utiliser avant calculate_field si le champ n'existe pas encore."
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
                            "description": "Longueur max pour les champs string. Défaut 100.",
                            "default": 100,
                        },
                    },
                    "required": ["layer_name", "field_name"],
                },
            },
        },
    },

    "calculate_field": {
        "intents": ["edit", "analyse"],
        "handler": "calculate_field",
        "schema": {
            "type": "function",
            "function": {
                "name": "calculate_field",
                "description": (
                    "Calcule ou met à jour un champ existant via une expression QGIS. "
                    "Expressions possibles : '\"surface\" * 2', 'length($geometry)', "
                    "'area($geometry)', 'concat(\"nom\", \\' \\', \"prenom\")'. "
                    "Le champ doit exister — utiliser add_field d'abord si nécessaire."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "field_name": {
                            "type": "string",
                            "description": "Champ à calculer (doit exister).",
                        },
                        "expression": {
                            "type": "string",
                            "description": "Expression QGIS. Ex: 'area($geometry)' ou '\"pop\" / \"surface\"'.",
                        },
                        "only_selected": {
                            "type": "boolean",
                            "description": "True = calculer uniquement sur les features sélectionnées.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name", "field_name", "expression"],
                },
            },
        },
    },

    "load_layer": {
        "intents": ["edit", "read"],
        "handler": "load_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "load_layer",
                "description": (
                    "Charge une couche dans le projet QGIS depuis un chemin fichier. "
                    "Formats supportés : GeoJSON, Shapefile (.shp), GeoPackage (.gpkg), "
                    "CSV, GeoTIFF, et tous les formats GDAL/OGR."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "file_path": {
                            "type": "string",
                            "description": "Chemin absolu vers le fichier.",
                        },
                        "layer_name": {
                            "type": "string",
                            "description": "Nom affiché dans QGIS. Si vide, utilise le nom du fichier.",
                            "default": "",
                        },
                    },
                    "required": ["file_path"],
                },
            },
        },
    },

    "export_layer": {
        "intents": ["export"],
        "handler": "export_layer",
        "schema": {
            "type": "function",
            "function": {
                "name": "export_layer",
                "description": (
                    "Exporte une couche vecteur vers un fichier. "
                    "format : 'GeoJSON', 'GPKG', 'ESRI Shapefile', 'CSV'. "
                    "Peut exporter uniquement les features sélectionnées avec only_selected=true."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "layer_name": {"type": "string"},
                        "output_path": {
                            "type": "string",
                            "description": "Chemin absolu de sortie avec extension. Ex: '/tmp/result.geojson'.",
                        },
                        "format": {
                            "type": "string",
                            "enum": ["GeoJSON", "GPKG", "ESRI Shapefile", "CSV"],
                            "default": "GeoJSON",
                        },
                        "only_selected": {
                            "type": "boolean",
                            "description": "True = exporter uniquement les features sélectionnées.",
                            "default": False,
                        },
                    },
                    "required": ["layer_name", "output_path"],
                },
            },
        },
    },

    # ══════════════════════════════════════════════════════════
    # ANALYSIS
    # ══════════════════════════════════════════════════════════

    "calculate_geometry": {
        "intents": ["analyse", "edit"],
        "handler": "calculate_geometry",
        "schema": {
            "type": "function",
            "function": {
                "name": "calculate_geometry",
                "description": (
                    "Calcule les attributs géométriques (aire, périmètre, longueur, coordonnées) "
                    "et les ajoute comme nouveaux champs dans une couche. "
                    "Utiliser pour 'ajoute la superficie', 'calcule les aires', 'ajoute la longueur'."
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
        "intents": ["analyse"],
        "handler": "check_geometry_validity",
        "schema": {
            "type": "function",
            "function": {
                "name": "check_geometry_validity",
                "description": (
                    "Vérifie la validité des géométries d'une couche. "
                    "Retourne le nombre de géométries valides et invalides. "
                    "À utiliser avant fix_geometries si des erreurs de géométrie apparaissent."
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
                    "Demande l'accès à des outils supplémentaires si tu réalises en cours d'exécution "
                    "que les outils disponibles ne couvrent pas tous les besoins. "
                    "Spécifie les intents manquants parmi : read, process, select, style, edit, export, analyse, view. "
                    "Les nouveaux outils seront immédiatement disponibles pour les prochains appels."
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "intents": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "Liste des intents dont tu as besoin, ex: [\"style\", \"edit\"].",
                        },
                        "reason": {
                            "type": "string",
                            "description": "Pourquoi ces outils supplémentaires sont nécessaires.",
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
                    "Capture une copie d'écran du canvas cartographique QGIS et la retourne sous forme d'image. "
                    "Utilise ce tool dans deux cas : "
                    "(1) **obligatoirement après avoir appliqué un style, une symbologie, des étiquettes ou "
                    "tout changement visuel sur une couche**, pour vérifier le résultat avant de répondre ; "
                    "(2) **si l'utilisateur demande à voir la carte, le canvas, ce qui est affiché ou "
                    "l'état visuel du projet**."
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
                    "FALLBACK ULTIME : exécute du code PyQGIS arbitraire. "
                    "À utiliser UNIQUEMENT si aucun autre tool ne couvre le besoin. "
                    "Le code a accès à : iface, QgsProject, QgsVectorLayer, processing, Qgis. "
                    "Toujours inclure dans le code une ligne de log du résultat : "
                    "iface.messageBar().pushInfo('Agent', 'X features traitées')"
                ),
                "parameters": {
                    "type": "object",
                    "properties": {
                        "code": {
                            "type": "string",
                            "description": "Code Python valide utilisant l'API PyQGIS.",
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

# Maps intent names to tool name lists, e.g. {"read": ["get_project_info", ...], "process": [...]}
TOOLS_BY_INTENT: dict = {}
for _name, _def in REGISTRY.items():
    for _intent in _def["intents"]:
        TOOLS_BY_INTENT.setdefault(_intent, []).append(_name)


def get_schemas_for_intent(intents: list) -> list:
    """
    Return the list of OpenAI function-call schemas to send to the LLM
    for a given list of detected intents.
    The run_pyqgis_code fallback is always appended last.
    """
    tool_names = []
    for intent in intents:
        for name in TOOLS_BY_INTENT.get(intent, []):
            if name not in tool_names:
                tool_names.append(name)

    # Always ensure the fallback and visual verification tools are available
    if "run_pyqgis_code" not in tool_names:
        tool_names.append("run_pyqgis_code")
    if "capture_map_canvas" not in tool_names:
        tool_names.append("capture_map_canvas")

    return [REGISTRY[name]["schema"] for name in tool_names]


def get_handler_name(tool_name: str) -> str:
    """Return the Python handler function name registered for a given tool."""
    return REGISTRY.get(tool_name, {}).get("handler", "")
