import asyncio
import io
import json
import wave
from unittest.mock import AsyncMock

from fastapi.testclient import TestClient
import httpx
import pytest

from services.api import adapters, main


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setattr(main, 'PRIVATE', tmp_path)
    main.sessions.clear()
    for var in ('XTTS_PYTHON', 'MLX_PYTHON', 'WHISPER_PYTHON', 'OPENAI_API_KEY', 'OPENAI_MODEL'):
        monkeypatch.delenv(var, raising=False)
    with TestClient(main.app, raise_server_exceptions=False) as client:
        yield client


def wav(seconds=4):
    buf = io.BytesIO()
    with wave.open(buf, 'wb') as w:
        w.setparams((1, 2, 16000, 0, 'NONE', ''))
        w.writeframes(b'\0\0' * (16000 * seconds))
    return buf.getvalue()


def test_health_no_paths(client):
    result = client.get('/health')
    assert result.status_code == 200
    assert 'private_data' not in result.text and '/workspace' not in result.text
    assert result.headers['cache-control'] == 'no-store'


def test_tts_playable_pcm(client):
    r = client.post('/api/tts', json={'text': '繁體中文：儲能系統 BMS SOC'})
    assert r.headers['x-disclosure'] == 'ai_generated'
    with wave.open(io.BytesIO(r.content)) as w:
        assert w.getnframes() > 0 and w.getframerate() == 16000 and w.getsampwidth() == 2


@pytest.mark.parametrize('body', [{'text': ''}, {'text': 'x'*2001}, {'text': 'a', 'engine': 'unknown'}], ids=['empty', 'too_long', 'unknown_engine'])
def test_invalid_tts_redacted(client, body):
    r = client.post('/api/tts', json=body)
    assert r.status_code == 422 and 'input' not in r.text


def test_cloud_requires_opt_in_before_network(client, monkeypatch):
    fake = AsyncMock(side_effect=AssertionError('no network allowed'))
    monkeypatch.setattr(adapters.Dialogue, 'reply', fake)
    assert client.post('/api/chat', json={'user_text': 'private', 'engine': 'openai'}).status_code == 403
    fake.assert_not_called()


def test_cloud_not_configured_explicit(client):
    r = client.post('/api/chat', json={'user_text': 'hi', 'engine': 'openai', 'cloud_consent': True})
    assert r.status_code == 503 and r.json()['error']['code'] == 'BACKEND_NOT_CONFIGURED'


def test_no_memory_and_context_deletion(client):
    for n in range(1, 4):
        r = client.post('/api/chat', json={'user_text': '爸爸曾經去過哪裡？', 'session_id': 'test'})
        d = r.json()
        assert d['source_status'] == 'no_personal_memory'
        assert f'第 {n} 回合' in d['reply_text'] and '沒有' in d['reply_text']
        assert d['evidence_refs'] == [] and d['disclosure'] == 'ai_generated'
    assert client.delete('/api/sessions/test').status_code == 200
    assert 'test' not in main.sessions


def test_memory_review_grounding_and_revocation(client):
    assert client.post('/api/memories', json={'title': '風箏', 'text': '合成故事', 'reviewed_by_owner': False}).status_code == 422
    m = client.post('/api/memories', json={'title': '風箏', 'text': '合成測試：一起做風箏。', 'reviewed_by_owner': True}).json()
    r = client.post('/api/chat', json={'user_text': '風箏', 'session_id': 's', 'memory_mode': 'reviewed'}).json()
    assert r['evidence_refs'][0]['memory_id'] == m['memory_id']
    assert r['disclosure'] == 'ai_generated' and '留下的紀錄' in r['reply_text']
    assert client.delete('/api/memories/'+m['memory_id']).json()['sessions_cleared']
    assert client.get('/api/memories').json() == [] and main.sessions == {}


def test_voice_consent_original_preview_delete(client):
    assert client.post('/api/voices', files={'audio': ('x.wav', wav(), 'audio/wav')}).status_code == 403
    r = client.post('/api/voices', files={'audio': ('do-not-store-filename.wav', wav(), 'audio/wav')}, data={'owner_consent': 'true'})
    v = r.json()['profile_id']
    assert len(v) == 32 and 'filename' not in r.text
    assert (main.PRIVATE / f'{v}.wav').exists()
    r = client.get(f'/api/voices/{v}/audio')
    assert r.headers['x-disclosure'] == 'authentic_recording' and r.content == wav()
    assert client.delete(f'/api/voices/{v}').json()['deleted']
    assert not (main.PRIVATE / f'{v}.wav').exists()
    assert client.get('/api/voices').json() == []


@pytest.mark.parametrize('data', [b'not wav', wav(1), wav(31)], ids=['invalid', 'too_short', 'too_long'])
def test_reject_bad_voice(client, data):
    assert client.post('/api/voices', files={'audio': ('x.wav', data)}, data={'owner_consent': 'true'}).status_code == 400


def test_stt_mock_warns_and_does_not_generate(client):
    r = client.post('/api/stt', files={'audio': ('x.wav', wav(), 'audio/wav')})
    assert r.status_code == 200 and r.json()['warnings'] == ['synthetic_transcript']
    assert main.sessions == {} and list(main.PRIVATE.iterdir()) == []


def test_stt_rejects_unknown_format(client):
    assert client.post('/api/stt', files={'audio': ('x.txt', b'x', 'text/plain')}).status_code == 415


def test_missing_real_tts_does_not_silently_mock(client):
    r = client.post('/api/tts', json={'text': 'hello', 'engine': 'mlx'})
    assert r.status_code == 503 and r.json()['error']['code'] == 'VOICE_PROFILE_REQUIRED'


def test_failed_turn_does_not_commit_context(client, monkeypatch):
    monkeypatch.setattr(adapters.Speech, 'synthesize', AsyncMock(side_effect=adapters.BackendError('MODEL_PROCESS_FAILED')))
    r = client.post('/api/turn', json={'user_text': 'test', 'session_id': 'retry'})
    assert r.status_code == 503 and main.sessions['retry']['messages'] == []
    assert not main.sessions['retry']['busy']


def test_timeout_visible(client, monkeypatch):
    monkeypatch.setattr(adapters.Dialogue, 'reply', AsyncMock(side_effect=asyncio.TimeoutError()))
    assert client.post('/api/chat', json={'user_text': 'test'}).json()['error']['code'] == 'BACKEND_TIMEOUT'


def test_origins_and_host(client):
    assert client.post('/api/chat', json={'user_text': 'x'}, headers={'Origin': 'https://evil.example'}).status_code == 403
    assert client.get('/health', headers={'Host': 'evil.example'}).status_code == 400
    assert client.post('/api/chat', json={'user_text': 'x'}, headers={'Origin': 'http://testserver'}).status_code == 200


def test_request_size_bounded(client):
    assert client.post('/api/chat', content=b'x'*(12*1024*1024+1)).status_code == 413


def test_local_llm_cannot_be_remote(client, monkeypatch):
    monkeypatch.setenv('LOCAL_LLM_URL', 'https://evil.example/v1')
    r = client.post('/api/chat', json={'user_text': 'x', 'engine': 'local'})
    assert r.status_code == 503 and r.json()['error']['code'] == 'LOCAL_ENDPOINT_MUST_BE_LOOPBACK'


def test_adapter_openai_wire_contract(client, monkeypatch):
    monkeypatch.setenv('OPENAI_API_KEY', 'synthetic-test-key')
    monkeypatch.setenv('OPENAI_MODEL', 'synthetic-model')
    original = httpx.AsyncClient
    def handler(req):
        body = json.loads(req.content)
        assert str(req.url) == 'https://api.openai.com/v1/chat/completions'
        assert body['messages'][0]['role'] == 'system'
        assert body['messages'][-1]['content'] == 'synthetic question'
        return httpx.Response(200, json={'choices': [{'message': {'content': 'AI 測試回覆'}}]})
    monkeypatch.setattr(httpx, 'AsyncClient', lambda **kw: original(transport=httpx.MockTransport(handler), **kw))
    r = client.post('/api/chat', json={'user_text': 'synthetic question', 'engine': 'openai', 'cloud_consent': True})
    assert r.json()['reply_text'] == 'AI 測試回覆' and 'synthetic-test-key' not in r.text


def test_worker_process_boundary(monkeypatch):
    monkeypatch.delenv('XTTS_PYTHON', raising=False)
    with pytest.raises(adapters.BackendError, match='BACKEND_NOT_CONFIGURED'):
        asyncio.run(adapters.worker('XTTS_PYTHON', 'not-called.py', {}))


def test_inflight_memory_revocation(client, monkeypatch):
    async def reply(*args):
        main.sessions.clear()
        return 'must not be delivered'
    monkeypatch.setattr(adapters.Dialogue, 'reply', reply)
    r = client.post('/api/chat', json={'session_id': 'revoked', 'user_text': 'test'})
    assert r.status_code == 409 and 'must not be delivered' not in r.text


def test_twenty_turns_and_ten_tts(client):
    for i in range(20):
        r = client.post('/api/turn', json={'user_text': '合成案例：勇氣', 'session_id': 'twenty'})
        assert r.status_code == 200 and r.json()['audio_base64']
    for _ in range(10):
        assert client.post('/api/tts', json={'text': '合成中文測試'}).status_code == 200


def test_disconnect_cancels_operation():
    class Disconnected:
        async def is_disconnected(self):
            return True
    async def operation():
        await asyncio.sleep(100)
    with pytest.raises(main.HTTPException) as exc:
        asyncio.run(main.cancellable(Disconnected(), operation()))
    assert exc.value.status_code == 499


def test_worker_timeout_kills_process(monkeypatch):
    import sys
    class Process:
        returncode = None
        killed = False
        async def communicate(self, data):
            await asyncio.sleep(100)
        def kill(self):
            self.killed = True
        async def wait(self):
            self.returncode = -9
    proc = Process()
    monkeypatch.setenv('XTTS_PYTHON', sys.executable)
    monkeypatch.setattr(asyncio, 'create_subprocess_exec', AsyncMock(return_value=proc))
    with pytest.raises(asyncio.TimeoutError):
        asyncio.run(adapters.worker('XTTS_PYTHON', 'not-executed.py', {}, timeout=.01))
    assert proc.killed and proc.returncode == -9


def test_tts_worker_contract_uses_private_temp_file(client, monkeypatch):
    r = client.post('/api/voices', files={'audio': ('synthetic.wav', wav(), 'audio/wav')}, data={'owner_consent': 'true'})
    v = r.json()['profile_id']
    seen = []
    async def fake_worker(env, script, payload):
        seen.append(payload['output'])
        assert env == 'XTTS_PYTHON' and script.endswith('worker.py')
        assert payload['reference'].endswith(v+'.wav')
        from pathlib import Path
        Path(payload['output']).write_bytes(wav())
        return {'status': 'ok'}
    monkeypatch.setattr(adapters, 'worker', fake_worker)
    r = client.post('/api/tts', json={'text': '合成測試', 'engine': 'xtts', 'voice_id': v})
    assert r.status_code == 200
    from pathlib import Path
    assert not Path(seen[0]).exists()
