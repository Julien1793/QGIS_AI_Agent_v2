# Test bootstrap.
#
# The plugin folder name contains a dash ("QGIS_AI_Agent_v2-master"), which is
# not a valid Python identifier — so it cannot be imported with regular
# `from X import Y` syntax. We use importlib to load it, then alias every
# submodule we need under a clean name `qgis_ai_plugin.*` so test files can
# write `from qgis_ai_plugin.core.agent_loop import AgentLoop`.
#
# We also stub out the QGIS modules (qgis.core, qgis.PyQt.*, processing) with
# MagicMock so plugin code that does `from qgis.core import Qgis` at module
# top-level can be imported in a plain Python venv without QGIS installed.

import importlib
import os
import sys
from unittest.mock import MagicMock

HERE = os.path.dirname(os.path.abspath(__file__))
PLUGIN_DIR = os.path.dirname(HERE)
PLUGIN_PARENT = os.path.dirname(PLUGIN_DIR)
PLUGIN_DIR_NAME = os.path.basename(PLUGIN_DIR)

# Stub QGIS / Qt / processing so module-level imports work without QGIS.
_QGIS_STUB_MODULES = [
    "qgis", "qgis.core", "qgis.gui",
    "qgis.PyQt", "qgis.PyQt.QtCore", "qgis.PyQt.QtWidgets", "qgis.PyQt.QtGui",
    "processing",
]
for _name in _QGIS_STUB_MODULES:
    sys.modules.setdefault(_name, MagicMock())

# Make the plugin importable.
if PLUGIN_PARENT not in sys.path:
    sys.path.insert(0, PLUGIN_PARENT)

# Pre-load the plugin package and alias frequently-used submodules so tests
# can use the clean `qgis_ai_plugin.*` namespace.
_real_pkg = importlib.import_module(PLUGIN_DIR_NAME)
sys.modules.setdefault("qgis_ai_plugin", _real_pkg)

for _sub in [
    "core",
    "core.agent_loop",
    "core.tools_registry",
    "core.tools_handlers",
    "core.conversation_manager",
    "utils",
    "utils.http",
    "utils.translation",
]:
    _mod = importlib.import_module(f"{PLUGIN_DIR_NAME}.{_sub}")
    sys.modules.setdefault(f"qgis_ai_plugin.{_sub}", _mod)
