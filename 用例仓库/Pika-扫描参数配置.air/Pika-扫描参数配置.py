# -*- encoding=utf8 -*-
__author__ = "liangtai"

from airtest.core.api import *

auto_setup(__file__)

#wifi-线激光-点云
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch((210,630))

#wifi-框架点-开启贴图
touch((90,210))
touch((70,360))
touch((310,415))
touch((210,630))

#线激光-点云-有标志点-标准
touch((90,210))
touch((95,323))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch((70,648))
touch((210,765))

#线激光-点云-有标志点-均衡
touch((90,210))
touch((95,323))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch((175,648))
touch((210,765))

#线激光-点云-有标志点-快速
touch((90,210))
touch((95,323))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch((280,648))
touch((210,765))

#线激光-点云-无标志点
touch((90,210))
touch((255,323))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch((210,605))

#线激光-框架点-开启贴图
touch((90,210))
touch((95,323))
touch((70,468))
touch((315,630))
touch((210,580))

#线激光-框架点-不贴图-标准
touch((90,210))
touch((95,323))
touch((70,468))
touch((70,565))
touch((210,680))

#线激光-框架点-不贴图-均衡
touch((90,210))
touch((95,323))
touch((70,468))
touch((180,565))
touch((210,680))

#线激光-框架点-不贴图-快速
touch((90,210))
touch((95,323))
touch((70,468))
touch((280,565))
touch((210,680))

#散斑-点云-大物体-几何
touch((240,210))
touch((54,320))
touch((60,435))
touch((60,545))
touch((210,657))

#散斑-点云-大物体-纹理
touch((240,210))
touch((54,320))
touch((60,435))
touch((170,545))
touch((210,657))


#散斑-点云-中物体-几何
touch((255,215))
touch((70,325))
touch((175,435))
touch((70,540))
touch((210,657))

#散斑-点云-中物体-纹理
touch((255,215))
touch((70,325))
touch((175,435))
touch((175,540))
touch((210,657))


#散斑-点云-小物体-几何
touch((255,215))
touch((70,325))
touch((280,435))
touch((70,540))
touch((210,657))

#散斑-点云-小物体-纹理
touch((255,215))
touch((70,325))
touch((280,435))
touch((175,540))
touch((210,657))

#散斑-点云-人脸-几何
touch((255,215))
touch((175,325))
touch((70,430))
touch((210,550))

#散斑-点云-人脸-纹理
touch((255,215))
touch((175,325))
touch((175,430))
touch((210,550))

#散斑-点云-人体-几何
touch((255,215))
touch((280,325))
touch((70,430))
touch((210,550))

#散斑-点云-人体-纹理
touch((255,215))
touch((280,325))
touch((175,435))
touch((210,550))


touch(Template(r"tpl1786437505693.png", record_pos=(-0.462, -0.093), resolution=(1920, 1080)))



















