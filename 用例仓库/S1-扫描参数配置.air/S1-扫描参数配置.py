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
touch((65,465))
touch((310,520))

#线激光-框架点-关闭贴图
touch((90,210))
touch((65,465))

#散斑-点云-大物体-几何-标准
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((60,650))
touch((60,760))

#散斑-点云-大物体-几何-广角
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((60,650))
touch((170,760))

#散斑-点云-大物体-纹理-标准
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((170,650))
touch((60,760))

#散斑-点云-大物体-纹理-广角
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((170,650))
touch((170,760))

#散斑-点云-大物体-标志点-标准
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((280,650))
touch((60,760))

#散斑-点云-大物体-标志点-广角
touch((240,210))
touch((54,300))
touch((60,435))
touch((60,545))
touch((280,650))
touch((170,760))

#散斑-点云-中物体-几何
touch((240,210))
touch((54,300))
touch((60,435))
touch((170,545))
touch((60,650))

#散斑-点云-中物体-纹理
touch((240,210))
touch((54,300))
touch((60,435))
touch((170,545))
touch((170,650))

#散斑-点云-中物体-标志点
touch((240,210))
touch((54,300))
touch((60,435))
touch((170,545))
touch((280,650))

#散斑-点云-小物体-几何
touch((240,210))
touch((54,300))
touch((60,435))
touch((280,540))
touch((60,650))

#散斑-点云-小物体-纹理
touch((240,210))
touch((54,300))
touch((60,435))
touch((280,540))
touch((170,650))

#散斑-点云-小物体-标志点
touch((240,210))
touch((54,300))
touch((60,435))
touch((280,540))
touch((280,650))

#散斑-点云-人脸-几何
touch((240,210))
touch((54,300))
touch((170,435))
touch((60,545))

#散斑-点云-人脸-纹理
touch((240,210))
touch((54,300))
touch((170,435))
touch((170,545))

#散斑-点云-人体-几何
touch((240,210))
touch((54,300))
touch((280,435))
touch((60,545))

#散斑-点云-人体-纹理
touch((240,210))
touch((54,300))
touch((280,435))
touch((170,545))

#散斑框架点-大物体
touch((240,210))
touch((60,330))
touch((60,435))

#散斑框架点-中物体
touch((240,210))
touch((60,330))
touch((175,435))

#散斑框架点-小物体
touch((240,210))
touch((60,330))
touch((280,435))



