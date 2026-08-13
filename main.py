from __future__ import annotations

import multiprocessing
import os
import sys
import tempfile
from pathlib import Path

from PySide6.QtCore import QLockFile, QTimer, Qt
from PySide6.QtGui import QFont
from PySide6.QtWidgets import QApplication


def desktop_main() -> int:
    multiprocessing.freeze_support()
    app = QApplication(sys.argv)
    # SoundCard initializes COM while captions.app is imported. Qt must create
    # the GUI thread's STA apartment first, otherwise QWindowsContext reports
    # RPC_E_CHANGED_MODE during QApplication startup.
    from captions.app import CaptionApplication

    instance_lock = QLockFile(
        str(Path(tempfile.gettempdir()) / "RealtimeSubtitle.instance.lock")
    )
    instance_lock.setStaleLockTime(0)
    if not instance_lock.tryLock(0):
        return 0
    app.setApplicationName("实时字幕")
    app.setOrganizationName("Local")
    app.setQuitOnLastWindowClosed(False)
    app.setFont(QFont("Microsoft YaHei UI", 10))
    app.setAttribute(Qt.ApplicationAttribute.AA_CompressHighFrequencyEvents)
    controller = CaptionApplication(app)
    controller.show()
    test_exit_ms = int(os.environ.get("CAPTIONS_TEST_EXIT_MS", "0"))
    if test_exit_ms > 0:
        QTimer.singleShot(test_exit_ms, controller.quit)
    exit_code = app.exec()
    instance_lock.unlock()
    # ThreadPoolExecutor and native ASR libraries may keep non-Qt threads alive
    # after QApplication exits. At this point configuration is saved and all
    # cooperative shutdown work has completed (or the quit watchdog expired),
    # so do not allow an orphaned Python process to survive.
    os._exit(exit_code)


def main() -> int:
    return desktop_main()


if __name__ == "__main__":
    raise SystemExit(main())
