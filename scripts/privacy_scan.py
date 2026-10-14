"""Fail on sensitive staged/tracked assets. Heuristic guard, not a DLP guarantee."""
import json
from pathlib import Path
import re
import subprocess

ROOT = Path(__file__).resolve().parents[1]
files = subprocess.check_output(['git', 'ls-files', '-z', '--cached'], cwd=ROOT).decode().split('\0')
blocked = {'private_data', 'personal_data', 'recordings', 'voice_samples', 'speaker_embeddings', 'family_archive', '.e2e-data'}
media = {'.wav', '.mp3', '.m4a', '.mp4', '.mov', '.jpg', '.jpeg', '.png', '.webm', '.pem', '.key', '.pth', '.pt', '.safetensors'}
allowed = {'evidence/mock-tone.wav', 'evidence/ui-idle.png', 'evidence/ui-speaking.png', 'evidence/ui-mobile.png'}
patterns = [re.compile(rb'sk-[A-Za-z0-9_-]{24,}'), re.compile(rb'gh[pousr]_[A-Za-z0-9]{30,}'), re.compile(rb'-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----')]
findings = []
for name in filter(None, files):
    p = Path(name)
    if blocked.intersection(p.parts) or (p.name.startswith('.env') and p.name != '.env.example'):
        findings.append({'path': name, 'rule': 'private_path'})
    if p.suffix.lower() in media and name not in allowed:
        findings.append({'path': name, 'rule': 'private_media_or_key'})
    # Scan the exact staged blob, not just the working tree.
    raw = subprocess.check_output(['git', 'show', ':'+name], cwd=ROOT)
    if any(rx.search(raw) for rx in patterns):
        findings.append({'path': name, 'rule': 'credential_pattern'})
report = {'scope': 'git index; heuristic patterns; synthetic evidence reviewed separately',
          'tracked_files': len(list(filter(None, files))), 'findings': findings, 'passed': not findings}
(ROOT/'evidence/privacy-scan.json').write_text(json.dumps(report, indent=2))
print(json.dumps(report))
raise SystemExit(bool(findings))
