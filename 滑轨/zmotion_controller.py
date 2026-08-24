# zmotion_controller.py
import ctypes
import time
import os

class ZMotionController:
    """正运动控制器 ECI1308 封装（基于 zauxdll.dll）"""
    
    def __init__(self, dll_path, ip="192.168.0.11"):
        """
        初始化控制器
        :param dll_path: zauxdll.dll 的完整路径（建议绝对路径）
        :param ip: 控制器 IP 地址
        """
        # 如果是相对路径，转换为绝对路径（相对于当前脚本目录或工作目录）
        if not os.path.isabs(dll_path):
            # 先尝试相对于当前工作目录
            if os.path.exists(os.path.abspath(dll_path)):
                dll_path = os.path.abspath(dll_path)
            else:
                # 再尝试相对于本脚本所在目录
                script_dir = os.path.dirname(os.path.abspath(__file__))
                alt_path = os.path.join(script_dir, dll_path)
                if os.path.exists(alt_path):
                    dll_path = alt_path

        # 将 DLL 所在目录添加到 PATH，确保能找到依赖项
        dll_dir = os.path.dirname(os.path.abspath(dll_path))
        if dll_dir not in os.environ.get('PATH', ''):
            os.environ['PATH'] = dll_dir + os.pathsep + os.environ.get('PATH', '')

        self.dll = ctypes.CDLL(dll_path)
        self.ip = ip
        self.handle = None

    # ------------------ 连接与关闭 ------------------
    def open(self):
        """连接控制器"""
        self.dll.ZAux_OpenEth.argtypes = [ctypes.c_char_p, ctypes.POINTER(ctypes.c_void_p)]
        self.dll.ZAux_OpenEth.restype = ctypes.c_int
        handle = ctypes.c_void_p()
        ret = self.dll.ZAux_OpenEth(self.ip.encode(), ctypes.byref(handle))
        if ret != 0:
            raise Exception(f"连接失败，错误码：{ret}")
        self.handle = handle.value
        print("控制器连接成功")

    def close(self):
        """关闭连接"""
        if self.handle:
            self.dll.ZAux_Close(self.handle)
            self.handle = None
            print("连接已关闭")

    def is_connected(self) -> bool:
        """检查控制器是否已连接"""
        return self.handle is not None

    def get_connection_status(self) -> dict:
        """获取连接状态详情"""
        return {
            "connected": self.is_connected(),
            "ip": self.ip,
            "handle": self.handle
        }

    # ------------------ 通用命令执行 ------------------
    def execute_command(self, cmd):
        """
        执行任意 BASIC 命令，返回响应字符串
        :param cmd: 命令字符串，如 "?DPOS(0)"
        :return: 响应字符串
        """
        self.dll.ZAux_Execute.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_char_p, ctypes.c_uint32]
        self.dll.ZAux_Execute.restype = ctypes.c_int
        resp = ctypes.create_string_buffer(256)
        ret = self.dll.ZAux_Execute(self.handle, cmd.encode(), resp, 256)
        if ret != 0:
            raise Exception(f"命令失败，错误码：{ret}")
        return resp.value.decode().strip()

    # ------------------ 水平轴（轴0）控制 ------------------
    def enable_axis(self, axis):
        """使能指定轴"""
        self.execute_command(f"AXIS_ENABLE({axis})=1")
        print(f"轴{axis}已使能")

    def set_speed(self, axis, speed):
        """设置轴运动速度（脉冲/秒）"""
        self.execute_command(f"SPEED({axis})={speed}")

    def set_accel(self, axis, accel):
        """设置轴加速度（脉冲/秒²）"""
        self.execute_command(f"ACCEL({axis})={accel}")

    def set_base(self, axis):
        """设置当前工作轴（BASE）"""
        self.execute_command(f"BASE({axis})")

    def move_abs(self, axis, pos):
        """绝对移动（脉冲）"""
        self.set_base(axis)
        self.execute_command(f"MOVEABS({pos})")
        print(f"轴{axis}绝对移动至 {pos} 脉冲")

    def move_relative(self, axis, delta):
        """相对移动（脉冲）"""
        self.set_base(axis)
        self.execute_command(f"MOVE({delta})")
        print(f"轴{axis}相对移动 {delta} 脉冲")

    def move_relative_safe(self, axis, delta, timeout=None) -> bool:
        """
        安全的相对移动，带超时和错误处理
        :param axis: 轴号
        :param delta: 相对位移（脉冲）
        :param timeout: 超时时间（秒），None表示自动计算
        :return: 是否成功
        """
        try:
            self.set_base(axis)
            self.execute_command(f"MOVE({delta})")

            # 自动计算超时：距离/速度 + 加减速时间(2秒)
            if timeout is None:
                speed = 10000  # 默认速度
                distance = abs(delta)
                timeout = max(10, distance / speed + 2)

            self.wait_idle(axis, timeout=timeout)
            return True
        except Exception as e:
            print(f"轴{axis}移动失败: {e}")
            return False

    def move_to_position(self, axis, target_pos, timeout=None) -> bool:
        """
        移动到指定绝对位置
        :param axis: 轴号
        :param target_pos: 目标位置（脉冲）
        :param timeout: 超时时间（秒），None表示自动计算
        :return: 是否成功
        """
        try:
            self.move_abs(axis, target_pos)

            # 自动计算超时
            if timeout is None:
                speed = 10000
                current_pos = self.get_dpos(axis)
                distance = abs(target_pos - current_pos)
                timeout = max(10, distance / speed + 2)

            self.wait_idle(axis, timeout=timeout)
            return True
        except Exception as e:
            print(f"轴{axis}移动到{target_pos}失败: {e}")
            return False

    def get_dpos(self, axis):
        """读取当前命令位置（脉冲）"""
        resp = self.execute_command(f"?DPOS({axis})")
        return float(resp.split('=')[-1].strip())

    def wait_idle(self, axis, timeout=5):
        """等待轴停止运动"""
        start = time.time()
        while True:
            resp = self.execute_command(f"?IDLE({axis})")
            if "-1" in resp:
                break
            if time.time() - start > timeout:
                raise Exception(f"轴{axis}等待停止超时")
            time.sleep(0.1)

    # ------------------ 升降平台控制（输出口 OP6/OP7） ------------------
    def lift_up(self):
        """升起（启动上升）"""
        self.lift_stop()               # 先停止任何动作
        time.sleep(0.05)
        self.execute_command("OP(7,1)")
        print("升降台上升")

    def read_input(self, in_num):
        """读取输入点状态，返回 True 表示高电平（绿色），False 表示低电平（灰色）"""
        resp = self.execute_command(f"?IN({in_num})")
        return resp.strip() == "1"

    def lift_down(self):
        """降下平台，重复发送输出指令以保证继电器可靠吸合。"""
        self.lift_stop()
        time.sleep(0.05)

        at_top_limit = not self.read_input(2)  # 上限位触发（IN2=0）
        print("上限位触发，发送下降指令" if at_top_limit else "发送下降指令")
        for _ in range(15):
            self.execute_command("OP(6,1)")
            time.sleep(0.02)
        print("升降台下降")

    def lift_stop(self):
        """停止升降"""
        self.execute_command("OP(6,0)")
        self.execute_command("OP(7,0)")
        # print("升降台停止")  # 避免日志过多，可注释

    def lift_up_with_duration(self, seconds):
        """升起并保持指定秒数后停止"""
        self.lift_up()
        time.sleep(seconds)
        self.lift_stop()
        print(f"升降台上行 {seconds} 秒后停止")

    def lift_down_with_duration(self, seconds):
        """降下并保持指定秒数后停止"""
        self.lift_down()
        try:
            time.sleep(seconds)
        finally:
            self.lift_stop()
        print(f"升降台下行使 {seconds} 秒后停止")

    # ------------------ 可选：限位检测（需外接限位开关） ------------------
    def read_input(self, in_num):
        """读取输入点状态（0或1）"""
        resp = self.execute_command(f"?IN({in_num})")
        return 1 if "1" in resp else 0

    # 假设上限位接 IN(10)，下限位接 IN(11)
    def is_top_limit(self):
        return self.read_input(10) == 1

    def is_bottom_limit(self):
        return self.read_input(11) == 1

    def lift_up_safe(self, seconds=0.5):
        """带限位保护的上升（到达上限自动停止）"""
        for _ in range(int(seconds / 0.05)):
            if self.is_top_limit():
                print("已达上限位，停止上升")
                break
            self.lift_up()
            time.sleep(0.05)
        self.lift_stop()

    def lift_down_safe(self, seconds=0.5):
        """带限位保护的下降"""
        for _ in range(int(seconds / 0.05)):
            if self.is_bottom_limit():
                print("已达下限位，停止下降")
                break
            self.lift_down()
            time.sleep(0.05)
        self.lift_stop()

    def home_lift_to_top(self, safe_down=0.2, max_time=5.0) -> dict:
        """
        升降平台复位到上限位
        :param safe_down: 到达上限位后下降的安全距离（秒）
        :param max_time: 最大上升时间（秒）
        :return: 结果字典
        """
        result = {"success": True, "reached_limit": False, "error": None}

        try:
            # 持续上升直到触发上限位
            step = 0.1
            elapsed = 0
            self.lift_up()

            while elapsed < max_time:
                if not self.read_input(2):  # IN2=0表示上限位触发
                    self.lift_stop()
                    print("[+] 已到达上限位")
                    result["reached_limit"] = True

                    # 安全下降
                    if safe_down > 0:
                        time.sleep(0.2)  # 等待稳定
                        self.lift_down_with_duration(safe_down)
                        result["safe_down_done"] = True

                    return result

                time.sleep(step)
                elapsed += step

            # 超时
            self.lift_stop()
            result["success"] = False
            result["error"] = f"未能在{max_time}秒内到达上限位"

        except Exception as e:
            self.lift_stop()
            result["success"] = False
            result["error"] = str(e)

        return result

    def execute_pre_scan_motion(self, lift_seconds: float, horizontal_pulse: int) -> dict:
        """
        执行扫描前的组合运动
        :param lift_seconds: 升降秒数（正数上升，负数下降，0不动）
        :param horizontal_pulse: 水平移动脉冲数
        :return: 执行结果字典
        """
        result = {
            "success": True,
            "lift_done": False,
            "horizontal_done": False,
            "error": None,
            "lift_seconds": 0,
            "horizontal_pulse": 0
        }

        try:
            # 1. 执行升降
            if lift_seconds > 0:
                self.lift_up_with_duration(lift_seconds)
                result["lift_done"] = True
                result["lift_seconds"] = lift_seconds
            elif lift_seconds < 0:
                self.lift_down_with_duration(abs(lift_seconds))
                result["lift_done"] = True
                result["lift_seconds"] = lift_seconds

            # 2. 执行水平移动
            if horizontal_pulse != 0:
                self.enable_axis(0)
                self.set_speed(0, 10000)
                self.set_accel(0, 50000)
                success = self.move_relative_safe(0, horizontal_pulse, timeout=30)
                result["horizontal_done"] = success
                result["horizontal_pulse"] = horizontal_pulse

        except Exception as e:
            result["success"] = False
            result["error"] = str(e)

        return result


# ------------------ 测试入口 ------------------
if __name__ == "__main__":
    # 请将 DLL 放在当前目录，或使用绝对路径
    script_dir = os.path.dirname(os.path.abspath(__file__))
    dll_path = os.path.join(script_dir, "zauxdll.dll")
    if not os.path.exists(dll_path):
        print(f"错误：找不到 DLL 文件 {dll_path}")
        exit(1)

    track = ZMotionController(dll_path, ip="192.168.0.11")
    try:
        track.open()

        # ----- 水平轴测试（轴0）-----
        axis = 0
        track.enable_axis(axis)
        track.set_speed(axis, 10000)
        track.set_accel(axis, 50000)

        print(f"当前位置: {track.get_dpos(axis)}")
        track.move_abs(axis, 10000)
        track.wait_idle(axis)
        print(f"移动后位置: {track.get_dpos(axis)}")

        # 回零
        track.move_abs(axis, 0)
        track.wait_idle(axis)
        print(f"回零后位置: {track.get_dpos(axis)}")

        # ----- 升降台测试（输出口控制）-----
        print("\n测试升降台：下降 0.5 秒")
        track.lift_down_with_duration(0.5)
        time.sleep(1)

        print("测试升降台：上升 0.5 秒")
        track.lift_up_with_duration(0.5)

    except Exception as e:
        print(f"执行出错: {e}")
    finally:
        track.close()
