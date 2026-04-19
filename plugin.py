from .main_plugin import MainPlugin

def classFactory(iface):
    return MainPlugin(iface)