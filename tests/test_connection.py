import unittest
from unittest.mock import patch

from alptha.launcher import verify_connection


class ConnectionTests(unittest.TestCase):
    def test_healthy_services_without_a_cache_round_trip_are_rejected(self):
        responses = [
            {'ok': True, 'protocol': 'CPE/1', 'service': 'cube-physics-engine-node-bridge'},
            {'ok': True, 'service': 'cpe-go-cache'},
            {'ok': True, 'go_cache': {'ok': False}},
            {'ok': True, 'state': {}},
        ]
        with patch('alptha.launcher.request', side_effect=responses):
            with self.assertRaisesRegex(RuntimeError, 'through to Go'):
                verify_connection('http://node', 'http://go')

    def test_stale_cache_is_rejected(self):
        def response(url, data=None):
            if url.endswith('/health'):
                return {'ok': True, 'protocol': 'CPE/1', 'service': 'cube-physics-engine-node-bridge' if 'node' in url else 'cpe-go-cache'}
            if data:
                return {'ok': True, 'go_cache': {'ok': True}}
            return {'state': {'alptha_connection': 'stale'}}
        with patch('alptha.launcher.request', side_effect=response):
            with self.assertRaisesRegex(RuntimeError, 'through to Go'):
                verify_connection('http://node', 'http://go')

    def test_matching_connection_token_passes(self):
        state = {}
        def response(url, data=None):
            if url.endswith('/health'):
                return {'ok': True, 'protocol': 'CPE/1', 'service': 'cube-physics-engine-node-bridge' if 'node' in url else 'cpe-go-cache'}
            if data:
                state.update(data)
                return {'ok': True, 'go_cache': {'ok': True}}
            return {'state': state}
        with patch('alptha.launcher.request', side_effect=response):
            verify_connection('http://node', 'http://go')
