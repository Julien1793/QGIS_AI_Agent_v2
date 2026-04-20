def get_translations(lang):
    translations = {
        "fr": {
            "dock_title": "Assistant IA",
            "assistant_tab": "Assistant",
            "debug_tab": "Debug",
            "send": "Envoyer",
            "message_prompt": "Entrez votre message ici...",
            "generate": "Générer Code",
            "execute": "Exécuter",
            "execute_label": "Du code est prêt à être exécuté",
            "clear": "Vider",
            "history_count": "N derniers échanges",
            "options": "Options",
            "fix_and_run": "Corriger et exécuter",
            "error_during_exec": "Une erreur est survenue. Vous pouvez demander une correction.",
            "status": "<b>Mode :</b> {} | <b>Modèle :</b> {} | <b>Tokens utilisés :</b> {}",
            "loading": "Requête en cours...",
            "no_code": "Aucun code à exécuter.",
            "correction": "Correction",
            "no_error": "Aucune erreur détectée.",
            "mode": "Mode",
            "model": "Modèle",
            "token_count": "Tokens utilisés",
            "dialog_title": "Assistant IA",
            "execution": "Exécution",
            "review_title": "Vérifier et exécuter",
            "code_preview": "Aperçu du code (modifiable avant exécution)",
            "run_now": "Lancer",
            "system_prompt_chat": (
                "Tu es un expert QGIS et tu aides un utilisateur qui est dans QGIS. "
                "Version actuelle : {qgis_version}. Réponds clairement à l'utilisateur. "
                "Réponds en français."
            ),
            "system_prompt_code": (
                "Tu es un expert QGIS et tu aides un utilisateur qui est dans QGIS. "
                "Version actuelle : {qgis_version}. "
                "Génère UNIQUEMENT du code PyQGIS exécutable (avec les imports), sans explications. "
                "Ajoute des commentaires Python en français. "
                "Si aucun chemin de sortie n'est précisé, écris en mémoire."
            ),
            "project_snapshot_intro": "Voici l'état du projet QGIS de l'utilisateur :",
            "reset": "Réinitialiser",
            "reset_confirm": "Réinitialiser tous les réglages du plugin ?\n(Cela n'efface pas vos projets QGIS.)",
            "reset_done": "Réglages réinitialisés.",
            "you_prefix": "Vous",
            "assistant_prefix": "Assistant",
            "warnings": "Avertissements",
            "no_warnings": "Aucun avertissement détecté.",
            "warn_fix_header": "Le script s'est exécuté mais avec des avertissements.",
            "warn_fix_instruction": (
                "Analyse et corrige le code pour supprimer ces avertissements, "
                "sans changer l'intention ni le comportement attendu. "
                "Renvoie UNIQUEMENT du code PyQGIS exécutable et n'oublie pas les imports."
            ),
            "error_fix_header": "Corrige le code PyQGIS ci-dessous pour résoudre l'erreur.",
            "error_fix_instruction": (
                "Conserve autant que possible le comportement et les attentes demandées à l'origine. "
                "Renvoie UNIQUEMENT du code PyQGIS exécutable et n'oublie pas les imports."
            ),
            "code_to_fix": "Voici le code à corriger",
            "exec_error_title": "Erreur d'exécution",
            "exec_success": "Exécution réussie.",
            "exec_warn_to_debug": "Exécution terminée avec avertissements — ouverture de l'onglet Debug.",
            "warnings_prefix_debug": "Avertissements QGIS pendant l'exécution :",
            "error_to_fix": "Erreur :",
            "llm_request_error": "Erreur de requête IA",
            "llm_backend_error": "Erreur du moteur IA",
            "review_cancelled_kept_debug": "Édition annulée : l'onglet Debug reste ouvert avec le code corrigé en attente.",
            "streaming_not_supported": "Le serveur ne supporte pas le streaming ; retour au mode normal.",
            "request_error_title": "Erreur de requête",
            "request_error_body": "Une erreur est survenue côté modèle : {err}",
            "context_chat": "Contexte envoyé à la prochaine requête",
            "context_last_messages_chat": "(derniers {count} messages)",

            # ═══════════════════════════════════════════════════
            # MODE AGENT — NOUVELLES CLÉS
            # ═══════════════════════════════════════════════════
            "agent_mode": "Mode agent",
            "agent_mode_hint": "Active l'exécution automatique via des outils QGIS natifs (function calling).",
            "agent_max_iterations": "Itérations max :",
            "agent_max_iterations_hint": "Nombre maximum d'étapes agent par requête.",
            "agent_show_steps": "Afficher les étapes en direct",
            "agent_show_steps_hint": "Affiche chaque appel d'outil et son résultat dans le chat.",

            # Étapes affichées dans le chat
            "agent_step_thinking": "Analyse de la demande...",
            "agent_step_intent_detected": "Intentions détectées : {intents}",
            "agent_step_tools_selected": "{count} outils sélectionnés : {names}",
            "agent_step_tool_calling": "Appel de {tool}...",
            "agent_step_tool_success": "✓ {summary}",
            "agent_step_tool_error": "✗ Erreur : {error}",
            "agent_step_iteration": "Étape limite {current}/{max}",
            "agent_step_final": "Synthèse de la réponse...",
            "agent_step_max_iterations": "Nombre maximum d'itérations atteint ({max}). Opération incomplète.",

            # Résumés de tool_result
            "agent_result_layer_created": "Couche '{name}' créée ({count} features)",
            "agent_result_selection": "{selected} features sélectionnées sur {total} dans '{layer}'",
            "agent_result_filter_applied": "Filtre appliqué sur '{layer}' ({count} features visibles)",
            "agent_result_style_applied": "Style appliqué sur '{layer}'",
            "agent_result_visibility_on": "Couche '{layer}' affichée",
            "agent_result_visibility_off": "Couche '{layer}' masquée",
            "agent_result_field_calculated": "Champ '{field}' calculé ({count} features mises à jour)",
            "agent_result_field_added": "Champ '{field}' ajouté à '{layer}'",
            "agent_result_layer_loaded": "Couche '{name}' chargée ({count} features)",
            "agent_result_layer_exported": "Couche '{layer}' exportée vers {path}",
            "agent_result_code_executed": "Code PyQGIS exécuté",
            "agent_result_generic": "{tool} terminé",
            "agent_result_stats": "Statistiques calculées sur '{field}' de '{layer}'",
            "agent_result_project_info": "Projet analysé : {count} couches",
            "agent_result_layer_info": "Infos de '{layer}' récupérées",
            "agent_result_fields_info": "{count} champs récupérés pour '{layer}'",
            "agent_result_features_info": "{returned} features retournées sur {total}",
            "agent_result_zoom": "Zoom effectué sur '{target}'",
            "agent_result_canvas_captured": "Capture d'écran du canvas ({width}×{height} px)",

            # Labels d'étape
            "agent_label_intent": "Analyse",
            "agent_label_tool_call": "Outil",
            "agent_label_tool_result": "Résultat",
            "agent_label_final": "Réponse",

            # Prompts système de l'agent
            "agent_system_prompt": (
                "Tu es un agent QGIS expert intégré dans le plugin QGIS AI Agent. "
                "Tu as accès à des tools pour manipuler le projet SIG ouvert dans QGIS.\n\n"
                "RÈGLES IMPORTANTES :\n"
                "- Exécute les opérations demandées étape par étape.\n"
                "- Après chaque tool_call, analyse le résultat avant de continuer.\n"
                "- Si une opération échoue (success: false), explique pourquoi et propose une alternative.\n"
                "- Si tu dois connaître les champs d'une couche, utilise get_layer_fields en premier.\n"
                "- Utilise run_pyqgis_code UNIQUEMENT si aucun autre tool ne couvre le besoin.\n"
                "- Après avoir appliqué un style, une symbologie, des étiquettes ou tout changement visuel "
                "sur une couche, appelle TOUJOURS capture_map_canvas pour vérifier visuellement le résultat "
                "avant de répondre à l'utilisateur.\n"
                "- Si l'utilisateur pose une question sur ce qui est affiché sur la carte, sa localisation "
                "actuelle, ce qu'il voit, ou l'état visuel du projet, appelle capture_map_canvas en premier "
                "AVANT de répondre — ne demande jamais à l'utilisateur d'envoyer une capture lui-même.\n"
                "- Réponds en français.\n"
                "- Quand toutes les opérations sont terminées, fais un résumé concis de ce qui a été fait."
            ),
            "agent_intent_system": (
                "Tu es un classifieur d'intention pour un assistant QGIS. "
                "Réponds UNIQUEMENT avec du JSON valide, sans texte avant ou après. "
                "Ne jamais expliquer, ne jamais ajouter de commentaires."
            ),
            "agent_intent_user": (
                "Classe cette demande QGIS en JSON.\n\n"
                "Intents disponibles (tu peux en choisir plusieurs) :\n"
                "- \"read\"    : lire des données, afficher infos, statistiques, valeurs d'un champ\n"
                "- \"process\" : géotraitement spatial (buffer, clip, dissolve, intersection, reprojection, jointure spatiale)\n"
                "- \"select\"  : sélectionner ou filtrer des features (par expression ou localisation)\n"
                "- \"style\"   : modifier l'apparence d'une couche (couleur, catégorisation, graduation, visibilité, opacité)\n"
                "- \"edit\"    : modifier des données (ajouter/calculer un champ, charger une couche)\n"
                "- \"export\"  : exporter ou sauvegarder une couche\n"
                "- \"analyse\" : calculs spatiaux, statistiques avancées, vérification qualité\n"
                "- \"view\"    : zoomer, naviguer dans la carte\n\n"
                "Format de réponse :\n"
                "{{\"intents\": [\"intent1\", \"intent2\"], \"layer_names\": [\"nom couche mentionnée\"]}}\n\n"
                "Demande : {prompt}"
            ),

            # Options
            "language": "Langue de réponse :",
            "api_key": "Clé API :",
            "url": "URL de l'API :",
            "test": "Tester l'URL",
            "save": "Enregistrer",
            "cancel": "Annuler",
            "error": "Erreur",
            "success": "Succès",
            "url_required": "Veuillez saisir une URL.",
            "connection_ok": "Connexion à l'API réussie.",
            "connection_failed": "Erreur : {}",
            "verify_before_execute": "Vérifier le code avant d'exécuter",
            "include_project_context": "Inclure le contexte projet",
            "project_context_max_kb": "Taille max (Ko) :",
            "index_project": "Indexer projet",
            "project_indexed": "Projet indexé (couches, champs, CRS…)",
            "export_traces": "Exporter les requêtes (debug)",
            "trace_dir": "Dossier d'export :",
            "browse": "Parcourir…",
            "choose_folder": "Choisir un dossier",
            "trace_dir_required": "Veuillez choisir un dossier d'export pour les traces.",
            "trace_dir_invalid": "Impossible d'utiliser ce dossier : {}",
            "streaming_mode": "Activer le mode streaming (SSE)",
            "streaming_hint": "Affiche la réponse en temps réel si l'API le supporte.",

            # ═══════════════════════════════════════════════════
            # TRAITEMENTS PERSONNALISÉS
            # ═══════════════════════════════════════════════════
            "save_process_btn": "Enregistrer comme traitement",
            "process_browser_tab": "Traitements",
            "process_no_steps": "Aucune étape enregistrée pour ce traitement.",
            "process_saved_ok": "Traitement enregistré avec succès.",
            "process_run_done": "Traitement terminé.",
            "process_run_error": "Erreur pendant l'exécution du traitement.",
            "processes_folder": "Dossier des traitements :",
        },
        "en": {
            "dock_title": "AI Assistant",
            "assistant_tab": "Assistant",
            "debug_tab": "Debug",
            "send": "Send",
            "message_prompt": "Enter your message here...",
            "generate": "Generate Code",
            "execute": "Execute",
            "execute_label": "Code is ready to run",
            "clear": "Clear",
            "history_count": "Last N turns",
            "options": "Options",
            "fix_and_run": "Fix and Execute",
            "error_during_exec": "An error occurred. You can request a correction.",
            "status": "<b>Mode:</b> {} | <b>Model:</b> {} | <b>Tokens used:</b> {}",
            "loading": "Processing request...",
            "no_code": "No code to execute.",
            "correction": "Correction",
            "no_error": "No error detected.",
            "mode": "Mode",
            "model": "Model",
            "token_count": "Tokens used",
            "dialog_title": "AI Assistant",
            "execution": "Execution",
            "review_title": "Review & Run",
            "code_preview": "Code preview (editable before running)",
            "run_now": "Run",
            "system_prompt_chat": (
                "You are a QGIS expert helping a user inside QGIS. "
                "Current version: {qgis_version}. Be clear and concise. "
                "Reply in English."
            ),
            "system_prompt_code": (
                "You are a QGIS expert helping a user inside QGIS. "
                "Current version: {qgis_version}. "
                "Return ONLY executable PyQGIS code (with imports) and no explanations. "
                "Add Python comments in English. "
                "If no output path is specified, write in memory."
            ),
            "project_snapshot_intro": "Here is the user's QGIS project state:",
            "reset": "Reset",
            "reset_confirm": "Reset all plugin settings?\n(This does not delete your QGIS projects.)",
            "reset_done": "Settings reset.",
            "you_prefix": "You",
            "assistant_prefix": "Assistant",
            "warnings": "Warnings",
            "no_warnings": "No warnings detected.",
            "warn_fix_header": "The script executed but produced warnings.",
            "warn_fix_instruction": (
                "Analyze and fix the code to remove these warnings without changing the intended behavior. "
                "Return ONLY executable PyQGIS code and include the imports."
            ),
            "error_fix_header": "Fix the PyQGIS code below to resolve the error.",
            "error_fix_instruction": (
                "Preserve the original intent and expected behavior as much as possible. "
                "Return ONLY executable PyQGIS code and include the imports."
            ),
            "code_to_fix": "Here is the code to fix",
            "exec_error_title": "Execution error",
            "exec_success": "Execution successful.",
            "exec_warn_to_debug": "Execution finished with warnings — opening Debug tab.",
            "warnings_prefix_debug": "QGIS warnings during execution:",
            "error_to_fix": "Error :",
            "llm_request_error": "AI request error",
            "llm_backend_error": "AI backend error",
            "review_cancelled_kept_debug": "Edit canceled: Debug tab remains open with pending corrected code.",
            "streaming_not_supported": "Server does not support streaming; falling back to normal mode.",
            "request_error_title": "Request error",
            "request_error_body": "An error occurred from the model: {err}",
            "context_chat": "Context sent on next request",
            "context_last_messages_chat": "(last {count} messages)",

            # ═══════════════════════════════════════════════════
            # AGENT MODE — NEW KEYS
            # ═══════════════════════════════════════════════════
            "agent_mode": "Agent mode",
            "agent_mode_hint": "Enables automatic execution via native QGIS tools (function calling).",
            "agent_max_iterations": "Max iterations:",
            "agent_max_iterations_hint": "Maximum number of agent steps per request.",
            "agent_show_steps": "Show steps in real time",
            "agent_show_steps_hint": "Display each tool call and its result in the chat.",

            # Steps in chat
            "agent_step_thinking": "Analyzing request...",
            "agent_step_intent_detected": "Detected intents: {intents}",
            "agent_step_tools_selected": "{count} tools selected: {names}",
            "agent_step_tool_calling": "Calling {tool}...",
            "agent_step_tool_success": "✓ {summary}",
            "agent_step_tool_error": "✗ Error: {error}",
            "agent_step_iteration": "Limit step {current}/{max}",
            "agent_step_final": "Finalizing response...",
            "agent_step_max_iterations": "Maximum iterations reached ({max}). Operation incomplete.",

            # Tool result summaries
            "agent_result_layer_created": "Layer '{name}' created ({count} features)",
            "agent_result_selection": "{selected} features selected out of {total} in '{layer}'",
            "agent_result_filter_applied": "Filter applied on '{layer}' ({count} features visible)",
            "agent_result_style_applied": "Style applied on '{layer}'",
            "agent_result_visibility_on": "Layer '{layer}' shown",
            "agent_result_visibility_off": "Layer '{layer}' hidden",
            "agent_result_field_calculated": "Field '{field}' calculated ({count} features updated)",
            "agent_result_field_added": "Field '{field}' added to '{layer}'",
            "agent_result_layer_loaded": "Layer '{name}' loaded ({count} features)",
            "agent_result_layer_exported": "Layer '{layer}' exported to {path}",
            "agent_result_code_executed": "PyQGIS code executed",
            "agent_result_generic": "{tool} completed",
            "agent_result_stats": "Statistics computed on '{field}' of '{layer}'",
            "agent_result_project_info": "Project analyzed: {count} layers",
            "agent_result_layer_info": "Info for '{layer}' retrieved",
            "agent_result_fields_info": "{count} fields retrieved for '{layer}'",
            "agent_result_features_info": "{returned} features returned out of {total}",
            "agent_result_zoom": "Zoomed to '{target}'",
            "agent_result_canvas_captured": "Map canvas captured ({width}×{height} px)",

            # Step labels
            "agent_label_intent": "Analysis",
            "agent_label_tool_call": "Tool",
            "agent_label_tool_result": "Result",
            "agent_label_final": "Answer",

            # Agent prompts
            "agent_system_prompt": (
                "You are a QGIS expert agent embedded in the QGIS AI Agent plugin. "
                "You have access to tools to manipulate the currently open GIS project.\n\n"
                "IMPORTANT RULES:\n"
                "- Execute the requested operations step by step.\n"
                "- After each tool_call, analyze the result before continuing.\n"
                "- If an operation fails (success: false), explain why and propose an alternative.\n"
                "- If you need to know the fields of a layer, use get_layer_fields first.\n"
                "- Use run_pyqgis_code ONLY if no other tool covers the need.\n"
                "- After applying any style, symbology, labels, or visual change to a layer, "
                "ALWAYS call capture_map_canvas to visually verify the result before responding to the user.\n"
                "- If the user asks about what is displayed on the map, their current location, what they see, "
                "or the visual state of the project, call capture_map_canvas FIRST before responding — "
                "never ask the user to send a screenshot themselves.\n"
                "- Reply in English.\n"
                "- When all operations are done, give a concise summary of what was done."
            ),
            "agent_intent_system": (
                "You are an intent classifier for a QGIS assistant. "
                "Respond ONLY with valid JSON, no text before or after. "
                "Never explain, never add comments."
            ),
            "agent_intent_user": (
                "Classify this QGIS request as JSON.\n\n"
                "Available intents (you can pick several):\n"
                "- \"read\"    : read data, show info, statistics, field values\n"
                "- \"process\" : spatial geoprocessing (buffer, clip, dissolve, intersection, reprojection, spatial join)\n"
                "- \"select\"  : select or filter features (by expression or location)\n"
                "- \"style\"   : change a layer's appearance (color, categorization, graduation, visibility, opacity)\n"
                "- \"edit\"    : modify data (add/compute a field, load a layer)\n"
                "- \"export\"  : export or save a layer\n"
                "- \"analyse\" : spatial calculations, advanced statistics, quality check\n"
                "- \"view\"    : zoom, navigate the map\n\n"
                "Response format:\n"
                "{{\"intents\": [\"intent1\", \"intent2\"], \"layer_names\": [\"mentioned layer name\"]}}\n\n"
                "Request: {prompt}"
            ),

            # Options
            "language": "Assistant language:",
            "api_key": "API Key:",
            "url": "API URL:",
            "test": "Test URL",
            "save": "Save",
            "cancel": "Cancel",
            "error": "Error",
            "success": "Success",
            "url_required": "Please enter a URL.",
            "connection_ok": "API connection successful.",
            "connection_failed": "Error: {}",
            "verify_before_execute": "Review code before running",
            "include_project_context": "Include project context",
            "project_context_max_kb": "Max size (KB):",
            "index_project": "Index project",
            "project_indexed": "Project indexed (layers, fields, CRS…)",
            "export_traces": "Export requests (debug)",
            "trace_dir": "Export folder:",
            "browse": "Browse…",
            "choose_folder": "Choose a folder",
            "trace_dir_required": "Please choose an export folder for traces.",
            "trace_dir_invalid": "Cannot use this folder: {}",
            "streaming_mode": "Enable streaming mode (SSE)",
            "streaming_hint": "Render the reply in real time if supported by the API.",

            # ═══════════════════════════════════════════════════
            # CUSTOM PROCESSES
            # ═══════════════════════════════════════════════════
            "save_process_btn": "Save as custom process",
            "process_browser_tab": "Processes",
            "process_no_steps": "No steps were recorded for this run.",
            "process_saved_ok": "Process saved successfully.",
            "process_run_done": "Process completed.",
            "process_run_error": "Error during process execution.",
            "processes_folder": "Processes folder:",
        },
    }
    base = translations["en"]
    cur = translations.get(lang, {})
    return {**base, **cur}
