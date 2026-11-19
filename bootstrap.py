"""Launch The Cube Alptha with a live connection and setup screen."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import queue
import sys
import threading

ROOT = Path(__file__).resolve().parent


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--headless', action='store_true', help='Log setup in the terminal instead of opening the connection screen')
    parser.add_argument('--connection-test', action='store_true', help='Verify Aspire, Node and Go, then stop without opening the game')
    parser.add_argument('--install-only', action='store_true', help='Verify and install bundled NuttyMod packages without starting services')
    args = parser.parse_args()
    if sys.version_info < (3, 11, 8):
        raise SystemExit('Alptha needs Python 3.11.8 or newer (3.14 recommended).')
    from alptha.packages import install
    if args.install_only:
        print(json.dumps(install(ROOT), indent=2))
        return
    from alptha.launcher import Launcher
    if args.headless:
        launcher = Launcher(ROOT)
        try:
            launcher.launch(args.connection_test)
        except KeyboardInterrupt:
            launcher.close()
        return
    try:
        import tkinter as tk
    except ImportError as exc:
        raise SystemExit('Install your OS Python Tk package, or run bootstrap.py --headless.') from exc
    events = queue.Queue()
    window = tk.Tk()
    window.title('The Cube Alptha · Connection')
    window.geometry('780x620')
    window.minsize(700, 590)
    window.configure(bg='#10121c')
    lock = json.loads((ROOT/'components.lock.json').read_text(encoding='utf-8'))
    font = 'Segoe UI' if sys.platform == 'win32' else 'DejaVu Sans'
    tk.Label(window, text='N U T T Y M O D', fg='#89e6c2', bg='#10121c', font=(font, 11, 'bold')).pack(anchor='w', padx=40, pady=(30, 5))
    tk.Label(window, text='THE CUBE ALPTHA', fg='#f5f3ff', bg='#10121c', font=(font, 30, 'bold')).pack(anchor='w', padx=36)
    tk.Label(window, text=f"Alptha {lock['version']}  ·  Game {lock['game']['version']}  ·  Client {lock['client']['version']}",
             fg='#a8adc4', bg='#10121c', font=(font, 10)).pack(anchor='w', padx=40, pady=(8, 22))
    labels = {}
    for phase, title, subtitle in [('node', '01   Node.js', 'Waiting for the CPE bridge'),
                                  ('dotnet', '02   .NET Aspire', 'Waiting for the connection host'),
                                  ('go', '03   Go', 'Waiting for the physics cache')]:
        frame = tk.Frame(window, bg='#1d2031', padx=18, pady=9)
        frame.pack(fill='x', padx=40, pady=4)
        tk.Label(frame, text=title, fg='#e8e7ff', bg='#1d2031', font=(font, 12, 'bold')).pack(anchor='w')
        label = tk.Label(frame, text=subtitle, fg='#a8adc4', bg='#1d2031', font=(font, 10))
        label.pack(anchor='w', pady=(4, 0))
        labels[phase] = label
    status = tk.Label(window, text='Preparing your connection…', fg='#89e6c2', bg='#10121c', font=(font, 11), wraplength=690, justify='left')
    status.pack(anchor='w', padx=40, pady=(18, 6))
    tk.Label(window, text='NuttyMod Loader · Client & CPE settings · Root Mode · NuttyMod Root',
             fg='#a8adc4', bg='#10121c', font=(font, 10)).pack(anchor='w', padx=40, pady=4)
    tk.Label(window, text='Setup installs missing dependencies locally. Logs: .runtime/logs',
             fg='#7b829c', bg='#10121c', font=(font, 9)).pack(anchor='w', padx=40, pady=4)
    launcher = Launcher(ROOT, lambda phase, message: events.put((phase, message)))
    running = True
    closing = False

    def worker():
        try:
            launcher.launch(args.connection_test)
        except Exception as exc:
            events.put(('error', str(exc)))
        finally:
            events.put(('finished', ''))

    def close():
        nonlocal closing
        if closing:
            return
        closing = True
        status.config(text='Closing the game and connection services…')
        threading.Thread(target=launcher.close, daemon=True).start()

    def poll():
        nonlocal running
        try:
            while True:
                phase, message = events.get_nowait()
                if phase == 'finished':
                    running = False
                    if closing:
                        window.destroy()
                        return
                    button.config(text='Close', command=window.destroy)
                elif phase == 'error':
                    status.config(text=message, fg='#ffb5aa')
                    window.deiconify()
                else:
                    status.config(text=message)
                    if phase in labels:
                        labels[phase].config(text=message, fg='#89e6c2' if 'connected' in message else '#bdb5ff')
                    if phase == 'ready' and not args.connection_test:
                        window.iconify()
        except queue.Empty:
            pass
        if closing and not running:
            window.destroy()
            return
        window.after(100, poll)

    button = tk.Button(window, text='Cancel', command=close, bg='#bcb0ff', fg='#10121c',
                       font=(font, 11, 'bold'), relief='flat', padx=25, pady=7)
    button.pack(anchor='e', padx=40, pady=10)
    window.protocol('WM_DELETE_WINDOW', close)
    threading.Thread(target=worker, daemon=True).start()
    window.after(100, poll)
    window.mainloop()
    launcher.close()


if __name__ == '__main__':
    main()
