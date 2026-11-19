"""Explicit Alptha hook, run after the verified Root and Client packages."""
from __future__ import annotations
import importlib.util
from pathlib import Path


def on_load(app, userdata):
    import pygame
    if not (getattr(app, 'root_mode_enabled', False) and getattr(app, 'nuttymod_root_enabled', False)):
        raise RuntimeError('Alptha requires verified NuttyMod Root and Root Mode: '+getattr(app, 'nuttymod_root_error', 'not active'))
    if not getattr(app, 'nuttymod_client_enabled', False):
        raise RuntimeError('Alptha Client failed to start.')
    app.cpeloader.require_flash()
    source = Path(game_root)/'addons'/'nuttymod'/'nuttymod_loader.py'
    spec = importlib.util.spec_from_file_location('_alptha_nuttymod_loader', source)
    loader = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(loader)
    loader.on_load(app, userdata)
    app.custom_cube_name = 'The Cube Alptha'
    pygame.display.set_caption(app.nuttymod_root_settings['game']['title'])
    app.notify('Alptha ready · F8 Client / CPE · Ctrl+Shift+R Root settings', 8)
