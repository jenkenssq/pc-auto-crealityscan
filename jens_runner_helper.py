from __future__ import annotations

import os
import sys

from jens_runner_entry import run_case


def main() -> int:
    case_path = ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-case":
        case_path = sys.argv[2]
    else:
        case_path = os.environ.get("JENS_CASE_PATH") or ""
    return int(run_case(case_path or None))


if __name__ == "__main__":
    raise SystemExit(main())
