"""Read-only legacy audit. Reports only to ignored private_data, never upload it."""
from datetime import datetime, timezone
import json
from pathlib import Path
import platform
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
legacy = Path.home()/'xtts_project'
report = {'timestamp': datetime.now(timezone.utc).isoformat(), 'os': platform.system(),
          'arch': platform.machine(), 'legacy_exists': legacy.is_dir(), 'status': 'BLOCKED: host access'}
if platform.system() == 'Darwin' and legacy.is_dir():
    report['macos'] = platform.mac_ver()[0]
    report['status'] = 'PARTIAL: inventory only, synthesis unverified'
    # Run only a discovered existing interpreter, disable bytecode writes. No model imports.
    candidates = [legacy/name/'bin/python' for name in ('.venv', 'venv', 'env')]
    interpreter = next((p for p in candidates if p.is_file()), None)
    if interpreter:
        code = "import importlib.metadata as m,json,sys; names=['TTS','torch','torchaudio','transformers']; print(json.dumps({'python':sys.version.split()[0],'packages':{n:next((d.version for d in m.distributions() if d.metadata['Name'].lower()==n.lower()),None) for n in names}}))"
        result = subprocess.run([str(interpreter), '-B', '-c', code], capture_output=True, text=True, timeout=30)
        if result.returncode == 0:
            report['legacy_runtime'] = json.loads(result.stdout)
        else:
            report['legacy_runtime'] = 'unreadable; stderr withheld'
    else:
        report['legacy_runtime'] = 'interpreter not found in .venv/venv/env'
    report['audio_files_present'] = any(legacy.glob('*.wav')) or any(legacy.glob('*.m4a'))
    report['note'] = 'Names, paths, audio and full pip freeze intentionally omitted; environment not modified.'
out = ROOT/'private_data'
out.mkdir(mode=0o700, exist_ok=True)
path = out/'inventory.json'
path.write_text(json.dumps(report, indent=2), encoding='utf-8')
path.chmod(0o600)
print(json.dumps(report, ensure_ascii=False))
sys.exit(2 if report['status'].startswith('BLOCKED') else 0)
