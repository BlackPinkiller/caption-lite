#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly project_dir="$(cd -- "$script_dir/.." && pwd)"
readonly cache_dir="${XDG_CACHE_HOME:-$HOME/.cache}/captions-android"
readonly sdk_dir="${ANDROID_HOME:-$HOME/Android/Sdk}"
readonly gradle_version="9.4.1"
readonly gradle_zip="$cache_dir/gradle-$gradle_version-bin.zip"
readonly gradle_dir="$cache_dir/gradle-$gradle_version"
readonly command_tools_zip="$cache_dir/commandlinetools-linux-15859902_latest.zip"
readonly command_tools_sha256="4e4c464f145a7512b57d088ac6c278c03c9eea610886b35a5e0804e74eedf583"
readonly sherpa_version="1.13.5"
readonly sherpa_aar="$project_dir/app/libs/sherpa-onnx-$sherpa_version.aar"
readonly sherpa_sha256="6419cd8bc983e0c4fab06067f0fe0313fdc0f7103818ac1e7a08d50787b7a82b"

mkdir -p "$cache_dir" "$sdk_dir"
mkdir -p "$project_dir/app/libs"

download_verified() {
    local url="$1"
    local expected_sha256="$2"
    local output="$3"

    if [[ -f "$output" ]] && ! echo "$expected_sha256  $output" | sha256sum --check --status; then
        rm -f -- "$output"
    fi
    if [[ ! -f "$output" ]]; then
        curl -fL --retry 3 --output "$output" "$url"
    fi
    echo "$expected_sha256  $output" | sha256sum --check
}

gradle_sha256="$(curl -fsSL "https://services.gradle.org/distributions/gradle-$gradle_version-bin.zip.sha256")"
download_verified \
    "https://services.gradle.org/distributions/gradle-$gradle_version-bin.zip" \
    "$gradle_sha256" \
    "$gradle_zip"

download_verified \
    "https://github.com/k2-fsa/sherpa-onnx/releases/download/v$sherpa_version/sherpa-onnx-$sherpa_version.aar" \
    "$sherpa_sha256" \
    "$sherpa_aar"

if [[ ! -x "$gradle_dir/bin/gradle" ]]; then
    unzip -q -o "$gradle_zip" -d "$cache_dir"
fi

if [[ ! -x "$sdk_dir/cmdline-tools/latest/bin/sdkmanager" ]]; then
    download_verified \
        "https://dl.google.com/android/repository/commandlinetools-linux-15859902_latest.zip" \
        "$command_tools_sha256" \
        "$command_tools_zip"
    command_tools_stage="$cache_dir/command-tools-stage"
    rm -rf -- "$command_tools_stage"
    mkdir -p "$command_tools_stage" "$sdk_dir/cmdline-tools"
    unzip -q "$command_tools_zip" -d "$command_tools_stage"
    mv "$command_tools_stage/cmdline-tools" "$sdk_dir/cmdline-tools/latest"
    rmdir "$command_tools_stage"
fi

set +o pipefail
yes | "$sdk_dir/cmdline-tools/latest/bin/sdkmanager" --sdk_root="$sdk_dir" --licenses >/dev/null
license_status="${PIPESTATUS[1]}"
set -o pipefail
if [[ "$license_status" -ne 0 ]]; then
    exit "$license_status"
fi
"$sdk_dir/cmdline-tools/latest/bin/sdkmanager" \
    --sdk_root="$sdk_dir" \
    --channel=3 \
    "platform-tools" \
    "platforms;android-37.0" \
    "build-tools;37.0.0" \
    "ndk;29.0.14206865" \
    "cmake;3.31.6"

printf 'sdk.dir=%s\n' "$sdk_dir" > "$project_dir/local.properties"

if [[ ! -x "$project_dir/gradlew" ]]; then
    "$gradle_dir/bin/gradle" \
        --project-dir "$project_dir" \
        wrapper \
        --gradle-version "$gradle_version" \
        --distribution-type bin
fi

echo "Android toolchain ready: $sdk_dir"
