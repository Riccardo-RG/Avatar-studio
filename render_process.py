"""Stream render progress without leaving stderr unread or children behind."""
from pathlib import Path
import os
import signal
import subprocess
import threading


def stop(proc):
    def signal_group(value):
        try:
            os.killpg(proc.pid, value)
        except ProcessLookupError:
            pass
        except PermissionError:
            # A sandbox may refuse signalling an already orphaned process group.
            if proc.poll() is None:
                try:
                    proc.send_signal(value)
                except ProcessLookupError:
                    pass
    signal_group(signal.SIGTERM)
    if proc.poll() is None:
        try:
            proc.wait(timeout=5)
        except subprocess.TimeoutExpired:
            signal_group(signal.SIGKILL)
            proc.wait(timeout=5)
    # A descendant can outlive the direct child and keep stdout open.
    signal_group(signal.SIGKILL)


def run(command, folder, env, set_process, progress, timeout=920):
    # A separate file avoids the stdout/stderr PIPE deadlock on verbose errors.
    log_path = Path(folder) / 'render-error.log'
    expired = threading.Event()
    with log_path.open('w', encoding='utf-8') as log:
        proc = subprocess.Popen(command, stdout=subprocess.PIPE, stderr=log,
                                text=True, env=env, start_new_session=True)
        stop_lock = threading.Lock()
        stopped = False
        def cleanup():
            nonlocal stopped
            with stop_lock:
                if not stopped:
                    stop(proc)
                    stopped = True
        def deadline():
            expired.set()
            cleanup()
        timer = threading.Timer(timeout, deadline)
        timer.daemon = True
        timer.start()
        try:
            set_process(proc)
            for line in proc.stdout:
                if line.startswith('PROGRESS '):
                    progress(float(line.split()[1]))
            code = proc.wait()
            if expired.is_set():
                raise ValueError('Esportazione oltre il tempo massimo. Puoi riprovare con un video più breve.')
            if code or not (Path(folder) / 'video.mp4').is_file():
                raise ValueError('Esportazione non riuscita. Dettagli in render-error.log nella cartella del video.')
        finally:
            timer.cancel()
            try:
                cleanup()
            finally:
                proc.stdout.close()
