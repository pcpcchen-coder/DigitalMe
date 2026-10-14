import asyncio
import io
import json
import math
import os
from pathlib import Path
import struct
import tempfile
import wave
from urllib.parse import urlparse

import httpx

from .domain import SYSTEM

ROOT = Path(__file__).resolve().parents[2]


class BackendError(Exception):
    pass


def mock_wav(text: str) -> bytes:
    """Synthetic tone fixture, deliberately NOT intelligible cloned speech."""
    rate = 16000
    length = min(3.0, max(.6, len(text) * .04))
    pcm = bytearray()
    for i in range(int(rate * length)):
        t = i / rate
        envelope = max(0, math.sin(2 * math.pi * 2.5 * t)) * min(1, t * 20)
        pcm.extend(struct.pack('<h', int(8500 * envelope * math.sin(2 * math.pi * 220 * t))))
    out = io.BytesIO()
    with wave.open(out, 'wb') as w:
        w.setparams((1, 2, rate, 0, 'NONE', 'not compressed'))
        w.writeframes(pcm)
    return out.getvalue()


async def worker(python_env: str, script: str, payload: dict, timeout=120) -> dict:
    executable = os.getenv(python_env)
    if not executable or not Path(executable).is_file():
        raise BackendError('BACKEND_NOT_CONFIGURED')
    proc = await asyncio.create_subprocess_exec(
        executable, str(ROOT / script), stdin=asyncio.subprocess.PIPE,
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    try:
        out, _ = await asyncio.wait_for(proc.communicate(json.dumps(payload).encode()), timeout)
        if proc.returncode:
            raise BackendError('MODEL_PROCESS_FAILED')
        return json.loads(out)
    except (asyncio.TimeoutError, asyncio.CancelledError):
        if proc.returncode is None:
            proc.kill()
        await proc.wait()
        raise
    except (ValueError, KeyError):
        raise BackendError('INVALID_MODEL_RESPONSE') from None


class Speech:
    def __init__(self, engine: str):
        self.engine = engine

    async def synthesize(self, text: str, reference: str | None) -> bytes:
        if self.engine == 'mock':
            return mock_wav(text)
        if not reference:
            raise BackendError('VOICE_PROFILE_REQUIRED')
        if self.engine == 'mlx' and (not os.getenv('MLX_MODEL') or not os.getenv('MLX_REFERENCE_TEXT')):
            raise BackendError('MLX_MODEL_AND_REFERENCE_TEXT_REQUIRED')
        script, env = {
            'xtts': ('services/tts_xtts_legacy/worker.py', 'XTTS_PYTHON'),
            'mlx': ('services/tts_mlx/worker.py', 'MLX_PYTHON'),
        }[self.engine]
        with tempfile.TemporaryDirectory(prefix='digitalme-') as tmp:
            output = str(Path(tmp) / 'speech.wav')
            await worker(env, script, {'text': text, 'reference': reference, 'output': output})
            audio = Path(output).read_bytes()
        try:
            with wave.open(io.BytesIO(audio)) as w:
                if w.getnchannels() not in (1, 2) or w.getsampwidth() != 2:
                    raise BackendError('INVALID_AUDIO_FORMAT')
        except wave.Error:
            raise BackendError('INVALID_AUDIO_FORMAT') from None
        return audio


class Recognition:
    def __init__(self, engine: str):
        self.engine = engine

    async def transcribe(self, audio: bytes, suffix: str) -> str:
        if self.engine == 'mock':
            return '這是模擬辨識文字，請修改後再送出。'
        with tempfile.TemporaryDirectory(prefix='digitalme-asr-') as tmp:
            path = Path(tmp) / ('input' + suffix)
            path.write_bytes(audio)
            result = await worker('WHISPER_PYTHON', 'services/stt/worker.py', {'input': str(path)})
            return result['text']


class Dialogue:
    def __init__(self, engine: str):
        self.engine = engine

    async def reply(self, messages: list[dict], evidence: list[dict]) -> str:
        if self.engine == 'mock':
            if evidence:
                return '留下的紀錄提到：' + evidence[0]['text'] + '（AI 整理，請查看來源）'
            turns = sum(m['role'] == 'user' for m in messages)
            return f'這是第 {turns} 回合模擬回覆。我沒有相關的本人記憶來源，無法知道他的真實經歷。你可以和家人一起整理故事。'
        if self.engine == 'local':
            base = os.getenv('LOCAL_LLM_URL', 'http://127.0.0.1:1234/v1')
            parsed = urlparse(base)
            if parsed.hostname not in ('127.0.0.1', 'localhost', '::1') or parsed.scheme != 'http' or parsed.username or parsed.password:
                raise BackendError('LOCAL_ENDPOINT_MUST_BE_LOOPBACK')
            key = os.getenv('LOCAL_LLM_KEY', 'local')
            model = os.getenv('LOCAL_LLM_MODEL', 'local-model')
        else:
            base = 'https://api.openai.com/v1'
            key = os.getenv('OPENAI_API_KEY')
            model = os.getenv('OPENAI_MODEL')
            if not key or not model:
                raise BackendError('BACKEND_NOT_CONFIGURED')
        system = SYSTEM + '\n已審核來源資料：' + json.dumps(evidence, ensure_ascii=False)
        try:
            async with httpx.AsyncClient(timeout=60, trust_env=False) as client:
                r = await client.post(base.rstrip('/') + '/chat/completions',
                    headers={'Authorization': f'Bearer {key}'},
                    json={'model': model, 'messages': [{'role': 'system', 'content': system}] + messages})
                r.raise_for_status()
                answer = r.json()['choices'][0]['message']['content']
                if not isinstance(answer, str) or not answer.strip():
                    raise BackendError('INVALID_MODEL_RESPONSE')
                return answer[:4000]
        except (httpx.HTTPError, KeyError, ValueError, IndexError):
            raise BackendError('LLM_UNAVAILABLE') from None
