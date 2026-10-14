import { useEffect, useRef, useState, type MutableRefObject } from "react";
import FaceViewer, { type Motion } from "./FaceViewer";
import { inspectGLB } from "./face-motion.mjs";
import "./face.css";

type Capture = {
  capture_id: string;
  purpose: string;
  pose: string;
  width: number;
  height: number;
};
type Scan = {
  scan_id: string;
  synthetic: boolean;
  camera_model: string;
  captures: Capture[];
  calibration: null | {
    synthetic: boolean;
    rms_px: number | null;
    baseline_m: number;
    accepted_pairs: number;
  };
  model: null | {
    vertices: number;
    triangles: number;
    valid_ratio: number;
    surface_kind: string;
    version_id: string;
  };
};
async function request(path: string, options: RequestInit = {}) {
  const r = await fetch("/api/face" + path, options);
  if (!r.ok) {
    let d = await r.json();
    throw Error(d.error?.code || "FACE_REQUEST_FAILED");
  }
  return r;
}
export default function FaceBuilder({
  drive,
  onUse,
  onSpeak,
  busy,
  ttsEngine,
  voiceId,
  lipEngine,
  onLipEngine,
}: {
  drive: MutableRefObject<Motion>;
  onUse: (model: ArrayBuffer) => void;
  onSpeak: (text: string) => Promise<void>;
  busy: boolean;
  ttsEngine: string;
  voiceId: string;
  lipEngine: string;
  onLipEngine: (engine: string) => void;
}) {
  const [scan, setScan] = useState<Scan | null>(null),
    [scans, setScans] = useState<Scan[]>([]),
    [error, setError] = useState(""),
    [working, setWorking] = useState(false);
  const [consent, setConsent] = useState(false),
    [layout, setLayout] = useState(false),
    [device, setDevice] = useState(""),
    [devices, setDevices] = useState<MediaDeviceInfo[]>([]),
    [connected, setConnected] = useState(false),
    [resolution, setResolution] = useState("尚未連接攝影機");
  const [purpose, setPurpose] = useState("calibration"),
    [pose, setPose] = useState("neutral"),
    [chosen, setChosen] = useState(""),
    [swap, setSwap] = useState(false);
  const [columns, setColumns] = useState(9),
    [rows, setRows] = useState(6),
    [square, setSquare] = useState(20);
  const [roi, setRoi] = useState([0.18, 0.05, 0.64, 0.9]),
    [anchors, setAnchors] = useState([0.5, 0.7, 0.38]);
  const [model, setModel] = useState<ArrayBuffer | null>(null),
    [modelSource, setModelSource] = useState(""),
    [talk, setTalk] = useState(
      "你好，這是我的數位分身。我們一起把故事留下來。",
    );
  const [manualJaw, setManualJaw] = useState(0),
    [status, setStatus] = useState("先確認左右影像與授權，再建立私人掃描。");
  const video = useRef<HTMLVideoElement>(null),
    stream = useRef<MediaStream | null>(null);
  useEffect(() => {
    request("/scans")
      .then((r) => r.json())
      .then(setScans)
      .catch((e) => setError(e.message));
    return () => stream.current?.getTracks().forEach((t) => t.stop());
  }, []);
  async function task(fn: () => Promise<void>) {
    setError("");
    setWorking(true);
    try {
      await fn();
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setWorking(false);
    }
  }
  async function update(s: Scan) {
    setScan(s);
    setScans(await (await request("/scans")).json());
    setChosen(
      s.captures.filter((c) => c.purpose === "face").at(-1)?.capture_id || "",
    );
    setModel(null);
    setModelSource("");
    if (s.model) {
      const data = await (
        await request(`/scans/${s.scan_id}/model.glb`)
      ).arrayBuffer();
      inspectGLB(data);
      setModel(data);
      setModelSource(
        s.synthetic
          ? "合成深度曲面 · 非本人模型"
          : "雙目單視角曲面 · 待本人驗收",
      );
    }
  }
  async function connect() {
    setError("");
    try {
      stream.current?.getTracks().forEach((t) => t.stop());
      const s = await navigator.mediaDevices.getUserMedia({
        video: {
          deviceId: device ? { exact: device } : undefined,
          width: { ideal: 2560 },
          height: { ideal: 800 },
          frameRate: { ideal: 30 },
        },
        audio: false,
      });
      stream.current = s;
      if (video.current) {
        video.current.srcObject = s;
        await video.current.play();
      }
      setDevices(
        (await navigator.mediaDevices.enumerateDevices()).filter(
          (d) => d.kind === "videoinput",
        ),
      );
      const t = s.getVideoTracks()[0].getSettings();
      setResolution(
        `${t.width} × ${t.height} @ ${t.frameRate?.toFixed(1) || "?"} fps · 須人工確認同一幀左右影像`,
      );
      setConnected(true);
    } catch {
      setConnected(false);
      setError("無法開啟攝影機。請在本機允許相機權限，或匯入同一幀 SBS 圖片。");
    }
  }
  async function upload(file: Blob) {
    if (!scan) return;
    const data = new FormData();
    data.append("image", file, "stereo.png");
    data.append("purpose", purpose);
    data.append("pose", pose);
    await update(
      await (
        await request(`/scans/${scan.scan_id}/captures`, {
          method: "POST",
          body: data,
        })
      ).json(),
    );
    setStatus("已存到本機私人掃描；原圖未傳公開 Repo。");
  }
  async function capture() {
    const v = video.current!;
    if (!v.videoWidth || v.videoWidth % 2) throw Error("SBS_FRAME_NOT_READY");
    const canvas = document.createElement("canvas");
    canvas.width = v.videoWidth;
    canvas.height = v.videoHeight;
    const ctx = canvas.getContext("2d")!;
    if (swap) {
      const w = canvas.width / 2;
      ctx.drawImage(v, w, 0, w, canvas.height, 0, 0, w, canvas.height);
      ctx.drawImage(v, 0, 0, w, canvas.height, w, 0, w, canvas.height);
    } else ctx.drawImage(v, 0, 0);
    const blob = await new Promise<Blob>((resolve, reject) =>
      canvas.toBlob(
        (b) => (b ? resolve(b) : reject(Error("CAPTURE_FAILED"))),
        "image/png",
      ),
    );
    await upload(blob);
  }
  const face = scan?.captures.filter((c) => c.purpose === "face") || [],
    cal = scan?.captures.filter((c) => c.purpose === "calibration") || [];
  return (
    <div className="face-builder">
      <div className="face-intro">
        <div>
          <span className="eyebrow">STEREO → SURFACE → RIG → VOICE</span>
          <h2>雙目人臉模型工作台</h2>
          <p>
            預設 Arducam RoAD.B
            B0645。以實測校正建立有尺度的表面，再接上同一份語音時間軸。
          </p>
        </div>
        <span className="badge">硬體／本人外觀尚未驗收</span>
      </div>
      <div className="face-warning">
        第一版產生<strong>正面 2.5D 曲面＋程序形變</strong>
        ，尚無後腦、多視角融合、牙齒或解剖級表情綁定。合成示範只用於驗證流程。
      </div>
      {error && (
        <div role="alert" className="error">
          {error}
        </div>
      )}
      <div className="face-toolbar">
        <label>
          本機掃描
          <select
            aria-label="本機掃描"
            value={scan?.scan_id || ""}
            onChange={(e) =>
              task(async () => {
                await update(
                  await (await request("/scans/" + e.target.value)).json(),
                );
              })
            }
          >
            <option value="">選擇或建立掃描</option>
            {scans.map((s, i) => (
              <option key={s.scan_id} value={s.scan_id}>
                {s.synthetic ? "合成示範" : "私人掃描"} {i + 1}
              </option>
            ))}
          </select>
        </label>
        <button
          disabled={working}
          onClick={() =>
            task(async () => {
              await update(
                await (await request("/demo", { method: "POST" })).json(),
              );
              setStatus(
                "合成示範已載入：已知虛擬相機，不能證明實體相機校正成功。",
              );
            })
          }
        >
          載入合成雙目示範
        </button>
        {scan && (
          <button
            disabled={working}
            onClick={() =>
              task(async () => {
                await request("/scans/" + scan.scan_id, { method: "DELETE" });
                setScan(null);
                setModel(null);
                setChosen("");
                setScans(await (await request("/scans")).json());
                setStatus(
                  "此掃描原圖、校正與生成模型已刪除；已下載／載入副本需自行移除。",
                );
              })
            }
          >
            刪除此掃描與模型
          </button>
        )}
      </div>
      <div className="face-grid">
        <section className="panel capture-panel">
          <div className="section-label">
            01 <span>設備與私人採集</span>
          </div>
          <label className="check">
            <input
              type="checkbox"
              checked={consent}
              onChange={(e) => setConsent(e.target.checked)}
            />
            我有權建立此人臉模型，素材只保存在本機
          </label>
          <label className="check">
            <input
              type="checkbox"
              checked={layout}
              onChange={(e) => setLayout(e.target.checked)}
            />
            已確認單一同步 SBS 影格，左半為左眼、右半為右眼
          </label>
          <button
            className="primary"
            disabled={!consent || !layout || working}
            onClick={() =>
              task(async () => {
                await update(
                  await (
                    await request("/scans", {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        owner_consent: consent,
                        layout_confirmed: layout,
                        camera_model: "Arducam B0645",
                      }),
                    })
                  ).json(),
                );
              })
            }
          >
            建立私人掃描
          </button>
          <div className="camera-controls">
            <select
              aria-label="攝影機"
              value={device}
              onChange={(e) => setDevice(e.target.value)}
            >
              <option value="">系統預設攝影機</option>
              {devices.map((d, i) => (
                <option value={d.deviceId} key={d.deviceId}>
                  {d.label || `攝影機 ${i + 1}`}
                </option>
              ))}
            </select>
            <button onClick={connect}>連接／切換攝影機</button>
            <button
              onClick={() => {
                stream.current?.getTracks().forEach((t) => t.stop());
                if (video.current) video.current.srcObject = null;
                setConnected(false);
              }}
            >
              停止攝影機
            </button>
          </div>
          <div className="stereo-feed">
            <video ref={video} playsInline muted />
            <span className="stereo-left">L</span>
            <span className="stereo-right">R</span>
            <span className="stereo-divider" />
            {!connected && (
              <div className="camera-empty">
                相機影像僅在 localhost 採集
                <br />
                尚未連接實體 B0645
              </div>
            )}
          </div>
          <small>{resolution}</small>
          <label className="check">
            <input
              type="checkbox"
              checked={swap}
              onChange={(e) => setSwap(e.target.checked)}
            />
            拍攝時交換左右半幅（不要鏡像翻轉）
          </label>
          <div className="fields">
            <label>
              採集用途
              <select
                aria-label="採集用途"
                value={purpose}
                onChange={(e) => setPurpose(e.target.value)}
              >
                <option value="calibration">棋盤格校正</option>
                <option value="face">人臉／表情</option>
              </select>
            </label>
            <label>
              姿態標籤
              <select
                aria-label="姿態標籤"
                value={pose}
                onChange={(e) => setPose(e.target.value)}
              >
                {[
                  ["neutral", "正面中性"],
                  ["left", "左轉"],
                  ["right", "右轉"],
                  ["up", "抬頭"],
                  ["down", "低頭"],
                  ["mouth_open", "張嘴"],
                  ["smile", "微笑"],
                  ["blink", "閉眼"],
                ].map(([v, l]) => (
                  <option key={v} value={v}>
                    {l}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <div className="face-toolbar">
            <button
              disabled={!connected || !scan || scan.synthetic || working}
              onClick={() => task(capture)}
            >
              擷取同步影格
            </button>
            <label className="upload compact">
              匯入 SBS 圖片
              <input
                aria-label="匯入 SBS 圖片"
                type="file"
                accept="image/png,image/jpeg"
                disabled={!scan || scan.synthetic || working}
                onChange={(e) => {
                  const f = e.target.files?.[0];
                  if (f) task(() => upload(f));
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          <div className="capture-counts">
            <span>校正 {cal.length} / 至少 12 組</span>
            <span>人臉 {face.length} 組</span>
          </div>
          <p className="hint">
            校正時移動與傾斜棋盤格，涵蓋不同位置與距離；拍臉時先維持中性表情。左右轉頭影像目前只保存，未做融合。
          </p>
        </section>
        <section className="panel">
          <div className="section-label">
            02 <span>校正與重建</span>
          </div>
          <div className="calibration-fields">
            <label>
              內角點欄數
              <input
                aria-label="內角點欄數"
                type="number"
                min={4}
                max={12}
                value={columns}
                onChange={(e) => setColumns(+e.target.value)}
              />
            </label>
            <label>
              內角點列數
              <input
                aria-label="內角點列數"
                type="number"
                min={4}
                max={9}
                value={rows}
                onChange={(e) => setRows(+e.target.value)}
              />
            </label>
            <label>
              方格邊長 mm
              <input
                aria-label="方格邊長 mm"
                type="number"
                min={5}
                max={60}
                value={square}
                onChange={(e) => setSquare(+e.target.value)}
              />
            </label>
          </div>
          <p>使用實際尺量的方格尺寸，不能只填 20 mm 基線就當成完成相機校正。</p>
          <a
            href={`/api/face/checkerboard.svg?columns=${columns}&rows=${rows}&square_mm=${square}`}
            download="stereo-checkerboard.svg"
          >
            下載棋盤格 SVG（列印 100%，請尺量）
          </a>
          <button
            className="primary"
            disabled={!scan || scan.synthetic || cal.length < 12 || working}
            onClick={() =>
              task(async () => {
                await update(
                  await (
                    await request(`/scans/${scan!.scan_id}/calibrate`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        columns,
                        rows,
                        square_mm: square,
                      }),
                    })
                  ).json(),
                );
                setStatus("已完成雙目校正；仍需以量測物確認深度誤差。");
              })
            }
          >
            執行雙目校正
          </button>
          <div className="calibration-state">
            {scan?.calibration ? (
              <>
                <b>
                  {scan.calibration.synthetic
                    ? "虛擬相機校正（合成測試）"
                    : "棋盤格校正結果"}
                </b>
                <span>
                  基線 {(scan.calibration.baseline_m * 1000).toFixed(2)} mm
                </span>
                <span>
                  RMS{" "}
                  {scan.calibration.rms_px === null
                    ? "不適用"
                    : scan.calibration.rms_px.toFixed(3) + " px"}
                </span>
              </>
            ) : (
              <span>尚未校正 · 禁止估造深度</span>
            )}
          </div>
          <label>
            選擇正面影格
            <select
              aria-label="選擇正面影格"
              value={chosen}
              onChange={(e) => setChosen(e.target.value)}
            >
              <option value="">尚無人臉影格</option>
              {face.map((c, i) => (
                <option value={c.capture_id} key={c.capture_id}>
                  {c.pose} · {i + 1} · {c.width}×{c.height}
                </option>
              ))}
            </select>
          </label>
          {chosen && scan && (
            <div className="sbs-image">
              <img
                alt="已保存的左右同步影格"
                src={`/api/face/scans/${scan.scan_id}/captures/${chosen}`}
              />
              <div
                className="face-roi"
                style={{
                  left: `${roi[0] * 50}%`,
                  top: `${roi[1] * 100}%`,
                  width: `${roi[2] * 50}%`,
                  height: `${roi[3] * 100}%`,
                }}
              />
            </div>
          )}
          <details>
            <summary>裁切與形變錨點（手動對齊）</summary>
            <div className="anchor-grid">
              {["ROI X", "ROI Y", "ROI 寬", "ROI 高"].map((label, i) => (
                <label key={label}>
                  {label}
                  <input
                    aria-label={label}
                    type="number"
                    step={0.01}
                    min={0}
                    max={1}
                    value={roi[i]}
                    onChange={(e) =>
                      setRoi((v) =>
                        v.map((n, j) => (i === j ? +e.target.value : n)),
                      )
                    }
                  />
                </label>
              ))}
              {["嘴部 X", "嘴部 Y", "眼睛 Y"].map((label, i) => (
                <label key={label}>
                  {label}
                  <input
                    aria-label={label}
                    type="range"
                    min={0.1}
                    max={0.9}
                    step={0.01}
                    value={anchors[i]}
                    onChange={(e) =>
                      setAnchors((v) =>
                        v.map((n, j) => (i === j ? +e.target.value : n)),
                      )
                    }
                  />
                </label>
              ))}
            </div>
            <small>
              錨點相對 ROI，先在中性正面定位；不是已訓練的表情 rig。
            </small>
          </details>
          <button
            className="primary"
            disabled={!scan?.calibration || !chosen || working}
            onClick={() =>
              task(async () => {
                await update(
                  await (
                    await request(`/scans/${scan!.scan_id}/reconstruct`, {
                      method: "POST",
                      headers: { "Content-Type": "application/json" },
                      body: JSON.stringify({
                        capture_id: chosen,
                        roi,
                        anchors,
                      }),
                    })
                  ).json(),
                );
                setStatus(
                  "曲面與 GLB 已建立；請檢查孔洞、嘴部錨點與外觀後再用於對話。",
                );
              })
            }
          >
            {working ? "處理中…" : "建立曲面與說話形變 GLB"}
          </button>
        </section>
      </div>
      <section className="panel face-rig-panel">
        <div>
          <div className="section-label">
            03 <span>模型預覽與聲音銜接</span>
          </div>
          <div className="model-stage">
            {model ? (
              <FaceViewer model={model} drive={drive} />
            ) : (
              <div className="empty">
                建立曲面，或匯入已綁定 jawOpen 的 GLB。
                <br />
                私人模型只留在本機。
              </div>
            )}
          </div>
          <small>{modelSource}</small>
          {scan?.model && (
            <div className="model-stats">
              <span>{scan.model.vertices} 頂點</span>
              <span>{scan.model.triangles} 三角面</span>
              <span>有效匹配 {(scan.model.valid_ratio * 100).toFixed(1)}%</span>
            </div>
          )}
        </div>
        <div>
          <p>
            先測試張嘴，再用實際播放時間驅動模型。可用 Blender 精修 GLB
            後重新匯入；保留 jawOpen、mouthPucker、eyeBlinkLeft／Right。
          </p>
          <label>
            手動張嘴測試
            <input
              aria-label="手動張嘴測試"
              type="range"
              min={0}
              max={1}
              step={0.01}
              value={manualJaw}
              onChange={(e) => {
                const n = +e.target.value;
                setManualJaw(n);
                drive.current = { jawOpen: n, mouthPucker: 0, manual: true };
              }}
            />
          </label>
          <label>
            嘴型驅動
            <select
              aria-label="嘴型驅動"
              value={lipEngine}
              onChange={(e) => onLipEngine(e.target.value)}
            >
              <option value="rms">RMS 音量時間軸 · 近似</option>
              <option value="rhubarb">
                Rhubarb phonetic · 需本機設定，中文待驗收
              </option>
            </select>
          </label>
          <textarea
            aria-label="模型試音文字"
            value={talk}
            onChange={(e) => setTalk(e.target.value)}
            maxLength={2000}
          />
          <small>
            沿用對話聲音引擎：{ttsEngine} ／{" "}
            {voiceId === "synthetic" ? "無私人聲音參照" : "已授權聲音"}。Mock
            為測試音。
          </small>
          <div className="face-toolbar">
            <button
              className="primary"
              disabled={!model || busy || !talk.trim()}
              onClick={() => onSpeak(talk)}
            >
              語音與模型連動測試
            </button>
            <button disabled={!model} onClick={() => model && onUse(model)}>
              套用到對話人像
            </button>
          </div>
          <div className="face-toolbar">
            {scan?.model && (
              <a href={`/api/face/scans/${scan.scan_id}/model.glb`} download>
                下載私人 GLB
              </a>
            )}
            <label className="upload compact">
              匯入 Blender GLB
              <input
                aria-label="匯入 Blender GLB"
                type="file"
                accept=".glb"
                onChange={(e) => {
                  const file = e.target.files?.[0];
                  if (file)
                    task(async () => {
                      if (file.size > 20 * 1024 * 1024)
                        throw Error("GLB_SIZE_INVALID");
                      const data = await file.arrayBuffer();
                      inspectGLB(data);
                      setModel(data);
                      setModelSource("本機匯入模型 · 未上傳伺服器");
                    });
                  e.target.value = "";
                }}
              />
            </label>
          </div>
          <p className="hint">
            中文精確對嘴與真人相似度尚未驗證。Rhubarb
            未設定會顯示錯誤，不會偷偷切換引擎。
          </p>
        </div>
      </section>
      <p role="status" className="face-status">
        {status}
      </p>
    </div>
  );
}
