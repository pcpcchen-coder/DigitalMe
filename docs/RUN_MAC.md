# 本機啟動與模型接入

本應用目前是單一使用者的 localhost 開發版。先使用 mock 驗證介面，再接真實模型。不要公開綁定 `0.0.0.0`，不要把私人素材提供給 CI。

## 1. 在 Mac 啟動

需求：Python 3.12、Node 22.12+、Git、make。此處使用全新 `.venv`，與 `~/xtts_project` 無關。

```bash
git clone https://github.com/pcpcchen-coder/DigitalMe.git
cd DigitalMe
git switch codex/reboot-mvp
make setup
make dev
# 瀏覽器開啟 http://127.0.0.1:8765
```

第一次用 Mock 合成測試音。它不會講話，也不是聲音複製。選「記憶與聲音」可以匯入已授權的 PCM16 單聲道 WAV（3–30 秒）；肖像可拖放到左側，圖片只留在瀏覽器記憶體。

## 2. 舊環境只讀盤點

```bash
.venv/bin/python scripts/inventory_mac.py
```

只查作業系統、既有 interpreter 的套件 metadata 與頂層音訊是否存在。不載入模型、不執行 pip install、不搬移或刪除舊檔。報告放在忽略版控的 `private_data/inventory.json`。不輸出錄音檔名、完整路徑、私有套件 URL 或原文。尚未找到 interpreter 時須在本機檢查實際環境名稱；不能直接重建舊環境。

## 3. 新方法：Qwen3-TTS / MLX

Apple Silicon 候選，**本次沒有 Mac，以下安裝與模型執行尚未實機驗證**。另外建環境，禁止裝進 XTTS venv。採 Base voice-clone 權重，不是 CustomVoice 預設聲線。

```bash
python3.12 -m venv .venv-mlx
.venv-mlx/bin/python -m pip install mlx-audio soundfile
# 先在本機確認套件／模型授權、下載所選模型並測試；需要網路下載模型權重。
# 設定後才會啟用，啟動 make dev 的同一個 shell：
export MLX_PYTHON="$PWD/.venv-mlx/bin/python"
export MLX_MODEL='mlx-community/Qwen3-TTS-12Hz-0.6B-Base-bf16'
export MLX_REFERENCE_TEXT='在本機填入聲音參照的正確逐字稿'
make dev
```

在介面選 MLX 與已匯入的聲音。`services/tts_mlx/worker.py` 以獨立程序載入模型，與 API 程序隔離；目前每次請求都重新載入，偏向相容與可中止，**不是低延遲常駐推論**。120 秒 timeout。通過音質驗收後再改常駐 worker 與分句串流。新環境確認成功後在本機保存 `pip freeze`，不要把含個人路徑的 freeze 上傳。

## 4. 既有 XTTS

不變更任何依賴。只指定已盤點的 interpreter：

```bash
# 以下為範例；依實際既有 venv 名稱調整。
export XTTS_PYTHON="$HOME/xtts_project/venv/bin/python"
make dev
```

在介面匯入參照 WAV，選 XTTS 與對應聲音。worker 由既有 interpreter 執行，無需在舊環境安裝 FastAPI。它呼叫原有 Coqui API；模型尚未快取時可能下載權重，因此先離線確認 cache。歷史 `transformers==4.37.2` 僅作線索，這份指南不會自動 pin、升降級或變更 Torch 載入策略。

## 5. 本地 Whisper 與 LLM

```bash
python3.12 -m venv .venv-whisper
.venv-whisper/bin/python -m pip install openai-whisper
# Whisper 解碼 WebM/M4A 需要本機 ffmpeg；先確認 command -v ffmpeg。
export WHISPER_PYTHON="$PWD/.venv-whisper/bin/python"
export WHISPER_MODEL=base
export LOCAL_LLM_URL=http://127.0.0.1:1234/v1
export LOCAL_LLM_MODEL='填入本機已載入的模型 ID'
make dev
```

先於本機準備 Whisper 權重。選 Whisper 後按麥克風開始／停止錄音，逐字稿不會自動送 LLM，需編輯確認再送。LM Studio 等本機模型只接受 loopback HTTP URL，避免誤把本地模式資料傳去外部。

OpenAI 文字 API：以 shell 設 `OPENAI_API_KEY`、`OPENAI_MODEL`，不要貼進前端或 Repo。選雲端引擎時要勾選資料外傳同意，會傳出文字、近期對話與選用記憶；錄音與肖像不傳到 OpenAI。應用不會自動讀 `.env`；可在本機自行匯出環境變數，勿把金鑰放在 shell 歷史或共享畫面。切換 backend 不會清除舊對話上下文，需要清除時按「清除對話」。

## 6. 驗證與回滾

```bash
make test smoke
cd apps/web
npx playwright install chromium
npm run e2e
npm audit --json > ../../evidence/npm-audit.json
cd ../..
make scan evidence
```

看板：http://127.0.0.1:8765/acceptance.html 。輸出由 mock 原始事件產生，不能當成真實模型驗收。E2E 使用 `.e2e-data/`，不接觸 `private_data/`；重跑前可透過介面清除測試 fixture。

回滾：停止 API，切回已知正常的 Git commit，再用該 commit lockfile 建新的 API venv。私人檔案獨立留在 `private_data/`；版本回滾不代表資料 schema 自動遷移。舊 XTTS 本來就是獨立環境。備份與還原、Keychain／加密、監護人登入與多使用者授權尚未實作。

## 刪除與保留

對話只存在 API RAM，閒置 1 小時後於下次請求清理，每 session 最多 20 組問答、最多 100 session；前端只在此分頁保留。記憶卡與聲音明確存於本機 private_data，不加密。撤回記憶會清除全部 API session；刪除聲音會移除應用持有的 WAV，不會刪你的原始母檔或其他備份。瀏覽器原聲播放器、已產生音訊、OS cache 或備份可能仍有副本；此版未提供安全抹除承諾。
