# DigitalMe — API 與資料契約（設計草案）

此為規格提案；尚未實作，變更需同步契約測試。

## Endpoints（P0）
- `GET /health` → `{status, backend_status, version}`；**不得**洩露本機檔案路徑或 secrets。
- `POST /api/tts` → body `{text, voice_id, engine}`；回傳 WAV bytes 或可短時限讀取的 job ID。
- `POST /api/stt` → multipart audio → `{text, language, confidence?, warnings[]}`。
- `POST /api/chat` → `{session_id, user_text, engine, memory_mode}` → `{turn_id, reply_text, source_status, evidence_refs[], disclosure}`。
- `POST /api/turn` （完整流程）→ `{session_id, text?, audio?, options}` → job/event stream（P1）。
- `GET /api/engines` → STT/LLM/TTS/Avatar 後端支援及就緒狀態。

## 統一事件
```json
{
  "schema_version": "1.0",
  "event": "tts_completed",
  "session_id": "generated-session-id",
  "turn_id": "generated-turn-id",
  "engine": "xtts",
  "duration_ms": 1800,
  "media_ref": "private-local-ref",
  "disclosure": "ai_generated"
}
```
請勿把音檔絕對路徑、API key 或真實人名寫入事件/log。事件時間要 monotonic 並可關聯 trace IDs。

## Speaker Profile（僅供本地）
```json
{
  "profile_id": "speaker-001",
  "owner_consent": true,
  "reference_audio": "private_data/voices/ref.wav",
  "language": "zh",
  "created_at": "ISO8601",
  "retention_policy": "local_only"
}
```

## Memory record（有證據來源）
```json
{
  "memory_id": "mem-001",
  "kind": "authentic_statement",
  "source_type": "audio_transcript",
  "source_ref": "private-store-id",
  "source_timestamp": "ISO8601",
  "reviewed_by_owner": true,
  "scope": "family",
  "text": "This is example synthetic data."
}
```

## 安全模型
- 使用者資料不預設傳到第三方，選用雲端 LLM 需明確告知其資料處理路徑。
- API Key 不回傳前端、不進 Repo；對話與語音原文為敏感資料。
- 身分揭露標示為 UI 固定元素，不可讓 LLM 以 prompt 移除。
- 家人有刪除／停止使用選項；未驗證的記憶不以第一人稱敘述為事實。
- 如跨機器/手機存取，必須另設認證和 TLS；不可公開裸 TTS service。
