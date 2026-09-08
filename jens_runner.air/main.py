# -*- encoding=utf8 -*-
import os

from jens_runner_entry import run_case


if __name__ == "__main__":
    raise SystemExit(run_case(os.environ.get("JENS_CASE_PATH")))
