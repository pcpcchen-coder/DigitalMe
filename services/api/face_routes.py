"""Private local scan repository and explicit calibration gates."""
import asyncio
from datetime import datetime, timezone
import json
from pathlib import Path
import re
import shutil
import uuid
from typing import Literal

import cv2
import numpy as np
from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import Response
from pydantic import BaseModel, Field

from .face_geometry import GeometryError, calibration, decode_sbs, reconstruct, synthetic_pair


class NewScan(BaseModel):
    owner_consent: Literal[True]
    camera_model: Literal['Arducam B0645', 'other_uvc'] = 'Arducam B0645'
    layout_confirmed: bool = False


class Calibrate(BaseModel):
    columns: int = Field(9, ge=4, le=12)
    rows: int = Field(6, ge=4, le=9)
    square_mm: float = Field(20, ge=5, le=60)


class BuildSurface(BaseModel):
    capture_id: str = Field(pattern=r'^[a-f0-9]{32}$')
    roi: list[float] = Field(default_factory=lambda:[.18,.05,.64,.9], min_length=4, max_length=4)
    anchors: list[float] = Field(default_factory=lambda:[.5,.7,.38], min_length=3, max_length=3)


def create_router(data_dir):
    router = APIRouter(prefix='/api/face')
    processing = asyncio.Lock()

    def scan_dir(scan_id):
        if not re.fullmatch('[a-f0-9]{32}', scan_id):
            raise HTTPException(400,'INVALID_SCAN_ID')
        path = data_dir()/'faces'/scan_id
        if not (path/'scan.json').is_file():
            raise HTTPException(404,'SCAN_NOT_FOUND')
        return path

    def save(path, data):
        path.write_text(json.dumps(data, ensure_ascii=False), encoding='utf-8')
        path.chmod(0o600)

    def summary(path):
        meta = json.loads((path/'scan.json').read_text())
        meta['captures'] = json.loads((path/'captures.json').read_text())
        meta['calibration'] = json.loads((path/'calibration.json').read_text()) if (path/'calibration.json').exists() else None
        meta['model'] = json.loads((path/'model.json').read_text()) if (path/'model.json').exists() else None
        return meta

    def new(req, synthetic=False):
        path = data_dir()/'faces'/uuid.uuid4().hex
        path.mkdir(mode=0o700, parents=True)
        save(path/'scan.json', {'scan_id':path.name, 'camera_model':req.camera_model,
            'owner_consent':True, 'layout_confirmed':req.layout_confirmed, 'synthetic':synthetic,
            'created_at':datetime.now(timezone.utc).isoformat()})
        save(path/'captures.json', [])
        return path

    async def compute(fn, *args):
        # Prevent concurrent writes/deletion/reconstruction of local scan artifacts.
        if processing.locked():
            raise HTTPException(409,'SCAN_PROCESSING_BUSY')
        async with processing:
            try:
                return await asyncio.to_thread(fn, *args)
            except GeometryError as exc:
                raise HTTPException(422,str(exc)) from None
            except cv2.error:
                raise HTTPException(422,'OPENCV_PROCESSING_FAILED') from None

    @router.post('/scans')
    async def create_scan(req:NewScan):
        return summary(new(req))

    @router.get('/checkerboard.svg')
    async def board(columns:int=9,rows:int=6,square_mm:float=20):
        if not 4<=columns<=12 or not 4<=rows<=9 or not 5<=square_mm<=60:
            raise HTTPException(422,'INVALID_BOARD_DIMENSIONS')
        width,height=(columns+1)*square_mm+10,(rows+1)*square_mm+10
        squares=''.join(f'<rect x="{5+x*square_mm}" y="{5+y*square_mm}" width="{square_mm}" height="{square_mm}"/>'
            for y in range(rows+1) for x in range(columns+1) if (x+y)%2==0)
        svg=f'<svg xmlns="http://www.w3.org/2000/svg" width="{width}mm" height="{height}mm" viewBox="0 0 {width} {height}"><rect width="100%" height="100%" fill="white"/>{squares}</svg>'
        return Response(svg,media_type='image/svg+xml',headers={'Content-Disposition':'attachment; filename="stereo-checkerboard.svg"'})

    @router.post('/demo')
    async def demo():
        # Code-generated stereo imagery, never labels itself a captured owner face.
        path = new(NewScan(owner_consent=True,layout_confirmed=True), synthetic=True)
        left,right,c = synthetic_pair()
        _, image = cv2.imencode('.png', np.hstack([left,right]))
        capture_id = uuid.uuid4().hex
        p = path/f'{capture_id}.png'
        p.write_bytes(image.tobytes());p.chmod(0o600)
        save(path/'captures.json',[{'capture_id':capture_id,'purpose':'face','pose':'neutral',
            'width':left.shape[1]*2,'height':left.shape[0],'synthetic':True}])
        save(path/'calibration.json',c)
        return summary(path)

    @router.get('/scans')
    async def scans():
        parent = data_dir()/'faces'
        return [summary(p) for p in sorted(parent.glob('*')) if (p/'scan.json').is_file()] if parent.exists() else []

    @router.get('/scans/{scan_id}')
    async def get_scan(scan_id:str):
        return summary(scan_dir(scan_id))

    @router.delete('/scans/{scan_id}')
    async def delete_scan(scan_id:str):
        if processing.locked():
            raise HTTPException(409,'SCAN_PROCESSING_BUSY')
        shutil.rmtree(scan_dir(scan_id))
        return {'deleted':True,'scope':'scan_captures_calibration_and_generated_model'}

    @router.post('/scans/{scan_id}/captures')
    async def capture(scan_id:str, image:UploadFile=File(...), purpose:Literal['calibration','face']=Form('face'),
        pose:Literal['neutral','left','right','up','down','mouth_open','smile','blink']=Form('neutral')):
        if processing.locked():
            raise HTTPException(409,'SCAN_PROCESSING_BUSY')
        path = scan_dir(scan_id)
        meta = summary(path)
        if not meta['layout_confirmed']:
            raise HTTPException(409,'CONFIRM_SAME_FRAME_STEREO_LAYOUT_FIRST')
        if meta['synthetic']:
            raise HTTPException(409,'CREATE_REAL_SCAN_FOR_CAMERA_CAPTURE')
        if len(meta['captures']) >= 36:
            raise HTTPException(413,'SCAN_CAPTURE_LIMIT_36')
        raw = await image.read(8*1024*1024+1)
        if len(raw)>8*1024*1024:
            raise HTTPException(413,'IMAGE_TOO_LARGE')
        # Upload reads may yield; revalidate the latest scan after they complete.
        if processing.locked():
            raise HTTPException(409,'SCAN_PROCESSING_BUSY')
        path=scan_dir(scan_id)
        meta=summary(path)
        if len(meta['captures'])>=36:
            raise HTTPException(413,'SCAN_CAPTURE_LIMIT_36')
        try:
            left,right = decode_sbs(raw)
        except GeometryError as exc:
            raise HTTPException(422,str(exc)) from None
        if meta['captures'] and (meta['captures'][0]['width'],meta['captures'][0]['height']) != (left.shape[1]*2,left.shape[0]):
            raise HTTPException(409,'CAPTURE_RESOLUTION_CHANGED')
        capture_id = uuid.uuid4().hex
        _, png = cv2.imencode('.png',np.hstack([left,right]))
        p = path/f'{capture_id}.png'
        p.write_bytes(png.tobytes());p.chmod(0o600)
        meta['captures'].append({'capture_id':capture_id,'purpose':purpose,'pose':pose,
            'width':left.shape[1]*2,'height':left.shape[0],'synthetic':False})
        save(path/'captures.json',meta['captures'])
        return summary(path)

    @router.get('/scans/{scan_id}/captures/{capture_id}')
    async def get_capture(scan_id:str,capture_id:str):
        path = scan_dir(scan_id)
        if not any(c['capture_id']==capture_id for c in summary(path)['captures']):
            raise HTTPException(404,'CAPTURE_NOT_FOUND')
        return Response((path/f'{capture_id}.png').read_bytes(),media_type='image/png')

    @router.post('/scans/{scan_id}/calibrate')
    async def calibrate(scan_id:str,req:Calibrate):
        path = scan_dir(scan_id)
        meta = summary(path)
        if meta['synthetic']:
            raise HTTPException(409,'SYNTHETIC_CALIBRATION_CANNOT_VALIDATE_HARDWARE')
        pairs = [decode_sbs((path/f'{c["capture_id"]}.png').read_bytes()) for c in meta['captures'] if c['purpose']=='calibration']
        c = await compute(calibration,pairs,req.columns,req.rows,req.square_mm)
        save(path/'calibration.json',c)
        (path/'model.json').unlink(missing_ok=True)
        (path/'surface.glb').unlink(missing_ok=True)
        return summary(path)

    @router.post('/scans/{scan_id}/reconstruct')
    async def build(scan_id:str,req:BuildSurface):
        path = scan_dir(scan_id)
        meta = summary(path)
        if not meta['calibration']:
            raise HTTPException(409,'CALIBRATE_BEFORE_RECONSTRUCTION')
        cap = next((c for c in meta['captures'] if c['capture_id']==req.capture_id and c['purpose']=='face'),None)
        if not cap:
            raise HTTPException(404,'FACE_CAPTURE_NOT_FOUND')
        if not np.isfinite(req.roi+req.anchors).all():
            raise HTTPException(422,'INVALID_ROI_OR_ANCHORS')
        x,y,w,h = req.roi
        if min(x,y)<0 or min(w,h)<.1 or x+w>1 or y+h>1 or not all(.05<a<.95 for a in req.anchors):
            raise HTTPException(422,'INVALID_ROI_OR_ANCHORS')
        left,right = decode_sbs((path/f'{req.capture_id}.png').read_bytes())
        glb,report = await compute(reconstruct,left,right,meta['calibration'],req.roi,req.anchors)
        p = path/'surface.glb';p.write_bytes(glb);p.chmod(0o600)
        report.update(capture_id=req.capture_id,roi=req.roi,anchors=req.anchors,
            version_id=uuid.uuid4().hex, limitations=['not_full_head','no_multiview_fusion','no_anatomical_rig','no_metric_accuracy_validation'])
        save(path/'model.json',report)
        return summary(path)

    @router.get('/scans/{scan_id}/model.glb')
    async def get_model(scan_id:str):
        path = scan_dir(scan_id)
        if not (path/'surface.glb').is_file():
            raise HTTPException(404,'MODEL_NOT_BUILT')
        return Response((path/'surface.glb').read_bytes(),media_type='model/gltf-binary',
            headers={'Content-Disposition':'attachment; filename="digitalme-surface.glb"'})

    return router
