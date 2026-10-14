"""Executed ONLY by the existing legacy Python, no pip changes, stdout is JSON."""
import contextlib
import json
import sys

if __name__ == '__main__':
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        from TTS.api import TTS
        tts = TTS('tts_models/multilingual/multi-dataset/xtts_v2')
        tts.tts_to_file(text=request['text'], speaker_wav=request['reference'],
                        language='zh-cn', file_path=request['output'])
    print(json.dumps({'status': 'ok'}))
