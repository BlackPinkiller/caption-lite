"""Build a distributable from an explicit allowlist, never the local dist tree."""
from __future__ import annotations

import io
import json
from pathlib import Path
import re
import zipfile

from PyInstaller.archive.readers import CArchiveReader


GOOGLE_KEY = re.compile(rb"AIza[0-9A-Za-z_-]{35}")
RELEASE_FILES = ("RealtimeSubtitle.exe", "config.example.json")
PROJECT_ROOT = Path(__file__).resolve().parents[1]
REPOSITORY_ROOT = PROJECT_ROOT.parent
RELEASE_NOTICES = ("LICENSE", "THIRD_PARTY_NOTICES.md", "resources/LICENSE.silero-vad")


def validate_example(path: Path) -> None:
    config = json.loads(path.read_text(encoding="utf-8-sig"))
    translation = config.get("translation", {})
    keys = [translation.get(name, "") for name in ("google2_api_key", "deepl_api_key")]
    keys.extend(provider.get("api_key", "") for provider in translation.get("llm_providers", []))
    if any(keys):
        raise ValueError("Release example configuration must have empty API keys")


def validate_archive_entry(name: str, data: bytes) -> None:
    basename = name.replace("\\", "/").rsplit("/", 1)[-1].lower()
    if basename in {"config.json", "config.invalid.json", "config.json.tmp"}:
        raise ValueError(f"Personal configuration included in executable: {name}")
    if GOOGLE_KEY.search(data):
        # Report only the file, never the credential itself.
        raise ValueError(f"Embedded Google API key found in executable: {name}")


def validate_executable(path: Path) -> None:
    archive = CArchiveReader(str(path))
    for name, entry in archive.toc.items():
        if entry[-1] == "z":
            modules = archive.open_embedded_archive(name)
            for module in modules.toc:
                validate_archive_entry(module, modules.extract(module, raw=True) or b"")
        else:
            data = archive.extract(name)
            validate_archive_entry(name, data)
            if name.endswith(".zip"):
                with zipfile.ZipFile(io.BytesIO(data)) as nested:
                    for member in nested.namelist():
                        validate_archive_entry(member, nested.read(member))


def package_release(dist: Path) -> Path:
    validate_example(dist / "config.example.json")
    validate_executable(dist / "RealtimeSubtitle.exe")
    package = dist / "RealtimeSubtitle-portable.zip"
    temporary = package.with_suffix(".zip.tmp")
    with zipfile.ZipFile(temporary, "w", compression=zipfile.ZIP_DEFLATED) as output:
        for name in RELEASE_FILES:
            output.write(dist / name, arcname=name)
        for name in RELEASE_NOTICES:
            source_root = PROJECT_ROOT if name.startswith("resources/") else REPOSITORY_ROOT
            output.write(source_root / name, arcname=name)
    temporary.replace(package)
    return package


if __name__ == "__main__":
    root = Path(__file__).resolve().parents[1]
    print(f"Distribution package: {package_release(root / 'dist')}")
