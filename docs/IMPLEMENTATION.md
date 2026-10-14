# 實作架構與限制

## 執行邊界

- React / Vite / TypeScript → 同源 FastAPI；production build 由 FastAPI 直接服務。
- `services/api/domain.py`：model-independent Protocol 與基本人格規則，無供應商 SDK。
- `services/api/adapters.py`：mock、loopback LLM／OpenAI、隔離語音 worker。mock 是確定性合成音與腳本回覆。
- XTTS／MLX／Whisper 只由使用者配置的 interpreter 啟動，不對既有環境執行安裝。
- `private_data/`：0600 JSON/WAV；新增目錄 0700。無 Repo media upload、自動家庭資料匯入或雲端語音 API。
- 肖像只用 browser blob URL；錄音上傳 localhost STT 後於暫存目錄處理並清除。TTS 用短期暫存 WAV 回傳。

## 協定

實際 OpenAPI 於 `/openapi.json`；`GET /health`、`GET /api/engines`、`POST /api/tts`（WAV）、`POST /api/stt`（multipart audio + engine）、`POST /api/chat`（文字）、`POST /api/turn`（對話 + base64 WAV）。

新增 `GET/POST /api/voices`、`GET /api/voices/{id}/audio`（本人原聲）、`DELETE /api/voices/{id}`、`GET/POST /api/memories`、`DELETE /api/memories/{id}`、`DELETE /api/sessions/{id}`。voice id 為伺服器產生隨機 ID，前端不能傳任意檔案路徑。

回覆包含 turn/session IDs、reply_text、source_status、evidence_refs、disclosure、backend、分段毫秒。LLM 的輸出永遠 `ai_generated`；就算引用本人記憶也不是 `authentic_recording`。原聲預覽以獨立標籤與 HTTP header 區分。

記憶檢索採簡單文字片段匹配，不是語義 RAG。參考資料「consulted」不代表每句回答都被來源證明。mock 可測缺資料回覆；真實 LLM 的 grounding / prompt injection／適齡紅隊驗收尚未完成，不能據此宣告適合兒童獨立長期使用。

## 故障處理

- 模型程序非零退出、缺少設定、timeout、無聲音參照都回明確錯誤，禁止偷偷改用 mock。
- 一次僅執行一個語音模型工作，避免同時載入多個模型。session busy 回 409。完成 TTS 後才寫入問答上下文，失敗重試不會增加假的 assistant turn。
- 中斷在前端 AbortController 停止 request，後端輪詢 disconnect 並取消 task／kill model subprocess。已完成且傳回的 turn 不會由中斷撤銷；可清除 session。
- 撤回記憶時清空 sessions，正在產生的舊 session 回 `SESSION_REVOKED`，避免撤回後仍返回舊來源。
- 只處理同源 Origin，TrustedHost 限 localhost，無 CORS 白名單或外部裸服務；不取代跨裝置認證。所有 response no-store，不回傳原始 vendor exception。
- POST 實體 request 12 MiB 上限、音訊 10 MiB 上限；不預設保存錄音／逐字稿；不記錄請求原文。

## 測試範圍

pytest：契約、格式與大小限制、授權、來源與刪除、timeout、重試、Origin/Host、mock 整合、HTTP 模擬傳輸。

Playwright：production bundle、真實瀏覽器播 WAV、RMS 嘴部高度、連續對話、TTS、錯誤恢復、synthetic mic、拒權注入、memory CRUD、肖像不發 request、390px layout。

未實測：真人音質／模型推論、Mac 麥克風與 OS 權限、精確音視時間偏差、GPU/RAM、透明置頂視窗、硬體睡眠喚醒、多使用者、加密／備份還原。無法以 Linux mock 數據替代。
