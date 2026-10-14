"""CPU stereo adapter. Metric surface reconstruction, NOT complete-head fusion/retopology."""
import json
import struct

import cv2
import numpy as np


class GeometryError(Exception):
    pass


def decode_sbs(raw):
    # Decode only PNG/JPEG with bounded header dimensions (before allocating pixels).
    if raw[:8] == b'\x89PNG\r\n\x1a\n' and len(raw) >= 24:
        width, height = struct.unpack('>II', raw[16:24])
    elif raw[:2] == b'\xff\xd8':
        from io import BytesIO
        # OpenCV allocation is bounded by upload size plus this JPEG header scan.
        offset, width, height = 2, 0, 0
        while offset + 8 < len(raw):
            if raw[offset] != 255:
                offset += 1
                continue
            marker = raw[offset+1]
            if marker in (0xD8, 0xD9):
                offset += 2
                continue
            size = int.from_bytes(raw[offset+2:offset+4], 'big')
            if marker in (0xC0, 0xC1, 0xC2):
                height, width = struct.unpack('>HH', raw[offset+5:offset+9])
                break
            if size < 2:
                break
            offset += 2 + size
    else:
        raise GeometryError('PNG_OR_JPEG_REQUIRED')
    if not (320 <= width <= 2560 and 120 <= height <= 800 and width % 2 == 0):
        raise GeometryError('SBS_DIMENSIONS_INVALID_MAX_2560x800')
    image = cv2.imdecode(np.frombuffer(raw, np.uint8), cv2.IMREAD_COLOR)
    if image is None or image.shape[:2] != (height, width):
        raise GeometryError('IMAGE_DECODE_FAILED')
    return image[:, :width//2].copy(), image[:, width//2:].copy()


def calibration(pairs, columns=9, rows=6, square_mm=20):
    if len(pairs) < 12:
        raise GeometryError('CALIBRATION_NEEDS_12_DIVERSE_PAIRS')
    obj = np.zeros((columns*rows, 3), np.float32)
    obj[:, :2] = np.mgrid[0:columns, 0:rows].T.reshape(-1, 2) * (square_mm/1000)
    objects, lefts, rights = [], [], []
    size = (pairs[0][0].shape[1], pairs[0][0].shape[0])
    for left, right in pairs:
        if (left.shape[1], left.shape[0]) != size or right.shape != left.shape:
            raise GeometryError('CAPTURE_RESOLUTION_CHANGED')
        gray1, gray2 = [cv2.cvtColor(i, cv2.COLOR_BGR2GRAY) for i in (left, right)]
        ok1, c1 = cv2.findChessboardCornersSB(gray1, (columns, rows))
        ok2, c2 = cv2.findChessboardCornersSB(gray2, (columns, rows))
        if ok1 and ok2:
            objects.append(obj)
            lefts.append(c1)
            rights.append(c2)
    if len(objects) < 12:
        raise GeometryError('CHESSBOARD_NOT_DETECTED_IN_12_PAIRS')
    centers = np.array([p.mean(axis=0).ravel() for p in lefts])
    spans = centers.max(axis=0)-centers.min(axis=0)
    if spans[0] < size[0]*.12 or spans[1] < size[1]*.12:
        raise GeometryError('CALIBRATION_POSES_TOO_SIMILAR')
    _, k1, d1, _, _ = cv2.calibrateCamera(objects, lefts, size, None, None)
    _, k2, d2, _, _ = cv2.calibrateCamera(objects, rights, size, None, None)
    rms, k1, d1, k2, d2, rotation, translation, _, _ = cv2.stereoCalibrate(
        objects, lefts, rights, k1, d1, k2, d2, size, flags=cv2.CALIB_FIX_INTRINSIC)
    baseline = float(np.linalg.norm(translation))
    if not np.isfinite(rms) or rms > 1.0 or not .005 < baseline < .15 or translation[0, 0] >= 0:
        raise GeometryError('CALIBRATION_QUALITY_FAILED_CHECK_ORDER_SCALE_AND_DIVERSITY')
    r1, r2, p1, p2, q, roi1, roi2 = cv2.stereoRectify(k1, d1, k2, d2, size, rotation, translation, alpha=0)
    return {'size': list(size), 'K1': k1.tolist(), 'D1': d1.tolist(), 'K2': k2.tolist(), 'D2': d2.tolist(),
        'R1': r1.tolist(), 'R2': r2.tolist(), 'P1': p1.tolist(), 'P2': p2.tolist(), 'Q': q.tolist(),
        'baseline_m': baseline, 'rms_px': float(rms), 'accepted_pairs': len(objects), 'synthetic': False}


def validate_calibration(c):
    for key, shape in [('K1', (3,3)), ('K2', (3,3)), ('R1', (3,3)), ('R2', (3,3)), ('P1', (3,4)), ('P2', (3,4)), ('Q', (4,4))]:
        value = np.asarray(c[key])
        if value.shape != shape or not np.isfinite(value).all():
            raise GeometryError('INVALID_CALIBRATION')
    if len(c['size']) != 2 or c['size'][0] > 1280 or c['size'][1] > 800:
        raise GeometryError('INVALID_CALIBRATION')


def reconstruct(left, right, c, roi, anchors, stride=3):
    validate_calibration(c)
    size = tuple(c['size'])
    if left.shape[:2] != (size[1], size[0]) or left.shape != right.shape:
        raise GeometryError('CALIBRATION_RESOLUTION_MISMATCH')
    rectified = []
    for side, image in [(1, left), (2, right)]:
        mx, my = cv2.initUndistortRectifyMap(np.array(c[f'K{side}']), np.array(c[f'D{side}']),
            np.array(c[f'R{side}']), np.array(c[f'P{side}']), size, cv2.CV_32FC1)
        rectified.append(cv2.remap(image, mx, my, cv2.INTER_LINEAR))
    gray1, gray2 = [cv2.cvtColor(i, cv2.COLOR_BGR2GRAY) for i in rectified]
    n = min(128, max(16, (size[0]//4)//16*16))
    options = dict(numDisparities=n, blockSize=5, P1=8*25, P2=32*25,
        disp12MaxDiff=1, uniquenessRatio=8, speckleWindowSize=60, speckleRange=2)
    d = cv2.StereoSGBM_create(minDisparity=0, **options).compute(gray1, gray2).astype(np.float32)/16
    dr = cv2.StereoSGBM_create(minDisparity=-n, **options).compute(gray2, gray1).astype(np.float32)/16
    yy, xx = np.indices(d.shape)
    xr = np.rint(xx-d).astype(int)
    inside = (xr >= 0) & (xr < size[0])
    right_match = dr[yy, np.clip(xr, 0, size[0]-1)]
    points = cv2.reprojectImageTo3D(d, np.array(c['Q']))
    x, y, w, h = roi
    nx = (xx/size[0]-x)/w
    ny = (yy/size[1]-y)/h
    crop = (nx >= 0) & (nx <= 1) & (ny >= 0) & (ny <= 1)
    ellipse = ((nx-.5)/.5)**2+((ny-.5)/.5)**2 <= 1
    mask = crop & ellipse & inside & (d > 0) & (right_match < 0) & (np.abs(d+right_match) < 1.5)
    mask &= np.isfinite(points).all(axis=2) & (points[:,:,2] > .12) & (points[:,:,2] < 1.5)
    ratio = float(mask.sum()/max(1, (crop & ellipse).sum()))
    if ratio < .08:
        raise GeometryError('INSUFFICIENT_STEREO_MATCHES_CHECK_LIGHT_TEXTURE_ORDER')
    indices = -np.ones(d.shape, dtype=np.int32)
    pixels = np.argwhere(mask[::stride, ::stride])*stride
    if len(pixels) < 100:
        raise GeometryError('INSUFFICIENT_SURFACE_POINTS')
    indices[pixels[:,0], pixels[:,1]] = np.arange(len(pixels))
    xyz = points[pixels[:,0], pixels[:,1]].copy()
    xyz[:,1:] *= -1  # OpenCV camera to glTF: +Y up, camera faces -Z.
    xyz -= np.median(xyz, axis=0)
    uv = np.column_stack([pixels[:,1]/(size[0]-1), pixels[:,0]/(size[1]-1)]).astype(np.float32)
    faces = []
    for py, px in pixels:
        if py+stride >= size[1] or px+stride >= size[0]:
            continue
        a,b,cc,dd = indices[py,px], indices[py,px+stride], indices[py+stride,px], indices[py+stride,px+stride]
        for tri in ((a,cc,b), (b,cc,dd)):
            if min(tri) >= 0 and np.ptp(xyz[list(tri),2]) < .02:
                faces.append(tri)
    if len(faces) < 80:
        raise GeometryError('INSUFFICIENT_CONNECTED_SURFACE')
    # Local procedural rig for a depth surface, not anatomical retopology or teeth/eye rig.
    local_x = (uv[:,0]-x)/w
    local_y = (uv[:,1]-y)/h
    mouth_x, mouth_y, eye_y = anchors
    jaw = np.zeros_like(xyz)
    influence = np.exp(-((local_x-mouth_x)/.28)**2) * np.clip((local_y-mouth_y+.05)/.25, 0, 1)
    jaw[:,1] = -.018*influence
    jaw[:,2] = -.005*influence
    pucker = np.zeros_like(xyz)
    lips = np.exp(-((local_x-mouth_x)/.16)**2-((local_y-mouth_y)/.09)**2)
    pucker[:,0] = (.5-local_x)*.012*lips
    pucker[:,2] = .008*lips
    blinks = []
    for center in (.32, .68):
        delta = np.zeros_like(xyz)
        region = np.exp(-((local_x-center)/.1)**2-((local_y-eye_y)/.07)**2)
        delta[:,1] = (local_y-eye_y)*.04*region
        blinks.append(delta)
    _, png = cv2.imencode('.png', rectified[0])
    glb = make_glb(xyz.astype(np.float32), np.array(faces, np.uint32), uv,
        [jaw.astype(np.float32), pucker.astype(np.float32)]+[b.astype(np.float32) for b in blinks], png.tobytes())
    return glb, {'vertices': len(xyz), 'triangles': len(faces), 'valid_ratio': round(ratio,4),
        'median_depth_m': float(np.median(points[pixels[:,0],pixels[:,1],2])),
        'surface_kind': 'single_view_2.5d', 'rig_kind': 'procedural_approximate',
        'morph_targets': ['jawOpen', 'mouthPucker', 'eyeBlinkLeft', 'eyeBlinkRight'],
        'synthetic': bool(c['synthetic']), 'metric_accuracy_verified': False}


def make_glb(positions, triangles, uv, targets, texture_png):
    binary, views, accessors = bytearray(), [], []
    def view(raw):
        while len(binary)%4:
            binary.append(0)
        offset = len(binary)
        binary.extend(raw)
        views.append({'buffer': 0, 'byteOffset': offset, 'byteLength': len(raw)})
        return len(views)-1
    def accessor(array, shape, component=5126, bounds=False):
        idx = view(array.tobytes())
        a = {'bufferView':idx, 'componentType':component, 'count':len(array), 'type':shape}
        if bounds:
            a.update(min=array.min(axis=0).tolist(), max=array.max(axis=0).tolist())
        accessors.append(a)
        return len(accessors)-1
    pos = accessor(positions, 'VEC3', bounds=True)
    tex = accessor(uv, 'VEC2')
    ind = accessor(triangles.reshape(-1), 'SCALAR', 5125)
    morphs = [{'POSITION':accessor(t, 'VEC3', bounds=True)} for t in targets]
    texture_view = view(texture_png)
    doc = {'asset': {'version':'2.0', 'generator':'DigitalMe CPU stereo prototype'},
        'scene':0, 'scenes':[{'nodes':[0]}], 'nodes':[{'mesh':0}],
        'meshes':[{'name':'StereoSurface', 'weights':[0]*len(targets),
            'extras':{'targetNames':['jawOpen','mouthPucker','eyeBlinkLeft','eyeBlinkRight']},
            'primitives':[{'attributes':{'POSITION':pos, 'TEXCOORD_0':tex}, 'indices':ind,
                'material':0, 'targets':morphs}]}],
        'materials':[{'doubleSided':True, 'pbrMetallicRoughness':{'baseColorTexture':{'index':0}},
            'extensions':{'KHR_materials_unlit':{}}}], 'extensionsUsed':['KHR_materials_unlit'],
        'textures':[{'source':0}], 'images':[{'bufferView':texture_view,'mimeType':'image/png'}],
        'buffers':[{'byteLength':len(binary)}], 'bufferViews':views, 'accessors':accessors}
    raw = json.dumps(doc, separators=(',', ':')).encode()
    raw += b' ' * (-len(raw)%4)
    binary.extend(b'\0' * (-len(binary)%4))
    return struct.pack('<III', 0x46546c67, 2, 12+8+len(raw)+8+len(binary)) + struct.pack('<II',len(raw),0x4e4f534a)+raw + struct.pack('<II',len(binary),0x004e4942)+binary


def synthetic_pair():
    width, height, focal, baseline = 320, 240, 300., .02
    yy, xx = np.indices((height,width))
    ellipse = ((xx-width/2)/95)**2+((yy-height/2)/108)**2
    depth = .58-.055*np.clip(1-ellipse,0,1)-.015*np.exp(-((xx-160)/18)**2-((yy-125)/25)**2)
    rng = np.random.default_rng(42)
    texture = rng.integers(0,100,(height,width,1),dtype=np.uint8)
    left = np.clip(texture+np.array([80,115,145],dtype=np.uint8),0,255).astype(np.uint8)
    left[ellipse > 1] = np.repeat(texture,3,axis=2)[ellipse > 1]
    cv2.ellipse(left,(130,95),(10,5),0,0,360,(25,38,35),-1)
    cv2.ellipse(left,(190,95),(10,5),0,0,360,(25,38,35),-1)
    cv2.ellipse(left,(160,163),(17,3),0,0,360,(50,65,95),-1)
    # Inverse warp at subpixel coordinates: no artificial quantized depth rings.
    source_x=xx.astype(np.float32)
    for _ in range(4):
        at=np.clip(np.rint(source_x).astype(int),0,width-1)
        source_x=xx.astype(np.float32)+focal*baseline/depth[yy,at]
    right=cv2.remap(left,source_x.astype(np.float32),yy.astype(np.float32),cv2.INTER_LINEAR,borderMode=cv2.BORDER_CONSTANT)
    k = np.array([[focal,0,width/2],[0,focal,height/2],[0,0,1.]])
    r1,r2,p1,p2,q,_,_ = cv2.stereoRectify(k,np.zeros(5),k,np.zeros(5),(width,height),np.eye(3),np.array([[-baseline],[0.],[0.]]),alpha=0)
    c = {'size':[width,height], 'K1':k.tolist(), 'K2':k.tolist(), 'D1':[0.]*5, 'D2':[0.]*5,
        'R1':r1.tolist(),'R2':r2.tolist(),'P1':p1.tolist(),'P2':p2.tolist(),'Q':q.tolist(),
        'baseline_m':baseline, 'rms_px':None, 'accepted_pairs':0, 'synthetic':True}
    return left,right,c
