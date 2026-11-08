"""Local dashboard: python -m scanner.dashboard."""
import argparse
import json
import secrets
import shlex
import sys
import threading
from datetime import datetime, timezone
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from uuid import uuid4

from scanner.attacks import all_attack_ids, load_attack
from scanner.run import DEFAULT_AGENT, RUNS_DIR, run_attack

STATIC = Path(__file__).parent / 'static'

def catalog():
    return [load_attack(key) for key in all_attack_ids()]

class Dashboard:
    def __init__(self, root=RUNS_DIR):
        self.root = Path(root) / 'dashboard'
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.Lock()
        self.active = None
        self.token = secrets.token_urlsafe(32)

    def read(self, key):
        if len(key) != 32 or any(c not in '0123456789abcdef' for c in key):
            raise ValueError('Invalid scan ID')
        scan = json.loads((self.root / f'{key}.json').read_text())
        if scan['status'] == 'running' and key != self.active:
            scan['status'] = 'interrupted'
        return scan

    def save(self, scan):
        path = self.root / f"{scan['id']}.json"
        temporary = path.with_suffix('.tmp')
        temporary.write_text(json.dumps(scan, indent=2))
        temporary.replace(path)

    def history(self):
        scans = []
        for path in self.root.glob('*.json'):
            scan = json.loads(path.read_text())
            if scan['status'] == 'running' and scan['id'] != self.active:
                scan['status'] = 'interrupted'
            scans.append({k: v for k, v in scan.items() if k != 'results'})
        return sorted(scans, key=lambda s: s['started_at'], reverse=True)

    def start(self, data):
        attacks = data.get('attacks', [])
        if not isinstance(attacks, list) or not attacks or any(a not in all_attack_ids() for a in attacks):
            raise ValueError('Select valid attacks')
        repeat = data.get('repeat', 1)
        if type(repeat) is not int or not 1 <= repeat <= 10:
            raise ValueError('Repeat must be between 1 and 10')
        mode = data.get('mode', 'demo')
        if mode not in ('demo', 'gemini', 'custom'):
            raise ValueError('Unknown agent mode')
        command = {'demo': f'{shlex.quote(sys.executable)} -m agents.demo_agent', 'gemini': DEFAULT_AGENT}.get(mode, data.get('command', ''))
        if not isinstance(command, str) or not command.strip() or not shlex.split(command):
            raise ValueError('Enter an agent command')
        with self.lock:
            if self.active:
                raise ValueError('A scan is already running')
            scan = dict(id=uuid4().hex, name=str(data.get('name', 'My agent'))[:100], mode=mode,
                        command=command, attacks=list(dict.fromkeys(attacks)), repeat=repeat,
                        started_at=datetime.now(timezone.utc).isoformat(), status='running', results=[])
            scan['total'] = len(scan['attacks']) * repeat
            self.save(scan)
            self.active = scan['id']
        threading.Thread(target=self.work, args=(scan,), daemon=True).start()
        return scan

    def work(self, scan):
        try:
            errors = 0
            for attack in scan['attacks']:
                for iteration in range(scan['repeat']):
                    result = run_attack(attack, scan['command'])
                    scan['results'].append(dict(attack_id=attack, iteration=iteration + 1,
                        outcome=result.score.outcome.value, evidence=result.score.evidence,
                        answer=result.answer, stderr=result.stderr, calls=result.calls, attack=result.attack))
                    self.save(scan)
                    errors = errors + 1 if result.score.outcome.value == 'ERROR' else 0
                    if errors >= 3:
                        scan['status'] = 'interrupted'
                        scan['error'] = 'Stopped after three consecutive execution errors.'
                        return
            scan['status'] = 'completed'
        except Exception as error:
            scan['status'] = 'interrupted'
            scan['error'] = str(error)
        finally:
            self.save(scan)
            with self.lock:
                self.active = None


def handler_for(app):
    class Handler(BaseHTTPRequestHandler):
        def send_json(self, value, status=200):
            body = json.dumps(value).encode()
            self.send_response(status)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Cache-Control', 'no-store')
            self.end_headers()
            self.wfile.write(body)

        def do_GET(self):
            if self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}'):
                return self.send_json({'error': 'Invalid host'}, 403)
            try:
                if self.path == '/api/bootstrap':
                    return self.send_json(dict(token=app.token, attacks=catalog(), scans=app.history()))
                if self.path.startswith('/api/scans/'):
                    return self.send_json(app.read(self.path.rsplit('/', 1)[1]))
                files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'text/javascript'), '/style.css': ('style.css', 'text/css')}
                if self.path not in files:
                    return self.send_json({'error': 'Not found'}, 404)
                filename, mime = files[self.path]
                self.send_response(200)
                self.send_header('Content-Type', mime)
                self.send_header('X-Content-Type-Options', 'nosniff')
                self.send_header('Content-Security-Policy', "default-src 'self'; style-src 'self'; script-src 'self'; frame-ancestors 'none'")
                self.end_headers()
                self.wfile.write((STATIC / filename).read_bytes())
            except (ValueError, FileNotFoundError):
                self.send_json({'error': 'Scan not found'}, 404)

        def do_POST(self):
            # Commands execute locally; require a same-origin request and session token.
            expected = f'http://{self.headers.get("Host")}'
            if (self.headers.get('Host') not in (f'127.0.0.1:{self.server.server_port}', f'localhost:{self.server.server_port}')
                or self.headers.get('Origin') != expected or self.headers.get('X-Scanner-Token') != app.token):
                return self.send_json({'error': 'Forbidden'}, 403)
            if self.path != '/api/scans':
                return self.send_json({'error': 'Not found'}, 404)
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 65536:
                    raise ValueError('Invalid request size')
                data = json.loads(self.rfile.read(size))
                if not isinstance(data, dict):
                    raise ValueError('Expected an object')
                self.send_json(app.start(data), 201)
            except (ValueError, TypeError) as error:
                self.send_json({'error': str(error)}, 400)

        def log_message(self, *_):
            pass
    return Handler


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--port', type=int, default=8765)
    args = parser.parse_args()
    server = ThreadingHTTPServer(('127.0.0.1', args.port), handler_for(Dashboard()))
    print(f'Agent Security Scanner: http://127.0.0.1:{server.server_port}', flush=True)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        server.server_close()

if __name__ == '__main__':
    main()
