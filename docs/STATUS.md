# DigitalMe observed status — 2026-10-14

狀態是實際觀察，不代表規格全部完成。精確時間、source commit、測試數字與原始輸出見 [`evidence/manifest.json`](../evidence/manifest.json)。

## 主機與 Repo

- 已完整閱讀 README、AGENTS、WORK_HANDOFF 與全部五份需求／架構／研究／路線／契約文件，以及 Issues #1–#3。
- 起始 main：`3b9940fd297513939197ffea806060c87b41ae4a`；僅規格，無既有程式。
- 本次可存取：Linux x86_64、Python 3.12.14、Node 24.19.0、Chromium 141（Playwright）。應用／測試依賴鎖於 requirements.lock 與 package-lock.json。
- **BLOCKED: host access**：無 Mac 本機／遠端連線；本環境 `~/xtts_project` 不存在。這不代表你的 Mac 上不存在。未操作或變更舊 venv、模型 cache、錄音、照片、家庭資料。
- `scripts/inventory_mac.py` 在本環境退出 2，正確回報 blocked。Mac 的 Python 3.11／torch／torchaudio／transformers／TTS 版本、原素材與依賴鎖全未驗證。

## Issue 進度

| Issue | 已實作／已測範圍 | 未完成／阻塞 |
|---|---|---|
| #1 | 只讀盤點程式、忽略私有路徑、mock smoke、staged privacy scan、依賴 audit | Mac 實際環境與資產盤點、legacy lock、真實聲音測試；保持 open |
| #2 | React / Vite + FastAPI；文本、引擎與 profile、播放、RMS 動畫、眨眼、本機肖像／原聲匯入／刪除、錯誤／中斷；10 次連續 mock TTS；瀏覽器截圖 | XTTS／MLX 真機中文、3 組聲音盲測、冷／熱啟動、RAM、精確音視偏差；保持 open |
| #3 | 錄音、逐字稿確認、session context、mock/local/OpenAI adapter、雲端 opt-in、來源揭露、靜音／清除；20 mock 回合；合成 MediaStream → STT → 編輯 → 對話 | 實體 Mac 麥克風／Whisper／真實 LLM／本人 TTS 整合，真正 mic-end→first-audible latency；保持 open |

額外完成 P1 起步：本人審核記憶卡、本機 CRUD、來源展示、撤回清空 session；不等於完整人生語義 RAG。

## 實際驗證

| 指令 | 結果與範圍 | 證據 |
|---|---|---|
| `.venv/bin/python -m pytest --junitxml=evidence/python-tests.xml -q` | 28 項通過（單元、契約、整合；無真實模型） | python-tests.xml |
| `cd apps/web && npm test` | RMS 數學／有界嘴部振幅測試通過 | npm-tests.tap |
| `cd apps/web && npm run build` | TypeScript + production build 成功 | 可重跑；E2E 使用 production bundle |
| `cd apps/web && npm run e2e` | 瀏覽器案例狀態由 raw JSON 計算；截圖含中文可讀字體 | browser-tests.json、ui-*.png |
| `make smoke` | 10 次 TTS + 20 回合完整 mock；延遲由事件量測 | smoke.json、mock-tone.wav |
| `make scan` | 索引私有路徑／素材／憑證模式檢查；合成證據人工核對 | privacy-scan.json |
| `npm audit` / `uvx pip-audit -r requirements.lock` | 已修正發現的 Vite／pytest 漏洞；查詢結果見原始 JSON | npm-audit.json、python-audit.json |

所有 latency 是 Linux mock 的 controller/LLM/TTS 時間；不能套用 Mac、真正語音模型、STT 或第一個可聽聲音，也不代表 ≤5 秒產品門檻通過。後端測試套件目前產生 Starlette/httpx 的 deprecation warning，未影響測試；後續相容性更新需另做回歸。

## 已知限制與下一步

1. 先依 RUN_MAC 做唯讀盤點，在**獨立**環境驗證 Qwen3-TTS MLX；同一段授權語音與文字對比既有 XTTS。未測真實引擎的品質、性能不得填分數。
2. worker 每次重載模型，120 秒 timeout；不具串流或常駐模型性能。確認實機可跑再做 resident worker、分句 TTS／VAD／barge-in。
3. Chromium 雲端實體 getUserMedia 回 NotSupportedError；E2E 注入合成 MediaStream，真實錄音編碼與發送路徑可測。拒權與不支援 UI 也有獨立測試；Mac OS 權限未測。
4. 使用本人審核文字與簡單關鍵字檢索；真實 LLM 來源忠實度、prompt injection 與適齡評估未完成。無來源的安全行為目前由 mock／契約測試證明。
5. 未實作 macOS 透明置頂視窗、精確 viseme、真實表情模型、監護人認證、加密備份／復原、接班權限。這是 localhost MVP，尚未達家庭長期使用 Release Gate。
6. `.gitignore` 與 heuristic scan 不是完整資料防洩漏；只有合成 fixture 與合成頭像截圖進公開 Repo。既有原始需求已含的歷史線索不等於本次上傳家庭資料。

看板、證據與 SHA256 由 `scripts/evidence.py` 產生；需求 AC-01–10 中尚有缺口的均維持 PARTIAL／UNVERIFIED，不用 mock 綠燈替代真人驗收。
