"""Independent raw-artifact to board consistency check; no hand-entered totals."""
import hashlib
import html
import json
from pathlib import Path
import statistics
import xml.etree.ElementTree as ET

root = Path(__file__).resolve().parents[1]/'evidence'
load = lambda n: json.loads((root/n).read_text())
manifest = load('manifest.json')
stats = manifest['stats']
for name, expected in manifest['sha256'].items():
    assert hashlib.sha256((root/name).read_bytes()).hexdigest() == expected, name
events = load('smoke.json')['events']
for prefix, case in [('tts', 'tts_10'), ('dialogue', 'dialogue_20')]:
    matching = [e for e in events if e['case'] == case]
    assert stats[prefix+'_total'] == len(matching)
    assert stats[prefix+'_passed'] == sum(e['ok'] for e in matching)
assert stats['mock_p50_ms'] == statistics.median(e['timings']['total_ms'] for e in events if e['case'] == 'dialogue_20')
tests = list(ET.parse(root/'python-tests.xml').iter('testcase'))
assert stats['python_total'] == len(tests)
assert stats['python_passed'] == sum(t.find('failure') is None and t.find('error') is None for t in tests)
def cases(suites):
    for suite in suites:
        yield from suite.get('specs', [])
        yield from cases(suite.get('suites', []))
specs = list(cases(load('browser-tests.json')['suites']))
assert stats['browser_total'] == len(specs)
assert stats['browser_passed'] == sum(s['ok'] for s in specs)
assert stats['privacy_scan'] == load('privacy-scan.json')['passed']
assert stats['npm_vulnerabilities'] == load('npm-audit.json')['metadata']['vulnerabilities']['total']
assert stats['python_vulnerabilities'] == sum(len(d.get('vulns', [])) for d in load('python-audit.json')['dependencies'])
page = (root/'index.html').read_text()
for key, value in stats.items():
    assert f'<small>{html.escape(key)}</small><b>{html.escape(str(value))}</b>' in page, key
assert len(manifest['matrix']) == 10 and manifest['matrix'][1][1] == 'UNVERIFIED'
print(json.dumps({'verified': True, 'artifact_hashes': len(manifest['sha256']), 'board_metrics': len(stats), 'criteria': 10}))
