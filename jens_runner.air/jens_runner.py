# -*- encoding=utf8 -*-
"""
Airtest CLI 默认会寻找与 .air 目录同名的 .py 文件：
  jens_runner.air -> jens_runner.py

这里作为薄封装，实际逻辑在 main.py 中，便于后续维护。
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from main import main

main()
