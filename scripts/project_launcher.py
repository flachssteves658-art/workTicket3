"""Windows launcher for workTicket3 and its local camera services (stdlib only)."""
from __future__ import annotations

import argparse
import contextlib
import ctypes
from ctypes import wintypes
from datetime import datetime
import hashlib
import json
import os
from pathlib import Path
import re
import shutil
import socket
import subprocess
import sys
import time
from urllib.request import ProxyHandler, Request, build_opener
import webbrowser

ROOT = Path(__file__).resolve().parents[1]
RUNTIME = ROOT / '.launcher'
STATE = RUNTIME / 'processes.json'
HTTP = build_opener(ProxyHandler({}))
NO_WINDOW = getattr(subprocess, 'CREATE_NO_WINDOW', 0)
_LOCK_HELD = False


def say(message):
    print(message, flush=True)


def read_env(root):
    result = {}
    path = Path(root) / '.env'
    if path.exists():
        for line in path.read_text(encoding='utf-8-sig').splitlines():
            match = re.match(r'^\s*(?:export\s+)?([A-Za-z_]\w*)\s*=\s*(.*)$', line)
            if match:
                value = match[2].strip()
                if len(value) >= 2 and value[0] == value[-1] and value[0] in "\"'":
                    value = value[1:-1]
                else:
                    value = re.split(r'\s+#', value, maxsplit=1)[0]
                result[match[1]] = value
    return result


def fingerprint(pid):
    """PID plus kernel creation time and image path protects against PID reuse."""
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel.OpenProcess.restype = wintypes.HANDLE
    kernel.GetProcessTimes.argtypes = [wintypes.HANDLE] + [ctypes.POINTER(wintypes.FILETIME)] * 4
    kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
    kernel.QueryFullProcessImageNameW.argtypes = [wintypes.HANDLE, wintypes.DWORD, wintypes.LPWSTR, ctypes.POINTER(wintypes.DWORD)]
    kernel.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel.OpenProcess(0x1000, False, int(pid))
    if not handle:
        return None
    try:
        exit_code = wintypes.DWORD()
        if not kernel.GetExitCodeProcess(handle, ctypes.byref(exit_code)) or exit_code.value != 259:
            return None
        stamps = [wintypes.FILETIME() for _ in range(4)]
        if not kernel.GetProcessTimes(handle, *(ctypes.byref(v) for v in stamps)):
            return None
        buffer = ctypes.create_unicode_buffer(32768)
        size = wintypes.DWORD(len(buffer))
        if not kernel.QueryFullProcessImageNameW(handle, 0, buffer, ctypes.byref(size)):
            return None
        return {'pid': int(pid), 'created': (stamps[0].dwHighDateTime << 32) | stamps[0].dwLowDateTime,
                'image': os.path.normcase(buffer.value)}
    finally:
        kernel.CloseHandle(handle)


def owned_alive(record):
    saved = record.get('identity')
    return bool(saved and fingerprint(saved['pid']) == saved)


def load_state():
    return json.loads(STATE.read_text(encoding='utf-8')) if STATE.exists() else {}


def save_state(state):
    temporary = STATE.with_suffix('.tmp')
    temporary.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding='utf-8')
    temporary.replace(STATE)


@contextlib.contextmanager
def lock():
    global _LOCK_HELD
    RUNTIME.mkdir(parents=True, exist_ok=True)
    if _LOCK_HELD:
        raise RuntimeError('另一个启动/停止操作正在执行，请等它完成。')
    kernel = ctypes.WinDLL('kernel32', use_last_error=True)
    name_hash = hashlib.sha256(str(ROOT).lower().encode('utf-8')).hexdigest()[:24]
    handle = kernel.CreateMutexW(None, True, f'Local\\WorkTicketLauncher-{name_hash}')
    if not handle:
        raise RuntimeError('无法创建启动器互斥锁。')
    acquired = ctypes.get_last_error() != 183
    if not acquired:
        acquired = kernel.WaitForSingleObject(handle, 0) == 0
    if not acquired:
        kernel.CloseHandle(handle)
        raise RuntimeError('另一个启动/停止操作正在执行，请等它完成。')
    _LOCK_HELD = True
    try:
        yield
    finally:
        _LOCK_HELD = False
        kernel.ReleaseMutex(handle)
        kernel.CloseHandle(handle)


def port_open(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=0.5):
            return True
    except OSError:
        return False


def ready(service):
    if not service['port']:
        return False
    path = '/' if service['name'] == 'video-web' else '/openapi.json'
    try:
        with HTTP.open(f"http://127.0.0.1:{service['port']}{path}", timeout=2) as response:
            content = response.read(4_000_000).decode('utf-8')
        if service['name'] == 'video-web':
            return 'Construction Hazard Detection' in content and '/@vite/client' in content
        data = json.loads(content)
        return all(key in data.get('paths', {}) for key in service['routes'])
    except (OSError, ValueError):
        return False


def process_env(python, root, extra=None):
    env = os.environ.copy()
    for key in list(env):
        if key.upper() in {'PYTHONHOME', 'PYTHONPATH', 'VIRTUAL_ENV'} or key.upper().startswith('CONDA_'):
            env.pop(key, None)
    env.update(read_env(root))
    base = Path(python).parent
    if base.name.lower() == 'scripts':
        cfg = base.parent / 'pyvenv.cfg'
        if cfg.exists():
            home = re.search(r'^home\s*=\s*(.+)$', cfg.read_text(), re.M)
            if home:
                base = Path(home[1].strip())
        env['VIRTUAL_ENV'] = str(Path(python).parent.parent)
    env['PATH'] = os.pathsep.join([str(base), str(base / 'Library' / 'bin'), str(base / 'Scripts'), env.get('PATH', '')])
    env.update(PYTHONUTF8='1', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1')
    for key in ('NO_PROXY', 'no_proxy'):
        env[key] = ','.join(filter(None, [env.get(key, ''), '127.0.0.1', 'localhost', '::1']))
    env.update(extra or {})
    return env


def find_node(config):
    explicit = config.get('node_executable')
    if explicit:
        return str(Path(explicit))
    candidates = [shutil.which('node'), str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'nodejs/node.exe'),
                  str(Path(os.environ.get('USERPROFILE', '')) / '.cache/codex-runtimes/codex-primary-runtime/dependencies/node/bin/node.exe')]
    return next((p for p in candidates if p and Path(p).is_file()), '')


def services(config, mode):
    ticket = Path(config['ticket_root'])
    hazard = Path(config['hazard_root'])
    hp = config['hazard_python']
    tp = str(ticket / '.venv/Scripts/python.exe')
    henv = read_env(hazard)
    common = {'DB_MANAGEMENT_API_URL': 'http://127.0.0.1:8005', 'STREAMING_API_URL': 'http://127.0.0.1:8800',
              'VIOLATION_RECORD_API_URL': 'http://127.0.0.1:8002', 'DETECT_API_URL': 'http://127.0.0.1:8000'}
    result = []

    def api(name, root, python, module, port, routes, extra=None):
        result.append({'name': name, 'cwd': str(root), 'port': port, 'routes': routes,
                       'command': [python, '-u', '-X', 'utf8', '-m', 'uvicorn', module, '--host', '127.0.0.1', '--port', str(port), '--workers', '1'],
                       'env': process_env(python, root, extra)})

    api('database', hazard, hp, 'examples.db_management.app:app', 8005, ['/integration/catalog/status'], common)
    ticket_extra = {'HAZARD_DBM_BASE_URL': 'http://127.0.0.1:8005'}
    if henv.get('INTEGRATION_TOKEN'):
        ticket_extra['HAZARD_INTEGRATION_TOKEN'] = henv['INTEGRATION_TOKEN']
    api('work-ticket', ticket, tp, 'app.main:app', 8880, ['/api/recognize-structure-stream'], ticket_extra)
    if mode == 'ticket':
        return result
    api('violations', hazard, hp, 'examples.violation_records.app:app', 8002, ['/upload', '/violations'], common)
    api('streaming', hazard, hp, 'examples.streaming_web.backend.app:app', 8800, ['/labels', '/frames'], common)
    if config.get('detection_api', True):
        api('yolo-api', hazard, hp, 'examples.YOLO_server_api.backend.app:app', 8000, ['/detect'], common)
    cred = henv.get('FIREBASE_CRED_PATH', '')
    credential_path = hazard / cred
    notification_option = config.get('notifications', 'auto')
    notify = notification_option is True or (notification_option == 'auto' and bool(cred) and credential_path.is_file())
    if notify:
        if not cred or not credential_path.is_file():
            raise RuntimeError('手机推送已启用，但 FIREBASE_CRED_PATH 凭证文件不存在。')
        api('notifications', hazard, hp, 'examples.local_notification_server.app:app', 8003, ['/send_fcm_notification'],
            {**common, 'FIREBASE_PROJECT_ID': henv.get('FIREBASE_PROJECT_ID') or henv.get('project_id', '')})
    report_mode = henv.get('AGENT_REPORT_MODE', 'llm').lower().strip()
    if report_mode not in {'off', 'disabled', 'false', '0', 'none', 'mock', 'test'}:
        report_url = henv.get('TICKET_AGENT_API_URL', 'http://127.0.0.1:8011/api/v1/generate_violation_report')
        if report_url.startswith(('http://127.0.0.1:8011/', 'http://localhost:8011/')):
            api('legacy-report', hazard.parent, config['legacy_python'], 'ticket.service.api_server:app', 8011,
                ['/api/v1/generate_violation_report'])
    result.append({'name': 'video-web', 'cwd': str(hazard / 'examples/streaming_web/frontend'), 'port': 8888, 'routes': [],
                   'command': [find_node(config), str(hazard / 'examples/streaming_web/frontend/node_modules/vite/bin/vite.js'), '--host', '127.0.0.1', '--port', '8888', '--strictPort'],
                   'env': process_env(hp, hazard, {'VITE_PLATFORM_API_URL': 'http://127.0.0.1:8005',
                          'VITE_STREAMING_BACKEND_API_URL': 'http://127.0.0.1:8800', 'VITE_VIOLATION_API_URL': 'http://127.0.0.1:8002'})})
    result.append({'name': 'camera-ai', 'cwd': str(hazard), 'port': None, 'routes': [],
                   'command': [hp, '-u', str(hazard / 'main.py'), '--poll', '10'],
                   'env': process_env(hp, hazard, {**common, 'FCM_ENABLED': '1' if notify else '0', 'FCM_API_URL': 'http://127.0.0.1:8003'})})
    return result


def preflight(config, selected):
    for service in selected:
        if not Path(service['cwd']).is_dir():
            raise RuntimeError(f"项目目录不存在：{service['cwd']}")
        exe = service['command'][0]
        if not exe or not Path(exe).is_file():
            raise RuntimeError(f"{service['name']} 的运行环境不存在，请检查 project-launcher.json 中的路径。")
        if service['name'] == 'video-web' and not Path(service['command'][1]).is_file():
            raise RuntimeError('视频前端缺少依赖。请在 examples/streaming_web/frontend 目录先运行 npm install。')
    for key in ('ticket_root', 'hazard_root'):
        if not (Path(config[key]) / '.env').is_file():
            raise RuntimeError(f"缺少配置文件：{Path(config[key]) / '.env'}")
    hazard_env = read_env(config['hazard_root'])
    if not hazard_env.get('INTEGRATION_TOKEN'):
        raise RuntimeError('检测项目 .env 缺少 INTEGRATION_TOKEN，无法执行工作票数据库联动。')
    database_url = hazard_env.get('DATABASE_URL', '')
    if not re.search(r'@(127\.0\.0\.1|localhost):13306/', database_url):
        raise RuntimeError('本启动器使用本机 Docker：DATABASE_URL 应连接 127.0.0.1:13306。请核对配置。')
    if hazard_env.get('REDIS_HOST') not in {'127.0.0.1', 'localhost'} or hazard_env.get('REDIS_PORT') != '16379':
        raise RuntimeError('本启动器使用本机 Docker：REDIS_HOST 应为 127.0.0.1，REDIS_PORT 应为 16379。')
    if any(s['name'] == 'camera-ai' for s in selected):
        main_source = (Path(config['hazard_root']) / 'main.py').read_text(encoding='utf-8-sig')
        if 'FCM_ENABLED' not in main_source:
            raise RuntimeError('检测项目缺少启动器所需的 FCM_ENABLED 开关，请重新安装完整启动工具。')


def docker_databases(config, start):
    docker = shutil.which('docker') or str(Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Docker/Docker/resources/bin/docker.exe')
    if not Path(docker).is_file():
        raise RuntimeError('找不到 Docker Desktop，请先安装并启动它。')
    for key, internal, external in [('mysql_container', '3306/tcp', 13306), ('redis_container', '6379/tcp', 16379)]:
        name = config[key]
        info = subprocess.run([docker, 'inspect', name], capture_output=True, text=True, encoding='utf-8', errors='replace', timeout=20, creationflags=NO_WINDOW)
        if info.returncode:
            raise RuntimeError(f'Docker 未就绪或容器 {name} 不存在。请打开 Docker Desktop，检查已有容器。')
        data = json.loads(info.stdout)[0]
        bindings = data.get('HostConfig', {}).get('PortBindings', {}).get(internal) or []
        if not any(str(row.get('HostPort')) == str(external) for row in bindings):
            raise RuntimeError(f'容器 {name} 未配置预期的 {external} 端口映射。')
        if not data['State']['Running']:
            if not start:
                say(f'[待启动] Docker {name}')
                continue
            run = subprocess.run([docker, 'start', name], capture_output=True, timeout=30, creationflags=NO_WINDOW)
            if run.returncode:
                raise RuntimeError(f'启动容器 {name} 失败，请检查端口 {external} 是否被其他程序占用。')
        deadline = time.monotonic() + (40 if start else 2)
        while not port_open(external) and time.monotonic() < deadline:
            time.sleep(0.5)
        if not port_open(external):
            raise RuntimeError(f'{name} 容器正在运行，但端口 {external} 尚未就绪。')
        say(f'[可用] Docker {name} :{external}')


def stop_record(name, record):
    if not record.get('identity'):
        say(f'[保留] {name} 是启动器外部的服务，请在原窗口停止。')
        return True
    if not owned_alive(record):
        say(f'[已退出] {name}')
        return True
    pid = record['identity']['pid']
    # Never stop by image name or by port; only our saved PID + creation time + executable.
    subprocess.run(['taskkill.exe', '/PID', str(pid), '/T', '/F'], capture_output=True, timeout=20, creationflags=NO_WINDOW)
    if owned_alive(record):
        # Exact-PID fallback for restricted shells where taskkill is denied.
        kernel = ctypes.WinDLL('kernel32', use_last_error=True)
        handle = kernel.OpenProcess(0x0001 | 0x100000, False, int(pid))
        if handle:
            try:
                kernel.TerminateProcess(handle, 1)
            finally:
                kernel.CloseHandle(handle)
    deadline = time.monotonic() + 5
    while owned_alive(record) and time.monotonic() < deadline:
        time.sleep(0.1)
    if owned_alive(record):
        say(f'[停止失败] {name} PID={pid}，保留状态供下次重试。')
        return False
    say(f'[已停止] {name}')
    return True


def start_service(service, state, timeout):
    name = service['name']
    old = state.get(name)
    if old and owned_alive(old):
        if service['port'] and not ready(service):
            raise RuntimeError(f'{name} 进程仍在，但接口未就绪。请查看日志或先执行 stop-all.cmd。')
        say(f'[已运行] {name}')
        return False
    if service['port'] and port_open(service['port']):
        if not ready(service):
            raise RuntimeError(f"端口 {service['port']} 被其他程序占用，或对应服务尚未就绪。不会强行结束该进程。")
        state[name] = {'port': service['port'], 'external': True}
        save_state(state)
        say(f"[复用外部服务] {name} :{service['port']}（统一停止不会关闭它）")
        return False
    if name == 'camera-ai':
        script = "Get-CimInstance Win32_Process -Filter \"Name='python.exe'\" | Where-Object { $_.CommandLine -match '(?i)(?:^|[ /\\\\\"])(?:main\\.py)(?:[\" ]|$)' } | Select-Object -ExpandProperty ProcessId"
        probe = subprocess.run(['powershell.exe', '-NoProfile', '-Command', script], capture_output=True, text=True, timeout=15, creationflags=NO_WINDOW)
        if probe.returncode != 0:
            raise RuntimeError('无法检查已有摄像头进程，暂不重复启动。请检查系统进程查询权限。')
        if probe.stdout.strip():
            raise RuntimeError('检测到其他手动运行的 main.py，请先在原终端按 Ctrl+C，再启动完整项目。')
    log_dir = RUNTIME / 'logs'
    log_dir.mkdir(parents=True, exist_ok=True)
    log_path = log_dir / f"{name}-{datetime.now():%Y%m%d-%H%M%S-%f}.log"
    say(f"[启动] {name}" + (f" :{service['port']}" if service['port'] else ''))
    with log_path.open('ab', buffering=0) as output:
        process = subprocess.Popen(service['command'], cwd=service['cwd'], env=service['env'],
                                   stdin=subprocess.DEVNULL, stdout=output, stderr=subprocess.STDOUT, creationflags=NO_WINDOW)
    identity = fingerprint(process.pid)
    if not identity:
        # The direct child is still held by Popen; no PID lookup or broad termination.
        if process.poll() is None:
            process.terminate()
        raise RuntimeError(f'{name} 无法取得进程身份，日志：{log_path}')
    state[name] = {'identity': identity, 'port': service['port'], 'log': str(log_path)}
    save_state(state)
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(f'{name} 启动退出（代码 {process.returncode}）。日志：{log_path}')
        if service['port'] and ready(service):
            say(f'[就绪] {name}')
            return True
        if not service['port'] and time.monotonic() >= deadline - timeout + 5:
            say(f'[进程已启动] {name}，模型加载和摄像头连接结果请查看日志。')
            return True
        time.sleep(0.5)
    raise RuntimeError(f'{name} 等待接口超时。日志：{log_path}')


def show_status(config):
    state = load_state()
    known = {'database': 8005, 'work-ticket': 8880, 'violations': 8002, 'streaming': 8800,
             'yolo-api': 8000, 'notifications': 8003, 'legacy-report': 8011, 'video-web': 8888, 'camera-ai': None}
    for name, port in known.items():
        record = state.get(name, {})
        status = '启动器进程运行中' if owned_alive(record) else ('端口有服务（外部/未托管）' if port and port_open(port) else '未运行')
        say(f'{name:16} {str(port or "-"):5} {status}')
        if record.get('log'):
            say(f"  日志：{record['log']}")
    say('工作票：http://127.0.0.1:8880/    视频：http://127.0.0.1:8888/')
    say('进程/端口状态不代表 OCR、模型推理或真实摄像头已通过测试。')


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('action', choices=['start', 'stop', 'status', 'check'])
    parser.add_argument('--mode', choices=['ticket', 'full'], default='ticket')
    parser.add_argument('--no-browser', action='store_true')
    args = parser.parse_args()
    config = json.loads((ROOT / 'project-launcher.json').read_text(encoding='utf-8-sig'))
    if args.action == 'status':
        show_status(config)
        return 0
    if args.action == 'stop':
        with lock():
            state = load_state()
            for name in list(state)[::-1]:
                if stop_record(name, state[name]):
                    del state[name]
                    save_state(state)
            say('已处理启动器管理的服务；MySQL、Redis和外部服务保持运行。')
            return 1 if state else 0
    selected = services(config, args.mode)
    preflight(config, selected)
    if args.action == 'check':
        say('[通过] 项目路径、解释器、前端依赖、数据库端点配置。')
        docker_databases(config, start=False)
        for service in selected:
            if service['port'] and port_open(service['port']):
                if not ready(service):
                    raise RuntimeError(f"端口 {service['port']} 有占用，但不是预期的就绪服务。")
                say(f"[可复用] {service['name']} :{service['port']}")
        say('检查完成。尚未执行 OCR 推理、连接摄像头或调用收费大模型接口。')
        return 0
    with lock():
        state = load_state()
        before = {name: record.get('identity') for name, record in state.items()}
        try:
            docker_databases(config, start=True)
            say('工作票子进程使用检测后端的集成令牌；不修改现有 .env。')
            if args.mode == 'full' and not any(s['name'] == 'notifications' for s in selected):
                say('未启用手机推送；页面告警和违规记录正常保留。')
            for service in selected:
                start_service(service, state, int(config.get('startup_timeout_seconds', 120)))
            # Test the authenticated catalog link; catches a reused backend with a different token.
            token = read_env(config['hazard_root'])['INTEGRATION_TOKEN']
            req = Request('http://127.0.0.1:8005/integration/catalog/status', headers={'X-Integration-Token': token})
            with HTTP.open(req, timeout=15) as response:
                json.loads(response.read())
        except BaseException:
            say('启动未完成，回收本次新启动的服务；之前已有服务和数据库保持运行。')
            for name in list(state)[::-1]:
                record = state[name]
                if record.get('identity') and record['identity'] != before.get(name):
                    if stop_record(name, record):
                        del state[name]
                        save_state(state)
            raise
    say('启动完成。可以关闭此控制窗口，后台服务将继续运行。')
    say('工作票：http://127.0.0.1:8880/')
    if args.mode == 'full':
        say('视频：http://127.0.0.1:8888/')
    say(f'日志目录：{RUNTIME / "logs"}')
    say('结束使用时，双击 stop-all.cmd。')
    if not args.no_browser:
        webbrowser.open('http://127.0.0.1:8880/')
        if args.mode == 'full':
            webbrowser.open('http://127.0.0.1:8888/')
    return 0


if __name__ == '__main__':
    try:
        sys.exit(main())
    except KeyboardInterrupt:
        say('操作已取消。')
        sys.exit(130)
    except Exception as exc:
        # Don't echo upstream HTTP bodies or credentials in configuration exceptions.
        say(f'[错误] {exc}')
        sys.exit(1)
