# motion_service.py
"""
运动控制服务 - 32位Python环境运行
通过Socket接收命令，控制ZMotion运动控制器
"""
import socket
import json
import threading
import time
import os
import sys

# 导入运动控制器
from zmotion_controller import ZMotionController

# 服务配置
# 默认监听所有网卡，便于 Mac/局域网其他机器通过 Windows 局域网 IP 连接。
# 可用环境变量覆盖：MOTION_SERVICE_HOST / MOTION_SERVICE_PORT
# 例：set MOTION_SERVICE_HOST=192.168.1.20 && python motion_service.py
HOST = os.environ.get('MOTION_SERVICE_HOST', '0.0.0.0')
PORT = int(os.environ.get('MOTION_SERVICE_PORT', '5000'))
BUFFER_SIZE = 4096

class MotionService:
    """运动控制服务"""

    def __init__(self):
        self.controller = None
        self.server = None
        self.running = False
        self.soft_zero = 0.0  # 软零点位置
        self._stop_continuous = False  # 停止持续扫描循环标志
        self._stop_horizontal = False  # 停止左右来回移动标志
        self._horizontal_stopped = True  # 左右来回移动是否已停止
        self._lift_state_lock = threading.RLock()
        self._lift_from_bottom_seconds = 0.0
        self._lift_position_known = True
        self._active_lift_motion = None
        self.calibration = {
            'max_up_time': 58.0,      # 最大上升时间（48秒 × 1.2余量）
            'max_down_time': 48.0,    # 最大下降时间（40秒 × 1.2余量）
            'safe_down_distance': 1.0,  # 安全下降距离（到达上限后下降1秒作为零点）
            'pulse_per_mm': 574.0,   # 脉冲/毫米比例（来自控制软件实际参数）
            'max_forward_pulse': 1260000,  # 最大正向脉冲（574×2000×1.1）
            'max_backward_pulse': -1260000,  # 最大反向脉冲
            'default_speed': 80000,   # 默认移动速度（脉冲/秒）
            'default_accel': 150000,  # 默认加速度（脉冲/秒²）
        }

    def start(self):
        """启动服务"""
        self.server = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self.server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self.server.bind((HOST, PORT))
        self.server.listen(5)
        self.running = True

        print(f"[*] 运动控制服务启动于 {HOST}:{PORT}")
        print(f"[*] 请在32位Python环境中运行此服务")
        print(f"[*] 按Ctrl+C停止服务")

        try:
            while self.running:
                client, addr = self.server.accept()
                print(f"[+] 客户端连接: {addr}")
                client_thread = threading.Thread(
                    target=self.handle_client,
                    args=(client, addr)
                )
                client_thread.daemon = True
                client_thread.start()
        except KeyboardInterrupt:
            print("\n[*] 正在停止服务...")
        finally:
            self.stop()

    def stop(self):
        """停止服务"""
        self.running = False
        if self.controller:
            self.controller.close()
        if self.server:
            self.server.close()
        print("[*] 服务已停止")

    def handle_client(self, client, addr):
        """处理客户端连接"""
        while self.running:
            try:
                data = client.recv(BUFFER_SIZE).decode('utf-8')
                if not data:
                    break

                # 处理可能的多条消息
                for line in data.strip().split('\n'):
                    if not line:
                        continue
                    try:
                        request = json.loads(line)
                        response = self.process_command(request)
                        client.send(json.dumps(response).encode('utf-8') + b'\n')
                    except json.JSONDecodeError as e:
                        error_response = {'status': 'error', 'message': f'JSON解析错误: {str(e)}'}
                        client.send(json.dumps(error_response).encode('utf-8') + b'\n')

            except Exception as e:
                print(f"[-] 客户端处理错误: {e}")
                break

        print(f"[-] 客户端断开: {addr}")
        client.close()

    def process_command(self, request):
        """处理命令"""
        cmd = request.get('command', '')
        params = request.get('params', {})

        handlers = {
            'connect': self.cmd_connect,
            'disconnect': self.cmd_disconnect,
            'is_connected': self.cmd_is_connected,
            'lift_up': self.cmd_lift_up,
            'lift_down': self.cmd_lift_down,
            'lift_stop': self.cmd_lift_stop,
            'lift_up_duration': self.cmd_lift_up_duration,
            'lift_down_duration': self.cmd_lift_down_duration,
            'lift_down_to_bottom': self.cmd_lift_down_to_bottom,
            'horizontal_move': self.cmd_horizontal_move,
            'horizontal_move_abs': self.cmd_horizontal_move_abs,
            'get_position': self.cmd_get_position,
            'set_soft_zero': self.cmd_set_soft_zero,
            'reset_to_zero': self.cmd_reset_to_zero,
            'home_lift': self.cmd_home_lift,
            'read_input': self.cmd_read_input,
            'emergency_stop': self.cmd_emergency_stop,
            'execute_pre_scan_motion': self.cmd_execute_pre_scan_motion,
            'execute_object_scan_motion': self.cmd_execute_object_scan_motion,
            'move_and_execute_cycle': self.cmd_move_and_execute_cycle,
            'move_and_lift': self.cmd_move_and_lift,
            'get_calibration': self.cmd_get_calibration,
            'set_calibration': self.cmd_set_calibration,
            'auto_calibrate_lift': self.cmd_auto_calibrate_lift,
            'test_connection': self.cmd_test_connection,
            # 调试工具需要的命令
            'set_speed': self.cmd_set_speed,
            'set_accel': self.cmd_set_accel,
            'stop_axis': self.cmd_stop_axis,
            'continuous_move': self.cmd_continuous_move,
            'continuous_scan_cycle': self.cmd_continuous_scan_cycle,
            'stop_continuous': self.cmd_stop_continuous,
            'get_lift_state': self.cmd_get_lift_state,
            'start_horizontal_sweep': self.cmd_start_horizontal_sweep,
            'stop_horizontal_sweep': self.cmd_stop_horizontal_sweep,
        }

        handler = handlers.get(cmd)
        if handler:
            try:
                return handler(params)
            except Exception as e:
                return {'status': 'error', 'message': str(e)}
        else:
            return {'status': 'error', 'message': f'未知命令: {cmd}'}

    # ==================== 命令处理 ====================

    def cmd_connect(self, params):
        """连接控制器"""
        if self.controller:
            return {'status': 'success', 'message': '已连接'}

        dll_path = params.get('dll_path', 'zauxdll.dll')
        ip = params.get('ip', '192.168.0.11')

        self.controller = ZMotionController(dll_path, ip)
        self.controller.open()

        # 初始化轴0（使用校准参数）
        self.controller.enable_axis(0)
        speed = self.calibration.get('default_speed', 80000)
        accel = self.calibration.get('default_accel', 150000)
        self.controller.set_speed(0, speed)
        self.controller.set_accel(0, accel)

        return {'status': 'success', 'message': '连接成功'}

    def cmd_disconnect(self, params):
        """断开连接"""
        if self.controller:
            self.controller.close()
            self.controller = None
        self._mark_lift_position_unknown()
        return {'status': 'success', 'message': '已断开'}

    def cmd_is_connected(self, params):
        """检查连接状态"""
        connected = self.controller is not None and self.controller.is_connected()
        return {'status': 'success', 'connected': connected}

    def cmd_lift_up(self, params):
        """上升"""
        self._begin_lift_motion('up')
        try:
            self.controller.lift_up()
        except Exception:
            self._mark_lift_position_unknown()
            raise
        return {'status': 'success', 'message': '开始上升'}

    def cmd_lift_down(self, params):
        """下降"""
        self._begin_lift_motion('down')
        try:
            self.controller.lift_down()
        except Exception:
            self._mark_lift_position_unknown()
            raise
        return {'status': 'success', 'message': '开始下降'}

    def cmd_lift_stop(self, params):
        """停止升降"""
        self.controller.lift_stop()
        return {'status': 'success', 'message': '已停止', **self._finish_lift_motion()}

    def cmd_lift_up_duration(self, params):
        """上升指定时间"""
        seconds = max(0.0, float(params.get('seconds', 0.5)))
        self._begin_lift_motion('up', expected_seconds=seconds)
        try:
            self.controller.lift_up_with_duration(seconds)
        except Exception:
            self._mark_lift_position_unknown()
            raise
        return {'status': 'success', 'message': f'上升{seconds}秒完成', **self._finish_lift_motion()}

    def cmd_lift_down_duration(self, params):
        """下降指定时间"""
        seconds = max(0.0, float(params.get('seconds', 0.5)))
        self._begin_lift_motion('down', expected_seconds=seconds)
        try:
            self.controller.lift_down_with_duration(seconds)
        except Exception:
            self._mark_lift_position_unknown()
            raise
        return {'status': 'success', 'message': f'下降{seconds}秒完成', **self._finish_lift_motion()}

    def cmd_lift_down_to_bottom(self, params):
        """一键下降到底（基于校准的下降时间）"""
        safety_margin = max(0.0, float(params.get('safety_margin', 1.0)))
        lift_state = self._get_lift_state()
        if lift_state['position_known']:
            down_time = lift_state['from_bottom_seconds']
            down_source = '最低位计数器'
            applied_safety_margin = 0.0
        else:
            down_time = self.calibration.get('max_down_time', 48.0)
            down_source = '校准兜底'
            applied_safety_margin = safety_margin
        total_time = down_time + applied_safety_margin

        print(f"[*] 开始下降到底，来源={down_source}，预计 {total_time:.1f} 秒...")
        self._begin_lift_motion('down', expected_seconds=total_time)
        try:
            self.controller.lift_down()
            time.sleep(total_time)
        finally:
            self.controller.lift_stop()
        self._set_lift_at_bottom()

        return {
            'status': 'success',
            'message': f'已下降到底（{total_time:.1f}秒）',
            'duration': total_time,
            'safety_margin': applied_safety_margin,
            **self._get_lift_state(),
        }

    def _begin_lift_motion(self, direction, expected_seconds=None):
        with self._lift_state_lock:
            if self._active_lift_motion is not None:
                self._finish_lift_motion()
            self._active_lift_motion = {
                'direction': direction,
                'started_at': time.monotonic(),
                'expected_seconds': expected_seconds,
            }

    def _finish_lift_motion(self):
        with self._lift_state_lock:
            motion = self._active_lift_motion
            if motion is None:
                return self._get_lift_state_locked()
            elapsed = motion['expected_seconds']
            if elapsed is None:
                elapsed = max(0.0, time.monotonic() - motion['started_at'])
            delta = float(elapsed)
            if motion['direction'] == 'down':
                delta = -delta
            if self._lift_position_known:
                self._lift_from_bottom_seconds = max(0.0, self._lift_from_bottom_seconds + delta)
            self._active_lift_motion = None
            return self._get_lift_state_locked()

    def _mark_lift_position_unknown(self):
        with self._lift_state_lock:
            self._lift_position_known = False
            self._active_lift_motion = None

    def _set_lift_at_bottom(self):
        with self._lift_state_lock:
            self._lift_from_bottom_seconds = 0.0
            self._lift_position_known = True
            self._active_lift_motion = None

    def _get_lift_state_locked(self):
        return {
            'from_bottom_seconds': round(self._lift_from_bottom_seconds, 3),
            'position_known': self._lift_position_known,
            'at_bottom': self._lift_position_known and self._lift_from_bottom_seconds <= 0.001,
        }

    def _get_lift_state(self):
        with self._lift_state_lock:
            return self._get_lift_state_locked()

    def cmd_get_lift_state(self, params):
        return {'status': 'success', **self._get_lift_state()}

    def cmd_horizontal_move(self, params):
        """相对移动"""
        pulse = params.get('pulse', 0)

        # 检查软限位
        current_pos = self.controller.get_dpos(0)
        target_pos = current_pos - self.soft_zero + pulse  # 相对于软零点的目标位置

        if target_pos > self.calibration['max_forward_pulse']:
            return {'status': 'error', 'message': f'超出正向软限位 ({self.calibration["max_forward_pulse"]})'}
        if target_pos < self.calibration['max_backward_pulse']:
            return {'status': 'error', 'message': f'超出反向软限位 ({self.calibration["max_backward_pulse"]})'}

        # 使用配置中的默认速度（80000脉冲/秒）
        speed = self.calibration.get('default_speed', 80000)
        accel = self.calibration.get('default_accel', 150000)
        timeout = max(10, abs(pulse) / speed + 2)

        self.controller.set_base(0)
        self.controller.set_speed(0, speed)
        self.controller.set_accel(0, accel)
        self.controller.move_relative(0, pulse)
        self.controller.wait_idle(0, timeout=timeout)

        new_pos = self.controller.get_dpos(0)
        relative_pos = new_pos - self.soft_zero

        return {
            'status': 'success',
            'message': f'移动{pulse}脉冲完成',
            'position': new_pos,
            'relative_position': relative_pos
        }

    def cmd_horizontal_move_abs(self, params):
        """绝对移动（基于软零点）"""
        target_relative = params.get('position', 0)  # 相对于软零点的目标位置
        target_abs = self.soft_zero + target_relative

        # 检查软限位
        if target_relative > self.calibration['max_forward_pulse']:
            return {'status': 'error', 'message': f'超出正向软限位 ({self.calibration["max_forward_pulse"]})'}
        if target_relative < self.calibration['max_backward_pulse']:
            return {'status': 'error', 'message': f'超出反向软限位 ({self.calibration["max_backward_pulse"]})'}

        # 使用配置中的默认速度（80000脉冲/秒）
        current_pos = self.controller.get_dpos(0)
        distance = abs(target_abs - current_pos)
        speed = self.calibration.get('default_speed', 80000)
        accel = self.calibration.get('default_accel', 150000)
        timeout = max(10, distance / speed + 2)

        self.controller.set_base(0)
        self.controller.set_speed(0, speed)
        self.controller.set_accel(0, accel)
        self.controller.move_abs(0, target_abs)
        self.controller.wait_idle(0, timeout=timeout)

        new_pos = self.controller.get_dpos(0)
        relative_pos = new_pos - self.soft_zero

        return {
            'status': 'success',
            'message': f'移动到{target_relative}完成',
            'position': new_pos,
            'relative_position': relative_pos
        }

    def cmd_get_position(self, params):
        """获取位置"""
        pos = self.controller.get_dpos(0)
        relative_pos = pos - self.soft_zero
        return {
            'status': 'success',
            'position': pos,
            'relative_position': relative_pos,
            'soft_zero': self.soft_zero
        }

    def cmd_set_soft_zero(self, params):
        """设置当前位置为软零点"""
        current_pos = self.controller.get_dpos(0)
        self.soft_zero = current_pos
        return {
            'status': 'success',
            'message': f'软零点设置为{current_pos}',
            'soft_zero': self.soft_zero
        }

    def cmd_reset_to_zero(self, params):
        """复位到软零点"""
        current_pos = self.controller.get_dpos(0)
        distance = abs(self.soft_zero - current_pos)

        # 自动计算超时
        speed = 10000
        timeout = max(10, distance / speed + 2)

        self.controller.move_abs(0, self.soft_zero)
        self.controller.wait_idle(0, timeout=timeout)
        return {
            'status': 'success',
            'message': '已复位到软零点',
            'position': self.controller.get_dpos(0),
            'relative_position': 0
        }

    def cmd_home_lift(self, params):
        """升降平台复位到上限位"""
        # 持续上升直到触发上限位
        max_time = self.calibration['max_up_time']
        step = 0.1
        elapsed = 0

        self._begin_lift_motion('up')
        try:
            self.controller.lift_up()
        except Exception:
            self._mark_lift_position_unknown()
            raise
        while elapsed < max_time:
            if not self.controller.read_input(2):  # IN2=0表示上限位触发
                self.controller.lift_stop()
                self._finish_lift_motion()
                print("[+] 已到达上限位")

                # 安全下降
                safe_down = params.get('safe_down', self.calibration['safe_down_distance'])
                if safe_down > 0:
                    down_result = self.cmd_lift_down_duration({'seconds': safe_down})
                    return {'status': 'success', 'message': f'复位完成（下降{safe_down}秒作为安全零点）', **self._get_lift_state()}
                return {'status': 'success', 'message': '复位完成', **self._get_lift_state()}

            time.sleep(step)
            elapsed += step

        self.controller.lift_stop()
        self._mark_lift_position_unknown()
        return {'status': 'error', 'message': f'未能在{max_time}秒内到达上限位'}

    def cmd_read_input(self, params):
        """读取输入点"""
        in_num = params.get('in_num', 0)
        value = self.controller.read_input(in_num)
        return {'status': 'success', 'value': value}

    def cmd_emergency_stop(self, params):
        """紧急停止"""
        self.controller.lift_stop()
        try:
            self.controller.execute_command("RAPIDSTOP")
        except:
            pass
        return {'status': 'success', 'message': '紧急停止已执行', **self._finish_lift_motion()}

    def cmd_move_and_lift(self, params):
        """
        同时执行水平移动和升降运动
        :param params: {
            'pulse': 水平脉冲数,
            'lift_direction': 'up'/'down',
            'lift_seconds': 升降秒数
        }
        """
        pulse = params.get('pulse', 0)
        lift_direction = params.get('lift_direction', 'up')
        lift_seconds = params.get('lift_seconds', 0)

        # 检查软限位
        current_pos = self.controller.get_dpos(0)
        target_pos = current_pos - self.soft_zero + pulse

        if target_pos > self.calibration['max_forward_pulse']:
            return {'status': 'error', 'message': f'超出正向软限位'}
        if target_pos < self.calibration['max_backward_pulse']:
            return {'status': 'error', 'message': f'超出反向软限位'}

        try:
            # 同时启动升降和水平移动
            if lift_direction == 'up':
                self._begin_lift_motion('up', expected_seconds=max(0.0, float(lift_seconds)))
                self.controller.lift_up()
            else:
                self._begin_lift_motion('down', expected_seconds=max(0.0, float(lift_seconds)))
                self.controller.lift_down()

            # 启动水平移动
            speed = 10000
            distance = abs(pulse)
            timeout = max(10, distance / speed + 2)

            self.controller.set_base(0)
            self.controller.move_relative(0, pulse)

            # 等待升降完成（按时间，不强制停止）
            start_time = time.time()
            total_time = max(lift_seconds, timeout) + 2

            while time.time() - start_time < total_time:
                # 检查水平移动是否完成
                resp = self.controller.execute_command("?IDLE(0)")
                if "-1" in resp:
                    # 水平移动完成，等待升降时间自然结束
                    horizontal_done = True

                # 等待升降时间自然结束
                elapsed = time.time() - start_time
                if elapsed >= lift_seconds:
                    # 升降时间到了，强制停止
                    self.controller.lift_stop()
                    lift_state = self._finish_lift_motion()
                    break

                time.sleep(0.1)

            return {
                'status': 'success',
                'message': f'同时移动完成（水平{pulse}脉冲，升降{lift_seconds}秒）',
                'horizontal_pulse': pulse,
                'lift_seconds': lift_seconds,
                **self._get_lift_state()
            }

        except Exception as e:
            self.controller.lift_stop()
            self._mark_lift_position_unknown()
            return {'status': 'error', 'message': str(e)}

    def cmd_execute_pre_scan_motion(self, params):
        """执行扫描前运动"""
        lift_seconds = params.get('lift_seconds', 0)
        horizontal_pulse = params.get('horizontal_pulse', 0)
        reset_first = params.get('reset_first', False)
        safe_down = params.get('safe_down', 0)

        result = {
            'success': True,
            'lift_done': False,
            'horizontal_done': False,
            'reset_done': False,
            'error': None
        }

        try:
            # 1. 先复位（如果需要）
            if reset_first:
                home_result = self.cmd_home_lift({'safe_down': safe_down})
                if home_result['status'] != 'success':
                    raise Exception(home_result['message'])
                result['reset_done'] = True
                time.sleep(0.5)

            # 2. 执行升降
            if lift_seconds != 0:
                if lift_seconds > 0:
                    lift_result = self.cmd_lift_up_duration({'seconds': lift_seconds})
                else:
                    lift_result = self.cmd_lift_down_duration({'seconds': abs(lift_seconds)})
                result['lift_done'] = True
                result['lift_state'] = self._get_lift_state()
                time.sleep(0.3)  # 等待稳定

            # 3. 执行水平移动
            if horizontal_pulse != 0:
                move_result = self.cmd_horizontal_move({'pulse': horizontal_pulse})
                if move_result['status'] != 'success':
                    raise Exception(move_result['message'])
                result['horizontal_done'] = True

        except Exception as e:
            result['success'] = False
            result['error'] = str(e)

        return {'status': 'success' if result['success'] else 'error', **result}

    def cmd_execute_object_scan_motion(self, params):
        """执行物体扫描运动（优化后的流程）
        1. 水平移动到物体位置
        2. 扫描起始位置就绪（假设已在最低点）
        注意：需要确保开始前平台在最低点
        """
        # 检查控制器是否已连接
        if self.controller is None:
            return {'status': 'error', 'message': '控制器未连接，请先调用 connect 命令'}

        horizontal_pulse = params.get('horizontal_pulse', 0)
        scan_cycle_seconds = params.get('scan_cycle_seconds', 2)  # 扫描上下运动的秒数
        obj_type = params.get('object_type', 'unknown')

        result = {
            'success': True,
            'horizontal_done': False,
            'scan_cycle_seconds': scan_cycle_seconds,
            'error': None
        }

        try:
            # 1. 水平移动到物体位置
            if horizontal_pulse != 0:
                print(f"[*] {obj_type}: 水平移动到位置")
                move_result = self.cmd_horizontal_move({'pulse': horizontal_pulse})
                if move_result['status'] != 'success':
                    raise Exception(move_result['message'])
                result['horizontal_done'] = True
                print(f"[+] 水平移动完成，位置: {move_result.get('relative_position', 0)}脉冲")
                time.sleep(0.3)

            # 2. 扫描起始位置就绪（假设已在最低点），后续由应用层控制上下扫描
            print(f"[*] {obj_type}: 扫描起始位置就绪（已在最低点），上下运动 {scan_cycle_seconds}秒/次")

        except Exception as e:
            result['success'] = False
            result['error'] = str(e)
            print(f"[-] {obj_type} 扫描前运动失败: {str(e)}")

        return {'status': 'success' if result['success'] else 'error', **result}

    def cmd_move_and_execute_cycle(self, params):
        """执行一次完整的上下循环运动
        1. 上升到顶部
        2. 下降到最底部
        """
        rise_to_top_seconds = params.get('rise_to_top_seconds', 4)
        down_to_bottom_seconds = params.get('down_to_bottom_seconds', 20)

        result = {
            'success': True,
            'rise_done': False,
            'down_done': False,
            'error': None
        }

        try:
            # 1. 上升到顶部
            self.controller.lift_up_with_duration(rise_to_top_seconds)
            result['rise_done'] = True
            time.sleep(0.3)

            # 2. 下降到最底部
            self.controller.lift_down_with_duration(down_to_bottom_seconds)
            result['down_done'] = True
            time.sleep(0.3)

        except Exception as e:
            result['success'] = False
            result['error'] = str(e)

        return {'status': 'success' if result['success'] else 'error', **result}

    def cmd_get_calibration(self, params):
        """获取校准参数"""
        return {'status': 'success', 'calibration': self.calibration}

    def cmd_set_calibration(self, params):
        """设置校准参数"""
        for key, value in params.items():
            if key in self.calibration:
                self.calibration[key] = value
        return {'status': 'success', 'calibration': self.calibration}

    def cmd_auto_calibrate_lift(self, params):
        """自动校准升降平台"""
        # 持续上升直到上限位，测量总时间
        step = 0.1
        max_attempt = 100  # 10秒
        elapsed = 0

        print("[*] 开始自动校准升降平台...")
        self.controller.lift_up()

        while elapsed < max_attempt * step:
            if not self.controller.read_input(2):  # 上限位触发
                self.controller.lift_stop()
                self.calibration['max_up_time'] = elapsed
                print(f"[+] 上升总时间: {elapsed:.1f}秒")

                # 可选：测量下降时间
                print("[*] 测量下降时间...")
                down_start = time.time()
                self.controller.lift_down()

                # 下降直到某个时间或检测下限位（如果有）
                time.sleep(0.5)
                self.controller.lift_stop()
                down_time = time.time() - down_start

                return {
                    'status': 'success',
                    'max_up_time': elapsed,
                    'calibration': self.calibration
                }

            time.sleep(step)
            elapsed += step

        self.controller.lift_stop()
        return {'status': 'error', 'message': '未能在10秒内到达上限位，请检查限位开关'}

    def cmd_test_connection(self, params):
        """测试连接"""
        return {
            'status': 'success',
            'connected': self.controller is not None and self.controller.is_connected(),
            'service': 'motion_service',
            'version': '1.0'
        }

    # ==================== 调试命令 ====================

    def cmd_set_speed(self, params):
        """设置轴速度"""
        axis = params.get('axis', 0)
        speed = params.get('speed', 80000)
        try:
            self.controller.set_speed(axis, speed)
            return {'status': 'success', 'message': f'设置轴{axis}速度为{speed}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def cmd_set_accel(self, params):
        """设置轴加速度"""
        axis = params.get('axis', 0)
        accel = params.get('accel', 150000)
        try:
            self.controller.set_accel(axis, accel)
            return {'status': 'success', 'message': f'设置轴{axis}加速度为{accel}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def cmd_stop_axis(self, params):
        """停止指定轴"""
        axis = params.get('axis', 0)
        try:
            self.controller.execute_command(f'STOP({axis})')
            return {'status': 'success', 'message': f'已停止轴{axis}'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def cmd_continuous_move(self, params):
        """持续移动（用于调试工具长按按钮）"""
        axis = params.get('axis', 0)
        direction = params.get('direction', 1)  # 1=正向, -1=反向
        speed = params.get('speed', 10000)

        try:
            # 设置速度和方向
            self.controller.set_base(axis)
            self.controller.set_speed(axis, speed)
            self.controller.set_accel(axis, 50000)

            # 发送持续移动命令（使用 MOVE_SPEED 命令）
            if direction > 0:
                self.controller.execute_command(f'MOVE_SPEED({axis},1,{speed})')
            else:
                self.controller.execute_command(f'MOVE_SPEED({axis},-1,{speed})')

            return {'status': 'success', 'message': f'轴{axis}持续移动中'}
        except Exception as e:
            return {'status': 'error', 'message': str(e)}

    def cmd_continuous_scan_cycle(self, params):
        """
        持续扫描循环：上下运动的同时水平来回移动
        :param params: {
            'scan_cycle_seconds': 上下运动秒数,
            'horizontal_pulse': 左右移动范围（脉冲）,
            'horizontal_speed': 水平移动速度（脉冲/秒，默认2000）
        }
        """
        self._stop_continuous = False  # 重置停止标志
        scan_cycle_seconds = params.get('scan_cycle_seconds', 4)
        horizontal_pulse = params.get('horizontal_pulse', 10000)
        horizontal_speed = params.get('horizontal_speed', 2000)

        print(f"[*] 开始持续扫描循环: 上下{scan_cycle_seconds}秒, 左右{horizontal_pulse}脉冲, 速度{horizontal_speed}脉冲/秒")

        try:
            # 设置水平移动速度和加速度
            self.controller.set_speed(0, horizontal_speed)
            self.controller.set_accel(0, horizontal_speed * 2)

            direction = 1  # 1=正向(左), -1=反向(右)
            while not self._stop_continuous:
                # 上升 + 向左/右移动
                self._begin_lift_motion('up')
                self.controller.lift_up()
                self.controller.move_relative(0, horizontal_pulse * direction)
                time.sleep(scan_cycle_seconds)
                self.controller.lift_stop()
                self._finish_lift_motion()
                time.sleep(0.1)

                if self._stop_continuous:
                    break

                # 下降 + 向右/左移动（反向）
                self._begin_lift_motion('down')
                self.controller.lift_down()
                self.controller.move_relative(0, -horizontal_pulse * direction)
                time.sleep(scan_cycle_seconds)
                self.controller.lift_stop()
                self._finish_lift_motion()
                time.sleep(0.1)

                # 切换方向
                direction *= -1

        except Exception as e:
            self.controller.lift_stop()
            self._mark_lift_position_unknown()
            return {'status': 'error', 'message': str(e)}

        self.controller.lift_stop()
        return {'status': 'success', 'message': '持续扫描循环结束', **self._get_lift_state()}

    def cmd_stop_continuous(self, params):
        """停止持续扫描循环"""
        self._stop_continuous = True
        try:
            self.controller.lift_stop()
            self.controller.execute_command('STOP(0)')
            return {'status': 'success', 'message': '已停止升降台和水平轴', **self._finish_lift_motion()}
        except Exception as e:
            return {'status': 'error', 'message': f'停止连续扫描失败: {e}'}

    def cmd_start_horizontal_sweep(self, params):
        """
        启动独立的左右来回移动（与上下运动无关）
        这个命令会在后台线程持续运行，直到被 stop_horizontal_sweep 停止
        :param params: {
            'horizontal_pulse': 左右移动范围（脉冲）,
            'horizontal_speed': 水平移动速度（脉冲/秒，默认2000）
        }
        """
        self._stop_horizontal = False
        self._horizontal_stopped = False
        horizontal_pulse = params.get('horizontal_pulse', 10000)
        horizontal_speed = params.get('horizontal_speed', 2000)

        print(f"[*] 启动左右来回移动: 范围{horizontal_pulse}脉冲, 速度{horizontal_speed}脉冲/秒")

        def horizontal_loop():
            """后台线程执行左右来回移动"""
            try:
                # 设置水平移动速度和加速度
                self.controller.set_speed(0, horizontal_speed)
                self.controller.set_accel(0, horizontal_speed * 2)

                direction = 1  # 1=正向(左), -1=反向(右)
                while not self._stop_horizontal:
                    # 左右来回移动
                    self.controller.move_relative(0, horizontal_pulse * direction)
                    time.sleep(abs(horizontal_pulse) / horizontal_speed + 0.5)
                    direction *= -1

            except Exception as e:
                print(f"[!] 左右来回移动异常: {e}")
            finally:
                self._horizontal_stopped = True
                print(f"[*] 左右来回移动线程结束")

        # 在后台线程执行，立即返回
        threading.Thread(target=horizontal_loop, daemon=True).start()
        return {'status': 'success', 'message': '左右来回移动已启动'}

    def cmd_stop_horizontal_sweep(self, params):
        """停止左右来回移动（立即返回，循环会自然停止）"""
        self._stop_horizontal = True
        return {'status': 'success', 'message': '停止信号已发送'}


if __name__ == '__main__':
    service = MotionService()
    service.start()
