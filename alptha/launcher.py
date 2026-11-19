"""Real connection checks, automatic local setup and owned-process cleanup."""
from __future__ import annotations
import json
import os
from pathlib import Path
import signal
import socket
import subprocess
import sys
import threading
import time
import urllib.request
import uuid
import venv

from .packages import install, write_json
from .tools import ensure_tool


def request(url, data=None):
    payload = None if data is None else json.dumps(data).encode()
    req = urllib.request.Request(url, data=payload, headers={'Content-Type': 'application/json'})
    with urllib.request.urlopen(req, timeout=3) as response:
        return json.load(response)


def verify_connection(node_url, go_url):
    node, cache = request(node_url+'/health'), request(go_url+'/health')
    if not (node.get('ok') and node.get('protocol') == 'CPE/1' and
            node.get('service') == 'cube-physics-engine-node-bridge' and
            cache.get('ok') and cache.get('service') == 'cpe-go-cache'):
        raise RuntimeError('Unexpected CPE service response.')
    token = str(uuid.uuid4())
    response = request(node_url+'/state', {'engine': 'CPE', 'bodies': [], 'particles': [], 'alptha_connection': token})
    cached = request(go_url+'/cache')
    if not response.get('go_cache', {}).get('ok') or cached.get('state', {}).get('alptha_connection') != token:
        raise RuntimeError('Node.js could not send the connection check through to Go.')


class Launcher:
    def __init__(self, root: Path, report=lambda phase, message: print(message, flush=True)):
        self.root = root.resolve()
        self.report = report
        self.cancelled = threading.Event()
        self.processes = []
        self.guard = threading.RLock()
        (self.root/'.runtime'/'logs').mkdir(parents=True, exist_ok=True)

    def start(self, args, name, cwd=None, env=None):
        with self.guard:
            if self.cancelled.is_set():
                raise InterruptedError('Launch cancelled.')
            with (self.root/'.runtime'/'logs'/(name+'.log')).open('ab') as log:
                process = subprocess.Popen([str(arg) for arg in args], cwd=cwd or self.root, env=env,
                    stdout=log, stderr=subprocess.STDOUT,
                    creationflags=subprocess.CREATE_NEW_PROCESS_GROUP if os.name == 'nt' else 0,
                    start_new_session=os.name != 'nt')
            self.processes.append(process)
            return process

    def run(self, args, name, cwd=None, env=None, timeout=1200):
        process = self.start(args, name, cwd, env)
        deadline = time.monotonic()+timeout
        while process.poll() is None:
            if self.cancelled.wait(.1):
                raise InterruptedError('Launch cancelled.')
            if time.monotonic() > deadline:
                raise TimeoutError(name+' timed out. See .runtime/logs/'+name+'.log')
        if process.returncode:
            raise RuntimeError(name+' failed. See .runtime/logs/'+name+'.log')

    def close(self):
        self.cancelled.set()
        with self.guard:
            for process in reversed(self.processes):
                # Aspire may have exited while leaving a child in its process group.
                if os.name == 'nt':
                    if process.poll() is None:
                        subprocess.run(['taskkill', '/PID', str(process.pid), '/T', '/F'], capture_output=True)
                else:
                    try:
                        os.killpg(process.pid, signal.SIGTERM)
                    except ProcessLookupError:
                        pass
            for process in reversed(self.processes):
                try:
                    process.wait(timeout=5)
                except subprocess.TimeoutExpired:
                    if os.name == 'nt':
                        process.kill()
                    else:
                        try:
                            os.killpg(process.pid, signal.SIGKILL)
                        except ProcessLookupError:
                            pass
                    process.wait(timeout=5)

    def prepare_python(self):
        folder = self.root/'.runtime'/'python'
        python = folder/('Scripts/python.exe' if os.name == 'nt' else 'bin/python')
        if not python.exists():
            self.report('packages', 'Creating Alptha’s private Python environment…')
            venv.EnvBuilder(with_pip=True).create(folder)
        check = subprocess.run([str(python), '-c',
            "from importlib.metadata import version; assert version('pygame-ce')=='2.5.8'; assert version('pymunk')=='7.3.1'"],
            capture_output=True, timeout=30)
        if check.returncode:
            self.report('packages', 'Installing pygame-ce and Pymunk…')
            self.run([python, '-m', 'pip', 'install', '--only-binary=:all:', '-r', self.root/'requirements.txt'], 'python-dependencies')
        return python

    def connect(self):
        tools = {}
        for name in ('node', 'dotnet', 'go'):
            self.report(name, 'Checking '+{'node': 'Node.js', 'dotnet': '.NET Aspire', 'go': 'Go'}[name]+'…')
            tools[name] = ensure_tool(name, self.root, self.report, self.cancelled.is_set)
        env = os.environ.copy()
        env['PATH'] = os.pathsep.join([str(path.parent) for path in tools.values()]+[env.get('PATH', '')])
        if '.runtime' in tools['dotnet'].parts:
            env['DOTNET_ROOT'] = str(tools['dotnet'].parent)
        if '.runtime' in tools['go'].parts:
            env['GOROOT'] = str(tools['go'].parent.parent)
        env.update(DOTNET_CLI_TELEMETRY_OPTOUT='1', DOTNET_NOLOGO='1', DOTNET_ROLL_FORWARD='Major', GOTOOLCHAIN='local',
                   CPE_NODE_EXE=str(tools['node']), CPE_GO_EXE=str(tools['go']),
                   ALPTHA_ROOT=str(self.root), ASPNETCORE_URLS='http://127.0.0.1:15271',
                   DOTNET_DASHBOARD_OTLP_ENDPOINT_URL='http://127.0.0.1:21271',
                   DOTNET_RESOURCE_SERVICE_ENDPOINT_URL='http://127.0.0.1:22271',
                   ASPIRE_ALLOW_UNSECURED_TRANSPORT='true', ASPNETCORE_ENVIRONMENT='Development')
        for port in (4310, 4311, 15271, 21271, 22271):
            with socket.socket() as probe:
                try:
                    probe.bind(('127.0.0.1', port))
                except OSError as exc:
                    raise RuntimeError(f'Port {port} is already in use. Close the other CPE/Aspire session and retry.') from exc
        project = self.root/'game'/'cpe'/'CPE.AppHost'/'CPE.AppHost.csproj'
        self.report('dotnet', 'Restoring and building the Aspire connection host…')
        self.run([tools['dotnet'], 'build', project, '--configuration', 'Release', '--nologo',
                  '-p:NuGetAudit=false'], 'aspire-build', env=env)
        self.report('go', 'Building the Go cache service…')
        binary = self.root/'.runtime'/('cpe-go-cache.exe' if os.name == 'nt' else 'cpe-go-cache')
        self.run([tools['go'], 'build', '-buildvcs=false', '-o', binary, '.'], 'go-build', cwd=self.root/'game'/'cpe'/'go-cache', env=env)
        env['CPE_GO_CACHE_EXE'] = str(binary)
        self.report('dotnet', 'Starting Aspire, Node.js and Go…')
        host = self.start([tools['dotnet'], 'run', '--project', project, '--configuration', 'Release',
                           '--no-build', '--no-launch-profile'], 'aspire', env=env)
        deadline = time.monotonic()+90
        node_url, go_url = 'http://127.0.0.1:4310', 'http://127.0.0.1:4311'
        last_error = ''
        while time.monotonic() < deadline:
            if self.cancelled.wait(.25):
                raise InterruptedError('Launch cancelled.')
            if host.poll() is not None:
                raise RuntimeError('Aspire stopped. See .runtime/logs/aspire.log')
            try:
                verify_connection(node_url, go_url)
                # The host is ours and started both services; probe its dashboard too.
                with urllib.request.urlopen('http://127.0.0.1:15271', timeout=3) as response:
                    if response.status != 200:
                        raise RuntimeError('Aspire dashboard is not ready.')
                break
            except (OSError, ValueError, RuntimeError) as exc:
                last_error = str(exc)
        else:
            raise RuntimeError('Connection timed out: '+last_error+'. See .runtime/logs/aspire.log')
        for phase, message in [('node', 'Node.js connected · CPE/1'), ('dotnet', '.NET Aspire connected'), ('go', 'Go connected · cache round trip verified')]:
            self.report(phase, message)
        return env

    def launch(self, connection_only=False):
        try:
            env = self.connect()
            if connection_only:
                self.report('ready', 'All three services connected and verified.')
                return
            self.report('packages', 'Installing and verifying NuttyMod Client, Root and Root Mode…')
            lock = install(self.root)
            python = self.prepare_python()
            self.report('ready', 'Connected. Loading The Cube Alptha…')
            env.update(CPE_BRIDGE_URL='http://127.0.0.1:4310', CPE_GO_CACHE_URL='http://127.0.0.1:4311',
                       CPE_ASPIRE_IP='127.0.0.1', CPE_NODE_PORT='4310', CPE_GO_CACHE_PORT='4311',
                       CPE_DISABLE_BRIDGE='0', PYGAME_HIDE_SUPPORT_PROMPT='1')
            write_json(self.root/'.runtime'/'last-connection.json', {'schema': 1, 'connected': True,
                'node': env['CPE_BRIDGE_URL'], 'go': env['CPE_GO_CACHE_URL'], 'components': lock})
            self.run([python, self.root/'game'/'the_cube_alptha.py'], 'game', cwd=self.root/'game', env=env, timeout=7*24*3600)
            self.report('done', 'Game closed. Stopping connection services…')
        finally:
            self.close()
