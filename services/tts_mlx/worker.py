"""Modern MLX backend; separate environment, Mac validation still required."""
import contextlib
import json
import os
import sys

if __name__ == '__main__':
    request = json.load(sys.stdin)
    with contextlib.redirect_stdout(sys.stderr):
        import numpy as np
        import soundfile as sf
        from mlx_audio.tts.utils import load_model
        model = load_model(os.environ['MLX_MODEL'])
        results = list(model.generate(text=request['text'], ref_audio=request['reference'],
            ref_text=os.environ.get('MLX_REFERENCE_TEXT', ''), lang_code='Chinese'))
        audio = np.concatenate([np.asarray(r.audio).reshape(-1) for r in results])
        sf.write(request['output'], audio, results[0].sample_rate, subtype='PCM_16')
    print(json.dumps({'status': 'ok'}))
