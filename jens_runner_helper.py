from __future__ import annotations

import os
import sys


def main() -> int:
    if len(sys.argv) >= 2 and sys.argv[1] == "--stress-run":
        from engine.stress_runner import main_stress_run

        return int(main_stress_run(sys.argv[2:]))
    if len(sys.argv) >= 2 and sys.argv[1] == "--stress-round":
        from engine.stress_runner import main_stress_round

        return int(main_stress_round(sys.argv[2:]))

    from jens_runner_entry import run_case

    case_path = ""
    if len(sys.argv) >= 3 and sys.argv[1] == "--run-case":
        case_path = sys.argv[2]
    else:
        case_path = os.environ.get("JENS_CASE_PATH") or ""
    return int(run_case(case_path or None))


if __name__ == "__main__":
    raise SystemExit(main())
