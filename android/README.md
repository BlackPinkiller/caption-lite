# Android

Android 端使用 Kotlin 和 Jetpack Compose，独立于 Windows/Linux 的 Python 构建。
只面向 Android 17（API 37），不保留旧系统兼容分支。

```bash
cd android
./tools/setup-wsl.sh
./tools/build-wsl.sh
```

需要从空生成目录验证时使用 `./tools/build-wsl.sh --clean`。

首次设置会把 Gradle 缓存和 Android SDK 放在 WSL 用户目录；仓库只保留 Wrapper 和源码。
`sherpa-onnx` 的官方 Android AAR 由设置脚本校验后下载，不提交二进制依赖。

端侧翻译通过 LiteRT-LM（`com.google.ai.edge.litertlm:litertlm-android`）运行
Gemma 4 E2B 模型（`litert-community/gemma-4-E2B-it-litert-lm`）。模型由应用在
翻译设置页按需下载到缓存目录，不需要在构建时准备，也不提交二进制。

主要边界：

- `core/`：会话数据与无平台状态规则。
- `ports/`：识别、翻译等能力接口。
- `ui/`：Compose 页面与交互状态。
- Android 权限、通知、系统识别和本地模型实现不得进入 `core/`。
- 端侧翻译的模型下载与 LiteRT-LM 推理封装在 `platform/translation/`，只对 `app` 暴露 `TranslationEngine`。
