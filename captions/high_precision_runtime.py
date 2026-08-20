from __future__ import annotations

import hashlib
import json
import os
import shutil
import subprocess
import threading
import time
import urllib.request
import zipfile
from dataclasses import dataclass
from pathlib import Path

from PySide6.QtCore import QObject, Signal, Slot

from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.ports.app_paths import AppPaths


UV_VERSION = "0.10.12"
UV_URL = (
    "https://releases.astral.sh/github/uv/releases/download/"
    f"{UV_VERSION}/uv-x86_64-pc-windows-msvc.zip"
)
UV_SIZE = 22_407_450
UV_SHA256 = "4c1d55501869b3330d4aabf45ad6024ce2367e0f3af83344395702d272c22e88"
MODEL_ID = "nvidia/nemotron-speech-streaming-en-0.6b"
MODEL_REVISION = "ebe59e5a817142986528bbbee5dba8db7b38ed50"
RUNTIME_REVISION = "nemotron-fp32-v1"


@dataclass(frozen=True)
class RuntimeFile:
    name: str
    size: int
    sha256: str


MODEL_FILES = (
    RuntimeFile(
        "config.json",
        1_284,
        "dffe850bc79ad2b0f8117804502b24d2c4a445aafbed4c1e40f8d78e0cb44065",
    ),
    RuntimeFile(
        "generation_config.json",
        192,
        "6ce531b39df8046cc8dbbe29dc64458b72972011d4717e160e6efb2c1af198d1",
    ),
    RuntimeFile(
        "model.safetensors",
        2_472_413_604,
        "bddd8a7300826efd19cf7e01f1c7db8402bed6786fc4c7739632894f69c71473",
    ),
    RuntimeFile(
        "processor_config.json",
        525,
        "cf35efc9abdd0963db7e96967f8a91d9c8243803b9f6bbd900aa936ee3ce42f3",
    ),
    RuntimeFile(
        "tokenizer_config.json",
        270,
        "0665bee664daf39a155e5ee013bb1d885c58b4901994abc07b9a6b3904cce132",
    ),
    RuntimeFile(
        "tokenizer.json",
        400_216,
        "60dc0361763fa3cd62df60f34fca3e61134676a939967853931db5f3869b2db2",
    ),
)


class InstallCancelled(Exception):
    pass


def high_precision_runtime_dir(
    *, app_paths: AppPaths = DEFAULT_APP_PATHS
) -> Path:
    return app_paths.application_dir() / "runtime" / "nemotron-fp32"


def high_precision_model_dir(
    *, app_paths: AppPaths = DEFAULT_APP_PATHS
) -> Path:
    return high_precision_runtime_dir(app_paths=app_paths) / "model"


def high_precision_site_packages(
    *, app_paths: AppPaths = DEFAULT_APP_PATHS
) -> Path:
    return (
        high_precision_runtime_dir(app_paths=app_paths)
        / ".venv"
        / "Lib"
        / "site-packages"
    )


def high_precision_runtime_ready(
    *, app_paths: AppPaths = DEFAULT_APP_PATHS
) -> bool:
    root = high_precision_runtime_dir(app_paths=app_paths)
    marker = root / ".ready"
    try:
        metadata = json.loads(marker.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return False
    if metadata.get("revision") != RUNTIME_REVISION:
        return False
    if not (root / ".venv" / "Scripts" / "python.exe").is_file():
        return False
    model = root / "model"
    return all(
        (model / item.name).is_file()
        and (model / item.name).stat().st_size == item.size
        for item in MODEL_FILES
    )


class HighPrecisionInstallWorker(QObject):
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
        require_nvidia: bool = True,
    ) -> None:
        super().__init__()
        self.destination = destination
        self.require_nvidia = require_nvidia
        self._cancel = threading.Event()
        self._response_lock = threading.Lock()
        self._response = None
        self._process_lock = threading.Lock()
        self._process: subprocess.Popen | None = None

    def cancel(self) -> None:
        self._cancel.set()
        with self._response_lock:
            response = self._response
        if response is not None:
            try:
                response.close()
            except Exception:
                pass
        with self._process_lock:
            process = self._process
        if process is not None:
            try:
                process.terminate()
            except Exception:
                pass

    def _check_cancelled(self) -> None:
        if self._cancel.is_set():
            raise InstallCancelled()

    @Slot()
    def run(self) -> None:
        parent = self.destination.parent
        staging = parent / f".{self.destination.name}.installing"
        archive = parent / f".{self.destination.name}.uv.zip"
        backup = parent / f".{self.destination.name}.previous-{os.getpid()}"
        try:
            self._check_platform()
            parent.mkdir(parents=True, exist_ok=True)
            free = shutil.disk_usage(parent).free
            if free < 8 * 1024**3:
                raise RuntimeError("高精度组件需要至少 8 GB 可用磁盘空间")
            if staging.exists():
                shutil.rmtree(staging)
            staging.mkdir(parents=True)
            archive.unlink(missing_ok=True)

            self.status.emit("正在下载安装工具")
            self._download(UV_URL, archive, UV_SIZE, UV_SHA256)
            with zipfile.ZipFile(archive) as bundle:
                member = next(
                    (name for name in bundle.namelist() if name.endswith("uv.exe")),
                    None,
                )
                if member is None:
                    raise RuntimeError("安装工具下载包不完整")
                uv_path = staging / "uv.exe"
                with bundle.open(member) as source, uv_path.open("wb") as output:
                    shutil.copyfileobj(source, output)

            environment = os.environ.copy()
            environment.update(
                {
                    "UV_CACHE_DIR": str(staging / ".cache"),
                    "UV_PYTHON_INSTALL_DIR": str(staging / "python"),
                    "UV_PYTHON_DOWNLOADS": "automatic",
                }
            )
            python = staging / ".venv" / "Scripts" / "python.exe"
            self.status.emit("正在准备独立运行环境")
            self._run_process(
                [
                    str(uv_path),
                    "venv",
                    "--python",
                    "3.12",
                    "--python-preference",
                    "only-managed",
                    str(staging / ".venv"),
                ],
                environment,
            )
            self.status.emit("正在安装 GPU 运行组件")
            self._run_process(
                [
                    str(uv_path),
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "--index-url",
                    "https://download.pytorch.org/whl/cu130",
                    "torch==2.13.0+cu130",
                ],
                environment,
            )
            self.status.emit("正在安装识别组件")
            self._run_process(
                [
                    str(uv_path),
                    "pip",
                    "install",
                    "--python",
                    str(python),
                    "transformers==5.15.1",
                    "librosa==1.0.0",
                    "soundfile==0.13.1",
                ],
                environment,
            )
            shutil.rmtree(staging / ".cache", ignore_errors=True)

            self.status.emit("正在下载高精度模型")
            model_dir = staging / "model"
            model_dir.mkdir()
            total = sum(item.size for item in MODEL_FILES)
            downloaded = 0
            for item in MODEL_FILES:
                self._download(
                    (
                        f"https://huggingface.co/{MODEL_ID}/resolve/"
                        f"{MODEL_REVISION}/{item.name}?download=true"
                    ),
                    model_dir / item.name,
                    item.size,
                    item.sha256,
                    progress_offset=downloaded,
                    progress_total=total,
                )
                downloaded += item.size

            (staging / ".ready").write_text(
                json.dumps(
                    {
                        "revision": RUNTIME_REVISION,
                        "model_revision": MODEL_REVISION,
                        "torch": "2.13.0+cu130",
                        "transformers": "5.15.1",
                    },
                    indent=2,
                ),
                encoding="utf-8",
            )
            self._check_cancelled()
            if backup.exists():
                shutil.rmtree(backup)
            had_previous = self.destination.exists()
            if had_previous:
                self.destination.replace(backup)
            try:
                staging.replace(self.destination)
            except Exception:
                if had_previous and backup.exists() and not self.destination.exists():
                    backup.replace(self.destination)
                raise
            else:
                if backup.exists():
                    shutil.rmtree(backup)
            self.completed.emit()
        except InstallCancelled:
            self.cancelled.emit()
        except Exception as error:
            if self._cancel.is_set():
                self.cancelled.emit()
            else:
                self.error.emit(str(error))
        finally:
            archive.unlink(missing_ok=True)
            if staging.exists():
                shutil.rmtree(staging, ignore_errors=True)
            self.stopped.emit()

    def _check_platform(self) -> None:
        if os.name != "nt":
            raise RuntimeError("高精度模式目前仅支持 Windows")
        if not self.require_nvidia:
            return
        executable = shutil.which("nvidia-smi")
        if not executable:
            raise RuntimeError("高精度模式需要 NVIDIA 显卡")
        completed = subprocess.run(
            [executable, "--query-gpu=name", "--format=csv,noheader"],
            capture_output=True,
            text=True,
            timeout=10,
        )
        if completed.returncode or not completed.stdout.strip():
            raise RuntimeError("未检测到可用的 NVIDIA 显卡")

    def _download(
        self,
        url: str,
        destination: Path,
        expected_size: int,
        expected_sha256: str,
        *,
        progress_offset: int = 0,
        progress_total: int | None = None,
    ) -> None:
        self._check_cancelled()
        digest = hashlib.sha256()
        downloaded = 0
        request = urllib.request.Request(url, headers={"User-Agent": "RealtimeSubtitle/1.0"})
        with urllib.request.urlopen(request, timeout=60) as response:
            with self._response_lock:
                self._response = response
            try:
                with destination.open("wb") as output:
                    while True:
                        self._check_cancelled()
                        chunk = response.read(1024 * 1024)
                        if not chunk:
                            break
                        output.write(chunk)
                        digest.update(chunk)
                        downloaded += len(chunk)
                        self.progress.emit(
                            progress_offset + downloaded,
                            progress_total or expected_size,
                        )
            finally:
                with self._response_lock:
                    if self._response is response:
                        self._response = None
        if downloaded != expected_size:
            raise RuntimeError(f"{destination.name} 下载大小不正确")
        if digest.hexdigest() != expected_sha256:
            raise RuntimeError(f"{destination.name} 下载校验失败")

    def _run_process(self, command: list[str], environment: dict[str, str]) -> None:
        self._check_cancelled()
        process = subprocess.Popen(
            command,
            cwd=self.destination.parent,
            env=environment,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            text=True,
            encoding="utf-8",
            errors="replace",
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        with self._process_lock:
            self._process = process
        output = ""
        try:
            while True:
                self._check_cancelled()
                try:
                    captured, _ = process.communicate(timeout=0.2)
                    output = (output + (captured or ""))[-4000:]
                    break
                except subprocess.TimeoutExpired:
                    time.sleep(0.01)
            if process.returncode:
                detail = output.strip().splitlines()[-1] if output.strip() else "未知错误"
                raise RuntimeError(f"高精度组件安装失败：{detail}")
        finally:
            with self._process_lock:
                if self._process is process:
                    self._process = None
