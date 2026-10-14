import asyncio
import io
import json
from pathlib import Path
import struct
import wave

import cv2
from fastapi.testclient import TestClient
import numpy as np
import pytest

from services.api import main
from services.api.face_geometry import GeometryError, calibration, decode_sbs, reconstruct, synthetic_pair
from services.api.lipsync import timeline


@pytest.fixture
def client(tmp_path,monkeypatch):
    monkeypatch.setattr(main,'PRIVATE',tmp_path)
    monkeypatch.delenv('RHUBARB_BIN',raising=False)
    with TestClient(main.app,raise_server_exceptions=False) as c:yield c


def glb_doc(raw):
    magic,version,length=struct.unpack('<III',raw[:12])
    assert magic==0x46546c67 and version==2 and length==len(raw)
    size,kind=struct.unpack('<II',raw[12:20]);assert kind==0x4e4f534a
    return json.loads(raw[20:20+size])


def test_surface_pipeline_private_export_and_delete(client):
    s=client.post('/api/face/demo').json();sid=s['scan_id']
    assert s['synthetic'] and s['calibration']['synthetic']
    s=client.post(f'/api/face/scans/{sid}/reconstruct',json={'capture_id':s['captures'][0]['capture_id']}).json()
    m=s['model'];assert m['vertices']>1000 and m['triangles']>1000 and m['valid_ratio']>.5
    assert m['metric_accuracy_verified'] is False and m['surface_kind']=='single_view_2.5d'
    result=client.get(f'/api/face/scans/{sid}/model.glb');assert result.status_code==200
    doc=glb_doc(result.content)
    assert doc['meshes'][0]['extras']['targetNames']==['jawOpen','mouthPucker','eyeBlinkLeft','eyeBlinkRight']
    assert all('uri' not in item for item in doc['buffers']+doc['images'])
    assert client.delete(f'/api/face/scans/{sid}').status_code==200
    assert client.get(f'/api/face/scans/{sid}/model.glb').status_code==404
    assert not (main.PRIVATE/'faces'/sid).exists()


def test_face_consent_and_calibration_gates(client):
    assert client.post('/api/face/scans',json={'owner_consent':False}).status_code==422
    s=client.post('/api/face/scans',json={'owner_consent':True}).json();sid=s['scan_id']
    assert client.post(f'/api/face/scans/{sid}/captures',files={'image':('x.png',b'x')}).status_code==409
    assert client.post(f'/api/face/scans/{sid}/reconstruct',json={'capture_id':'a'*32}).json()['error']['code']=='CALIBRATE_BEFORE_RECONSTRUCTION'
    assert client.post(f'/api/face/scans/{sid}/calibrate',json={}).json()['error']['code']=='CALIBRATION_NEEDS_12_DIVERSE_PAIRS'


def test_no_real_capture_can_use_synthetic_calibration(client):
    s=client.post('/api/face/demo').json();sid=s['scan_id']
    assert client.post(f'/api/face/scans/{sid}/captures',files={'image':('x.png',b'x')}).status_code==409
    assert client.post(f'/api/face/scans/{sid}/calibrate',json={}).status_code==409


def test_bounded_images_resolution_changes_and_invalid_roi(client):
    s=client.post('/api/face/scans',json={'owner_consent':True,'layout_confirmed':True}).json();sid=s['scan_id']
    fake=b'\x89PNG\r\n\x1a\n'+b'0'*8+struct.pack('>II',999999,999999)
    assert client.post(f'/api/face/scans/{sid}/captures',files={'image':('bomb.png',fake)}).status_code==422
    left,right,_=synthetic_pair();_,raw=cv2.imencode('.png',np.hstack([left,right]))
    s=client.post(f'/api/face/scans/{sid}/captures',files={'image':('pair.png',raw.tobytes())}).json()
    assert len(s['captures'])==1 and s['captures'][0]['width']==640
    _,small=cv2.imencode('.png',np.hstack([left,right])[::2,::2])
    assert client.post(f'/api/face/scans/{sid}/captures',files={'image':('small.png',small.tobytes())}).status_code==409
    demo=client.post('/api/face/demo').json()
    assert client.post(f'/api/face/scans/{demo["scan_id"]}/reconstruct',json={'capture_id':demo['captures'][0]['capture_id'],'roi':[.9,.1,.8,.8]}).status_code==422


def test_stereo_depth_scale_from_known_disparity():
    left,_,c=synthetic_pair();rng=np.random.default_rng(7);left=rng.integers(0,256,left.shape,dtype=np.uint8)
    right=np.zeros_like(left);right[:,:-12]=left[:,12:]
    _,r=reconstruct(left,right,c,[.2,.1,.6,.8],[.5,.7,.38])
    assert abs(r['median_depth_m']-.5)<.003  # Z=f*B/disparity = 300*.02/12
    with pytest.raises(GeometryError,match='INSUFFICIENT'):
        reconstruct(np.zeros_like(left),np.zeros_like(left),c,[.2,.1,.6,.8],[.5,.7,.38])


def test_metric_chessboard_calibration_recovers_virtual_baseline():
    width,height,focal=640,480,600.
    k=np.array([[focal,0,width/2],[0,focal,height/2],[0,0,1.]])
    board=np.array([[-.02,-.02,0],[.18,-.02,0],[.18,.12,0],[-.02,.12,0]],np.float32)
    template=np.full((350,500),255,np.uint8)
    for y in range(7):
        for x in range(10):
            if (x+y)%2==0:template[y*50:(y+1)*50,x*50:(x+1)*50]=0
    source=np.array([[0,0],[500,0],[500,350],[0,350]],np.float32)
    pairs=[]
    for i in range(16):
        r=np.array([.12*np.sin(i),.23*np.cos(i*.7),.04*np.sin(i*.8)])
        t=np.array([-.11+(i%4)*.035,-.08+(i//4)*.03,.48+.03*(i%3)])
        imgs=[]
        for dx in (0,-.02):
            points,_=cv2.projectPoints(board,r,t+np.array([dx,0,0]),k,np.zeros(5))
            h=cv2.getPerspectiveTransform(source,points.reshape(-1,2).astype(np.float32))
            image=cv2.warpPerspective(template,h,(width,height),borderValue=180)
            imgs.append(cv2.cvtColor(image,cv2.COLOR_GRAY2BGR))
        pairs.append(tuple(imgs))
    c=calibration(pairs,9,6,20)
    assert abs(c['baseline_m']-.02)<.002 and c['rms_px']<1 and c['accepted_pairs']>=12


def test_board_svg_print_dimensions_and_no_private_identifiers(client):
    r=client.get('/api/face/checkerboard.svg')
    import xml.etree.ElementTree as ET
    doc=ET.fromstring(r.text)
    assert r.status_code==200 and float(doc.attrib['width'].removesuffix('mm'))==210 and float(doc.attrib['height'].removesuffix('mm'))==150
    assert client.get('/api/face/checkerboard.svg?columns=1000').status_code==422
    assert client.get('/api/face/scans/../../').status_code!=200


def audio(samples,rate=16000):
    f=io.BytesIO()
    with wave.open(f,'wb') as w:
        w.setparams((1,2,rate,0,'NONE',''));w.writeframes(np.asarray(samples,dtype='<i2').tobytes())
    return f.getvalue()


def test_lipsync_timing_and_rest():
    data=audio(np.r_[np.zeros(320),np.full(320,12000),np.zeros(320)])
    out=asyncio.run(timeline(data))
    assert out['driver']=='rms_approximate' and out['duration_seconds']==.06
    assert out['frames'][0]['jawOpen']==0
    assert max(f['jawOpen'] for f in out['frames'])>.8
    assert out['frames'][-1]['time']==.06 and out['frames'][-1]['jawOpen']==0


def test_lipsync_api_errors_are_explicit_and_turn_contains_timeline(client):
    raw=audio(np.zeros(1600))
    r=client.post('/api/lipsync',files={'audio':('s.wav',raw,'audio/wav')},data={'engine':'rhubarb'})
    assert r.status_code==503 and r.json()['error']['code']=='RHUBARB_NOT_CONFIGURED'
    r=client.post('/api/lipsync',files={'audio':('s.wav',b'invalid','audio/wav')})
    assert r.status_code==503
    r=client.post('/api/turn',json={'user_text':'合成語音測試'})
    assert r.status_code==200 and r.json()['animation']['frames'][-1]['jawOpen']==0
