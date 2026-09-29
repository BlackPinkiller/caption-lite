# 第三方声明

Captions 自有代码采用 [MIT](LICENSE)，不改变第三方组件的许可。

## 随源码附带

| 组件 | 文件 | 许可 |
| --- | --- | --- |
| [Silero VAD](https://github.com/snakers4/silero-vad) | `desktop/resources/silero_vad.int8.onnx`、Android 同名资源 | [MIT · Silero Team](desktop/resources/LICENSE.silero-vad) |
| [Gradle Wrapper](https://github.com/gradle/gradle) | `android/gradlew`、`gradlew.bat`、`gradle-wrapper.jar` | [Apache-2.0 及附带声明](android/gradle/LICENSE) |

Silero INT8 模型由 [sherpa-onnx 官方模型发布](https://github.com/k2-fsa/sherpa-onnx/releases/tag/asr-models)提供。
Android 资源目录也保留了它的许可证副本。

## 运行依赖与下载模型

Python 依赖见 [requirements-lock.txt](desktop/requirements-lock.txt)，Android 依赖见
[build.gradle.kts](android/app/build.gradle.kts)。这些组件保留各自的许可证与版权声明，包括
[sherpa-onnx](https://github.com/k2-fsa/sherpa-onnx/blob/master/LICENSE)、
[Qt / PySide6](https://doc.qt.io/qtforpython-6/licenses.html) 和
[LiteRT-LM](https://github.com/google-ai-edge/LiteRT-LM)。

Nemotron、Zipformer、Gemma 等模型和可选 GPU 组件不包含在本仓库中，由用户按需下载；
它们遵循各自模型发布页和下载包中的条款，不适用 Captions 的 MIT 许可证。
