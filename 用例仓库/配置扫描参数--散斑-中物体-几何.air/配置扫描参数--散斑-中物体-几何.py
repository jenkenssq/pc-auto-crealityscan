# -*- encoding=utf8 -*-
__author__ = "liangtai"

from airtest.core.api import *

auto_setup(__file__)

# touch((360,305))#选中红外模式

touch((280,310))#选中点云扫描

touch((290,425))#选中“物体”
touch((780,380))#选中“空白地”


# touch((386,520))#选中“中物体”
touch((285,520))#选中“大物体”

touch((295,615))#选中“几何”

# touch(Template(r"tpl1772625900852.png", record_pos=(-0.299, -0.172), resolution=(1920, 1080)))


