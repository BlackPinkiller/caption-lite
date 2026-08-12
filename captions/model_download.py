from __future__ import annotations

import shutil
import tarfile
import threading
import urllib.request
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from captions.config import MODEL_NAME, MODEL_URL


class DownloadCancelled(Exception):
    pass


class ModelDownloadWorker(QObject):
    progress = Signal(int, int)
    status = Signal(str)
    completed = Signal()
    cancelled = Signal()
    error = Signal(str)
    stopped = Signal()

    def __init__(
        self,
        destination: Path,
        *,
        model_name: str = MODEL_NAME,
        model_url: str = MODEL_URL,
    ) -> None:
        super().__init__()
        self.destination = destination
        self.model_name = model_name
        self.model_url = model_url
        self._cancel = threading.Event()

    def cancel(self) -> None:
        self._cancel.set()

    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise DownloadCancelled()

    @Slot()
    def run(self) -> None:
        parent = self.destination.parent
        archive = parent / f".{self.model_name}.download"
        staging = parent / f".{self.model_name}.extracting"
        try:
            parent.mkdir(parents=True, exist_ok=True)
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging)
            self._check_cancelled()
            self.status.emit("正在连接下载服务器")
            request = urllib.request.Request(
                self.model_url, headers={"User-Agent": "RealtimeSubtitle/1.0"}
            )
            with urllib.request.urlopen(request, timeout=30) as response:
                total = int(response.headers.get("Content-Length") or 0)
                downloaded = 0
                with archive.open("wb") as output:
                    while True:
                        self._check_cancelled()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(downloaded, total)

            self._check_cancelled()
            self.status.emit("正在解压模型")
            staging.mkdir(parents=True, exist_ok=True)
            with tarfile.open(archive, "r:bz2") as bundle:
                for member in bundle:
                    self._check_cancelled()
                    bundle.extract(member, staging, filter="data")

            source = staging / self.model_name
            required = (
                source / "encoder.int8.onnx",
                source / "decoder.int8.onnx",
                source / "joiner.int8.onnx",
                source / "tokens.txt",
            )
            if not all(path.is_file() for path in required):
                raise RuntimeError("下载包中缺少所需的 Nemotron 模型文件")
            self._check_cancelled()
            if self.destination.exists():
                shutil.copytree(source, self.destination, dirs_exist_ok=True)
            else:
                source.replace(self.destination)
            self.completed.emit()
        except DownloadCancelled:
            self.cancelled.emit()
        except Exception as error:
            self.error.emit(str(error))
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self.stopped.emit()
