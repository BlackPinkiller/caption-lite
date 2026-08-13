#!/usr/bin/env bash
set -euo pipefail

readonly script_dir="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
readonly project_dir="$(cd -- "$script_dir/.." && pwd)"
readonly sdk_dir="${ANDROID_HOME:-$HOME/Android/Sdk}"

export ANDROID_HOME="$sdk_dir"
cd "$project_dir"
tasks=(test assembleDebug)
if [[ "${1:-}" == "--clean" ]]; then
    tasks=(clean "${tasks[@]}")
fi
./gradlew "${tasks[@]}"
