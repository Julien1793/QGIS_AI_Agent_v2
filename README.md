# AI Assistant QGIS — Agent v2

> A QGIS plugin that brings AI-powered natural language control to your GIS workflows.  
> Talk to your maps. Let the agent do the work.

![QGIS Version](https://img.shields.io/badge/QGIS-3.22%2B-green)
![Python](https://img.shields.io/badge/Python-3.x-blue)
![License](https://img.shields.io/badge/license-GPL--2.0-lightgrey)
![Status](https://img.shields.io/badge/status-experimental-orange)

---

## Overview

**AI Assistant QGIS** is a plugin that lets you control QGIS using plain language. Describe what you want to do — buffer that layer, style features by category, clip two datasets, calculate a field — and the AI agent figures out how, selects the right tools, calls them in sequence, and reports back.

It works with **local LLMs** (LM Studio, Ollama) as well as **cloud APIs** (OpenAI, OpenRouter, Fireworks). No internet connection is required if you run a local model.

Two modes are available:

- **Chat mode** — conversational assistant that generates and optionally executes PyQGIS code
- **Agent mode** — autonomous loop that calls a library of ~30 native GIS tools to complete multi-step tasks

---

## Features

### Agent Mode (~30 native GIS tools)

| Category | Capabilities |
|---|---|
| **Read / Inspect** | Layer info, field schemas, feature attributes, statistics, unique values, selected features |
| **Geoprocessing** | Buffer, clip, intersect, dissolve, difference, union, reproject, spatial join, centroid, fix geometries, calculate geometry |
| **Selection** | Select by expression, select by location, set layer filter, zoom to layer/feature |
| **Styling** | Single symbol, categorized, graduated, rule-based, custom colors, opacity, visibility, marker shapes, canvas refresh |
| **Labeling** | Enable/disable labels, font/size/color, buffer, placement, expression-based labels, shadow, background |
| **Data Editing** | Add field, calculate field, load layer, export layer, geometry validation |
| **Fallback** | Run arbitrary PyQGIS code, request additional tool intents, capture map canvas |

### Chat Mode

- Generates PyQGIS code from natural language descriptions
- Optional code review dialog before execution
- Automatic error recovery — the agent reads the error message and tries to fix the code
- Full conversation history sent with each request (configurable depth)

### General

- **Bilingual** interface: French and English
- **Multi-backend LLM support**: LM Studio, Ollama, OpenAI, OpenRouter, Fireworks, any OpenAI-compatible endpoint
- **SSE streaming** with graceful fallback to batch response
- **Project context injection**: current layer names, geometry types, field schemas, and CRS are automatically included in the system prompt
- **Process recording and replay**: save agent runs as `.aiprocess.json` templates with variable substitution
- Real-time step visualization in the chat panel

---

## Requirements

- QGIS **3.22** or later
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

### Remote backend

| Field | Value |
|---|---|
| Mode | Remote |
| API URL | `https://api.openai.com/v1/chat/completions` (or your provider's endpoint) |
| Model | `gpt-4o`, `gpt-4o-mini`, `openai/gpt-4o` (OpenRouter), etc. |
| API Key | Your provider API key |

**Supported providers**: OpenAI, OpenRouter, Fireworks, or any OpenAI-compatible endpoint.

### Other settings

| Setting | Description |
|---|---|
| Language | Interface and system prompt language (French / English) |
| History depth | Number of past conversation turns sent with each request (0–50) |
| Streaming | Enable SSE streaming for real-time token output |
| Project context | Inject a snapshot of the current QGIS project into the system prompt |
| Max context size | Upper bound on the project snapshot size (8–1024 KB) |
| Agent max iterations | Maximum tool-calling rounds per agent run |
| Show agent steps | Display intermediate steps in the chat panel |

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

1. Detect the intent (read, process, style, select, edit…)
2. Select the relevant tools from the library
3. Call them iteratively, passing results between steps
4. Capture the map canvas after visual changes
5. Synthesize a final answer

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
| `ui/main_dock.py` | Central dock widget — chat display, streaming, dialogs |

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

## Contributing

Contributions are welcome. A few notes before opening a pull request:

- There is no test suite or CI pipeline at the moment.
- All code comments must be written in **English**.
- Keep new tools in sync between `tools_registry.py` (schema) and `tools_handlers.py` (implementation).
- New user-facing strings must be added to `utils/translation.py` in **both** `fr` and `en`.
- Prefer editing existing modules over creating new ones for small additions.

Please open an issue first for significant feature additions or architectural changes.

---

## License

This project is licensed under the **GNU General Public License v2.0** — see [LICENSE](LICENSE) for details.

---

## Acknowledgements

Built on top of [QGIS](https://qgis.org/) and the PyQGIS API.  
LLM backend communication follows the [OpenAI Chat Completions API](https://platform.openai.com/docs/api-reference/chat) format, which is also supported by LM Studio, Ollama, OpenRouter, and Fireworks.
