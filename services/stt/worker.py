import contextlib
import json
import os
import sys

if __name__ == '__main__':
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        import whisper
        model = whisper.load_model(os.environ.get('WHISPER_MODEL', 'base'))
        text = model.transcribe(request['input'], language='zh', fp16=False)['text']
    print(json.dumps({'text': text}, ensure_ascii=False))
