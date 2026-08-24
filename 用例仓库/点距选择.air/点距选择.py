# -*- encoding=utf8 -*-
__author__ = "86177"

from airtest.core.api import *

auto_setup(__file__)

import os


# 点距（mm）：默认 0.45
# - 若要从外部注入：设置环境变量 `JENS_POINT_DISTANCE_MM`（例如 0.45）
point_distance_mm = str(os.getenv("JENS_POINT_DISTANCE_MM", "0.45") or "0.45").strip()

# 方案 2：用“点距区域”的模板定位，再用 target_pos 把点击落到右侧文本框
# - target_pos 需要按实际 UI 微调：x 越大越靠右，y 越大越靠下
point_distance_region = Template(
    r"tpl1772710690978.png",
    resolution=(1920, 1080),
    target_pos=(0.42, 0.0),
)

# 兜底：如果区域模板不命中，则退回直接点击输入框模板
input_box_fallback = Template(r"tpl1772710704748.png", record_pos=(-0.409, -0.055), resolution=(1920, 1080))

if exists(point_distance_region):
    touch(point_distance_region)
elif exists(input_box_fallback):
    touch(input_box_fallback)
else:
    raise Exception("未找到点距区域/输入框（模板未命中），请确认已打开“扫描设置”面板且分辨率为 1920x1080。")
sleep(0.2)

def _try_keyevent(keys: list[str]) -> None:
    last = None
    for k in keys:
        try:
            keyevent(k)
            return
        except Exception as e:
            last = e
            continue
    if last:
        raise last

# Ctrl+A 全选
_try_keyevent(["^a", "CTRL+A", "{CTRL}a", "{CTRL}A"])
sleep(0.05)
# 删除选中内容
_try_keyevent(["BACKSPACE", "{BACKSPACE}"])
sleep(0.05)

text(point_distance_mm)
sleep(0.05)

# Enter 确认
_try_keyevent(["ENTER", "{ENTER}"])




