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

本地翻译的 HyMT2 模型（`tencent/Hy-MT2-1.8B-1.25Bit-GGUF`）依赖 llama.cpp 的
STQ1_0 内核（[PR #22836](https://github.com/ggml-org/llama.cpp/pull/22836)），
尚未合入 master。`llama/` 模块由 `setup-wsl.sh` 从该 PR 的固定提交检出源码后
编译，不提交二进制；`:app` 直接依赖 `:llama` 项目，无需手动拷贝 AAR。

主要边界：

- `core/`：会话数据与无平台状态规则。
- `ports/`：识别、翻译等能力接口。
- `ui/`：Compose 页面与交互状态。
- Android 权限、通知、系统识别和本地模型实现不得进入 `core/`。
- `llama/`：HyMT2 本地推理的 JNI 封装和 llama.cpp 构建，只对 `app` 暴露 `HyMt2Engine`。
