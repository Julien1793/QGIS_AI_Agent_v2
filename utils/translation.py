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
            "project_snapshot_intro": "Voici l'état du projet QGIS de l'utilisateur :",
            "help": "? Aide",
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
            "agent_max_tokens": "Tokens max (réponse) :",
            "agent_max_tokens_hint": "Nombre maximum de tokens générés par appel LLM en mode agent (sortie uniquement, n'affecte pas le contexte).",
            "request_timeout": "Timeout requête (s) :",
            "request_timeout_hint": "Durée maximale d'attente d'une réponse du serveur LLM, en secondes. Augmenter si le modèle est lent sur de longs contextes.",
            "canvas_capture_enabled": "Activer la capture du canvas (vérification visuelle)",
            "canvas_capture_enabled_hint": "Permet à l'agent de capturer le canvas QGIS pour vérifier visuellement les styles et étiquettes.",

            # Étapes affichées dans le chat
            "agent_step_thinking": "Analyse de la demande...",
            "agent_step_intent_detected": "Intentions détectées : {intents}",
            "agent_step_tools_selected": "{count} outils sélectionnés : {names}",
            "agent_step_tool_calling": "Appel de {tool}...",
            "agent_step_tool_success": "{summary}",
            "agent_step_tool_error": "Erreur : {error}",
            "agent_step_iteration": "Étape limite {current}/{max}",
            "agent_step_final": "Synthèse de la réponse...",
            "agent_step_max_iterations": "Nombre maximum d'itérations atteint ({max}). Opération incomplète.",
            "agent_no_new_tools":"aucun nouveau",
            "agent_summary_label": "Résumé de l'IA",

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
            "agent_result_tools_expanded": "Outils ajoutés : {tools}",

            # Labels d'étape
            "agent_label_intent": "Analyse",
            "agent_label_tool_call": "Outil",
            "agent_label_tool_result": "Résultat",
            "agent_label_final": "Réponse",

            # Jauge contexte
            "context_usage_label": "Prompt",
            "agent_context_warning": "⚠ Fenêtre de contexte presque pleine ({used} / {max} tokens)",
            "agent_context_overflow": "⛔ Fenêtre de contexte saturée ({used} / {max} tokens) — la réponse risque d'être tronquée",

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
            "project_context_max_tokens": "Tokens contexte (entrée) :",
            "index_project": "Indexer projet",
            "project_indexed": "Projet indexé (couches, champs, CRS…)",
            "export_traces": "Exporter les requêtes (debug)",
            "trace_dir": "Dossier d'export :",
            "browse": "Parcourir…",
            "choose_folder": "Choisir un dossier",
            "trace_dir_required": "Veuillez choisir un dossier d'export pour les traces.",
            "trace_dir_invalid": "Impossible d'utiliser ce dossier : {}",
            "mode_local": "Local",
            "mode_remote": "Distant",
            "streaming_mode": "Activer le mode streaming (SSE)",
            "streaming_hint": "Affiche la réponse en temps réel si l'API le supporte.",

            # ═══════════════════════════════════════════════════
            # TRAITEMENTS PERSONNALISÉS
            # ═══════════════════════════════════════════════════
            "save_process_btn": "Enregistrer comme traitement",
            "process_browser_tab": "Traitements",
            "process_no_steps": "Aucune étape enregistrée pour ce traitement.",
            "process_saved_ok": "Traitement enregistré avec succès.",
            "process_saved_updated": "Traitement mis à jour :\n{path}",
            "process_run_done": "Traitement terminé.",
            "process_run_error": "Erreur pendant l'exécution du traitement.",
            "processes_folder": "Dossier des traitements :",
            "process_save_dlg_title_new": "Enregistrer comme traitement personnalisé",
            "process_save_dlg_title_edit": "Modifier le traitement personnalisé",
            "process_btn_save": "Enregistrer",
            "process_btn_save_as": "Enregistrer sous…",
            "process_btn_cancel": "Annuler",
            "process_context_run": "Ouvrir / Lancer",
            "process_context_edit": "Éditer",
            "process_context_delete": "Supprimer",
            "process_context_new_folder": "Nouveau sous-dossier…",
            "process_context_delete_folder": "Supprimer le dossier",
            "process_new_folder_title": "Nouveau dossier",
            "process_new_folder_prompt": "Nom du nouveau dossier :",
            "process_delete_folder_confirm": "Supprimer le dossier « {name} » et tout son contenu ?",
            "process_folder_dest":"Choisir le dossier de base des traitements",
            # Onglets
            "process_tab_info": "Informations",
            "process_tab_variables": "Variables",
            "process_tab_steps": "Étapes / Code",
            "process_tab_preview": "Aperçu JSON",
            # Onglet Informations
            "process_name_label": "Nom du traitement :",
            "process_name_placeholder": "Ex : Reprojection + Export",
            "process_desc_label": "Description :",
            "process_desc_placeholder": "Description courte (optionnelle)…",
            "process_folder_label": "Dossier projet :",
            "process_folder_placeholder": "Ex : Vecteur/Géotraitement",
            "process_folder_browse_btn": "Parcourir…",
            "process_folder_info": "Les traitements sont enregistrés dans :",
            "process_browse_dlg_title": "Choisir un dossier de base",
            # Onglet Variables
            "process_vars_note": "Variables détectées automatiquement.\nVous pouvez modifier les labels et les types.",
            "process_vars_col_id": "ID",
            "process_vars_col_label": "Label utilisateur",
            "process_vars_col_type": "Type",
            "process_vars_col_default": "Valeur par défaut",
            "process_vars_add_btn": "+ Ajouter une variable",
            "process_vars_del_btn": "Supprimer la sélection",
            "process_new_variable_label": "Nouvelle variable",
            # Types de variables
            "process_vartype_layer": "Couche",
            "process_vartype_field": "Champ",
            "process_vartype_file": "Fichier",
            "process_vartype_crs": "SCR",
            "process_vartype_value": "Valeur",
            "process_vartype_code": "Code PyQGIS",
            # Onglet Étapes
            "process_steps_note": "Étapes enregistrées. Utilisez × pour supprimer une étape. Pour les blocs de code PyQGIS, vous pouvez éditer le code directement (il remplacera la valeur par défaut de la variable).",
            "process_step_header": "Étape {num}",
            "process_step_delete_tooltip": "Supprimer cette étape",
            "process_step_code_label": "Code PyQGIS (éditable) :",
            # Messages de sauvegarde / erreur
            "process_saved_title": "Enregistré",
            "process_saved_new": "Traitement enregistré :\n{path}",
            "process_error_title": "Erreur",
            "process_error_save": "Impossible d'enregistrer :\n{error}",
            "process_missing_name_title": "Nom manquant",
            "process_missing_name_msg": "Veuillez saisir un nom pour le traitement.",
            "process_fallback_name": "Sans nom",
            "process_browser_header": "Traitements personnalisés",
            "process_refresh_tooltip": "Actualiser la liste",
            "process_change_folder_tooltip": "Changer le dossier de base",
            "process_base_folder_label": "Dossier : {path}",
            "process_none_saved": "Aucun traitement enregistré",
            "process_load_error": "Impossible de charger le traitement :\n{error}",
            "process_delete_confirm_msg": "Supprimer le traitement « {name} » ?\n{path}",
            "process_delete_error": "Impossible de supprimer :\n{error}",

            # Windows CA bundle
            "use_windows_ca_bundle": "Utiliser les certificats Windows (CA bundle)",
            "use_windows_ca_bundle_hint": "Exporte les certificats racine Windows et les utilise pour les requêtes HTTPS. Utile pour les LLM hébergés sur un réseau interne avec des certificats d'entreprise.",
            "ca_bundle_cert_encoding": "Encodage des certificats :",
            "ca_bundle_cert_encoding_hint": "Format des certificats à extraire du store Windows.",
            "ca_bundle_refreshed": "CA bundle mis à jour ({count} certificats exportés).",
            "ca_bundle_error": "Erreur lors de la mise à jour du CA bundle : {}",
            "ca_bundle_encoding_empty": "Le champ d'encodage des certificats est vide. Veuillez le renseigner avant d'activer l'option.",
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
                "Always reply in the same language the user is writing in."
            ),
            "system_prompt_code": (
                "You are a QGIS expert helping a user inside QGIS. "
                "Current version: {qgis_version}. "
                "Return ONLY executable PyQGIS code (with imports) and no explanations. "
                "Add Python comments in English. "
                "If no output path is specified, write in memory."
            ),
            "project_snapshot_intro": "Here is the user's QGIS project state:",
            "help": "? Help",
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
            "agent_max_tokens": "Max tokens (response):",
            "agent_max_tokens_hint": "Maximum tokens generated per LLM call in agent mode (output only, does not affect context).",
            "request_timeout": "Request timeout (s):",
            "request_timeout_hint": "Maximum wait time for an LLM server response, in seconds. Increase if the model is slow on long contexts.",
            "canvas_capture_enabled": "Enable canvas capture (visual verification)",
            "canvas_capture_enabled_hint": "Allows the agent to capture the QGIS canvas to visually verify styles and labels.",

            # Steps in chat
            "agent_step_thinking": "Analyzing request...",
            "agent_step_intent_detected": "Detected intents: {intents}",
            "agent_step_tools_selected": "{count} tools selected: {names}",
            "agent_step_tool_calling": "Calling {tool}...",
            "agent_step_tool_success": "{summary}",
            "agent_step_tool_error": "Error: {error}",
            "agent_step_iteration": "Limit step {current}/{max}",
            "agent_step_final": "Finalizing response...",
            "agent_step_max_iterations": "Maximum iterations reached ({max}). Operation incomplete.",
            "agent_no_new_tools":"no new tools",
            "agent_summary_label": "AI Summary",

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
            "agent_vision_screenshot_intro": "Here is the screenshot of the QGIS canvas after the operation:",
            "agent_result_tools_expanded": "Tools added: {tools}",

            # Step labels
            "agent_label_intent": "Analysis",
            "agent_label_tool_call": "Tool",
            "agent_label_tool_result": "Result",
            "agent_label_final": "Answer",

            # Context gauge
            "context_usage_label": "Prompt",
            "agent_context_warning": "⚠ Context window filling up ({used} / {max} tokens)",
            "agent_context_overflow": "⛔ Context window nearly full ({used} / {max} tokens) — response may be truncated",

            # Agent prompts
            "agent_system_prompt": (
                "You are a QGIS expert agent embedded in the QGIS AI Agent plugin. "
                "You have access to tools to manipulate the currently open GIS project.\n\n"
                "IMPORTANT RULES:\n"
                "- Execute the requested operations step by step.\n"
                "- After each tool_call, analyze the result before continuing.\n"
                "- If an operation fails (success: false), explain why and propose an alternative.\n"
                "- If you need to know the fields of a layer, use get_layer_fields first.\n"
                "- CRS AND DISTANCE UNITS: Before any distance-based operation (buffer, offset, distance matrix...), "
                "check the layer CRS with get_layer_info. If 'is_geographic' is true (map_units: degrees, e.g. EPSG:4326), "
                "reproject the layer to a metric CRS first (use an appropriate UTM zone or local projection). "
                "Never apply metric distances to a geographic CRS — the result will be silently wrong.\n"
                "- Use run_pyqgis_code ONLY if no other tool covers the need.\n"
                "- When using run_pyqgis_code, use print() to output verification results — "
                "all printed output is captured and returned to you in the 'print_output' field. "
                "Use this to confirm real success: check counts, values, or state rather than trusting the absence of an error.\n"
                "  STRICT RULE — print() is FORBIDDEN inside any loop (for, while). "
                "A loop over features can iterate thousands of times and flood the result. "
                "Instead: accumulate data in a variable, then print a single summary AFTER the loop. "
                "WRONG: `for f in layer.getFeatures(): print(f['name'])` "
                "RIGHT: `names = [f['name'] for f in layer.getFeatures()]; print(f'{len(names)} features: {names[:5]}')`\n"
                "- Never call iface.messageBar() inside run_pyqgis_code: the agent loop handles user communication.\n"
                "- Always reply in the same language the user is writing in.\n"
                "- When all operations are done, give a concise summary of what was done."
            ),
            "agent_system_prompt_canvas_rules": (
                "- After applying any style, symbology, labels, or visual change to a layer, "
                "ALWAYS call capture_map_canvas to visually verify the result before responding to the user.\n"
                "- If the user asks about what is displayed on the map, their current location, what they see, "
                "or the visual state of the project, call capture_map_canvas FIRST before responding — "
                "never ask the user to send a screenshot themselves."
            ),
            "agent_intent_system": (
                "You are an intent classifier for a QGIS assistant. "
                "Respond ONLY with valid JSON, no text before or after. "
                "Never explain, never add comments."
            ),
            "agent_intent_user": (
                "Classify this QGIS request as JSON.\n\n"
                "Available intents (pick only the ones needed):\n"
                "- \"chat\"    : general conversation, GIS questions, explanations — no specific QGIS operation needed\n"
                "- \"read\"    : inspect layers, list fields, browse features, get layer extent or CRS\n"
                "- \"stats\"   : compute statistics — min/max/mean, frequency tables, percentiles, correlation, geometry validity\n"
                "- \"process\" : geometry operations producing a new layer (buffer, clip, dissolve, intersection, difference, union, reproject, centroids, fix geometries)\n"
                "- \"join\"    : combine data from multiple layers (spatial join, attribute join, count points in polygon, merge layers)\n"
                "- \"select\"  : select or filter features (by expression, by location, extract to new layer, set filter, clear/invert selection)\n"
                "- \"style\"   : set layer renderer / classification (single symbol, categorized, graduated, proportional, rule-based) "
                "AND adjust symbol appearance (marker shape, size, stroke, opacity, blending mode)\n"
                "- \"label\"   : add, remove or configure labels (text, font, buffer, placement, expression, shadow, background, callout)\n"
                "- \"field\"   : add, delete, rename or calculate a field; calculate geometry attributes\n"
                "- \"layer\"   : load, remove, rename a layer in the project, or export/save a layer to a file\n"
                "- \"view\"    : zoom, navigate the map, show/hide layers, set scale visibility\n"
                "- \"raster\"  : raster-specific operations (info, statistics, pseudocolor/grayscale style)\n\n"
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
            "project_context_max_tokens": "Context tokens (input):",
            "index_project": "Index project",
            "project_indexed": "Project indexed (layers, fields, CRS…)",
            "export_traces": "Export requests (debug)",
            "trace_dir": "Export folder:",
            "browse": "Browse…",
            "choose_folder": "Choose a folder",
            "trace_dir_required": "Please choose an export folder for traces.",
            "trace_dir_invalid": "Cannot use this folder: {}",
            "mode_local": "Local",
            "mode_remote": "Remote",
            "streaming_mode": "Enable streaming mode (SSE)",
            "streaming_hint": "Render the reply in real time if supported by the API.",

            # ═══════════════════════════════════════════════════
            # CUSTOM PROCESSES
            # ═══════════════════════════════════════════════════
            "save_process_btn": "Save as custom process",
            "process_browser_tab": "Processes",
            "process_no_steps": "No steps were recorded for this run.",
            "process_saved_ok": "Process saved successfully.",
            "process_saved_updated": "Process updated:\n{path}",
            "process_run_done": "Process completed.",
            "process_run_error": "Error during process execution.",
            "processes_folder": "Processes folder:",
            "process_save_dlg_title_new": "Save as custom process",
            "process_save_dlg_title_edit": "Edit custom process",
            "process_btn_save": "Save",
            "process_btn_save_as": "Save as…",
            "process_btn_cancel": "Cancel",
            "process_context_run": "Open / Run",
            "process_context_edit": "Edit",
            "process_context_delete": "Delete",
            "process_context_new_folder": "New subfolder…",
            "process_context_delete_folder": "Delete folder",
            "process_new_folder_title": "New folder",
            "process_new_folder_prompt": "New folder name:",
            "process_delete_folder_confirm": "Delete folder \"{name}\" and all its contents?",
            "process_folder_dest":"Choose the base folder for the process",
            # Tabs
            "process_tab_info": "Information",
            "process_tab_variables": "Variables",
            "process_tab_steps": "Steps / Code",
            "process_tab_preview": "JSON Preview",
            # Information tab
            "process_name_label": "Process name:",
            "process_name_placeholder": "E.g.: Reprojection + Export",
            "process_desc_label": "Description:",
            "process_desc_placeholder": "Short description (optional)…",
            "process_folder_label": "Project folder:",
            "process_folder_placeholder": "E.g.: Vector/Geoprocessing",
            "process_folder_browse_btn": "Browse…",
            "process_folder_info": "Processes are saved in:",
            "process_browse_dlg_title": "Choose base folder",
            # Variables tab
            "process_vars_note": "Variables detected automatically.\nYou can edit labels and types.",
            "process_vars_col_id": "ID",
            "process_vars_col_label": "User label",
            "process_vars_col_type": "Type",
            "process_vars_col_default": "Default value",
            "process_vars_add_btn": "+ Add variable",
            "process_vars_del_btn": "Delete selection",
            "process_new_variable_label": "New variable",
            # Variable types
            "process_vartype_layer": "Layer",
            "process_vartype_field": "Field",
            "process_vartype_file": "File",
            "process_vartype_crs": "CRS",
            "process_vartype_value": "Value",
            "process_vartype_code": "PyQGIS Code",
            # Steps tab
            "process_steps_note": "Recorded steps. Use × to delete a step. For PyQGIS code blocks, you can edit the code directly (it will replace the variable's default value).",
            "process_step_header": "Step {num}",
            "process_step_delete_tooltip": "Delete this step",
            "process_step_code_label": "PyQGIS code (editable):",
            # Save / error messages
            "process_saved_title": "Saved",
            "process_saved_new": "Process saved:\n{path}",
            "process_error_title": "Error",
            "process_error_save": "Could not save:\n{error}",
            "process_missing_name_title": "Missing name",
            "process_missing_name_msg": "Please enter a name for the process.",
            "process_fallback_name": "Untitled",
            "process_browser_header": "Custom processes",
            "process_refresh_tooltip": "Refresh list",
            "process_change_folder_tooltip": "Change base folder",
            "process_base_folder_label": "Folder: {path}",
            "process_none_saved": "No saved processes",
            "process_load_error": "Could not load the process:\n{error}",
            "process_delete_confirm_msg": "Delete the process \"{name}\"?\n{path}",
            "process_delete_error": "Could not delete:\n{error}",

            # Windows CA bundle
            "use_windows_ca_bundle": "Use Windows certificates (CA bundle)",
            "use_windows_ca_bundle_hint": "Exports Windows root certificates and uses them for HTTPS requests. Useful for on-premise LLMs with corporate certificates.",
            "ca_bundle_cert_encoding": "Certificate encoding:",
            "ca_bundle_cert_encoding_hint": "Format of certificates to extract from the Windows store.",
            "ca_bundle_refreshed": "CA bundle updated ({count} certificates exported).",
            "ca_bundle_error": "Error updating CA bundle: {}",
            "ca_bundle_encoding_empty": "The certificate encoding field is empty. Please fill it in before enabling this option.",
        },
    }
    base = translations["en"]
    cur = translations.get(lang, {})
    return {**base, **cur}
