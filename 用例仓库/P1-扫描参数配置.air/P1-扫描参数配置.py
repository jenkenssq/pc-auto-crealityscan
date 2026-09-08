# -*- encoding=utf8 -*-
__author__ = "liangtai"

from airtest.core.api import *

auto_setup(__file__)

#线激光-点云-交叉线
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch(Template(r"tpl1772712186259.png", record_pos=(-0.473, -0.007), resolution=(1920, 1080)))

#线激光-点云--平行线
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch(Template(r"tpl1774440021941.png", record_pos=(-0.479, 0.06), resolution=(1920, 1080)))


#线激光-点云--单线
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch(Template(r"tpl1774410082997.png", record_pos=(-0.483, 0.019), resolution=(1920, 1080)))

#线激光-框架点-开启贴图
touch((90,210))
touch((70,360))
touch((315,415))

#线激光-框架点-关闭贴图
touch((90,210))
touch((70,360))

#散斑-小物体-几何
touch((255,215))
touch((70,325))
touch((280,435))
touch((70,540))

#散斑-小物体-纹理
touch((255,215))
touch((70,325))
touch((280,435))
touch((175,540))

#散斑-中物体-几何
touch((255,215))
touch((70,325))
touch((175,435))
touch((70,540))

#散斑-中物体-纹理
touch((255,215))
touch((70,325))
touch((175,435))
touch((175,540))

#散斑-大物体-几何-标准
touch((255,215))
touch((70,325))
touch((70,435))
touch((70,540))
touch((70,645))

#散斑-大物体-几何-广角
touch((255,215))
touch((70,325))
touch((70,435))
touch((70,540))
touch((175,645))

#散斑-大物体-纹理-标准
touch((255,215))
touch((70,325))
touch((70,435))
touch((175,540))
touch((70,645))

#散斑-大物体-纹理-广角
touch((255,215))
touch((70,325))
touch((70,435))
touch((175,540))
touch((175,645))

#散斑-人脸-几何-标准
touch((255,215))
touch((175,325))
touch((70,430))
touch((70,540))

#散斑-人脸-几何-广角
touch((255,215))
touch((175,325))
touch((70,430))
touch((175,540))

#散斑-人脸-纹理-标准
touch((255,215))
touch((175,325))
touch((175,430))
touch((70,540))

#散斑-人脸-纹理-广角
touch((255,215))
touch((175,325))
touch((175,430))
touch((175,540))

#散斑-人体-几何
touch((255,215))
touch((280,325))
touch((70,430))

#散斑-人体-纹理
touch((255,215))
touch((280,325))
touch((175,435))



