# DigitalMe — 交付路線圖、驗證與驗收

**規劃原則**：Agent 主導開發；每個階段必須附可視化、可重播、可追溯的測試證據，未驗證項目明標 unknown。

## Phase 0 — Repo Bootstrap / Legacy Inventory（P0）
- 建立 `README`, `AGENTS`, docs, `.gitignore`, 流程 CI；敏感資訊不入庫。
- Mac 本地盤點 `~/xtts_project`（僅讀取，不先破壞），匯出 `pip freeze`、macOS/Python/CPU 架構、XTTS benchmark。
- 確認原始 voice reference 音訊僅留本地；以隨機檔名與本地路徑替代公開樣本。
**DoD**：列出每項原始資產存在／缺失、可重現依賴鎖、啟動指令；秘密掃描 pass。

## Phase 1 — Speaking Avatar MVP（P0）
- 網頁一個文字輸入框；選擇 TTS adapter、輸入句子、播放自己聲音；Avatar 依音訊動態呈現。
- 先以 mock voice（合成測試音）跑 CI；本人語音只跑本地私有真機測試。
- 頁面標示 AI-generated voice；有 loading / error / cancel；不能上傳聲音資料到 public GitHub。
**DoD**：一鍵本地啟動、中文語音輸出、Avatar 播放同步、10 次連續成功、可測量延遲。

## Phase 2 — Voice Conversation MVP（P0）
- Mic permission / VAD（可從按住說話開始） / STT / LLM adapter / TTS / playback。
- 支援多輪、逐字稿校正、敏感失敗降級、重試/中斷。
- OpenAI API Key 僅在 backend .env / Keychain，不進前端 bundle；也能使用 mock LLM。
**DoD**：20 輪對話無未處理例外；可保存脫敏事件 trace，回答由本人 TTS 播放且註明 AI 身分。

## Phase 3 — Mac Floating Head + Higher Fidelity（P1）
- Tauri 或 Swift 透明置頂視窗、拖動/縮放/關閉、顯示/隱藏；不搶焦點，不干擾其它 App。
- 使用語音對齊 viseme 或具真實模型支援的 audio-driven avatar；保留即時對話退化路徑。
**DoD**：macOS 實機影片證據（使用合成測試素材）、外接螢幕、多桌面、睡眠喚醒、取消播放通過。

## Phase 4 — Memory / Legacy（P1–P2）
- 由本人主動導入回憶卡、故事原聲、文字、照片，分設真實來源與推論。
- 檢索附來源／時間碼、可撤回、可匯出、加密備份與受託家人權限。
**DoD**：可回答已收錄的故事並顯示證據；未收錄故事不可冒稱記得；資料刪除經驗證。

## 驗收矩陣（Agent 應為每一列連到證據）
| ID | 驗收案例 | 預期證據 |
|---|---|---|
| AC-01 | 輸入繁體中文及專有名詞 | WAV、辨識／生成文字、版本快照 |
| AC-02 | 3 種 5–30 秒參考聲音 | 對照音檔（私有）、人類評分紀錄 |
| AC-03 | 連續 20 輪對話 | 成功率、延遲分布、trace |
| AC-04 | 網頁播音與 Avatar 同步 | 自動化影片或實機錄影、音視偏差報告 |
| AC-05 | TTS / LLM 服務停止 | 明確錯誤、重試、可切換 backend |
| AC-06 | 不授權麥克風 | 提示與純文字備援 |
| AC-07 | 無個人記憶來源 | 不捏造人生經驗、提供一般建議標示 |
| AC-08 | 刪除私有資料 | 刪除報告、無公開洩漏、備份策略 |
| AC-09 | secret scan | 0 committed secrets / 0 private voice/image assets |
| AC-10 | 從乾淨 clone 啟動 | setup script、lockfile、smoke test 綠燈 |

## 量化目標（非已驗證性能）
- 測試環境分別記錄 M4 16GB、M6 32GB（有哪台才測哪台）；不得假設兩台速度相同。
- 初期目標：推論模型預熱後，錄音結束→第一段可播放聲音 **p50 <= 5 秒**（需實測，超標建立 issue 並拆段計時）。
- 初期目標：在 20-turn scripted conversation 中成功完成 >= 19 次，任何錯誤可看見與重試。
- 2D Avatar 用 RMS 音量驅動，不列為 phoneme-perfect；真實 lip-sync 改用可量化 timestamp metrics。
- 音質指標需家人自願主觀評分與 ASR 回讀，不以單一 embedding score 宣稱已經「像本人」。

## 可視化驗證
Agent 自動產生：需求 ↔ 測試 ↔ 原始證據矩陣、案例回放、修復前後對比、延遲瀑布圖、配置版本、缺失與已知限制。Evidence board 的數字必須由底層測試記錄計算，禁止手填假綠燈。

## Release Gate
功能跑通 ≠ Production。必須通過 security/privacy、重建可重現、錯誤降級、明確身分揭露、家人退出權限、回滾與備份還原測試，才能宣告可長期使用。
