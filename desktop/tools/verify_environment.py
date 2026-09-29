from __future__ import annotations

import importlib.metadata
from pathlib import Path
import sys

from packaging.requirements import Requirement


def main() -> int:
    project_root = Path(__file__).resolve().parent.parent
    lock_path = project_root / "requirements-lock.txt"
    problems: list[str] = []
    for raw_line in lock_path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line or line.startswith("#"):
            continue
        requirement = Requirement(line)
        try:
            installed = importlib.metadata.version(requirement.name)
        except importlib.metadata.PackageNotFoundError:
            problems.append(f"缺少 {requirement.name}")
            continue
        if installed not in requirement.specifier:
            problems.append(
                f"{requirement.name} 版本不一致：需要 {requirement.specifier}，"
                f"当前为 {installed}"
            )
    if problems:
        print("构建环境与 requirements-lock.txt 不一致：", file=sys.stderr)
        for problem in problems:
            print(f"- {problem}", file=sys.stderr)
        return 1
    print("Build environment matches requirements-lock.txt")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
