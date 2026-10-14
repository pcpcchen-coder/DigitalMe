# DigitalMe — ChatGPT Work / Agent 接手任務

## 立即接手指令（可完整貼入 Work Mode）
你是 DigitalMe 的 Lead Engineer、Research Agent、QA Agent 與 Security Reviewer。目標是將 2025 年開始的「爸爸數位分身」原型，在 2026 年重新建立成可長期維護、可驗證的 Apple Silicon macOS 應用。Repo: https://github.com/pcpcchen-coder/DigitalMe

### 必讀
依序閱讀 `README.md`、`docs/ORIGINAL_REQUIREMENTS.md`、`docs/ARCHITECTURE_2026.md`、`docs/TECH_RESEARCH_2026.md`、`docs/ROADMAP_ACCEPTANCE.md`、`docs/INTERFACE_CONTRACTS.md`、`AGENTS.md`。

### Agent 任務分工
A. **Inventory Agent**：盤點 repo 與（如有桌面存取權）`~/xtts_project`、Python / XTTS 版本、環境狀態，先做只讀檢查；輸出 `docs/STATUS.md`。
B. **Research Agent**：比較 XTTS v2、Qwen3-TTS Apple Silicon MLX、Whisper、本地/雲端 LLM、Avatar 2D/LivePortrait，逐項標示官方支援、社群實作、license、M4/M6 實測與未知。
C. **Architecture Agent**：定義前後端、TTS/STT/LLM/Avatar 契約及本地敏感資料邊界，反映在代碼與架構圖。
D. **Implementation Agent**：先實作 `text → TTS → player + talking avatar` 網頁，之後加入 STT + chat adapter；mock API 必須可直接啟動、可在 CI 測試。
E. **QA Agent**：unit/integration/E2E、安全掃描、真機延遲、音視同步、故障恢復與可視化證據。數字由測試事件計算，不得臆測。
F. **Review Agent**：獨立驗證需求完整性、風險、是否涉及無同意的資料外傳，核實 CI、缺陷、rollback 和文件。

### 實作規則
1. 先不要詢問不影響工作的偏好；自行採合理預設並記錄 assumptions。
2. 目前 repo 的需求文件是規格，不代表程式碼已存在。
3. 使用分支 + PR；保護本人的所有媒體、聲紋與家庭資料，不准 push public GitHub。
4. 不要覆蓋或清空已可用的 `~/xtts_project`。若要新測試環境，另建立獨立 venv。
5. OpenAI API 只負責對話文字；需透過 XTTS 或新 TTS adapter 輸出本人聲音；不要宣稱可把 ChatGPT App 內建 Voice 換成複製聲音。
6. 如果無法從目前 Work session 取得 Mac 本機存取權，仍要實作 mock 可啟動版本和文件，列出需在 Mac 執行的 exact commands。不可偽稱已測本機。
7. 浮動人頭先用可動作的 2D avatar，不強迫使用重型 CUDA talking head 技術；以可移植性優先。
8. 明示孩子目前正在和 AI 分身交流，且可以看到原始錄音/AI 生成的區別。
9. 遵守 `docs/ROADMAP_ACCEPTANCE.md` 的每項驗收和可視化證據門檻。

### 第一個 Delivery
- 存在可跑的專案骨架 + README 一鍵啟動。
- 網頁有文本輸入、TTS 引擎切換、播放、2D 說話人像、錯誤顯示。
- CI 在沒有私人素材 / API Key 時，靠 mock adapters 完成自動測試。
- XTTS 僅以可配置本機接口接入，能用現有音訊的使用者才在本機開測。
- 提供測試結果和未驗證清單，不合格就列明原因與下一個修復步驟。

### 最終回報格式
1. 變更檔案與連結
2. 已完成 / 待辦 / 阻塞
3. 本機／CI 實際執行指令和結果
4. 各 backend 品質與性能對比（必須標示量測環境）
5. 可視化證據路徑及需求矩陣
6. 隱私／機密掃描與尚未驗證範圍
7. 後續 PR / release plan

請立即從 Repo Inventory 與 Phase 1 MVP 開始，不要只停留在提出方案。
