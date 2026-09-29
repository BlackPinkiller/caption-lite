from __future__ import annotations

from pathlib import Path

from captions.core.settings import AppConfig
from captions.platforms.portable_paths import DEFAULT_APP_PATHS
from captions.ports.app_paths import AppPaths


def resolve_model_files(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> dict[str, Path]:
    model_dir = resolve_model_dir(config, app_paths=app_paths)
    return {
        name: model_dir / getattr(config.asr, name)
        for name in ("encoder", "decoder", "joiner", "tokens")
    }


def resolve_model_dir(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> Path:
    return app_paths.resolve_data_path(config.asr.model_dir)


def model_is_complete(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> bool:
    if config.asr.precision == "fp32":
        from captions.platforms.windows.high_precision_runtime import high_precision_runtime_ready

        return high_precision_runtime_ready(app_paths=app_paths)
    return all(
        path.is_file()
        for path in resolve_model_files(config, app_paths=app_paths).values()
    )


def model_install_key(
    config: AppConfig,
    *,
    app_paths: AppPaths = DEFAULT_APP_PATHS,
) -> tuple[str, ...]:
    if config.asr.precision == "fp32":
        from captions.platforms.windows.high_precision_runtime import high_precision_runtime_dir

        return ("fp32", str(high_precision_runtime_dir(app_paths=app_paths)))
    return (
        "int8",
        config.asr.model_variant,
        str(resolve_model_dir(config, app_paths=app_paths)),
    )
