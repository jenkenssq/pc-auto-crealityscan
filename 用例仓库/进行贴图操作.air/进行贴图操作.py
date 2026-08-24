# -*- encoding=utf8 -*-
__author__ = "liangtai"

from airtest.core.api import *

auto_setup(__file__)

touch(Template(r"tpl1774270225446.png", record_pos=(-0.277, -0.254), resolution=(1920, 1080)))

touch(Template(r"tpl1772613788279.png", record_pos=(-0.089, -0.177), resolution=(1920, 1080)))


wait(Template(r"tpl1772613816094.png", record_pos=(-0.07, 0.008), resolution=(1920, 1080)))



timeout = 90
start_time = time.time()

while time.time() - start_time < timeout:
    # 尝试查找进度条
    if not exists(Template(r"tpl1772613816094.png", record_pos=(-0.07, 0.008), resolution=(1920, 1080))):
        print("进度条已消失，加载完成")
        break
    # 每0.5秒检测一次，降低CPU占用
    sleep(0.5)
else:
    raise Exception("等待进度条超时")

# 继续后续操作
print("操作完成")