import os
from qgis.PyQt.QtCore import Qt
from qgis.PyQt.QtWidgets import QAction
from qgis.PyQt.QtGui import QIcon

from .ui.main_dock import MainDock
from .core.settings_manager import SettingsManager
from .core.conversation_manager import ConversationManager


class MainPlugin:
    def __init__(self, iface):
        self.iface = iface
        self.dock_widget = None
        self.action = None
        self.settings_manager = None
        self.conversation_manager = None

    def initGui(self):
        # Action (menu + toolbar)
        icon_path = os.path.join(os.path.dirname(__file__), "icons", "ai_assistant_icon.png")
        self.action = QAction("AI Assistant", self.iface.mainWindow())
        self.action.setIcon(QIcon(icon_path))
        self.action.triggered.connect(self.toggle_dock)
        self.iface.addPluginToMenu("&AI Assistant", self.action)
        self.iface.addToolBarIcon(self.action)

        # Managers
        self.settings_manager = SettingsManager()
        # Conversation history is stored in the plugin folder; adjust the path here if needed.
        plugin_dir = os.path.dirname(__file__)
        self.conversation_manager = ConversationManager(plugin_dir)

    def toggle_dock(self):
        # Create the dock widget exactly once; subsequent calls toggle its visibility.
        if self.dock_widget is None:
            self.dock_widget = MainDock(
                iface=self.iface,
                settings_manager=self.settings_manager,
                conversation_manager=self.conversation_manager
            )
            self.iface.addDockWidget(Qt.RightDockWidgetArea, self.dock_widget)
            self.dock_widget.show()
            self.dock_widget.raise_()
            self.dock_widget.activateWindow()
            return

        # Toggle visibility without re-adding the dock to avoid duplicates.
        if self.dock_widget.isVisible():
            self.dock_widget.hide()
        else:
            self.dock_widget.show()
            self.dock_widget.raise_()
            self.dock_widget.activateWindow()

    def unload(self):
        # Cleanly remove the dock widget and release the reference.
        if self.dock_widget is not None:
            try:
                self.iface.removeDockWidget(self.dock_widget)
            except Exception:
                pass
            self.dock_widget.deleteLater()
            self.dock_widget = None

        # Reset the restore guard so the dock can be fully re-initialised on next open.
        try:
            from .ui.main_dock import MainDock
            if hasattr(MainDock, "_restore_done"):
                MainDock._restore_done = False
        except Exception:
            pass

        # Remove the menu item and toolbar icon.
        if self.action is not None:
            try:
                self.iface.removePluginMenu("&AI Assistant", self.action)
            except Exception:
                pass
            try:
                self.iface.removeToolBarIcon(self.action)
            except Exception:
                pass
            self.action = None
