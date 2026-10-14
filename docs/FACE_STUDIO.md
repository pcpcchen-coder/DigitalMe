# 雙目人臉工作台：工具選型、建立流程與驗收

2026-10-14。目標是使用本人授權的雙目影像建立可長期保存、能接語音的模型。此次沒有 Mac／實體相機存取權；已執行的重建與動畫測試全部用程式產生的虛擬影像。

## 設備基準與已知界線

先前紀錄找回的設備選擇是 **Arducam RoAD.B B0645**，不等於本次已確認到貨或成功開啟。官方 [RoAD 產品表](https://docs.arducam.com/RoAD-Robotics-Camera/Introduction/) 列出：彩色、全域快門、20 mm 基線、Stereo Sync、USB Type-C、2560×800@30 fps、1280×400@100 fps。 [官方商品頁](https://www.arducam.com/arducam-road-b-1mp-color-global-shutter-synchronized-stereo-camera-20mm-short-baseline-usb2-kit-with-enclosure.html) 與 [通路連到的原廠資料表](https://cdn.arducam.com/wp-content/uploads/2026/05/Arducam_B0645_RoAD_1MP_Color_BL20_Stereo_Camera_Datasheet.pdf) 可供本機核對。

UVC 供應的是影像，不可直接把 20 mm 規格當成完整內外參／深度校正。應以實機影像驗證左右半幅順序、是否同一硬體同步幀、實際解析度、曝光與畸變。瀏覽器的 `getSettings()` 只反映協商結果，無法證明硬體同步或真實產品型號。macOS UVC 相容性尚未實測。首版只支援**一個裝置、同一影格左右拼接 SBS**；不把兩台獨立 webcam 的時間戳當成同步雙目。

## 工具選型

| 工具 | 用途與決定 | 本次狀態／限制 |
|---|---|---|
| [OpenCV](https://docs.opencv.org/4.13.0/d9/d0c/group__calib3d.html) | 棋盤格內外參、rectification、StereoSGBM、三角化；CPU 基準，不需 CUDA | 已實作與虛擬校正／已知視差深度測試；真實人臉低紋理可能有孔洞，不能宣稱毫米級 |
| [Blender](https://www.blender.org/features/pipeline/) | 完整頭模的清理、retopology、牙齒／眼瞼、解剖級 shape keys 與 GLB 匯出 | 選作正式模型整理工具，尚未在此 session 執行 Blender；這些精修工作尚未完成 |
| [glTF 2.0](https://registry.khronos.org/glTF/specs/2.0/glTF-2.0.html) + [Three.js GLTFLoader](https://threejs.org/docs/pages/GLTFLoader.html) | 自含貼圖 GLB、本機 3D 預覽、標準 morph targets、同一播放器驅動 | 已實作，合成模型瀏覽器通過；外部影像／buffer URI 禁止，私人匯入 GLB 只在瀏覽器 RAM |
| [Rhubarb Lip Sync](https://github.com/DanielSWolf/rhubarb-lip-sync) | 可替換的離線音素嘴型時間軸；非英語用 `phonetic` | 已寫 adapter，但可執行檔未安裝／未實跑；繁體中文嘴型品質未驗收。預設 RMS 為音量近似，非音素級 |
| [MediaPipe Face Landmarker](https://developers.google.com/edge/mediapipe/solutions/vision/face_landmarker) | 後續自動定位嘴／眼、表情採集與係數擬合候選 | 輸出是模型估計的 landmarks／blendshapes，不是雙目公尺尺度深度；目前用手動錨點，尚未整合／下載權重 |
| [Fast-FoundationStereo](https://github.com/NVlabs/Fast-FoundationStereo) | 2026 新模型候選，評估改善低紋理視差後再替換 SGBM | 尚未整合／測試 Apple Silicon；原 repo GPU 路徑與權重授權需各別核對，不把 NVIDIA 數字套用到 Mac |
| [NVIDIA Audio2Face-3D SDK](https://github.com/NVIDIA/Audio2Face-3D-SDK) | 更高擬真語音表情的後續 GPU 路線 | 官方 C++/CUDA 路徑，非目前 Mac 預設；未安裝，未宣稱 Mac 可用 |

授權：OpenCV／Three.js 為各自開源授權；Blender 為 GPL，輸出作品不因此自動受 GPL 限制。Rhubarb 主程式 MIT、相依程式另有授權。MediaPipe 程式／模型、FoundationStereo 各權重與 Audio2Face 各元件要分別確認，不能把 repo license 一律套到模型。

## 已實作的工作台

分支 `codex/stereo-face-studio` 建立在 PR #5 的 MVP 上。Python 3.12、Node 22.12+，**只在 DigitalMe 新 API venv 安裝依賴**，完全不操作 `~/xtts_project`。

```bash
git clone -b codex/stereo-face-studio https://github.com/pcpcchen-coder/DigitalMe.git
cd DigitalMe
make setup
make dev
# http://127.0.0.1:8765 → 人臉模型建立
```

1. **先看合成流程**：按「載入合成雙目示範」→「建立曲面與說話形變 GLB」→手動張嘴→語音與模型連動→套用到對話人像。示範校正不能拿來重建真人影像；伺服器會阻擋混用。
2. **設備與授權**：連接 B0645，允許相機權限；選正確裝置。確認同一張 SBS 的左／右半幅與硬體模式，再勾選本人授權及 layout 確認，建立私人掃描。必要時交換左右半幅，禁止鏡像處理。
3. **拍校正板**：下載棋盤格 SVG、100% 列印，以尺確認方格邊長。預設 9×6 是「內角點」，圖案為 10×7 方格。棋盤格涵蓋不同位置、距離、角度至少 12 對；不要一直複製相同姿態。採集目的選「棋盤格校正」。
4. **執行校正**：輸入量到的方格尺寸；相機與解析度保持不變。需偵測到至少 12 對、位置有變化、RMS ≤1 px、合理基線與正確左右順序才保存。這些是工程門檻，**不是量測精度保證**；以已知尺度／深度物體額外驗證。
5. **人臉採集**：均勻漫射光、避免反光眼鏡和移動背景。採集目的選「人臉／表情」；先拍正面中性、再保存左／右／抬頭／低頭／張嘴／微笑／閉眼，作為後續多視角與表情資料。首版只用選定的單對影像重建，尚未融合這些姿態。
6. **建立曲面**：調 ROI 與嘴／眼錨點（錨點相對 ROI）；OpenCV 去畸變、rectify、SGBM、左右一致性、深度範圍／斷面過濾，產生有貼圖的正面曲面 GLB。使用公尺座標轉 glTF 右手系。匹配不足會報錯，不猜補成人臉。孔洞可能來自低紋理、反光或遮擋。
7. **試動作與聲音**：手動張嘴、旋轉與縮放檢查；沿用對話頁的 TTS 引擎／授權聲音。GLB 目前有 `jawOpen`、`mouthPucker`、`eyeBlinkLeft`、`eyeBlinkRight`。RMS 或可配置 Rhubarb 依播放 `audio.currentTime` 驅動，暫停／中斷回到靜止。不是完整 ARKit 52 通道、語意表情或精確對嘴。
8. **精修與匯回**：下載私人 GLB，用 Blender 清理／重拓撲／製作真正的嘴唇、牙齒與眼瞼 shape keys。匯出自含貼圖與 buffer 的 GLB，保留上述命名，再按「匯入 Blender GLB」。可帶其他表情，但本版只驅動這四個通道。此步尚需真實模型與實機完成。

## 語音動作契約

`POST /api/turn` 增加 `lipsync_engine: rms | rhubarb`；回覆 `animation={driver,duration_seconds,frames[]}`，frame 以秒記錄 `time,jawOpen,mouthPucker`。同一份產生的 WAV、同一個 audio 元素與播放位置驅動模型；不是用獨立 wall clock 猜嘴型。`POST /api/lipsync` 接 PCM16 WAV 也可產生時間軸，RMS 約 50Hz，結尾回零。LLM、TTS、lipsync 時間分開記錄；真實喇叭／顯示器音視偏差未量測。

要試 Rhubarb，先在本機另行安裝官方可執行檔、確認 macOS 架構相容性，再設定：

```bash
export RHUBARB_BIN='/absolute/path/to/rhubarb'
make dev
```

選 Rhubarb 時以 `-r phonetic -f json` 處理本機暫存 WAV，不傳雲端；90 秒 timeout。未設定或失敗會顯示錯誤，不偷偷切回 RMS。只回傳清理過的 cue，不回原工具可能含音檔路徑的 metadata。此 adapter 尚未真實執行，也沒有中文／情緒自然度評分。

## 本機資料與刪除

`private_data/faces/<random-id>/` 保存 `scan.json`、SBS PNG、`captures.json`、`calibration.json`、`surface.glb`、`model.json`；圖片／GLB／JSON 為私人衍生資料，禁止進公開 repo。`model.json` 保留 ROI、錨點、來源 capture、版本與限制。單張上限 8MiB，SBS 上限 2560×800，一次掃描上限 36 張；重新校正成功會使舊衍生模型失效。CPU 校正與重建期間禁止並行處理／刪除；本版無強制中止 native OpenCV thread 的承諾。

「刪除此掃描與模型」移除應用持有的該掃描、校正與模型。已下載的檔案、已載入瀏覽器的模型、OS cache 與外部備份不會自動被抹除；可在對話頁按「移除 3D 模型」，停止相機釋放裝置。沒有雲端人臉 API、自動公開上傳、加密備份或多使用者認證。

## 驗收與剩餘工作

合成測試：虛擬棋盤格恢復 20mm 基線、已知視差驗證 `Z=fB/d`、GLB 內嵌貼圖／morph、實際 mesh 形變權重、語音時間軸／回零、同源私有儲存／刪除、相機拒權與校正門檻、匯入阻擋外部 URI。原始結果在 `evidence/python-tests.xml`、`browser-tests.json`、`face-smoke.json`、`face-builder.png`、`face-speaking.png`，由看板 AF-01–08 對應。

**未完成／未驗證**：實體 B0645/Mac 擷取與同步、真人皮膚與頭髮的深度精度、完整頭部／多視角融合、解剖級口腔／眼瞼／表情 rig、Blender 精修實跑、Rhubarb 中文、本人音色與外觀相似度、實測音視偏差、家庭長期使用。不得用這個可操作原型宣稱已建立正式擬真的本人完整頭模。
