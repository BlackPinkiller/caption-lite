from __future__ import annotations

import argparse
import json
import sys
import threading
import winsound
from pathlib import Path

from PySide6.QtCore import QCoreApplication, QThread, QTimer

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from captions.audio_asr import AudioAsrWorker
from captions.config import AppConfig, MODEL_PRESETS, application_dir, default_model_dir


def main() -> int:
    parser = argparse.ArgumentParser(description="Play a WAV and recognize it via WASAPI loopback")
    parser.add_argument(
        "wav",
        nargs="?",
        type=Path,
        default=None,
    )
    parser.add_argument(
        "--model", choices=("english", "multilingual"), default="english"
    )
    parser.add_argument("--language", default="auto")
    args = parser.parse_args()
    if args.wav is None:
        model_name, _ = MODEL_PRESETS[args.model]
        sample_name = "en.wav" if args.model == "multilingual" else "0.wav"
        args.wav = application_dir() / "models" / model_name / "test_wavs" / sample_name
    if not args.wav.is_file():
        parser.error(f"WAV not found: {args.wav}")

    app = QCoreApplication([])
    thread = QThread()
    config = AppConfig()
    config.asr.model_variant = args.model
    config.asr.model_dir = default_model_dir(args.model)
    config.asr.language = args.language
    worker = AudioAsrWorker(config)
    worker.moveToThread(thread)
    results: list[str] = []
    errors: list[str] = []
    playback_started = False

    def status(text: str) -> None:
        nonlocal playback_started
        print(text, flush=True)
        if "正在识别：" in text and not playback_started:
            playback_started = True

            def play() -> None:
                winsound.PlaySound(str(args.wav), winsound.SND_FILENAME)
                threading.Timer(4, worker.stop).start()

            threading.Thread(target=play, daemon=True).start()

    worker.partial.connect(lambda text, revision: results.append(text))
    worker.status.connect(status)
    worker.error.connect(lambda text: errors.append(text))
    worker.stopped.connect(thread.quit)
    worker.stopped.connect(app.quit)
    thread.started.connect(worker.run)
    thread.start()
    QTimer.singleShot(45000, worker.stop)
    app.exec()
    thread.wait(5000)
    print(json.dumps({"last_result": results[-1] if results else "", "errors": errors}, ensure_ascii=True))
    return 0 if results and not errors else 1


if __name__ == "__main__":
    raise SystemExit(main())
