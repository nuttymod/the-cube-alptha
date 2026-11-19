"""The launcher must release its service ports when the session ends."""
import socket
import time

for port in (4310, 4311, 15271, 21271, 22271):
    deadline = time.monotonic()+15
    while True:
        with socket.socket() as probe:
            if probe.connect_ex(('127.0.0.1', port)) != 0:
                break
        if time.monotonic() >= deadline:
            raise SystemExit(f'Alptha service still listening on port {port}')
        time.sleep(.2)
print('All Alptha service ports released.')
