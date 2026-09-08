# motion_client.py
"""
运动控制客户端 - 64位Python环境使用
通过Socket与32位运动控制服务通信
"""
import socket
import json
import time
import threading

# 服务配置
DEFAULT_HOST = '127.0.0.1'
DEFAULT_PORT = 5000
BUFFER_SIZE = 4096
TIMEOUT = 180  # 超时时间：3分钟（覆盖最长移动时间 + 通信余量）


class MotionClient:
    """运动控制客户端"""

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.socket = None
        self.lock = threading.Lock()
        self.connected = False
        self.last_error = None

    def connect(self):
        """连接到服务"""
        try:
            self.socket = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            self.socket.settimeout(TIMEOUT)
            self.socket.connect((self.host, self.port))
            self.connected = True

            # 测试连接
            response = self.send_command('test_connection')
            if response.get('status') == 'success':
                print(f"[*] 已连接到运动控制服务 (服务版本: {response.get('version', 'unknown')})")
                return True
            else:
                self.connected = False
                return False
        except Exception as e:
            self.last_error = str(e)
            self.connected = False
            return False

    def disconnect(self):
        """断开连接"""
        if self.socket:
            try:
                self.socket.close()
            except:
                pass
        self.socket = None
        self.connected = False
        print("[*] 已断开与运动控制服务的连接")

    def send_command(self, command, params=None):
        """发送命令并接收响应"""
        if params is None:
            params = {}

        request = {
            'command': command,
            'params': params
        }

        with self.lock:
            try:
                if not self.socket:
                    return {'status': 'error', 'message': '未连接到服务'}

                # 发送命令
                message = json.dumps(request) + '\n'
                self.socket.send(message.encode('utf-8'))

                # 接收响应
                response_data = b''
                while True:
                    chunk = self.socket.recv(BUFFER_SIZE)
                    if not chunk:
                        return {'status': 'error', 'message': '连接已断开'}
                    response_data += chunk
                    if b'\n' in response_data:
                        break

                response_str = response_data.decode('utf-8').strip().split('\n')[0]
                return json.loads(response_str)

            except socket.timeout:
                return {'status': 'error', 'message': '请求超时'}
            except Exception as e:
                return {'status': 'error', 'message': str(e)}

    # ==================== 连接控制 ====================

    def connect_controller(self, dll_path='zauxdll.dll', ip='192.168.0.11'):
        """连接运动控制器"""
        return self.send_command('connect', {'dll_path': dll_path, 'ip': ip})

    def disconnect_controller(self):
        """断开运动控制器"""
        return self.send_command('disconnect')

    def is_controller_connected(self):
        """检查控制器连接状态"""
        response = self.send_command('is_connected')
        return response.get('connected', False) if response.get('status') == 'success' else False

    # ==================== 升降控制 ====================

    def lift_up(self):
        """上升"""
        return self.send_command('lift_up')

    def lift_down(self):
        """下降"""
        return self.send_command('lift_down')

    def lift_stop(self):
        """停止升降"""
        return self.send_command('lift_stop')

    def lift_up_duration(self, seconds):
        """上升指定时间"""
        return self.send_command('lift_up_duration', {'seconds': seconds})

    def lift_down_duration(self, seconds):
        """下降指定时间"""
        return self.send_command('lift_down_duration', {'seconds': seconds})

    def lift_down_to_bottom(self, safety_margin=1.0):
        """一键下降到底
        :param safety_margin: 额外安全余量（秒），默认1秒
        """
        return self.send_command('lift_down_to_bottom', {'safety_margin': safety_margin})

    def get_lift_state(self):
        """获取距最低位的升降秒数计数器状态"""
        return self.send_command('get_lift_state')

    def move_and_lift(self, pulse, lift_direction, lift_seconds):
        """
        同时执行水平移动和升降
        :param pulse: 水平脉冲数
        :param lift_direction: 'up' 或 'down'
        :param lift_seconds: 升降秒数
        """
        return self.send_command('move_and_lift', {
            'pulse': pulse,
            'lift_direction': lift_direction,
            'lift_seconds': lift_seconds
        })

    # ==================== 水平移动 ====================

    def move_relative(self, pulse):
        """相对移动"""
        return self.send_command('horizontal_move', {'pulse': pulse})

    def move_absolute(self, position):
        """绝对移动（基于软零点）"""
        return self.send_command('horizontal_move_abs', {'position': position})

    def get_position(self):
        """获取当前位置"""
        return self.send_command('get_position')

    # ==================== 复位功能 ====================

    def set_soft_zero(self):
        """设置当前位置为软零点"""
        return self.send_command('set_soft_zero')

    def reset_to_zero(self):
        """复位到软零点"""
        return self.send_command('reset_to_zero')

    def home_lift_platform(self, safe_down=None):
        """升降平台复位到上限位"""
        params = {}
        if safe_down is not None:
            params['safe_down'] = safe_down
        return self.send_command('home_lift', params)

    # ==================== 扫描前运动 ====================

    def execute_pre_scan_motion(self, lift_seconds=0, horizontal_pulse=0,
                                 reset_first=False, safe_down=0):
        """
        执行扫描前运动
        :param lift_seconds: 升降秒数（正数上升，负数下降）
        :param horizontal_pulse: 水平移动脉冲数
        :param reset_first: 是否先复位
        :param safe_down: 复位后下降距离（秒）
        :return: 执行结果
        """
        return self.send_command('execute_pre_scan_motion', {
            'lift_seconds': lift_seconds,
            'horizontal_pulse': horizontal_pulse,
            'reset_first': reset_first,
            'safe_down': safe_down
        })

    def execute_object_scan_motion(self, horizontal_pulse=0, scan_cycle_seconds=2,
                                   object_type='unknown'):
        """
        执行物体扫描运动（优化后的流程）
        1. 水平移动到物体位置
        2. 下降到最底部（固定秒数 = 扫描上下运动的秒数）
        3. 扫描自动上下进行
        :param horizontal_pulse: 水平脉冲数
        :param scan_cycle_seconds: 扫描上下运动的秒数（下降和上升都使用这个值）
        :param object_type: 物体类型（用于日志）
        :return: 执行结果
        """
        return self.send_command('execute_object_scan_motion', {
            'horizontal_pulse': horizontal_pulse,
            'scan_cycle_seconds': scan_cycle_seconds,
            'object_type': object_type
        })

    def lift_up_seconds(self, seconds):
        """上升指定秒数"""
        return self.lift_up_duration(seconds)

    def lift_down_seconds(self, seconds):
        """下降指定秒数"""
        return self.lift_down_duration(seconds)

    def move_and_execute_cycle(self, rise_to_top_seconds=4, down_to_bottom_seconds=20):
        """
        执行一次完整的上下循环运动
        1. 上升到顶部
        2. 下降到最底部
        :param rise_to_top_seconds: 上升到顶部的秒数
        :param down_to_bottom_seconds: 下降到最底部的秒数
        :return: 执行结果
        """
        return self.send_command('move_and_execute_cycle', {
            'rise_to_top_seconds': rise_to_top_seconds,
            'down_to_bottom_seconds': down_to_bottom_seconds
        })

    def lift_up_with_horizontal(self, lift_seconds, horizontal_pulse):
        """
        上升时同时水平移动
        :param lift_seconds: 上升秒数
        :param horizontal_pulse: 水平移动脉冲数（正数左移，负数右移）
        :return: 执行结果
        """
        return self.send_command('move_and_lift', {
            'pulse': horizontal_pulse,
            'lift_direction': 'up',
            'lift_seconds': lift_seconds
        })

    def lift_down_with_horizontal(self, lift_seconds, horizontal_pulse):
        """
        下降时同时水平移动
        :param lift_seconds: 下降秒数
        :param horizontal_pulse: 水平移动脉冲数（正数左移，负数右移）
        :return: 执行结果
        """
        return self.send_command('move_and_lift', {
            'pulse': horizontal_pulse,
            'lift_direction': 'down',
            'lift_seconds': lift_seconds
        })

    def continuous_scan_cycle(self, scan_cycle_seconds=4, horizontal_pulse=10000, horizontal_speed=2000):
        """
        持续扫描循环：上下运动的同时水平来回移动
        :param scan_cycle_seconds: 上下运动秒数
        :param horizontal_pulse: 左右移动范围（脉冲）
        :param horizontal_speed: 水平移动速度（脉冲/秒）
        :return: 执行结果
        """
        return self.send_command('continuous_scan_cycle', {
            'scan_cycle_seconds': scan_cycle_seconds,
            'horizontal_pulse': horizontal_pulse,
            'horizontal_speed': horizontal_speed
        })

    def stop_continuous(self):
        """停止持续扫描循环"""
        return self.send_command('stop_continuous')

    def start_horizontal_sweep(self, horizontal_pulse=10000, horizontal_speed=2000):
        """
        启动左右来回移动（独立于上下运动）
        :param horizontal_pulse: 左右移动范围（脉冲）
        :param horizontal_speed: 水平移动速度（脉冲/秒）
        :return: 执行结果
        """
        return self.send_command('start_horizontal_sweep', {
            'horizontal_pulse': horizontal_pulse,
            'horizontal_speed': horizontal_speed
        })

    def stop_horizontal_sweep(self):
        """停止左右来回移动"""
        return self.send_command('stop_horizontal_sweep')

    # ==================== 配置管理 ====================

    def get_calibration(self):
        """获取校准参数"""
        return self.send_command('get_calibration')

    def set_calibration(self, **kwargs):
        """设置校准参数"""
        return self.send_command('set_calibration', kwargs)

    def auto_calibrate_lift(self):
        """自动校准升降平台"""
        return self.send_command('auto_calibrate_lift')

    # ==================== 其他 ====================

    def read_input(self, in_num):
        """读取输入点"""
        return self.send_command('read_input', {'in_num': in_num})

    def emergency_stop(self):
        """紧急停止"""
        return self.send_command('emergency_stop')

    def check_connection(self):
        """检查服务连接"""
        if not self.connected:
            return False
        response = self.send_command('test_connection')
        return response.get('status') == 'success'

    # ==================== 调试命令 ====================

    def set_speed(self, axis, speed):
        """设置轴速度"""
        return self.send_command('set_speed', {'axis': axis, 'speed': speed})

    def set_accel(self, axis, accel):
        """设置轴加速度"""
        return self.send_command('set_accel', {'axis': axis, 'accel': accel})

    def stop_axis(self, axis):
        """停止指定轴"""
        return self.send_command('stop_axis', {'axis': axis})

    def continuous_move(self, axis, direction, speed):
        """
        持续移动
        :param axis: 轴号
        :param direction: 方向 (1=正向, -1=反向)
        :param speed: 速度
        """
        return self.send_command('continuous_move', {
            'axis': axis,
            'direction': direction,
            'speed': speed
        })


class MockMotionClient:
    """
    模拟运动控制客户端 - 用于没有32位服务的测试环境
    所有操作仅打印日志，不实际执行
    """

    def __init__(self, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.host = host
        self.port = port
        self.connected = False
        self.mock_position = 0
        self.mock_lift_position = 0

    def connect(self):
        print("[MOCK] 模拟连接到运动控制服务")
        self.connected = True
        return True

    def disconnect(self):
        print("[MOCK] 模拟断开连接")
        self.connected = False

    def connect_controller(self, dll_path='zauxdll.dll', ip='192.168.0.11'):
        print(f"[MOCK] 模拟连接控制器: {ip}")
        return {'status': 'success', 'message': '模拟连接成功'}

    def is_controller_connected(self):
        return self.connected

    def lift_up(self):
        print("[MOCK] 升降平台上升")
        return {'status': 'success'}

    def lift_down(self):
        print("[MOCK] 升降平台下降")
        return {'status': 'success'}

    def lift_stop(self):
        print("[MOCK] 升降平台停止")
        return {'status': 'success'}

    def lift_up_duration(self, seconds):
        print(f"[MOCK] 升降平台上升 {seconds} 秒")
        self.mock_lift_position += seconds * 10
        return {'status': 'success'}

    def lift_down_duration(self, seconds):
        print(f"[MOCK] 升降平台下降 {seconds} 秒")
        self.mock_lift_position -= seconds * 10
        return {'status': 'success'}

    def lift_down_to_bottom(self, safety_margin=1.0):
        print(f"[MOCK] 升降平台下降到底（48+{safety_margin}秒）")
        self.mock_lift_position = 0
        return {
            'status': 'success',
            'message': '已下降到底',
            'duration': max(0.0, float(safety_margin)),
            'from_bottom_seconds': 0.0,
            'position_known': True,
            'at_bottom': True,
        }

    def get_lift_state(self):
        return {
            'status': 'success',
            'from_bottom_seconds': max(0.0, self.mock_lift_position / 10),
            'position_known': True,
            'at_bottom': self.mock_lift_position <= 0,
        }

    def move_and_lift(self, pulse, lift_direction, lift_seconds):
        print(f"[MOCK] 同时移动: 水平{pulse}脉冲, 升降{lift_direction} {lift_seconds}秒")
        self.mock_position += pulse
        if lift_direction == 'up':
            self.mock_lift_position += lift_seconds * 10
        else:
            self.mock_lift_position -= lift_seconds * 10
        return {
            'status': 'success',
            'message': f'同时移动完成',
            'horizontal_pulse': pulse,
            'lift_seconds': lift_seconds
        }

    def move_relative(self, pulse):
        print(f"[MOCK] 水平移动 {pulse} 脉冲")
        self.mock_position += pulse
        return {'status': 'success', 'relative_position': self.mock_position}

    def move_absolute(self, position):
        print(f"[MOCK] 水平移动到 {position}")
        self.mock_position = position
        return {'status': 'success', 'relative_position': self.mock_position}

    def get_position(self):
        return {
            'status': 'success',
            'relative_position': self.mock_position,
            'soft_zero': 0
        }

    def set_soft_zero(self):
        print("[MOCK] 设置软零点")
        return {'status': 'success'}

    def reset_to_zero(self):
        print("[MOCK] 复位到软零点")
        self.mock_position = 0
        return {'status': 'success'}

    def home_lift_platform(self, safe_down=None):
        print(f"[MOCK] 升降平台复位 (安全下降: {safe_down})")
        self.mock_lift_position = 0
        return {'status': 'success'}

    def execute_pre_scan_motion(self, lift_seconds=0, horizontal_pulse=0,
                                 reset_first=False, safe_down=0):
        print(f"[MOCK] 执行扫描前运动:")
        print(f"       升降: {lift_seconds}秒, 水平: {horizontal_pulse}脉冲")
        print(f"       先复位: {reset_first}, 安全下降: {safe_down}")
        return {
            'status': 'success',
            'lift_done': lift_seconds != 0,
            'horizontal_done': horizontal_pulse != 0,
            'reset_done': reset_first
        }

    def get_calibration(self):
        return {
            'status': 'success',
            'calibration': {
                'max_up_time': 3.0,
                'max_down_time': 3.0,
                'pulse_per_mm': 574.0,
                'max_forward_pulse': 50000,
                'max_backward_pulse': -50000,
            }
        }

    def emergency_stop(self):
        print("[MOCK] 紧急停止")
        return {'status': 'success'}

    def check_connection(self):
        return self.connected

    def read_input(self, in_num):
        print(f"[MOCK] 读取输入点 IN{in_num}")
        return {'status': 'success', 'value': False}


def create_motion_client(use_mock=False, host=DEFAULT_HOST, port=DEFAULT_PORT):
    """
    创建运动控制客户端
    :param use_mock: 是否使用模拟客户端
    :param host: 服务地址
    :param port: 服务端口
    :return: MotionClient 或 MockMotionClient 实例
    """
    if use_mock:
        return MockMotionClient(host, port)
    return MotionClient(host, port)


# ==================== 便捷的上下文管理器 ====================

class MotionClientContext:
    """运动控制客户端上下文管理器"""

    def __init__(self, use_mock=False, host=DEFAULT_HOST, port=DEFAULT_PORT):
        self.client = create_motion_client(use_mock, host, port)
        self.use_mock = use_mock

    def __enter__(self):
        if not self.client.connect():
            if not self.use_mock:
                raise Exception("无法连接到运动控制服务，请确保motion_service.py已在32位Python环境中运行")
        return self.client

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.client.disconnect()
        return False


if __name__ == '__main__':
    # 测试客户端
    print("[*] 测试运动控制客户端...")

    client = MotionClient()
    if client.connect():
        print("[*] 连接成功")

        # 测试连接控制器
        result = client.connect_controller()
        print(f"[*] 连接控制器: {result}")

        # 测试获取位置
        result = client.get_position()
        print(f"[*] 当前位置: {result}")

        client.disconnect()
    else:
        print("[-] 连接失败，请确保服务已启动")
