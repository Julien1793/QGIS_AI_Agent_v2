# AI Assistant QGIS — Agent v2

> A QGIS plugin that brings AI-powered natural language control to your GIS workflows.  
> Talk to your maps. Let the agent do the work.

![QGIS Version](https://img.shields.io/badge/QGIS-3.44%2B-green)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![License](https://img.shields.io/badge/license-GPL--2.0-lightgrey)
![Status](https://img.shields.io/badge/status-experimental-orange)

---

## Overview

**AI Assistant QGIS** is a plugin that lets you control QGIS using plain language. Describe what you want to do — buffer that layer, style features by category, clip two datasets, calculate a field — and the AI agent figures out how, selects the right tools, calls them in sequence, and reports back.

It works with **local LLMs** (LM Studio, Ollama), **cloud APIs** (OpenAI, OpenRouter, Fireworks), and **on-premise LLM servers** (any OpenAI-compatible endpoint). No internet connection is required if you run a local or internal model.

Two modes are available:

- **Chat mode** — conversational assistant that generates and optionally executes PyQGIS code
- **Agent mode** — autonomous loop that calls a library of 75 native GIS tools to complete multi-step tasks
---

## Features

### Agent Mode (75 native GIS tools)

| Intent | Tools |
|---|---|
| **read** | `get_project_info`, `get_layer_info`, `get_layer_fields`, `get_layer_features`, `get_layer_statistics`, `get_unique_values`, `get_selected_features`, `get_layer_extent`, `get_layer_style`, `get_label_settings` |
| **stats** | `get_field_value_counts`, `get_statistics_by_group`, `get_field_percentiles`, `get_field_correlation`, `check_geometry_validity` |
| **process** | `buffer`, `clip`, `intersection`, `dissolve`, `difference`, `union`, `reproject_layer`, `centroids`, `fix_geometries`, `calculate_geometry`, `list_algorithms`, `get_algorithm_info`, `run_processing_algorithm` |
| **join** | `join_by_location`, `join_by_field`, `count_points_in_polygon`, `merge_layers`, `extract_by_expression`, `extract_by_location` |
| **select** | `select_by_expression`, `select_by_location`, `set_layer_filter`, `clear_selection`, `invert_selection` |
| **style** | `set_single_symbol`, `set_categorized_style`, `set_graduated_style`, `set_proportional_symbols`, `set_rule_based_style`, `set_custom_categorized_colors`, `set_symbol_properties`, `set_marker_shape`, `set_layer_opacity`, `set_layer_blending_mode`, `get_layer_style` |
| **label** | `get_label_settings`, `enable_labels`, `disable_labels`, `set_label_text_format`, `set_label_buffer`, `set_label_placement`, `set_label_expression`, `set_label_shadow`, `set_label_background`, `set_label_callout` |
| **field** | `add_field`, `delete_field`, `rename_field`, `calculate_field`, `calculate_geometry` |
| **layer** | `load_layer`, `rename_layer`, `remove_layer`, `export_layer`, `set_layer_visibility`, `set_scale_based_visibility` |
| **view** | `zoom_to_layer`, `zoom_to_feature`, `refresh_canvas` |
| **raster** | `get_raster_info`, `get_raster_statistics`, `set_raster_style` |
| **always** | `capture_map_canvas`, `request_additional_tools` |
| **fallback** | `run_pyqgis_code` |

### Chat Mode

- Generates PyQGIS code from natural language descriptions
- Optional code review dialog before execution
- Automatic error recovery — the agent reads the error message and tries to fix the code
- Full conversation history sent with each request (configurable depth)

### General

- **Bilingual** interface: French and English
- **Multi-backend LLM support**: LM Studio, Ollama, OpenAI, OpenRouter, Fireworks, on-premise LLM servers, any OpenAI-compatible endpoint
- **SSE streaming** with graceful fallback to batch response
- **Project context injection**: current layer names, geometry types, and CRS are automatically included per request; field schemas are fetched on demand via `get_layer_fields`
- **Prompt token gauge**: live status bar indicator showing tokens consumed by the current request vs. the configured context window limit
- **Process recording and replay**: save agent runs as `.aiprocess.json` templates with variable substitution
- Real-time step visualization in the chat panel

---

## Requirements

- QGIS **3.44** or later
- Python **3.x** (bundled with QGIS)
- Access to an LLM via a local server or a cloud API key

---

## Installation

### From source

1. Clone or download this repository.

2. Copy the plugin folder to your QGIS plugins directory:

   **Windows**
   ```
   %APPDATA%\QGIS\QGIS3\profiles\default\python\plugins\
   ```

   **Linux / macOS**
   ```
   ~/.local/share/QGIS/QGIS3/profiles/default/python/plugins/
   ```

3. In QGIS, open **Plugins → Manage and Install Plugins**, find **AI Assistant QGIS**, and enable it.

4. The plugin adds a toolbar button and a **Plugins → AI Assistant** menu entry that opens the side panel.

### Hot-reload during development

After editing any source file, reload without restarting QGIS:

```python
iface.reloadPlugin('QGIS_AI_Agent_v2-master')
```

---

## Configuration

Open **Options** from the plugin panel to configure the connection.

### Local backend (no API key required)

| Field | Value |
|---|---|
| Mode | Local |
| API URL | `http://localhost:1234/v1/chat/completions` (LM Studio) or `http://localhost:11434/v1/chat/completions` (Ollama) |
| Model | The model name as reported by your local server |
| API Key | Leave empty |

**Recommended models for GIS tasks**: any instruction-tuned model with ≥ 7B parameters. Models with good tool-calling support (e.g. Mistral, Qwen, LLaMA 3.1) work best in agent mode.

**On-premise / internal servers**: set the API URL to your internal endpoint and leave the API key empty or set it to your internal token.

### Remote backend

| Field | Value |
|---|---|
| Mode | Remote |
| API URL | `https://api.openai.com/v1/chat/completions` (or your provider's endpoint) |
| Model | `gpt-4o`, `gpt-4o-mini`, `openai/gpt-4o` (OpenRouter), etc. |
| API Key | Your provider API key |

**Supported providers**: OpenAI, OpenRouter, Fireworks, or any OpenAI-compatible endpoint.

### Tab: LLM

| Setting | Description |
|---|---|
| Enable streaming mode (SSE) | Stream tokens in real time as the model generates them (recommended) |
| Last N turns | Number of past conversation turns sent with each request (0 = no history) |
| Max tokens (response) | Maximum tokens the model can generate per response (`max_tokens` in the API request) |
| Request timeout (s) | Maximum wait time for an LLM server response before the request is considered failed (30–600 s, default 300 s) |
| Include project context | Inject a snapshot of the current QGIS project (layer names, geometry types, CRS) into each request |
| Context tokens (input) | Context window size of your model — used as the denominator in the prompt token gauge |

### Tab: Agent

| Setting | Description |
|---|---|
| Agent mode | Enable the autonomous tool-calling agent (disabling switches to chat mode) |
| Max iterations | Maximum tool-calling rounds per agent run before the loop is forced to stop |
| Show steps in real time | Display each tool call and its result as intermediate steps in the chat panel |
| Enable canvas capture (visual verification) | Allow the agent to screenshot the QGIS canvas to verify visual results after style or symbol changes |

### Tab: Interface

| Setting | Description |
|---|---|
| Assistant language | Interface and system prompt language (French / English) |
| Review code before running | Show a dialog to inspect and edit generated code before it runs (chat mode only) |
| Export requests (debug) | Write each API request and response to a JSON file for debugging |
| Export folder | Folder where debug trace files are saved |

### Tab: Connexion — Advanced

| Setting | Description |
|---|---|
| Use Windows certificates (CA bundle) | Use a custom certificate authority bundle for HTTPS (on-premise deployments with self-signed certificates) |

---

## Usage

### Chat mode

Type a request in the input box and press **Send** (or `Ctrl+Enter`).

The assistant generates PyQGIS code. You can:
- **Execute** it directly (with or without a review dialog, depending on your preference)
- **Copy** the code to the Python console
- Let the agent **auto-fix** errors if execution fails

Example prompts:
```
Add a new field "area_ha" to the parcels layer and calculate the area in hectares.
Load the file /data/communes.geojson and reproject it to EPSG:2154.
Show me the 5 largest features in the buildings layer.
```

### Agent mode

Switch to **Agent** mode in the panel. Describe your task in plain language — the agent will:

1. Classify the intent using a lightweight LLM pre-call (12 intent categories below)
2. Select only the relevant tools for those intents (max ~10 tools per call)
3. Call them iteratively, passing results between steps
4. Capture the map canvas after visual changes
5. Synthesize a final answer

| Intent | Description |
|---|---|
| `chat` | General conversation, GIS questions, explanations — no specific QGIS operation needed |
| `read` | Inspect layers, list fields, browse features, get layer extent or CRS |
| `stats` | Compute statistics — min/max/mean, frequency tables, percentiles, correlation, geometry validity |
| `process` | Geometry operations producing a new layer (buffer, clip, dissolve, intersection, difference, union, reproject, centroids, fix geometries) |
| `join` | Combine data from multiple layers (spatial join, attribute join, count points in polygon, merge layers) |
| `select` | Select or filter features (by expression, by location, extract to new layer, set filter, clear/invert selection) |
| `style` | Set layer renderer / classification (single symbol, categorized, graduated, proportional, rule-based) and adjust symbol appearance (marker shape, size, stroke, opacity, blending mode) |
| `label` | Add, remove or configure labels (text, font, buffer, placement, expression, shadow, background, callout) |
| `field` | Add, delete, rename or calculate a field; calculate geometry attributes |
| `layer` | Load, remove, rename a layer in the project, or export/save a layer to a file |
| `view` | Zoom, navigate the map, show/hide layers, set scale visibility |
| `raster` | Raster-specific operations (info, statistics, pseudocolor/grayscale style) |

Pure conversational requests (`chat` intent) skip the project snapshot injection entirely to avoid unnecessary token usage.

Example prompts:
```
Buffer the roads layer by 50 meters, clip it to the study_area boundary,
and style the result with a red dashed line.

Select all buildings with an area greater than 500 m², zoom to the selection,
and export it as a GeoPackage to C:/output/large_buildings.gpkg.

Apply a graduated style to the communes layer based on the population field,
using 5 classes and a blue-to-red color ramp. Add labels showing the commune name.
```

### Process recording and replay

After a successful agent run, use **Save as process** to export the steps as an `.aiprocess.json` file. Layer names and field names detected during the run become named variables.

Saved processes appear in the **Process Browser** tab and can be replayed against different data by substituting variables at run time.

---

## Architecture

```
plugin.py → classFactory(iface) → MainPlugin
  MainPlugin.initGui()      → toolbar action
  MainPlugin.toggle_dock()  → MainDockWidget (ui/main_dock.py)
```

```
Chat mode:   user message → AIAgent.chat()    → LLM → optional code execution
Agent mode:  user message → AgentLoop.run()   → intent detection
                                              → tool selection
                                              → iterative LLM + tool calls
                                              → final synthesis
```

### Core modules

| Module | Role |
|---|---|
| `core/agent.py` | Raw LLM calls — streaming SSE, multi-backend, tracing |
| `core/agent_loop.py` | Agentic orchestration: intent → tools → loop → synthesis |
| `core/tools_registry.py` | Tool schemas (name, description, parameters) |
| `core/tools_handlers.py` | Tool implementations — actual PyQGIS/processing calls |
| `core/executor.py` | Executes PyQGIS code strings, captures warnings/errors |
| `core/conversation_manager.py` | JSON-backed conversation history |
| `core/settings_manager.py` | QSettings wrapper for all plugin config |
| `core/project_indexer.py` | Serializes the current QGIS project as LLM context |
| `core/process_recorder.py` | Records agent runs for saving as reusable processes |
| `core/process_runner.py` | Replays `.aiprocess.json` files with variable substitution |
| `utils/http.py` | Centralized HTTP retry utility — exponential backoff on 429/503 and network errors |
| `ui/main_dock.py` | Central dock widget — chat display, streaming, dialogs |
| `ui/workers.py` | Qt worker classes (`ChatWorker`, `AgentWorker`, `StreamWorker`) — run LLM calls off the main thread |
| `ui/markdown_renderer.py` | Markdown-to-HTML renderer for chat messages (no external dependencies) |

### Adding a tool

1. Add the JSON schema (name, description, parameters) to `core/tools_registry.py`.
2. Add the Python implementation to `core/tools_handlers.py`.
3. Register the handler in the dispatch dict inside `tools_handlers.py`.

Tools are automatically available in agent mode once registered.

---

## Known Limitations

- **Experimental status**: the plugin is under active development. APIs and file formats may change.
- **Model quality matters**: agent mode heavily depends on the model's ability to follow tool-calling instructions. Smaller or quantized models may struggle with complex multi-step tasks.
- **No undo for tool operations**: geoprocessing tools create new layers but some edit operations (field calculations) modify existing data in place. Use QGIS edit buffers or backup your data.
- **PyQGIS code execution** in chat mode runs arbitrary code in the QGIS Python environment. Review code before executing it on production data.

---

## License

This project is licensed under the **GNU General Public License v2.0** — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

Built on top of [QGIS](https://qgis.org/) and the PyQGIS API.  
LLM backend communication follows the [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat) format, which is also supported by LM Studio, Ollama, OpenRouter, and Fireworks.
