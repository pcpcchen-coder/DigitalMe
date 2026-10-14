"""Actual OpenCV synthetic stereo → GLB → audio motion acceptance trace."""
import asyncio
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import platform
import subprocess
import sys
import tempfile
import time

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from fastapi.testclient import TestClient
from services.api import main
from services.api.adapters import mock_wav
from services.api.lipsync import timeline

with tempfile.TemporaryDirectory() as tmp:
    main.PRIVATE=Path(tmp)
    with TestClient(main.app) as client:
        s=client.post('/api/face/demo').json()
        start=time.perf_counter()
        response=client.post(f'/api/face/scans/{s["scan_id"]}/reconstruct',json={'capture_id':s['captures'][0]['capture_id']})
        elapsed=(time.perf_counter()-start)*1000
        assert response.status_code==200
        model=response.json()['model']
        glb=client.get(f'/api/face/scans/{s["scan_id"]}/model.glb').content
        motion=asyncio.run(timeline(mock_wav('這是一段用來測試合成人臉模型與語音時間軸的測試文字。')))
        assert motion['frames'][-1]['jawOpen']==0
        assert client.delete(f'/api/face/scans/{s["scan_id"]}').status_code==200
        assert client.get(f'/api/face/scans/{s["scan_id"]}').status_code==404
        report={'source_commit':subprocess.check_output(['git','rev-parse','HEAD'],cwd=ROOT,text=True).strip(),
            'timestamp':datetime.now(timezone.utc).isoformat(),'os':platform.system(),'arch':platform.machine(),
            'scope':'synthetic calibrated stereo only; no owner face or physical camera',
            'hardware_verified':False,'full_head':False,'anatomical_rig':False,
            'reconstruction_ms':round(elapsed,3),'vertices':model['vertices'],'triangles':model['triangles'],
            'valid_ratio':model['valid_ratio'],'glb_bytes':len(glb),'glb_sha256':hashlib.sha256(glb).hexdigest(),
            'morph_targets':model['morph_targets'],'deletion_verified':True,'motion_frames':len(motion['frames']),
            'max_jaw_open':max(f['jawOpen'] for f in motion['frames']),'audio_duration_seconds':motion['duration_seconds'],
            'driver':motion['driver'],'last_frame_rest':motion['frames'][-1]['jawOpen']==0}
        (ROOT/'evidence/face-smoke.json').write_text(json.dumps(report,indent=2))
        print(json.dumps(report))
