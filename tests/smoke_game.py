"""Run the real game with the real Root packages, without network or player data."""
import json
import logging
import os
from pathlib import Path
import shutil
import sys
import tempfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from alptha.packages import install

os.environ.update(SDL_VIDEODRIVER='dummy', SDL_AUDIODRIVER='dummy',
                  CPE_DISABLE_BRIDGE='1', PYGAME_HIDE_SUPPORT_PROMPT='1')

with tempfile.TemporaryDirectory(prefix='alptha-game-') as folder:
    stage = Path(folder)
    for name in ('game', 'alptha', 'packages'):
        shutil.copytree(ROOT/name, stage/name, ignore=shutil.ignore_patterns(
            '__pycache__', 'userdata', 'flash_scripts', 'cpe-flash-profile.json',
            'cpeloader_state.json', 'cpeloader_manifest.json', 'settings.json', '*_state.json',
            '.nuttymod*.json', 'bin', 'obj', 'backup', 'legacy-versions', 'og-recovery'))
    shutil.copy2(ROOT/'components.lock.json', stage)
    install(stage)
    sys.path.insert(0, str(stage/'game'))
    os.chdir(stage/'game')
    import pygame
    import cube_core
    from cpe.performance import fast_enabled
    from the_cube_beta_summer import GameApp
    app = GameApp()
    assert app.nuttymod_root_enabled and app.root_mode_enabled and app.nuttymod_client_enabled
    assert app.nuttymod_loader_version == '1.4.5'
    assert pygame.display.get_caption()[0] == 'The Cube Alptha'
    client = app.nuttymod_client
    assert client.root_ready()
    frames = [0]
    original = app.draw_toast
    original_update = cube_core.PhysicsWorld.update
    output = ROOT/'docs'
    output.mkdir(exist_ok=True)

    def draw():
        frames[0] += 1
        frame = frames[0]
        if frame == 1:
            client.activate('optimizer')
            assert client.optimizer_active and fast_enabled() and client.world.cpe.fast_mode
            assert client.world.space.iterations == 12
            assert client.world.cpe.particles.max_particles == 800
        if frame in (3, 4, 5):
            client.open = True
            client.tab = {3: 'CPE Basic', 4: 'CPE Advanced', 5: 'Root'}[frame]
        if frame == 6:
            client.open = False
            client.activate('optimizer')
            assert not client.optimizer_active
        original()
        if frame in (3, 4, 5):
            pygame.image.save(app.screen, str(output/(client.tab.lower().replace(' ', '-')+'.png')))
        if frame == 8:
            pygame.image.save(app.screen, str(output/'gameplay.png'))
        if frame == 12:
            pygame.event.post(pygame.event.Event(pygame.KEYDOWN, key=pygame.K_ESCAPE, mod=0))

    app.draw_toast = draw
    app.run_simulation()
    assert frames[0] == 12
    assert cube_core.PhysicsWorld.update is original_update
    assert not fast_enabled()
    pygame.quit()
    logging.shutdown()
    report = {'frames': frames[0], 'real_root_packages': True, 'root_mode_library': '1.2',
              'client': '1.0.2', 'loader': app.nuttymod_loader_version, 'custom_title': True,
              'optimizer': True, 'physics_restored': True, 'network_used': False}
    (output/'game-verification.json').write_text(json.dumps(report, indent=2)+'\n', encoding='utf-8')
    print(json.dumps(report, indent=2))
