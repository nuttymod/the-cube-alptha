"""Find runtimes, or install verified official distributions in .runtime/tools."""
from __future__ import annotations
import hashlib
import json
import os
from pathlib import Path
import platform
import re
import shutil
import subprocess
import tarfile
import urllib.request
import zipfile

HEADERS = {'User-Agent': 'The-Cube-Alptha/0.1'}


def read_json(url):
    with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=45) as response:
        return json.load(response)


def download(url, target, expected=None, algorithm='sha256', cancelled=lambda: False):
    target.parent.mkdir(parents=True, exist_ok=True)
    temporary = target.with_name(target.name+'.partial')
    hasher = hashlib.new(algorithm)
    try:
        with urllib.request.urlopen(urllib.request.Request(url, headers=HEADERS), timeout=60) as source, temporary.open('wb') as output:
            total = 0
            while chunk := source.read(1024*1024):
                if cancelled():
                    raise InterruptedError('Setup cancelled.')
                total += len(chunk)
                if total > 512*1024**2:
                    raise ValueError('Download exceeds the 512 MB limit.')
                output.write(chunk)
                hasher.update(chunk)
        if expected and hasher.hexdigest().casefold() != expected.strip().casefold():
            raise ValueError('Download checksum mismatch: '+target.name)
        temporary.replace(target)
    finally:
        temporary.unlink(missing_ok=True)


def unpack(archive: Path, destination: Path):
    destination.mkdir(parents=True, exist_ok=True)
    base = destination.resolve()
    if archive.suffix == '.zip':
        with zipfile.ZipFile(archive) as bundle:
            for member in bundle.infolist():
                target = (base/member.filename.replace('\\', '/')).resolve()
                if not target.is_relative_to(base) or ':' in member.filename:
                    raise ValueError('Invalid runtime archive path.')
            bundle.extractall(base)
    else:
        with tarfile.open(archive, 'r:*') as bundle:
            # Validate everything before extracting; official runtimes contain
            # internal links (for example Node's npm executable).
            for member in bundle.getmembers():
                target = (base/member.name).resolve()
                if not target.is_relative_to(base) or member.isdev() or member.isfifo():
                    raise ValueError('Invalid runtime archive member.')
                if member.issym() or member.islnk():
                    link = (target.parent/member.linkname if member.issym() else base/member.linkname).resolve()
                    if not link.is_relative_to(base):
                        raise ValueError('Runtime archive link escapes its directory.')
            bundle.extractall(base, filter='data')


def compatible(name, executable):
    try:
        args = ['--list-sdks'] if name == 'dotnet' else ['version'] if name == 'go' else ['--version']
        result = subprocess.run([str(executable), *args], capture_output=True, text=True, timeout=20)
        if result.returncode:
            return False
        text = result.stdout
        if name == 'dotnet':
            return any(int(v) >= 10 for v in re.findall(r'^(\d+)\.', text, re.M))
        match = re.search(r'(?:go|v)?(\d+)\.(\d+)', text)
        return bool(match) and tuple(map(int, match.groups())) >= ((1, 24) if name == 'go' else (20, 0))
    except (OSError, subprocess.SubprocessError):
        return False


def ensure_tool(name, root: Path, report, cancelled=lambda: False) -> Path:
    executable = name+('.exe' if os.name == 'nt' else '')
    folder = root/'.runtime'/'tools'/name
    candidates = [shutil.which(name), *folder.glob('**/'+executable)]
    for candidate in candidates:
        if candidate and compatible(name, candidate):
            return Path(candidate).resolve()
    system = {'Windows': 'win', 'Linux': 'linux', 'Darwin': 'osx'}.get(platform.system())
    arch = {'x86_64': 'x64', 'AMD64': 'x64', 'aarch64': 'arm64', 'arm64': 'arm64'}.get(platform.machine())
    if not system or not arch:
        raise RuntimeError('Automatic runtime setup supports Windows, Linux and macOS on x64/arm64.')
    report('setup', 'Installing '+name+' from its official distribution…')
    if name == 'node':
        releases = read_json('https://nodejs.org/dist/index.json')
        version = next(r['version'] for r in releases if r['lts'])
        os_part = 'darwin' if system == 'osx' else system
        filename = f'node-{version}-{os_part}-{arch}'+('.zip' if system == 'win' else '.tar.xz')
        base = f'https://nodejs.org/dist/{version}/'
        with urllib.request.urlopen(base+'SHASUMS256.txt', timeout=45) as response:
            sums = dict((line.split()[1].lstrip('*'), line.split()[0]) for line in response.read().decode().splitlines() if len(line.split()) == 2)
        url, checksum, algorithm = base+filename, sums[filename], 'sha256'
    elif name == 'go':
        version = read_json('https://go.dev/dl/?mode=json')[0]
        item = next(f for f in version['files'] if f['os'] == ('windows' if system == 'win' else 'darwin' if system == 'osx' else system)
                    and f['arch'] == ('amd64' if arch == 'x64' else arch) and f['kind'] == 'archive')
        filename, checksum, algorithm = item['filename'], item['sha256'], 'sha256'
        url = 'https://go.dev/dl/'+filename
    else:
        releases = read_json('https://builds.dotnet.microsoft.com/dotnet/release-metadata/10.0/releases.json')
        sdk = releases['latest-sdk']
        record = next(s for release in releases['releases'] for s in release.get('sdks', []) if s['version'] == sdk)
        item = next(f for f in record['files'] if f['rid'] == f'{system}-{arch}' and f['name'].endswith('.zip' if system == 'win' else '.tar.gz'))
        url, checksum, algorithm = item['url'], item['hash'], 'sha512'
        filename = url.rsplit('/', 1)[-1]
    archive = root/'.runtime'/'downloads'/filename
    download(url, archive, checksum, algorithm, cancelled)
    if folder.exists():
        shutil.rmtree(folder)
    unpack(archive, folder)
    for candidate in folder.glob('**/'+executable):
        if candidate.is_file() and compatible(name, candidate):
            return candidate.resolve()
    raise RuntimeError('The downloaded runtime could not start: '+name)
