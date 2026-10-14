# DigitalMe — 個人數位傳承與互動 AI 分身

> **願景**：保存一個人真正留下的聲音、影像、故事、知識、人生經驗與價值觀，讓家人能透過透明且可追溯的 AI 系統持續互動，而不是讓 AI 假裝真人仍然在場。

**專案重啟日期：2026-10-14** · **狀態：Local MVP / mock 已測、真實模型待 Mac 驗證** · **目標環境：Apple Silicon Mac mini**。

## 立即操作

**新增：雙目人臉模型工作台**。以先前選擇的 Arducam B0645 為設備預設，提供本機 SBS 採集、棋盤格校正、CPU 深度曲面、帶貼圖／形變的 GLB、3D 預覽與語音時間軸，並可套用至對話頁。首版是 **正面 2.5D＋程序形變原型**；本人完整頭模、實機精度與精確對嘴尚未驗收。操作、工具選型與缺口請看 [FACE_STUDIO.md](docs/FACE_STUDIO.md)。

已實作 React + FastAPI 工作室：文字／錄音輸入、可編輯逐字稿、多輪對話、WAV 播放、RMS 2D 頭像、授權聲音與記憶卡管理、來源揭露及清除。XTTS、Qwen3-TTS MLX、Whisper 以獨立 Python 程序接入，LLM 可選本地相容 API 或明確同意後的 OpenAI 文字 API。

```bash
# Python 3.12、Node 22.12+、Git、make
git clone https://github.com/pcpcchen-coder/DigitalMe.git
cd DigitalMe
git switch codex/stereo-face-studio
make setup
make dev
# 開啟 http://127.0.0.1:8765
```

預設不需密鑰或私人素材；Mock 只輸出合成測試音與腳本回覆，**不是真人語音或真實 LLM**。本次實測環境是 Linux x86_64，沒有 Mac 本機存取權。請見 [實際狀態](docs/STATUS.md)、[Mac 操作與新模型接入](docs/RUN_MAC.md)、[實作架構](docs/IMPLEMENTATION.md)、[可視化驗收看板](evidence/index.html)、[證據 manifest](evidence/manifest.json)。

```bash
make test smoke scan
cd apps/web && npx playwright install chromium && npm run e2e && cd ../..
make evidence
# 啟動後 /acceptance.html 可檢視由原始測試事件產生的看板
```

Issues #1–#3 均保留真機驗收缺口；不宣告完整數位分身已完成。私人資料預設只在 localhost 使用，不可把此開發服務公開部署。

## 一句話目標

孩子對著電腦說話，DigitalMe 聽懂提問、參照本人留下的資料產生回答，再用授權的本人聲音及螢幕上浮動的虛擬人像呈現；介面永遠清楚標示哪些是**本人原始留言**、哪些是**AI 生成內容**。

## 原始需求（由 2025–2026 討論重建）

1. **聲音保存與克隆**：錄製自己的聲音，使用可自行保管的聲音模型，讓文字能變成自己的聲音。
2. **對話式 AI**：孩子說話 → 語音辨識（STT）→ ChatGPT／其他可切換的 LLM → 本人聲音 TTS → 播放，支援多輪中文對話。
3. **螢幕上的虛擬人像**：從靜態肖像起步，進化到嘴型、眨眼、表情、頭部動作；最終在 macOS 桌面以可移動、置頂、透明背景的小視窗呈現。
4. **數位記憶與人格參照**：由本人主動整理故事、錄音、照片、專業知識、態度與人生觀；回答需區分有來源的記憶與 LLM 自行生成的推論。
5. **長期保存**：本地優先、可攜式資料格式、版本化與備份、可遷移模型與服務，家人可控制存取與刪除。
6. **可持續演進**：語音、STT、LLM、Avatar 引擎均使用可替換 adapter，避免依賴單一供應商／模型。
7. **安全與尊重家人**：明確揭露 AI 身分，不偽造本人未曾說過的承諾與記憶；未成年使用者需要監護人控制、適齡模式、資料保護。

## 已有實驗成果（來自原始對話，不代表已存在本 Repo）

- 本地使用 Coqui **XTTS v2**，從自己的 `.m4a` 錄音轉成 `.wav` 當作 speaker reference。
- 在 macOS／Python 3.11 建立 `~/xtts_project`，已成功以本人聲音產生文字轉語音。
- 關鍵 debug 紀錄：`GPT2InferenceModel has no attribute generate`，當時透過 **`pip install transformers==4.37.2`** 解決。往後請把 XTTS 視為需隔離、鎖定依賴版本的 legacy backend，勿直接污染新模型的 Python 環境。
- 曾設計短篇故事《月亮蛋糕》測試中文語音及多句合成。
- 曾提出 SadTalker、LivePortrait 等人像方案，但**沒有證據顯示它們已在使用者裝置成功跑通**。
- 此 Repo 在 2026-10-14 檢查時為空白；以上成果仍待從原 Mac 本機盤點／匯入，不能當作 GitHub 現有程式碼。

## 2026 建議架構

```text
Mic / text input
      |
 STT / VAD  -----> conversation controller -----> LLM adapter
                         |                           |
                consent + retrieval <------ verified memories
                         |
                  response text + source tags
                         |
                    TTS adapter
                     /       \
               XTTS v2    Qwen3-TTS/MLX (候選)
                         |
                audio player + timing
                         |
              floating avatar renderer
```

先交付**可驗證的端到端 MVP**，再引入高成本、尚未驗證 Apple Silicon 即時性能的寫實人像模型。**ChatGPT App 本身不能直接載入本地 XTTS 作為自訂語音**；對話中控需要呼叫 OpenAI API 或可替換的本地 LLM，且 API 與 ChatGPT 訂閱應分開估算。

## 文件導覽

- [原始需求與界線](docs/ORIGINAL_REQUIREMENTS.md)
- [2026 系統架構](docs/ARCHITECTURE_2026.md)
- [技術調查與選型](docs/TECH_RESEARCH_2026.md)
- [路線圖、測試與驗收](docs/ROADMAP_ACCEPTANCE.md)
- [Work / Coding Agent 接手指令](docs/WORK_HANDOFF.md)
- [Agent 工作規則](AGENTS.md)
- [雙目人臉模型建立與工具選型](docs/FACE_STUDIO.md)

## 隱私與公開 Repo 規則

本 Repo 為 **public**。禁止提交任何本人或孩子的人臉照、錄音、聲紋／speaker embedding、家庭資料、逐字稿、API token、身分憑證。真正的樣本及資料只存本地的 `private_data/` 或使用獨立加密儲存；以合成／匿名 fixtures 寫測試。

## 當前下一步

在 macOS 執行只讀 `scripts/inventory_mac.py`；優先比較獨立 MLX 新後端與既有 XTTS，再接真實 Whisper／LLM 完成 20 回合、本人音質、延遲與音視偏差驗收。接續常駐推論／串流、macOS 浮動視窗、監護人授權與加密備份。原始需求文件仍為規格基準，實作與證據以 `docs/STATUS.md` 為準。
