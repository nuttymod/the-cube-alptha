"""Install the original, pinned NuttyMod packages into this edition only."""
from __future__ import annotations

import hashlib
import io
import json
from pathlib import Path, PurePosixPath
import tarfile
import zipfile


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def archive_files(data: bytes, kind: str) -> dict[str, bytes]:
    result = {}
    total = 0
    archive = zipfile.ZipFile(io.BytesIO(data)) if kind == 'zip' else tarfile.open(fileobj=io.BytesIO(data), mode='r:*')
    with archive:
        entries = archive.infolist() if kind == 'zip' else archive.getmembers()
        if len(entries) > 10000:
            raise ValueError('Archive contains too many entries.')
        for entry in entries:
            name = entry.filename if kind == 'zip' else entry.name
            path = PurePosixPath(name.replace('\\', '/'))
            if path.is_absolute() or not path.parts or any(p in {'.', '..'} or ':' in p for p in path.parts):
                raise ValueError('Unsupported archive path: '+name)
            if kind == 'tar' and not (entry.isfile() or entry.isdir()):
                raise ValueError('Archive links and devices are unsupported.')
            if kind == 'zip' and (entry.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError('Archive links are unsupported.')
            key = path.as_posix()
            if any(key.casefold() == previous.casefold() for previous in result):
                raise ValueError('Duplicate archive path: '+name)
            if entry.is_dir() if kind == 'zip' else entry.isdir():
                continue
            total += entry.file_size if kind == 'zip' else entry.size
            if total > 256 * 1024**2:
                raise ValueError('Archive exceeds 256 MB.')
            stream = archive.open(entry) if kind == 'zip' else archive.extractfile(entry)
            with stream:
                result[key] = stream.read()
    return result


def write_json(path: Path, value: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(path.name+'.writing')
    temporary.write_text(json.dumps(value, indent=2)+'\n', encoding='utf-8')
    temporary.replace(path)


def package_payload(root: Path) -> tuple[dict, dict[str, bytes], dict]:
    lock = json.loads((root/'components.lock.json').read_text(encoding='utf-8'))
    original = {}
    for name, spec in lock['packages'].items():
        data = (root/'packages'/name).read_bytes()
        if digest(data) != spec['sha256']:
            raise ValueError('Package checksum mismatch: '+name)
        original[name] = data
    outer = archive_files(original['NuttyMod-Root-1.0.0-Packages.zip'], 'zip')
    bundle = {PurePosixPath(name).name: data for name, data in outer.items()}
    verification = json.loads(archive_files(bundle['nuttymod_cube_verifycation.tar'], 'tar')['verification.json'])
    expected = {'loader_py': digest(bundle['nuttymod_loader.py']),
                'loader_zip': digest(bundle['NuttyMod-Root-Loader.zip']),
                'root_tar': digest(bundle['nuttymod_root.tar']),
                'rootmode_tar': digest(bundle['rootmode.tar'])}
    if verification['schema'] != 1 or verification['sha256'] != expected:
        raise ValueError('The official Root package set does not match its verification TAR.')
    cp = archive_files(bundle['nuttymod_root.tar'], 'tar')
    manifest = json.loads(cp['root_manifest.json'])
    if manifest['schema'] != 1 or manifest['version'] != verification['version']:
        raise ValueError('Root package version mismatch.')
    mode = archive_files(bundle['rootmode.tar'], 'tar')
    if set(mode) != {'root_mode_runtime.py', 'root_mode_loader.py', 'rootmode_manifest.json'}:
        raise ValueError('Root Mode has an unexpected file inventory.')
    if json.loads(mode['rootmode_manifest.json']).get('library') != lock['root']['library']:
        raise ValueError('Root Mode library version mismatch.')
    loaders = archive_files(bundle['NuttyMod-Root-Loader.zip'], 'zip')
    entries = [p for p in loaders if PurePosixPath(p).name == 'nuttymod_loader.py']
    if len(entries) != 1 or loaders[entries[0]] != bundle['nuttymod_loader.py']:
        raise ValueError('Root loader ZIP does not match the verified entry point.')
    prefix = str(PurePosixPath(entries[0]).parent)+'/'
    if any(not name.startswith(prefix) for name in loaders):
        raise ValueError('Root loader files must share one folder.')
    payload = {'userdata/nuttymod/loader/'+name[len(prefix):]: data for name, data in loaders.items()}
    payload.update({'userdata/nuttymod/cp/'+name: data for name, data in cp.items()})
    payload.update({'userdata/nuttymod/cp/'+name: bundle[name] for name in ('nuttymod_root.tar', 'rootmode.tar')})
    payload['userdata/nuttymod_cube_verifycation.tar'] = bundle['nuttymod_cube_verifycation.tar']
    payload.update(mode)
    client = archive_files(original['NuttyMod-Client-1.0.2.tar'], 'tar')
    client_manifest = json.loads(client['custom-cube.json'])
    if client_manifest['api'] != 'CubeBeta/1' or client_manifest['version'] != lock['client']['version']:
        raise ValueError('Unsupported client API or version.')
    for name, checksum in client_manifest['files'].items():
        if digest(client[name]) != checksum:
            raise ValueError('Client source checksum mismatch.')
    if client_manifest['startup'] not in client_manifest['files']:
        raise ValueError('The client startup file is not verified.')
    payload['flash_scripts/nuttymod_client.py'] = client[client_manifest['startup']]
    payload['flash_scripts/alptha_hooks.py'] = (root/'alptha'/'game_hooks.py').read_bytes()
    root_profile = {'schema': 1, 'version': manifest['version'],
                    'loader': 'userdata/nuttymod/loader/nuttymod_loader.py',
                    'files': {name: digest(data) for name, data in payload.items()
                              if name.startswith(('userdata/nuttymod/loader/', 'userdata/nuttymod/cp/'))},
                    'root_mode': {'version': lock['root']['mode'], 'library': lock['root']['library'],
                                  'files': {name: digest(data) for name, data in mode.items()}}}
    profile = {'schema': 1, 'edition': lock['name'], 'verbose_python': True,
               'safety_cube_alerts': True, 'full_rewrite': True, 'loader': None,
               'scripts': ['flash_scripts/nuttymod_client.py', 'flash_scripts/alptha_hooks.py'],
               'nuttymod_root': root_profile}
    return profile, payload, lock


def install(root: Path) -> dict:
    root = root.resolve()
    game = root/'game'
    profile, payload, lock = package_payload(root)
    profile_path = game/'cpe-flash-profile.json'
    first = not profile_path.exists()
    # A failed/partial installation may be resumed, but changed code is never blessed.
    for name, data in payload.items():
        target = game/name
        if target.is_symlink() or not target.resolve().is_relative_to(game.resolve()):
            raise ValueError('Redirected package file: '+name)
        if target.exists() and target.read_bytes() != data:
            raise ValueError('Installed package was modified: '+name+'. Restore it from the bundled packages.')
    if not first and json.loads(profile_path.read_text(encoding='utf-8')) != profile:
        raise ValueError('The installed flash profile has changed. Restore the Alptha profile.')
    for name, data in payload.items():
        target = game/name
        target.parent.mkdir(parents=True, exist_ok=True)
        if not target.exists():
            target.write_bytes(data)
    data_path = game/'userdata'/'userdata.json'
    if not data_path.exists():
        write_json(data_path, {'schema': 1, 'edition': 'The Cube Alptha'})
    preferences = game/'userdata'/'nuttymod'/'settings.json'
    if not preferences.exists():
        write_json(preferences, {'schema': 1, 'game': {'title': lock['name'], 'theme': 'christmas',
                   'gravity': 900, 'music': True, 'sound': True, 'event_interval': 18},
                   'root_mode': {'verbose_loading': True, 'safety': True},
                   'cpe': {'aspire_ip': '127.0.0.1', 'node_port': 4310, 'bridge_enabled': True}})
    if first:
        write_json(profile_path, profile)
        # This new edition ships with application-level Root enabled. Preserve
        # the real CPELoader implementation and its startup/integrity warnings.
        import importlib.util
        spec = importlib.util.spec_from_file_location('_alptha_cpeloader', game/'cpeloader.py')
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
        module.CPELoader(game).unlock()
    write_json(root/'.runtime'/'installed.json', {'schema': 1, 'edition': lock['version'],
               'packages': lock['packages'], 'files': {name: digest(data) for name, data in payload.items()}})
    return lock
