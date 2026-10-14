"""Audio-derived timelines. RMS is approximate; Rhubarb phonetic is optional."""
import asyncio
import io
import json
import os
from pathlib import Path
import tempfile
import wave

import numpy as np

from .adapters import BackendError


async def timeline(audio:bytes,engine='rms'):
    try:
        with wave.open(io.BytesIO(audio)) as w:
            if w.getsampwidth()!=2 or w.getnchannels() not in (1,2) or w.getnframes()/w.getframerate()>180:
                raise BackendError('LIPSYNC_REQUIRES_PCM16_WAV_MAX_180_SECONDS')
            rate,channels = w.getframerate(),w.getnchannels()
            samples = np.frombuffer(w.readframes(w.getnframes()),dtype='<i2').astype(float).reshape(-1,channels).mean(axis=1)/32768
    except (wave.Error, EOFError, ValueError):
        raise BackendError('LIPSYNC_REQUIRES_PCM16_WAV_MAX_180_SECONDS') from None
    duration = len(samples)/rate
    if engine=='rms':
        frames=[]
        for start in range(0,len(samples),max(1,rate//50)):
            level = float(np.sqrt(np.mean(samples[start:start+rate//50]**2)))
            frames.append({'time':round(start/rate,4),'jawOpen':min(1,max(0,(level-.01)*5)),'mouthPucker':0.})
        frames.append({'time':duration,'jawOpen':0.,'mouthPucker':0.})
        return {'driver':'rms_approximate','duration_seconds':duration,'frames':frames}
    executable=os.getenv('RHUBARB_BIN')
    if not executable or not Path(executable).is_file():
        raise BackendError('RHUBARB_NOT_CONFIGURED')
    with tempfile.TemporaryDirectory(prefix='digitalme-lips-') as tmp:
        path=Path(tmp)/'input.wav';path.write_bytes(audio)
        proc=await asyncio.create_subprocess_exec(executable,'-r','phonetic','-f','json','--quiet',str(path),
            stdout=asyncio.subprocess.PIPE,stderr=asyncio.subprocess.DEVNULL)
        try:
            out,_=await asyncio.wait_for(proc.communicate(),90)
            if proc.returncode:
                raise BackendError('RHUBARB_PROCESS_FAILED')
            cues=json.loads(out)['mouthCues']
            jaw={'A':0.,'B':.15,'C':.4,'D':.85,'E':.35,'F':.15,'G':.1,'H':.5,'X':0.}
            frames=[{'time':float(c['start']),'jawOpen':jaw[c['value']],
                'mouthPucker':.9 if c['value'] in ('E','F') else 0.} for c in cues]
            if any(not np.isfinite(f['time']) or f['time']<0 or f['time']>duration+.1 for f in frames):
                raise ValueError()
            frames.append({'time':duration,'jawOpen':0.,'mouthPucker':0.})
            return {'driver':'rhubarb_phonetic_unvalidated_mandarin','duration_seconds':duration,'frames':frames}
        except (asyncio.CancelledError,asyncio.TimeoutError):
            if proc.returncode is None:proc.kill()
            await proc.wait()
            raise
        except (ValueError,KeyError,TypeError):
            raise BackendError('INVALID_RHUBARB_RESPONSE') from None
