from __future__ import annotations

import os
import sys


def is_android_runtime() -> bool:
    return bool(
        sys.platform == "android"
        or callable(getattr(sys, "getandroidapilevel", None))
        or os.environ.get("ANDROID_ARGUMENT")
    )
