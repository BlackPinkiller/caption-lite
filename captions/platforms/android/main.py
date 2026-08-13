from __future__ import annotations

import sys

from PySide6.QtGui import QGuiApplication

from captions.platforms.android.controller import AndroidApplication


def main() -> int:
    application = QGuiApplication(sys.argv)
    application.setApplicationName("Captions")
    application.setOrganizationName("Local")
    controller = AndroidApplication(application)
    if not controller.show():
        return 1
    return application.exec()
