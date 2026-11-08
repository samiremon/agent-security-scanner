import json
import threading
import time
from http.client import HTTPConnection
from http.server import ThreadingHTTPServer

import pytest
from scanner.dashboard import Dashboard, handler_for


def wait_scan(app, key):
    deadline = time.monotonic() + 30
    while time.monotonic() < deadline:
        scan = app.read(key)
        if scan['status'] != 'running':
            return scan
        time.sleep(.05)
    pytest.fail('Scan did not finish')


def test_demo_records_real_mcp_calls_and_replay(tmp_path):
    app = Dashboard(tmp_path)
    config = dict(attacks=['email_exfiltration_01'], mode='demo', repeat=1)
    first = wait_scan(app, app.start(config)['id'])
    assert first['status'] == 'completed'
    result = first['results'][0]
    assert result['outcome'] == 'ATTACK_SUCCEEDED'
    assert [c['tool'] for c in result['calls']] == ['read_email', 'get_config', 'send_email']
    assert result['attack']['canary'] in result['evidence']['args']['body']
    second = wait_scan(app, app.start(config)['id'])
    assert second['results'][0]['attack']['canary'] != result['attack']['canary']
    assert len(app.history()) == 2


@pytest.mark.parametrize('data', [dict(attacks=[]), dict(attacks=['../../.env']),
    dict(attacks=['email_exfiltration_01'], repeat=0),
    dict(attacks=['email_exfiltration_01'], mode='custom', command='')])
def test_invalid_scan_rejected(tmp_path, data):
    with pytest.raises(ValueError):
        Dashboard(tmp_path).start(data)


def test_interrupted_scans_survive_restart(tmp_path):
    app = Dashboard(tmp_path)
    key = 'a' * 32
    app.save(dict(id=key, status='running', started_at='2026', results=[]))
    assert Dashboard(tmp_path).read(key)['status'] == 'interrupted'


def test_http_requires_session_token_and_same_origin(tmp_path):
    app = Dashboard(tmp_path)
    server = ThreadingHTTPServer(('127.0.0.1', 0), handler_for(app))
    threading.Thread(target=server.serve_forever, daemon=True).start()
    client = HTTPConnection('127.0.0.1', server.server_port)
    try:
        client.request('GET', '/')
        response = client.getresponse()
        assert response.status == 200
        assert b'SENTINEL' in response.read()
        client.request('GET', '/api/bootstrap')
        response = client.getresponse()
        bootstrap = json.loads(response.read())
        assert len(bootstrap['attacks']) == 11
        client.request('POST', '/api/scans', '{}')
        response = client.getresponse()
        assert response.status == 403
        response.read()
        headers = {'Origin':f'http://127.0.0.1:{server.server_port}', 'X-Scanner-Token':bootstrap['token']}
        client.request('POST', '/api/scans', json.dumps(dict(attacks=[])), headers)
        response = client.getresponse()
        assert response.status == 400
        response.read()
        client.request('GET', '/api/scans/../../.env')
        response = client.getresponse()
        assert response.status == 404
        response.read()
    finally:
        client.close()
        server.shutdown()
        server.server_close()
