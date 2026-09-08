# -*- encoding=utf8 -*-
__author__ = "86177"

from airtest.core.api import *

auto_setup(__file__)

#小物体-几何
touch((70,360)) 
touch((280,470)) 
touch((60,575)) 

#小物体-纹理
touch((70,360)) 
touch((280,470))
touch((170,575))

#小物体-标志点
touch((70,360)) 
touch((280,470))
touch((280,575))
#中物体-几何
touch((70,360)) 
touch((175,465)) 
touch((70,570)) 

#中物体-纹理
touch((70,360)) 
touch((175,465)) 
touch((175,570)) 

#大物体-几何-快速
touch((70,360)) 
touch((70,465))
touch((70,570)) 
touch((70,680)) 

#大物体-几何-高精度
touch((70,360)) 
touch((70,465))
touch((70,570)) 
touch((175,680)) 

#大物体-纹理-快速
touch((70,360)) 
touch((70,465))
touch((175,570)) 
touch((70,680)) 

#大物体-纹理-高精度
touch((70,360)) 
touch((70,465))
touch((175,570)) 
touch((175,680)) 

#大物体-标志点
touch((70,360)) 
touch((70,465))
touch((280,570))

#人脸-几何
touch((175,360)) 
touch((70,465))

#人脸-纹理
touch((175,360)) 
touch((175,465))

#人体-几何-高精度
touch((280,360)) 
touch((70,465))
touch((175,570)) 

#人体-几何-快速
touch((280,360)) 
touch((70,465))
touch((70,570))

#人体-纹理-快速
touch((280,360)) 
touch((175,465))
touch((70,570))

#人体-纹理-高精度
touch((280,360)) 
touch((175,465))
touch((175,570)) 

