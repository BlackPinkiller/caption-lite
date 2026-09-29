# 开发约定

- `main` 保存桌面端和 Android 的完整代码。开发使用短期功能分支，完成后合并并删除分支。
- `desktop/` 和 `android/` 分别维护各自的依赖、资源和构建工具；公共说明放在仓库根目录或 `docs/`。
- 一次提交聚焦一件事，标题标明范围，例如 `fix(android): ...`、`fix(desktop): ...`、`docs(repo): ...`。
- 目录迁移与功能修改分开提交，方便审查和回退。
- 两端独立构建，命令见 [README](README.md#从源码构建)。

## 发布

- 正式版本设为 GitHub 的 Latest。附件固定命名为 `caption-lite-windows-x64.zip` 和 `caption-lite-android-arm64.apk`，同时更新 `SHA256SUMS.txt`。
- README 使用 `releases/latest/download/<附件名>`，无需随版本号修改；每版 Release 说明中的下载链接固定指向该版本，方便下载历史版本。
