"""Reproducible synthetic-only pipeline traces. Never records conversational text."""
import base64
from datetime import datetime, timezone
import io
import json
from pathlib import Path
import platform
import statistics
import subprocess
import sys
import tempfile
import time
import wave

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from fastapi.testclient import TestClient
from services.api import main


def run():
    events = []
    with tempfile.TemporaryDirectory() as tmp:
        main.PRIVATE = Path(tmp)
        main.sessions.clear()
        with TestClient(main.app) as client:
            for i in range(10):
                start = time.perf_counter()
                r = client.post('/api/tts', json={'text': '合成測試：儲能系統與勇氣故事'})
                with wave.open(io.BytesIO(r.content)) as w:
                    frames = w.getnframes()
                events.append({'case': 'tts_10', 'index': i+1, 'ok': r.status_code == 200 and frames > 0,
                    'elapsed_ms': round((time.perf_counter()-start)*1000, 3)})
            for i in range(20):
                r = client.post('/api/turn', json={'session_id': 'scripted-mock', 'user_text': '合成測試：談談勇氣'})
                d = r.json()
                events.append({'case': 'dialogue_20', 'index': i+1, 'ok': r.status_code == 200 and bool(d.get('audio_base64')),
                    'turn_id': d['turn_id'], 'timings': d['timings'], 'engine': 'mock', 'disclosure': d['disclosure']})
                if i == 0:
                    (ROOT/'evidence/mock-tone.wav').write_bytes(base64.b64decode(d['audio_base64']))
    latency = [e['timings']['total_ms'] for e in events if e['case'] == 'dialogue_20']
    report = {'schema_version': '1.0', 'timestamp': datetime.now(timezone.utc).isoformat(),
        'source_commit': subprocess.check_output(['git', 'rev-parse', 'HEAD'], cwd=ROOT, text=True).strip(),
        'working_tree_diff_sha256': __import__('hashlib').sha256(subprocess.check_output(['git', 'diff', 'HEAD'], cwd=ROOT)).hexdigest(),
        'environment': {'os': platform.system(), 'arch': platform.machine(), 'python': platform.python_version()},
        'scope': 'synthetic mock only; not real speech, Mac, first-audible latency or audio/video synchronization',
        'p50_pipeline_ms': statistics.median(latency), 'events': events}
    (ROOT/'evidence/smoke.json').write_text(json.dumps(report, indent=2), encoding='utf-8')
    print(json.dumps({'events': len(events), 'successful': sum(e['ok'] for e in events), 'mock_p50_ms': report['p50_pipeline_ms']}))
    assert all(e['ok'] for e in events)


if __name__ == '__main__':
    run()
