# -*- encoding=utf8 -*-
__author__ = "86177"

from airtest.core.api import *

auto_setup(__file__)

#线激光-点云-交叉线
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch(Template(r"tpl1772712186259.png", record_pos=(-0.473, -0.007), resolution=(1920, 1080)))


#线激光-点云--平行线
touch((90,210))
touch(Template(r"tpl1772712168620.png", record_pos=(-0.469, -0.122), resolution=(1920, 1080)))
touch(Template(r"tpl1772712213026.png", record_pos=(-0.473, 0.008), resolution=(1920, 1080)))

#线激光框架点-开启贴图
touch(Template(r"tpl1772712329360.png", record_pos=(-0.461, -0.094), resolution=(1920, 1080)))
touch((305,402))
exists(Template(r"tpl1772712364002.png", record_pos=(-0.34, -0.063), resolution=(1920, 1080)))#代表贴图已开启


#线激光框架点-关闭贴图
touch(Template(r"tpl1772712329360.png", record_pos=(-0.461, -0.094), resolution=(1920, 1080)))
touch((305,402))
exists(Template(r"tpl1772712384437.png", record_pos=(-0.339, -0.062), resolution=(1920, 1080)))#代表贴图已关闭



#散斑-点云-大物体-几何
touch((250,215))
touch((60,300))
touch((70,435))
touch((70,540))
touch((70,650))
#散斑-点云-大物体-纹理
touch((250,215))
touch((60,300))
touch((70,435))
touch((70,540))
touch((175,650))
#散斑-点云-大物体-标志点
touch((250,215))
touch((60,300))
touch((70,435))
touch((70,540))
touch((280,650))
#散斑-点云-中物体-几何
touch((250,215))
touch((60,300))
touch((70,435))
touch((175,540))
touch((70,650))
#散斑-点云-中物体-纹理
touch((250,215))
touch((60,300))
touch((70,435))
touch((175,540))
touch((175,650))
#散斑-点云-中物体-标志点
touch((250,215))
touch((60,300))
touch((70,435))
touch((175,540))
touch((280,650))
#散斑-点云-小物体-几何
touch((250,215))
touch((60,300))
touch((70,435))
touch((280,540))
touch((70,650))
#散斑-点云-小物体-纹理
touch((250,215))
touch((60,300))
touch((70,435))
touch((280,540))
touch((175,650))
#散斑-点云-小物体-标志点
touch((250,215))
touch((60,300))
touch((70,435))
touch((280,540))
touch((280,650))
#散斑-点云-人脸-几何
touch((250,215))
touch((60,300))
touch((175,435))
touch((65,540))
#散斑-点云-人脸-纹理
touch((250,215))
touch((60,300))
touch((175,435))
touch((175,540))
#散斑-点云-人体-几何
touch((250,215))
touch((60,300))
touch((285,435))
touch((65,540))
#散斑-点云-人体-纹理
touch((250,215))
touch((60,300))
touch((285,435))
touch((175,540))

#散斑框架点-大物体
touch((250,215))
touch((70,330))
touch((70,435))
#散斑框架点-中物体
touch((250,215))
touch((70,330))
touch((175,435))
#散斑框架点-小物体
touch((250,215))
touch((70,330))
touch((285,435))wait(Template(r"tpl1772717104966.png", record_pos=(-0.336, -0.06), resolution=(1920, 1080)))










