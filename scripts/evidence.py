"""Generate board and matrix from raw events; missing/failed inputs never turn green."""
from datetime import datetime, timezone
import hashlib
import html
import json
from pathlib import Path
import shutil
import statistics
import re
import xml.etree.ElementTree as ET

ROOT = Path(__file__).resolve().parents[1]
E = ROOT/'evidence'


def load(name):
    p = E/name
    return json.loads(p.read_text()) if p.exists() else {}


def build():
    smoke = load('smoke.json')
    browser = load('browser-tests.json')
    scan = load('privacy-scan.json')
    npm = load('npm-audit.json')
    face = load('face-smoke.json')
    events = smoke.get('events', [])
    tts = [e for e in events if e['case'] == 'tts_10']
    turns = [e for e in events if e['case'] == 'dialogue_20']
    root = ET.parse(E/'python-tests.xml').getroot() if (E/'python-tests.xml').exists() else None
    pytests = list(root.iter('testcase')) if root is not None else []
    pyfailed = [p for p in pytests if p.find('failure') is not None or p.find('error') is not None]
    def walk(suites):
        out = []
        for s in suites:
            out.extend(walk(s.get('suites', [])))
            for spec in s.get('specs', []):
                out.append({'title': spec['title'], 'ok': spec['ok']})
        return out
    cases = walk(browser.get('suites', []))
    stats = {'python_passed': len(pytests)-len(pyfailed), 'python_total': len(pytests),
        'browser_passed': sum(c['ok'] for c in cases), 'browser_total': len(cases),
        'tts_passed': sum(e['ok'] for e in tts), 'tts_total': len(tts),
        'dialogue_passed': sum(e['ok'] for e in turns), 'dialogue_total': len(turns),
        'mock_p50_ms': statistics.median([e['timings']['total_ms'] for e in turns]) if turns else None, 'privacy_scan': scan.get('passed', False),
        'npm_vulnerabilities': npm.get('metadata', {}).get('vulnerabilities', {}).get('total', 'unknown')}
    stats['python_vulnerabilities'] = sum(len(d.get('vulns', [])) for d in load('python-audit.json').get('dependencies', [])) if load('python-audit.json') else 'unknown'
    node_text=(E/'npm-tests.tap').read_text() if (E/'npm-tests.tap').exists() else ''
    for key,pattern in [('frontend_total',r'(?:ℹ|#) tests (\d+)'),('frontend_passed',r'(?:ℹ|#) pass (\d+)')]:
        match=re.search(pattern,node_text)
        stats[key]=int(match.group(1)) if match else 'unknown'
    if face:
        stats.update(synthetic_surface_vertices=face['vertices'],synthetic_surface_triangles=face['triangles'],synthetic_motion_frames=face['motion_frames'])
    # AC statuses cover full requirements, including deliberately unverified real-model scope.
    matrix = [
        ('AC-01', 'PARTIAL', 'Mock PCM WAV verified; real Chinese cloned speech unverified', 'make smoke; make test', 'smoke.json'),
        ('AC-02', 'UNVERIFIED', '3 voice references / family blind quality rating require Mac and consent', 'Mac voice comparison', None),
        ('AC-03', 'PARTIAL', '20 mock turns; real owner-voice natural dialogue unverified', 'make smoke; npm run e2e', 'smoke.json'),
        ('AC-04', 'PARTIAL', 'Browser RMS movement and playable audio; no measured A/V offset', 'npm run e2e', 'browser-tests.json'),
        ('AC-05', 'PARTIAL', 'Injected failure, timeout, retry; real model process-stop recovery unverified', 'make test; npm run e2e', 'python-tests.xml'),
        ('AC-06', 'PARTIAL', 'Permission rejection simulated in browser; physical Mac permission unverified', 'npm run e2e', 'browser-tests.json'),
        ('AC-07', 'PARTIAL', 'Mock no-source disclosure and retrieval; live LLM hallucination red-team unverified', 'make test', 'python-tests.xml'),
        ('AC-08', 'PARTIAL', 'Local voice/memory/session deletion; encrypted backups/secure erasure not implemented', 'make test; npm run e2e', 'python-tests.xml'),
        ('AC-09', 'PASS' if scan.get('passed') else 'FAIL', 'Index pattern scan; only synthetic evidence allowed; heuristic scope', 'make scan', 'privacy-scan.json'),
        ('AC-10', 'PARTIAL', 'Lockfiles, build and smoke tested; Mac clean clone not tested', 'make setup test smoke', 'python-tests.xml'),
    ]
    if face:
        matrix.extend([
            ('AF-01','UNVERIFIED','B0645 physical device, firmware, Mac UVC layout / sync verification pending','Mac camera capture',None),
            ('AF-02','PARTIAL','Virtual chessboard baseline recovery tested; real calibration and measured depth error pending','make test','python-tests.xml'),
            ('AF-03','PARTIAL','CPU SGBM metric virtual stereo surface; real skin / hair / eye depth unverified','make smoke','face-smoke.json'),
            ('AF-04','PARTIAL','Embedded textured GLB and actual morph weights tested with synthetic surface; owner likeness unverified','npm run e2e','browser-tests.json'),
            ('AF-05','PARTIAL','RMS timeline follows playback time and interrupts; Rhubarb Mandarin and AV offset unverified','make test; npm run e2e','face-smoke.json'),
            ('AF-06','PARTIAL','Local scan deletion and external GLB URI blocking tested; no secure-erasure guarantee','make test','python-tests.xml'),
            ('AF-07','UNVERIFIED','Full head / multi-view fusion / anatomical retopology / teeth / eyelids not implemented','future reconstruction/rig work',None),
            ('AF-08','UNVERIFIED','Real owner voice + owner scan + family likeness and naturalness acceptance pending','Mac private acceptance',None),
        ])
    evidence_files = ['smoke.json', 'face-smoke.json', 'python-tests.xml', 'browser-tests.json', 'privacy-scan.json', 'npm-audit.json', 'python-audit.json', 'regressions.json', 'ui-idle.png', 'ui-speaking.png', 'ui-mobile.png', 'face-builder.png', 'face-speaking.png', 'mock-tone.wav', 'npm-tests.tap']
    manifest = {n: hashlib.sha256((E/n).read_bytes()).hexdigest() for n in evidence_files if (E/n).exists()}
    bundle = {'generated_at': datetime.now(timezone.utc).isoformat(), 'source_commit': smoke.get('source_commit'),
        'environment': smoke.get('environment'), 'stats': stats, 'matrix': matrix, 'sha256': manifest,
        'scope': smoke.get('scope'), 'browser_cases': cases}
    (E/'manifest.json').write_text(json.dumps(bundle, indent=2, ensure_ascii=False))
    cards = ''.join(f'<div class="card"><small>{html.escape(k)}</small><b>{html.escape(str(v))}</b></div>' for k,v in stats.items())
    rows = ''.join(f'<tr><td>{i}</td><td class="{s}">{s}</td><td>{html.escape(note)}</td><td><code>{html.escape(cmd)}</code></td><td>{f"<a href={src}>{src}</a>" if src else "—"}</td></tr>' for i,s,note,cmd,src in matrix)
    points = ''.join(f'<div class="bar-row"><span>{e["index"]:02d}</span><i style="width:{max(1, min(100,e["timings"]["total_ms"] / max([v["timings"]["total_ms"] for v in turns] or [1])*100))}%"></i><small>{e["timings"]["total_ms"]:.1f} ms · LLM {e["timings"]["llm_ms"]:.1f} / TTS {e["timings"]["tts_ms"]:.1f}</small></div>' for e in turns)
    content = f'''<!doctype html><html lang="zh-Hant"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>DigitalMe · 驗收證據</title><style>body{{font:14px system-ui;background:#f5f7f0;color:#294c3a;margin:0;padding:40px;line-height:1.7}}main{{max-width:1250px;margin:auto}}h1{{font-size:30px}}.note{{padding:18px;background:#fff1d6;border-radius:10px}}.cards{{display:grid;grid-template-columns:repeat(auto-fit,minmax(160px,1fr));gap:12px;margin:24px 0}}.card{{background:white;border:1px solid #dce3d3;border-radius:10px;padding:18px}}small{{display:block;color:#829176}}b{{font-size:25px;display:block}}table{{width:100%;border-collapse:collapse;background:white}}td,th{{padding:14px;text-align:left;border-bottom:1px solid #e1e7da}}.PASS{{color:#36804e}}.PARTIAL,.UNVERIFIED{{color:#ad7d27}}.FAIL{{color:#ad4435}}a{{color:#357954}}img{{width:100%;border-radius:12px;border:1px solid #dce3d3}}.bar-row{{display:flex;align-items:center;gap:8px;margin:5px 0}}.bar-row span{{width:25px}}.bar-row i{{height:10px;background:#73966a;display:block;max-width:60%}}.bar-row small{{white-space:nowrap}}code{{font-size:11px}}@media(max-width:700px){{body{{padding:15px}}table{{font-size:10px}}td,th{{padding:5px}}}}</style><main>
    <small>DIGITALME / OBSERVED EVIDENCE</small><h1>功能可操作，驗證有界線。</h1><p class="note">此看板由原始測試輸出計算。全部語音與對話效能數據來自 Linux mock 合成測試音，不是爸爸聲音、Mac 實測或真實對嘴。Mac／聲音品質／長期家庭使用尚未驗收。</p><p>來源 commit：<code>{smoke.get('source_commit')}</code>（工作樹改動另記於 smoke.json）<br>測試時間：{smoke.get('timestamp')}<br>環境：{html.escape(str(smoke.get('environment')))}</p><div class="cards">{cards}</div><h2>需求 ↔ 測試 ↔ 證據</h2><table><thead><tr><th>ID</th><th>狀態</th><th>已測與缺口</th><th>重跑指令</th><th>原始輸出</th></tr></thead><tbody>{rows}</tbody></table><h2>20 回合時間線（Mock）</h2>{points}<p>LLM/TTS 計時不含麥克風、STT、網路和第一個可聽聲音時間；不作 ≤5 秒真機門檻證據。</p><h2>瀏覽器畫面（合成頭像）</h2><img src="ui-speaking.png" alt="播放與 RMS 嘴部動畫的瀏覽器證據"><p><a href="ui-idle.png">待機畫面</a> · <a href="ui-mobile.png">手機排版</a> · <a href="manifest.json">數據與 SHA256 manifest</a></p><h2>待驗證與未實作</h2><ul><li>Mac 舊環境盤點、真實 XTTS／MLX／Whisper、雲端或本地 LLM 推論</li><li>真實音質、冷啟動、峰值記憶體、ASR 正確率、音視偏差</li><li>macOS 透明置頂視窗、精確嘴型、監護人權限、加密備份還原</li></ul></main></html>'''
    (E/'index.html').write_text(content, encoding='utf-8')
    if face:
        content=content.replace('<h2>待驗證與未實作</h2>', '<h2>雙目建模與語音連動（全部合成素材）</h2><img src="face-builder.png" alt="雙目建模工作台與合成曲面"><p>重建報告：<a href="face-smoke.json">face-smoke.json</a>。正面 2.5D 原型，非完整頭部或本人相似度驗收。</p><img src="face-speaking.png" alt="合成曲面與對話語音連動"><h2>待驗證與未實作</h2>')
        (E/'index.html').write_text(content, encoding='utf-8')
    # Only generated synthetic evidence is copied; never mount the repository/private_data.
    dist = ROOT/'apps/web/dist'
    if dist.exists():
        (dist/'acceptance.html').write_text(content, encoding='utf-8')
        for n in manifest:
            shutil.copyfile(E/n, dist/n)
        shutil.copyfile(E/'manifest.json', dist/'manifest.json')
    print(json.dumps(stats))


if __name__ == '__main__':
    build()
