import asyncio
import base64
import io
import json
import os
from pathlib import Path
import re
import time
from typing import Literal
import uuid
import wave

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from starlette.middleware.trustedhost import TrustedHostMiddleware

from .adapters import BackendError, Dialogue, Recognition, ROOT, Speech
from .face_routes import create_router as create_face_router
from .lipsync import timeline

app = FastAPI(title='DigitalMe local API', version='0.1.0', docs_url=None, redoc_url=None)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=['127.0.0.1', 'localhost', '[::1]', 'testserver'])
PRIVATE = Path(os.getenv('DIGITALME_DATA', ROOT / 'private_data')).resolve()
PRIVATE.mkdir(mode=0o700, parents=True, exist_ok=True)
sessions: dict[str, dict] = {}
model_lock = asyncio.Lock()
TTS = Literal['mock', 'xtts', 'mlx']
LLM = Literal['mock', 'local', 'openai']


@app.middleware('http')
async def local_boundary(request, call_next):
    origin = request.headers.get('origin')
    expected = f'{request.url.scheme}://{request.headers.get("host", "")}'
    if origin and origin != expected:
        return JSONResponse({'error': {'code': 'ORIGIN_DENIED'}}, status_code=403)
    # Bound both regular and chunked requests before multipart/JSON parsing.
    if request.method in ('POST', 'PUT', 'PATCH'):
        body = bytearray()
        async for chunk in request.stream():
            body.extend(chunk)
            if len(body) > 12 * 1024 * 1024:
                return JSONResponse({'error': {'code': 'REQUEST_TOO_LARGE'}}, status_code=413)
        request._body = bytes(body)
    response = await call_next(request)
    response.headers['Cache-Control'] = 'no-store'
    response.headers['X-Content-Type-Options'] = 'nosniff'
    response.headers['Referrer-Policy'] = 'no-referrer'
    response.headers['Content-Security-Policy'] = "default-src 'self'; img-src 'self' blob:; media-src 'self' blob:; connect-src 'self' blob:; style-src 'self' 'unsafe-inline'; script-src 'self'; frame-ancestors 'none'"
    return response


@app.exception_handler(RequestValidationError)
async def validation_error(request, exc):
    return JSONResponse({'error': {'code': 'INVALID_REQUEST'}}, status_code=422)


@app.exception_handler(HTTPException)
async def http_error(request, exc):
    return JSONResponse({'error': {'code': str(exc.detail)}}, status_code=exc.status_code)


@app.exception_handler(BackendError)
async def backend_error(request, exc):
    return JSONResponse({'error': {'code': str(exc)}}, status_code=503)


@app.exception_handler(asyncio.TimeoutError)
async def timeout_error(request, exc):
    return JSONResponse({'error': {'code': 'BACKEND_TIMEOUT'}}, status_code=504)


@app.exception_handler(Exception)
async def unexpected_error(request, exc):
    # Never expose model stderr, paths, prompts or credentials to the client.
    return JSONResponse({'error': {'code': 'INTERNAL_ERROR'}}, status_code=500)


def read_records(kind):
    path = PRIVATE / f'{kind}.json'
    return json.loads(path.read_text()) if path.exists() else []


def save_records(kind, records):
    path = PRIVATE / f'{kind}.json'
    temp = path.with_suffix('.tmp')
    temp.write_text(json.dumps(records, ensure_ascii=False), encoding='utf-8')
    temp.chmod(0o600)
    temp.replace(path)


def reference(voice_id):
    if voice_id == 'synthetic':
        return None
    if not re.fullmatch(r'[a-f0-9]{32}', voice_id):
        raise HTTPException(400, 'INVALID_VOICE_ID')
    found = next((v for v in read_records('voices') if v['profile_id'] == voice_id and v['owner_consent']), None)
    if not found:
        raise HTTPException(404, 'VOICE_NOT_FOUND')
    return str(PRIVATE / f'{voice_id}.wav')


def session(session_id):
    now = time.monotonic()
    for key in list(sessions):
        if now - sessions[key]['at'] > 3600:
            del sessions[key]
    if session_id not in sessions:
        if len(sessions) >= 100:
            raise HTTPException(429, 'SESSION_LIMIT')
        sessions[session_id] = {'messages': [], 'at': now, 'busy': False}
    sessions[session_id]['at'] = now
    return sessions[session_id]


class SpeakRequest(BaseModel):
    text: str = Field(min_length=1, max_length=2000)
    voice_id: str = 'synthetic'
    engine: TTS = 'mock'


class ChatRequest(BaseModel):
    session_id: str = Field(default_factory=lambda: str(uuid.uuid4()), pattern=r'^[a-zA-Z0-9-]{1,80}$')
    user_text: str = Field(min_length=1, max_length=2000)
    engine: LLM = 'mock'
    memory_mode: Literal['off', 'reviewed'] = 'off'
    cloud_consent: bool = False


class TurnRequest(ChatRequest):
    tts_engine: TTS = 'mock'
    voice_id: str = 'synthetic'
    lipsync_engine: Literal['rms','rhubarb'] = 'rms'


class Memory(BaseModel):
    text: str = Field(min_length=1, max_length=4000)
    title: str = Field(min_length=1, max_length=100)
    reviewed_by_owner: Literal[True]
    source_type: Literal['owner_statement'] = 'owner_statement'


@app.get('/health')
def health():
    return {'status': 'ok', 'version': '0.1.0', 'backend_status': 'mock_ready_real_models_unverified'}


@app.get('/api/engines')
def engines():
    return {'tts': [{'id': e, 'configured': e == 'mock' or bool(os.getenv(var)),
                      'verified': e == 'mock', 'kind': 'test_tone' if e == 'mock' else 'cloned_voice'}
        for e, var in [('mock', ''), ('xtts', 'XTTS_PYTHON'), ('mlx', 'MLX_PYTHON')]],
        'stt': ['mock', 'whisper'], 'llm': ['mock', 'local', 'openai'], 'avatar': 'rms_approximate_2d'}


@app.post('/api/tts')
async def tts(req: SpeakRequest, request: Request):
    async def synthesize():
        ref = reference(req.voice_id)
        async with model_lock:
            return await Speech(req.engine).synthesize(req.text, ref)
    audio = await cancellable(request, synthesize())
    return Response(audio, media_type='audio/wav', headers={'X-Disclosure': 'ai_generated'})


async def dialogue(req, synthesize=False):
    if req.engine == 'openai' and not req.cloud_consent:
        raise HTTPException(403, 'CLOUD_CONSENT_REQUIRED')
    state = session(req.session_id)
    if state['busy']:
        raise HTTPException(409, 'SESSION_BUSY')
    state['busy'] = True
    start = time.perf_counter()
    try:
        refs = []
        if req.memory_mode == 'reviewed':
            # Literal keyword retrieval; no claim of semantic or exhaustive retrieval.
            tokens = re.findall(r'[\u4e00-\u9fff]{2}|[a-zA-Z]{3,}', req.user_text.lower())
            refs = [m for m in read_records('memories') if m['reviewed_by_owner']
                    and any(t in (m['title'] + m['text']).lower() for t in tokens)][:3]
        user = {'role': 'user', 'content': req.user_text}
        messages = state['messages'][-38:] + [user]
        reply = await Dialogue(req.engine).reply(messages, refs)
        llm_ms = (time.perf_counter() - start) * 1000
        audio = None
        animation = None
        tts_end = time.perf_counter()
        if synthesize:
            async with model_lock:
                audio = await Speech(req.tts_engine).synthesize(reply, reference(req.voice_id))
            tts_end = time.perf_counter()
            animation = await timeline(audio,req.lipsync_engine)
        end = time.perf_counter()
        if sessions.get(req.session_id) is not state:
            raise HTTPException(409, 'SESSION_REVOKED')
        # Commit context only when requested pipeline completes, making retry safe.
        state['messages'] = (messages + [{'role': 'assistant', 'content': reply}])[-40:]
        return {'turn_id': str(uuid.uuid4()), 'session_id': req.session_id, 'reply_text': reply,
            'source_status': 'reviewed_sources_consulted' if refs else 'no_personal_memory',
            'evidence_refs': refs, 'disclosure': 'ai_generated', 'llm_backend': req.engine,
            'voice_backend': req.tts_engine if synthesize else None,
            'audio_base64': base64.b64encode(audio).decode() if audio else None,
            'animation': animation,
            'timings': {'llm_ms': round(llm_ms, 3), 'tts_ms': round((tts_end-start)*1000-llm_ms, 3),
                        'lipsync_ms': round((end-tts_end)*1000,3),
                        'total_ms': round((end-start)*1000, 3)}}
    finally:
        state['busy'] = False
        if req.session_id not in sessions:
            state['messages'] = []


@app.post('/api/chat')
async def chat(req: ChatRequest, request: Request):
    return await cancellable(request, dialogue(req))


@app.post('/api/turn')
async def turn(req: TurnRequest, request: Request):
    return await cancellable(request, dialogue(req, True))


async def cancellable(request, operation):
    task = asyncio.create_task(operation)
    try:
        while not task.done():
            if await request.is_disconnected():
                task.cancel()
                await asyncio.gather(task, return_exceptions=True)
                raise HTTPException(499, 'CLIENT_CANCELLED')
            await asyncio.wait({task}, timeout=.1)
        return await task
    finally:
        if not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)


@app.delete('/api/sessions/{session_id}')
def delete_session(session_id: str):
    sessions.pop(session_id, None)
    return {'deleted': True}


@app.post('/api/stt')
async def stt(request: Request, audio: UploadFile = File(...), engine: Literal['mock', 'whisper'] = Form('mock')):
    suffix = {'audio/webm': '.webm', 'audio/wav': '.wav', 'audio/mp4': '.m4a', 'audio/ogg': '.ogg'}.get(audio.content_type.split(';')[0])
    if not suffix:
        raise HTTPException(415, 'UNSUPPORTED_AUDIO')
    raw = await audio.read(10 * 1024 * 1024 + 1)
    if not raw or len(raw) > 10 * 1024 * 1024:
        raise HTTPException(413, 'AUDIO_SIZE_INVALID')
    start = time.perf_counter()
    async def recognize():
        async with model_lock:
            return await Recognition(engine).transcribe(raw, suffix)
    text = await cancellable(request, recognize())
    return {'text': text, 'language': 'zh', 'warnings': ['synthetic_transcript'] if engine == 'mock' else [],
            'timings': {'stt_ms': round((time.perf_counter()-start)*1000, 3)}}


@app.get('/api/voices')
async def voices():
    return read_records('voices')


@app.post('/api/voices')
async def add_voice(audio: UploadFile = File(...), owner_consent: bool = Form(False)):
    if not owner_consent:
        raise HTTPException(403, 'VOICE_CONSENT_REQUIRED')
    data = await audio.read(10 * 1024 * 1024 + 1)
    if len(data) > 10 * 1024 * 1024:
        raise HTTPException(413, 'AUDIO_SIZE_INVALID')
    try:
        with wave.open(io.BytesIO(data)) as w:
            duration = w.getnframes() / w.getframerate()
            if not 3 <= duration <= 30 or w.getsampwidth() != 2 or w.getnchannels() != 1:
                raise ValueError()
    except (wave.Error, EOFError, ValueError, ZeroDivisionError):
        raise HTTPException(400, 'REQUIRE_MONO_PCM16_WAV_3_TO_30_SECONDS') from None
    profile_id = uuid.uuid4().hex
    path = PRIVATE / f'{profile_id}.wav'
    path.write_bytes(data)
    path.chmod(0o600)
    records = read_records('voices')
    records.append({'profile_id': profile_id, 'owner_consent': True, 'duration_seconds': round(duration, 2)})
    save_records('voices', records)
    return records[-1]


@app.get('/api/voices/{voice_id}/audio')
async def voice_audio(voice_id: str):
    path = reference(voice_id)
    if path is None:
        raise HTTPException(404, 'VOICE_NOT_FOUND')
    return Response(Path(path).read_bytes(), media_type='audio/wav', headers={'X-Disclosure': 'authentic_recording'})


@app.delete('/api/voices/{voice_id}')
async def delete_voice(voice_id: str):
    path = reference(voice_id)
    if path:
        Path(path).unlink(missing_ok=True)
        save_records('voices', [v for v in read_records('voices') if v['profile_id'] != voice_id])
    return {'deleted': True}


@app.get('/api/memories')
async def memories():
    return read_records('memories')


@app.post('/api/memories')
async def add_memory(req: Memory):
    records = read_records('memories')
    record = {**req.model_dump(), 'memory_id': uuid.uuid4().hex, 'kind': 'authentic_statement'}
    records.append(record)
    save_records('memories', records)
    return record


@app.delete('/api/memories/{memory_id}')
async def delete_memory(memory_id: str):
    save_records('memories', [m for m in read_records('memories') if m['memory_id'] != memory_id])
    # Revocation removes previously grounded session context too.
    sessions.clear()
    return {'deleted': True, 'sessions_cleared': True}


@app.post('/api/lipsync')
async def lipsync(request:Request,audio:UploadFile=File(...),engine:Literal['rms','rhubarb']=Form('rms')):
    raw=await audio.read(10*1024*1024+1)
    if len(raw)>10*1024*1024:
        raise HTTPException(413,'AUDIO_SIZE_INVALID')
    return await cancellable(request,timeline(raw,engine))


app.include_router(create_face_router(lambda:PRIVATE))

dist = ROOT / 'apps/web/dist'
if dist.exists():
    app.mount('/', StaticFiles(directory=dist, html=True), name='web')
