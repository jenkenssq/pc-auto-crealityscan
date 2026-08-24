# -*- encoding=utf8 -*-
__author__ = "liangtai"

from airtest.core.api import *

auto_setup(__file__)



from poco.drivers.unity3d import UnityPoco
poco = UnityPoco()

touch(Template(r"tpl1772613488033.png", record_pos=(-0.343, -0.134), resolution=(1920, 1080)))

touch(Template(r"tpl1772613496430.png", record_pos=(-0.307, 0.131), resolution=(1920, 1080)))

wait(Template(r"tpl1772613590748.png", record_pos=(-0.004, 0.017), resolution=(1920, 1080)))




# 轮询等待进度条消失（最多等待60秒）
timeout = 60
start_time = time.time()

while time.time() - start_time < timeout:
    # 尝试查找进度条
    if not exists(Template(r"tpl1772613590748.png", record_pos=(-0.004, 0.017), resolution=(1920, 1080))):
        print("进度条已消失，加载完成")
        break
    # 每0.5秒检测一次，降低CPU占用
    sleep(0.5)
else:
    raise Exception("等待进度条超时")

# 继续后续操作
print("操作完成")