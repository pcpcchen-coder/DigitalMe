# DigitalMe — 2026 技術選型與待驗證事項

**研究日期**：2026-10-14。這是選型候選與公開文件查證，**不是本機性能測試或保證可用**。

## 1. 語音合成與聲音複製
| 技術 | 角色 | 判斷 | 風險 |
|---|---|---|---|
| Coqui XTTS v2 | 已跑通的基準（legacy） | 先接 adapter 保留成果 | 過往 Python / torch / torchaudio / transformers 版本敏感；授權需檢視 |
| Qwen3-TTS 0.6B / 1.7B Base | 優先新模型候選 | 官方支援中文、zero-shot clone，MLX 社群提供 Apple Silicon 本地實作 | 第三方實作可維護性、繁中/台灣口音、延遲與記憶體要實測 |
| CosyVoice 3 | 替代方案 | 候選：自然度、風格與複製品質 | Mac backend 相容性需實測 |
| F5-TTS 等 | 對照組 | 短語音 / clone 主觀盲測 | 權重與商用授權須逐項查核 |

官方 Qwen3-TTS：https://github.com/QwenLM/Qwen3-TTS

Mac MLX 實作候選：https://github.com/kapi2800/qwen3-tts-apple-silicon

可替換 TTS server 參考：https://github.com/adrianwedd/afterwords

### XTTS 當年真實修復案例
```bash
# 僅在既有 ~/xtts_project/.venv 內操作；不要用同一環境直接裝新版 Qwen
source ~/xtts_project/.venv/bin/activate
python -m pip show TTS torch torchaudio transformers
# 當年成功關鍵 pin：
python -m pip install "transformers==4.37.2"
```
當時的 `GPT2InferenceModel.generate` 錯誤是 Transformers 的 generation mixin 行為改變所致；**不要再把錯誤直接歸因於快取損壞，也不要盲目刪掉所有模型**。下一次升級先建立完整環境快照及回歸測試。XTTS 維持隔離。

## 2. ASR / 對話
- Whisper / whisper.cpp：本地中文語音辨識候選，需測試家庭噪音與口音。
- OpenAI API Responses/聊天模型：可作對話引擎；請**另行計費**，不是 ChatGPT App 直接套入自訂聲音。
- OpenAI Realtime：有低延遲語音互動能力，但官方 TTS 輸出聲音是內建 voice selection，不等於直接使用本人的 XTTS。若必須用自己聲音，優先採 **STT → text LLM → local voice clone** 的可控架構。
- 本地模型候選：可透過 LM Studio / OpenAI-compatible endpoint 接 adapter；長期可離線。不可預設本地模型具備本人記憶。

OpenAI Realtime 官方文件：https://developers.openai.com/api/docs/guides/realtime-conversations

## 3. Avatar 路線
1. **Stage A / 即時輕量化**：2D 靜態頭像 + 音訊振幅驅動嘴型（視覺回饋 MVP，不假裝精確 phoneme lip-sync）。
2. **Stage B / 語音對齊**：文字/時間戳→viseme mapping、圖片部位 morph 或 2D rig；測定延遲及自然度。
3. **Stage C / 寫實 talking head**：比較 SadTalker、LivePortrait 搭配音訊嘴型工具、MuseTalk 等，並檢查能否在 Apple Silicon 實時運作；若只可離線生成 MP4，歸入故事錄製模式，不能作即時 Avatar。
4. **Stage D / 3D**：必要時才做 rigged 3D 頭像、表情和 WebGL/WebGPU。

LivePortrait 官方：https://github.com/KwaiVGI/LivePortrait

SadTalker：https://github.com/OpenTalker/SadTalker

## 4. 真正要比較的指標
| 類別 | 評測 |
|---|---|
| 聲音像不像 | 使用者及家人主觀盲測（需知情），清晰度、穩定度、台灣口音、情緒、姓名發音 |
| 合成速度 | warm/cold start、10/30/100 字 latency、峰值 RAM、CPU/GPU 占用 |
| 雙向對話 | mic end→first audible speech、可中斷、連續 20 回合錯誤率 |
| 視覺 | 嘴巴動作與語音的時間誤差、閃爍、CPU/GPU 占用、FPS |
| 安全 | 來源追溯、未找到資料時拒絕捏造、未成年模式、離線可用、資料刪除 |
| 工程 | 可重裝、版本鎖定、測試證據、回滾、授權與 API 成本 |

## 5. 調研決策原則
先驗證用戶真正要的**互動、聲音與熟悉感**，再投資昂貴的擬真視覺。任何「Real-Time」、「支持 Mac」聲稱都必須在指定硬體和目標聲音樣本上跑 benchmark，不能把 NVIDIA CUDA benchmark 套用在 Apple M 系列。
