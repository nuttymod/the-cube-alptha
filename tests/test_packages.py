import io
import json
from pathlib import Path
import shutil
import tarfile
import tempfile
import unittest

from alptha.packages import archive_files, install, package_payload

ROOT = Path(__file__).resolve().parents[1]


class PackageTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix='alptha-test-')
        self.addCleanup(self.temp.cleanup)
        self.root = Path(self.temp.name)
        for name in ('packages', 'alptha'):
            shutil.copytree(ROOT/name, self.root/name, ignore=shutil.ignore_patterns('__pycache__'))
        shutil.copy2(ROOT/'components.lock.json', self.root)
        (self.root/'game').mkdir()
        for name in ('cpeloader.py', 'cpeloader_core_runtime.js', 'cpeloader_core.rb'):
            shutil.copy2(ROOT/'game'/name, self.root/'game'/name)

    def test_original_packages_install_with_complete_root_inventory(self):
        lock = install(self.root)
        game = self.root/'game'
        self.assertEqual(lock['client']['version'], '1.0.2')
        for name in ('userdata/nuttymod/cp/nuttymod_root.tar', 'userdata/nuttymod/cp/rootmode.tar',
                     'userdata/nuttymod_cube_verifycation.tar', 'root_mode_runtime.py',
                     'flash_scripts/nuttymod_client.py'):
            self.assertTrue((game/name).is_file(), name)
        profile = json.loads((game/'cpe-flash-profile.json').read_text())
        self.assertEqual(profile['nuttymod_root']['root_mode']['library'], '1.2')
        state = json.loads((game/'cpeloader_state.json').read_text())
        self.assertTrue(state['unlocked'])

    def test_repeat_install_preserves_preferences_and_loader_lock(self):
        install(self.root)
        game = self.root/'game'
        settings = game/'userdata/nuttymod/settings.json'
        value = json.loads(settings.read_text())
        value['game']['title'] = 'My Alptha'
        settings.write_text(json.dumps(value))
        state = game/'cpeloader_state.json'
        state.write_text('{"unlocked": false}')
        install(self.root)
        self.assertEqual(json.loads(settings.read_text())['game']['title'], 'My Alptha')
        self.assertFalse(json.loads(state.read_text())['unlocked'])

    def test_modified_client_is_not_silently_overwritten(self):
        install(self.root)
        client = self.root/'game/flash_scripts/nuttymod_client.py'
        client.write_text('modified')
        with self.assertRaisesRegex(ValueError, 'modified'):
            install(self.root)
        self.assertEqual(client.read_text(), 'modified')

    def test_corrupt_bundle_is_rejected_before_installing(self):
        path = self.root/'packages/NuttyMod-Root-1.0.0-Packages.zip'
        path.write_bytes(path.read_bytes()+b'corrupt')
        with self.assertRaisesRegex(ValueError, 'checksum'):
            install(self.root)
        self.assertFalse((self.root/'game/userdata').exists())

    def test_archive_escape_and_symlink_rejected(self):
        for name, link in [('../escape.py', False), ('loader.py', True)]:
            buffer = io.BytesIO()
            with tarfile.open(fileobj=buffer, mode='w') as tar:
                member = tarfile.TarInfo(name)
                if link:
                    member.type = tarfile.SYMTYPE
                    member.linkname = '../outside'
                tar.addfile(member)
            with self.assertRaises(ValueError):
                archive_files(buffer.getvalue(), 'tar')


if __name__ == '__main__':
    unittest.main()
