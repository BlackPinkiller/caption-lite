# Android

面向 **Android 17（API 37）、arm64** 的独立客户端，使用麦克风生成字幕，支持悬浮窗。
识别可选系统服务或本地 Nemotron；翻译可选端侧模型或在线服务。

## 使用

安装 APK 后授予麦克风权限；需要在其他应用上方显示字幕时，再开启悬浮窗权限。
在设置中选择识别与翻译方式，按提示下载模型，然后开始会话。

本地 Nemotron 在设备上识别；系统识别服务可能上传音频。在线翻译会发送文字，
使用端侧翻译需先下载对应模型。

## 构建

与桌面 Python 环境独立。使用 Linux 或 WSL 2，准备 **JDK 17、curl 和 unzip**。
在仓库根目录执行：

```bash
cd android
./tools/setup-wsl.sh
./tools/build-wsl.sh
```

设置脚本下载并校验 Gradle、Android SDK 和 sherpa-onnx 1.13.8 AAR，
并接受 Android SDK 许可。SDK 默认位于 `~/Android/Sdk`，可通过 `ANDROID_HOME` 指定。
模型由应用按需下载，不参与构建。

构建脚本生成 `app/build/outputs/apk/debug/app-debug.apk`。
这是调试包；正式发行包需配置自己的签名。

```bash
./gradlew lintDebug          # 静态检查
./tools/build-wsl.sh --clean # 清理后重新构建
```

## 结构

`core/` 管理会话与状态规则，`ports/` 定义能力接口，`platform/` 封装 Android 和第三方引擎，
`ui/` 负责 Compose 页面。权限、音频、识别和模型下载逻辑不进入界面或核心状态规则。
