def classFactory(iface):
    from .plugin import classFactory as realFactory
    return realFactory(iface)