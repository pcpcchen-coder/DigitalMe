import React, { useEffect, useRef, useState } from "react";
import { createRoot } from "react-dom/client";
import { mouthScale } from "./audio.mjs";
import "./style.css";

type Voice = { profile_id: string; duration_seconds: number };
type Memory = { memory_id: string; title: string; text: string };
type Turn = {
  turn_id: string;
  reply_text: string;
  source_status: string;
  evidence_refs: Memory[];
  audio_base64: string;
  timings: Record<string, number>;
};
async function api(path: string, options: RequestInit = {}) {
  const r = await fetch(path, options);
  if (!r.ok) {
    let e = await r.json();
    throw new Error(e.error?.code || "REQUEST_FAILED");
  }
  return r;
}
function App() {
  const [tab, setTab] = useState("studio"),
    [mode, setMode] = useState("chat");
  const [text, setText] = useState("你好，我想聽一個關於勇氣的故事。"),
    [tts, setTts] = useState("mock"),
    [llm, setLlm] = useState("mock"),
    [stt, setStt] = useState("mock");
  const [voice, setVoice] = useState("synthetic"),
    [voices, setVoices] = useState<Voice[]>([]),
    [memories, setMemories] = useState<Memory[]>([]);
  const [cloud, setCloud] = useState(false),
    [ground, setGround] = useState(false),
    [consent, setConsent] = useState(false);
  const [busy, setBusy] = useState(false),
    [error, setError] = useState(""),
    [status, setStatus] = useState("準備好了"),
    [playing, setPlaying] = useState(false);
  const [messages, setMessages] = useState<{ user: string; turn: Turn }[]>([]),
    [timings, setTimings] = useState<Record<string, number>>({});
  const [portrait, setPortrait] = useState(""),
    [muted, setMuted] = useState(false),
    [recording, setRecording] = useState(false);
  const [title, setTitle] = useState(""),
    [memoryText, setMemoryText] = useState(""),
    [reviewed, setReviewed] = useState(false);
  const session = useRef(crypto.randomUUID()),
    generation = useRef(0),
    controller = useRef<AbortController | null>(null),
    audio = useRef<HTMLAudioElement>(null),
    ctx = useRef<AudioContext | null>(null),
    source = useRef<MediaElementAudioSourceNode | null>(null),
    frame = useRef(0),
    mouth = useRef<HTMLDivElement>(null),
    audioURL = useRef(""),
    portraitURL = useRef(""),
    recorder = useRef<MediaRecorder | null>(null),
    stream = useRef<MediaStream | null>(null);
  const [audioReady, setAudioReady] = useState(false);
  async function refresh() {
    setVoices(await (await api("/api/voices")).json());
    setMemories(await (await api("/api/memories")).json());
  }
  useEffect(() => {
    refresh().catch((e) => setError(e.message));
    return () => {
      controller.current?.abort();
      stream.current?.getTracks().forEach((t) => t.stop());
      cancelAnimationFrame(frame.current);
      URL.revokeObjectURL(audioURL.current);
      URL.revokeObjectURL(portraitURL.current);
      ctx.current?.close();
    };
  }, []);
  function cancel() {
    generation.current++;
    controller.current?.abort();
    if (recorder.current?.state === "recording") recorder.current.stop();
    stream.current?.getTracks().forEach((t) => t.stop());
    setRecording(false);
    audio.current?.pause();
    if (audio.current) audio.current.currentTime = 0;
    setPlaying(false);
    setBusy(false);
    setStatus("已中斷；可修改文字後重試");
  }
  async function play() {
    if (!audio.current) return;
    try {
      ctx.current ||= new AudioContext();
      if (!source.current) {
        source.current = ctx.current.createMediaElementSource(audio.current);
        const analyser = ctx.current.createAnalyser();
        analyser.fftSize = 512;
        source.current.connect(analyser);
        analyser.connect(ctx.current.destination);
        const data = new Float32Array(analyser.fftSize);
        const draw = () => {
          analyser.getFloatTimeDomainData(data);
          if (mouth.current)
            mouth.current.style.height = `${5 + mouthScale(Array.from(data)) * 28}px`;
          frame.current = requestAnimationFrame(draw);
        };
        draw();
      }
      await ctx.current.resume();
      await audio.current.play();
    } catch {
      setStatus("音訊已準備，請按播放以允許瀏覽器播音");
    }
  }
  async function submit() {
    if (!text.trim()) return;
    cancel();
    const gen = generation.current;
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    setStatus("正在處理…");
    // Resume audio while in a user gesture; autoplay may still require manual playback.
    ctx.current ||= new AudioContext();
    await ctx.current.resume();
    try {
      let blob: Blob;
      if (mode === "tts") {
        const r = await api("/api/tts", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.current.signal,
          body: JSON.stringify({ text, engine: tts, voice_id: voice }),
        });
        blob = await r.blob();
      } else {
        const r = await api("/api/turn", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          signal: controller.current.signal,
          body: JSON.stringify({
            session_id: session.current,
            user_text: text,
            engine: llm,
            tts_engine: tts,
            voice_id: voice,
            memory_mode: ground ? "reviewed" : "off",
            cloud_consent: cloud,
          }),
        });
        const turn: Turn = await r.json();
        if (gen !== generation.current) return;
        setMessages((m) => [...m, { user: text, turn }]);
        setTimings(turn.timings);
        blob = new Blob(
          [Uint8Array.from(atob(turn.audio_base64), (c) => c.charCodeAt(0))],
          { type: "audio/wav" },
        );
      }
      if (gen !== generation.current) return;
      URL.revokeObjectURL(audioURL.current);
      audioURL.current = URL.createObjectURL(blob);
      if (audio.current) {
        audio.current.src = audioURL.current;
        audio.current.load();
      }
      setAudioReady(true);
      setStatus(
        tts === "mock" ? "已完成 · 測試音，非人聲" : "AI 生成聲音已準備",
      );
      await play();
    } catch (e) {
      if ((e as Error).name !== "AbortError") setError((e as Error).message);
    } finally {
      if (gen === generation.current) setBusy(false);
    }
  }
  async function startMic() {
    if (recording) {
      recorder.current?.stop();
      return;
    }
    setError("");
    cancel();
    const gen = generation.current;
    try {
      if (!navigator.mediaDevices?.getUserMedia)
        throw new Error("MIC_REQUIRES_LOCALHOST_OR_HTTPS");
      const s = await navigator.mediaDevices.getUserMedia({ audio: true });
      if (gen !== generation.current) {
        s.getTracks().forEach((t) => t.stop());
        return;
      }
      stream.current = s;
      const mimeType = [
        "audio/webm;codecs=opus",
        "audio/webm",
        "audio/mp4",
        "audio/ogg;codecs=opus",
      ].find((type) => MediaRecorder.isTypeSupported(type));
      if (!mimeType)
        throw new DOMException("Unsupported recorder", "NotSupportedError");
      const r = new MediaRecorder(s, { mimeType });
      recorder.current = r;
      const chunks: BlobPart[] = [];
      r.ondataavailable = (e) => chunks.push(e.data);
      r.onstop = async () => {
        clearTimeout(recordingLimit);
        s.getTracks().forEach((t) => t.stop());
        setRecording(false);
        if (gen !== generation.current) return;
        setBusy(true);
        setStatus("正在辨識，辨識後請確認文字");
        try {
          const form = new FormData();
          form.append(
            "audio",
            new Blob(chunks, { type: r.mimeType }),
            "microphone",
          );
          form.append("engine", stt);
          controller.current = new AbortController();
          const data = await (
            await api("/api/stt", {
              method: "POST",
              body: form,
              signal: controller.current.signal,
            })
          ).json();
          if (gen === generation.current) {
            setText(data.text);
            setTimings(data.timings);
            setStatus("逐字稿已準備 · 請編輯確認後送出");
          }
        } catch (e) {
          if ((e as Error).name !== "AbortError")
            setError((e as Error).message);
        } finally {
          if (gen === generation.current) setBusy(false);
        }
      };
      r.start();
      const recordingLimit = setTimeout(() => {
        if (r.state === "recording") r.stop();
      }, 30000);
      setRecording(true);
      setStatus("錄音中 · 再按一次停止");
    } catch (e) {
      stream.current?.getTracks().forEach((t) => t.stop());
      setError(
        (e as Error).name === "NotSupportedError"
          ? "目前瀏覽器或執行環境不支援錄音，請直接輸入文字。"
          : "無法使用麥克風：請允許權限，或直接輸入文字。",
      );
    }
  }
  async function clear() {
    cancel();
    recorder.current?.state === "recording" && recorder.current.stop();
    await api(`/api/sessions/${session.current}`, { method: "DELETE" });
    session.current = crypto.randomUUID();
    setMessages([]);
    setText("");
    setTimings({});
    setAudioReady(false);
    audio.current?.removeAttribute("src");
    URL.revokeObjectURL(audioURL.current);
    setStatus("對話已清除（記憶卡與聲音需分別刪除）");
  }
  function setImage(file?: File) {
    if (!file) return;
    if (!file.type.startsWith("image/") || file.size > 10 * 1024 * 1024) {
      setError("請選擇 10MB 以下圖片");
      return;
    }
    URL.revokeObjectURL(portraitURL.current);
    portraitURL.current = URL.createObjectURL(file);
    setPortrait(portraitURL.current);
  }
  async function upload(file?: File) {
    if (!file) return;
    try {
      const form = new FormData();
      form.append("audio", file);
      form.append("owner_consent", String(consent));
      await api("/api/voices", { method: "POST", body: form });
      await refresh();
      setStatus("聲音已存於本機，尚未驗證複製音質");
    } catch (e) {
      setError((e as Error).message);
    }
  }
  async function saveMemory() {
    try {
      await api("/api/memories", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          title,
          text: memoryText,
          reviewed_by_owner: reviewed,
        }),
      });
      setTitle("");
      setMemoryText("");
      setReviewed(false);
      await refresh();
    } catch (e) {
      setError((e as Error).message);
    }
  }
  return (
    <div className="shell">
      <aside>
        <a className="brand" href="/">
          d<span>m</span>
          <small>DigitalMe</small>
        </a>
        <nav>
          {[
            ["studio", "◉", "對話工作室"],
            ["archive", "▤", "記憶與聲音"],
            ["verify", "✓", "驗證與狀態"],
          ].map(([id, icon, label]) => (
            <button
              className={tab === id ? "selected" : ""}
              onClick={() => setTab(id)}
              key={id}
            >
              <b>{icon}</b>
              {label}
            </button>
          ))}
        </nav>
        <div className="side-note">
          <i /> 本地優先
          <br />
          <small>
            留住真實的故事
            <br />
            讓每次相遇都有來源
          </small>
        </div>
        <footer>
          PERSONAL LEGACY LAB
          <br />
          v0.1 · 開發預覽
        </footer>
      </aside>
      <main>
        <header>
          <div className="crumb">
            個人數位傳承 <span>/</span>{" "}
            {tab === "studio"
              ? "對話工作室"
              : tab === "archive"
                ? "記憶與聲音"
                : "驗證與狀態"}
          </div>
          <span className="pill">◌ LOCAL WORKSPACE</span>
        </header>
        <section className="heading">
          <div>
            <div className="eyebrow">A VOICE. A STORY. A CONNECTION.</div>
            <h1>
              {tab === "studio"
                ? "讓故事，繼續被聽見。"
                : tab === "archive"
                  ? "從真實留下的紀錄開始。"
                  : "每一步，都有驗證依據。"}
            </h1>
            <p>
              {tab === "studio"
                ? "熟悉的聲音，承載值得留下的話。從今天的一段對話開始。"
                : tab === "archive"
                  ? "只有你確認過的記憶，才會成為分身的參考來源。"
                  : "測試模式與真實模型分開呈現；未驗證項目保留標記。"}
            </p>
          </div>
        </section>
        <div className="disclosure">
          <b>AI 數位分身</b>
          <span>
            你正在與 AI 交流。生成內容不等於本人說過的話，也不代表本人的意識。
          </span>
        </div>
        {error && (
          <div role="alert" className="error">
            {error} <button onClick={() => setError("")}>關閉</button>
          </div>
        )}
        {tab === "studio" && (
          <>
            <div className="workspace">
              <section
                className="avatar-card"
                onDragOver={(e) => e.preventDefault()}
                onDrop={(e) => {
                  e.preventDefault();
                  setImage(e.dataTransfer.files[0]);
                }}
              >
                <div className="card-top">
                  <span>YOUR DIGITAL PRESENCE</span>
                  <span className="badge">2D · 近似嘴型</span>
                </div>
                <div className={"portrait-area " + (playing ? "speaking" : "")}>
                  <div className="orbit one" />
                  <div className="orbit two" />
                  <div className="portrait">
                    {portrait ? (
                      <img src={portrait} alt="本機授權肖像" />
                    ) : (
                      <svg viewBox="0 0 260 280" aria-label="合成示意頭像">
                        <path
                          d="M25 280 Q25 215 95 206 L165 206 Q235 215 235 280"
                          fill="#e0b78e"
                        />
                        <path
                          d="M99 190 V222 Q130 240 161 222 V190"
                          fill="#bf8c68"
                        />
                        <ellipse
                          cx="130"
                          cy="119"
                          rx="71"
                          ry="91"
                          fill="#ddb28b"
                        />
                        <path
                          d="M60 117 Q27 21 108 15 Q195 -5 201 85 L193 118 L179 74 Q119 98 77 69 Z"
                          fill="#35433d"
                        />
                        <g className="eyes" fill="#35433d">
                          <ellipse cx="101" cy="124" rx="5" ry="4" />
                          <ellipse cx="160" cy="124" rx="5" ry="4" />
                        </g>
                        <path
                          d="M130 130 L123 152 L136 152"
                          fill="none"
                          stroke="#bc8766"
                          strokeWidth="3"
                        />
                        <path
                          d="M84 111 L113 109 M146 109 L173 111"
                          stroke="#535247"
                          strokeWidth="4"
                          strokeLinecap="round"
                        />
                      </svg>
                    )}
                    <div className="mouth" ref={mouth} />
                  </div>
                  <span className="presence-label">
                    {playing ? "正在播放" : "安靜聆聽，等待下一個故事"}
                  </span>
                </div>
                <div className="wave">
                  {Array.from({ length: 35 }, (_, i) => (
                    <i
                      key={i}
                      style={{
                        height: playing ? `${8 + ((i * 13) % 27)}px` : "4px",
                        animationDelay: `${i * 0.025}s`,
                      }}
                    />
                  ))}
                </div>
                <div className="avatar-bottom">
                  <label className="link">
                    ＋ 選擇本機肖像
                    <input
                      aria-label="選擇本機肖像"
                      type="file"
                      accept="image/*"
                      onChange={(e) => setImage(e.target.files?.[0])}
                    />
                  </label>
                  {portrait && (
                    <button
                      onClick={() => {
                        URL.revokeObjectURL(portraitURL.current);
                        setPortrait("");
                      }}
                    >
                      移除
                    </button>
                  )}
                  <small>圖片僅在此瀏覽器頁面顯示，可拖曳放入</small>
                </div>
              </section>
              <section className="composer">
                <div className="segmented">
                  <button
                    className={mode === "chat" ? "active" : ""}
                    onClick={() => setMode("chat")}
                  >
                    自然對話
                  </button>
                  <button
                    className={mode === "tts" ? "active" : ""}
                    onClick={() => setMode("tts")}
                  >
                    文字轉語音
                  </button>
                </div>
                <div className="section-label">
                  01 <span>選擇聲音與對話引擎</span>
                </div>
                <div className="fields">
                  <label>
                    聲音引擎
                    <select
                      aria-label="聲音引擎"
                      value={tts}
                      onChange={(e) => setTts(e.target.value)}
                    >
                      <option value="mock">Mock · 合成測試音</option>
                      <option value="mlx">Qwen3-TTS / MLX · 待真機驗證</option>
                      <option value="xtts">XTTS Legacy · 待真機驗證</option>
                    </select>
                  </label>
                  <label>
                    聲音檔案
                    <select
                      aria-label="聲音檔案"
                      value={voice}
                      onChange={(e) => setVoice(e.target.value)}
                    >
                      <option value="synthetic">無私人參照 · 示意模式</option>
                      {voices.map((v, i) => (
                        <option value={v.profile_id} key={v.profile_id}>
                          已授權聲音 {i + 1}
                        </option>
                      ))}
                    </select>
                  </label>
                </div>
                {mode === "chat" && (
                  <div className="fields">
                    <label>
                      對話引擎
                      <select
                        aria-label="對話引擎"
                        value={llm}
                        onChange={(e) => {
                          setLlm(e.target.value);
                          setCloud(false);
                        }}
                      >
                        <option value="mock">Mock · 腳本對話</option>
                        <option value="local">本地 LLM · OpenAI 相容</option>
                        <option value="openai">OpenAI · 雲端文字 API</option>
                      </select>
                    </label>
                    <label>
                      語音辨識
                      <select
                        aria-label="語音辨識"
                        value={stt}
                        onChange={(e) => setStt(e.target.value)}
                      >
                        <option value="mock">Mock · 示意逐字稿</option>
                        <option value="whisper">Whisper · 本地</option>
                      </select>
                    </label>
                  </div>
                )}
                {llm === "openai" && mode === "chat" && (
                  <label className="check cloud">
                    <input
                      type="checkbox"
                      checked={cloud}
                      onChange={(e) => setCloud(e.target.checked)}
                    />
                    同意將目前文字、近期對話與選用的記憶傳至
                    OpenAI；聲音留在本機
                  </label>
                )}
                <div className="section-label">
                  02{" "}
                  <span>
                    {mode === "chat" ? "想聊些什麼？" : "寫下想說的話"}
                  </span>
                  <small>繁體中文</small>
                </div>
                <textarea
                  aria-label="對話文字"
                  maxLength={2000}
                  value={text}
                  onChange={(e) => setText(e.target.value)}
                  placeholder="說一個故事，或提出一個問題…"
                />
                <div className="text-tools">
                  <button
                    disabled={busy}
                    onClick={startMic}
                    className={recording ? "recording" : ""}
                  >
                    {recording ? "■ 停止錄音" : "♩ 麥克風輸入"}
                  </button>
                  <small>{text.length} / 2000</small>
                </div>
                <label className="check">
                  <input
                    type="checkbox"
                    checked={ground}
                    onChange={(e) => setGround(e.target.checked)}
                  />
                  參照已審核記憶 <span>{memories.length} 則</span>
                </label>
                <div className="actions">
                  <button
                    className="primary"
                    onClick={submit}
                    disabled={
                      busy ||
                      recording ||
                      !text.trim() ||
                      (mode === "chat" && llm === "openai" && !cloud)
                    }
                  >
                    {busy
                      ? "處理中…"
                      : mode === "chat"
                        ? "開始對話 ↗"
                        : "產生聲音 ↗"}
                  </button>
                  <button onClick={cancel}>中斷</button>
                </div>
                <p className="hint">
                  {tts === "mock"
                    ? "測試模式會播放合成音，不是本人聲音。"
                    : "需要本機配置模型及已授權參照聲音。"}
                </p>
              </section>
            </div>
            <section className="playback">
              <div>
                <span className={"status-dot " + (playing ? "on" : "")} />
                <b role="status">{status}</b>
              </div>
              <div className="player-buttons">
                <button disabled={!audioReady} onClick={play}>
                  ▶ 播放
                </button>
                <button onClick={() => setMuted(!muted)}>
                  {muted ? "取消靜音" : "靜音"}
                </button>
                <button
                  onClick={() => clear().catch((e) => setError(e.message))}
                >
                  清除對話
                </button>
              </div>
            </section>
            <section className="conversation">
              <div className="section-title">
                <h2>
                  對話紀錄 <small>僅本次工作階段</small>
                </h2>
                <span>{messages.length} 回合</span>
              </div>
              {messages.length === 0 ? (
                <p className="empty">從一句問候開始，為故事留一個位置。</p>
              ) : (
                messages.map(({ user, turn }) => (
                  <article key={turn.turn_id}>
                    <p className="user-text">你 · {user}</p>
                    <div className="reply">
                      <span className="mini-brand">dm</span>
                      <div>
                        <b>
                          AI 生成內容{" "}
                          <small>
                            {turn.source_status === "no_personal_memory"
                              ? "沒有相關本人記憶"
                              : "參照已審核紀錄"}
                          </small>
                        </b>
                        <p>{turn.reply_text}</p>
                        {turn.evidence_refs.map((m) => (
                          <details key={m.memory_id}>
                            <summary>本人留下的文字紀錄 · {m.title}</summary>
                            <p>{m.text}</p>
                          </details>
                        ))}
                      </div>
                    </div>
                  </article>
                ))
              )}
            </section>
            <div className="metrics">
              <span>本回合處理時間</span>
              {Object.entries(timings).map(([k, v]) => (
                <span key={k}>
                  {k} <b>{v.toFixed(1)} ms</b>
                </span>
              ))}
              <small>不含模型品質或音視同步驗證</small>
            </div>
          </>
        )}
        {tab === "archive" && (
          <div className="archive-grid">
            <section className="panel">
              <h2>聲音參照</h2>
              <p>
                匯入已授權的單聲道 PCM16 WAV，3–30
                秒。檔案存於本機，不送至模型供應商。
              </p>
              <label className="check">
                <input
                  type="checkbox"
                  checked={consent}
                  onChange={(e) => setConsent(e.target.checked)}
                />
                我有權使用並同意以此聲音生成 AI 語音
              </label>
              <label className="upload">
                ＋ 匯入聲音 WAV
                <input
                  aria-label="匯入聲音"
                  disabled={!consent}
                  type="file"
                  accept=".wav"
                  onChange={(e) => upload(e.target.files?.[0])}
                />
              </label>
              {voices.map((v, i) => (
                <div className="record" key={v.profile_id}>
                  <b>
                    已授權聲音 {i + 1} · {v.duration_seconds} 秒
                  </b>
                  <span className="source-tag">本人留下的原聲 · 未合成</span>
                  <audio controls src={`/api/voices/${v.profile_id}/audio`} />
                  <button
                    onClick={async () => {
                      try {
                        await api(`/api/voices/${v.profile_id}`, {
                          method: "DELETE",
                        });
                        setVoice("synthetic");
                        await refresh();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    刪除聲音
                  </button>
                </div>
              ))}
            </section>
            <section className="panel">
              <h2>本人記憶卡</h2>
              <p>
                僅收錄本人審核的文字。標記為來源，AI
                回覆仍是生成內容。目前使用簡單關鍵字檢索。
              </p>
              <input
                aria-label="記憶標題"
                placeholder="故事標題"
                value={title}
                onChange={(e) => setTitle(e.target.value)}
              />
              <textarea
                aria-label="記憶內容"
                value={memoryText}
                onChange={(e) => setMemoryText(e.target.value)}
                placeholder="這段記錄是…"
              />
              <label className="check">
                <input
                  type="checkbox"
                  checked={reviewed}
                  onChange={(e) => setReviewed(e.target.checked)}
                />
                本人已確認這是真實、可供家人參考的記錄
              </label>
              <button
                className="primary"
                disabled={!reviewed || !title.trim() || !memoryText.trim()}
                onClick={saveMemory}
              >
                儲存本機記憶卡
              </button>
              {memories.map((m) => (
                <div className="record" key={m.memory_id}>
                  <h3>{m.title}</h3>
                  <p>{m.text}</p>
                  <button
                    onClick={async () => {
                      try {
                        await api(`/api/memories/${m.memory_id}`, {
                          method: "DELETE",
                        });
                        await clear();
                        await refresh();
                      } catch (e) {
                        setError((e as Error).message);
                      }
                    }}
                  >
                    撤回並清除對話
                  </button>
                </div>
              ))}
            </section>
          </div>
        )}
        {tab === "verify" && (
          <section className="panel">
            <h2>驗證範圍</h2>
            <p>
              自動化測試結果與原始記錄請查看{" "}
              <a href="/acceptance.html" target="_blank" rel="noreferrer">
                驗收證據看板 ↗
              </a>
              （執行 make evidence 後產生）。
            </p>
            <table>
              <thead>
                <tr>
                  <th>能力</th>
                  <th>目前界線</th>
                </tr>
              </thead>
              <tbody>
                {[
                  ["文字／對話／播放器", "Mock 流程可測；測試音不是聲音複製"],
                  ["麥克風與 STT", "可錄音與編輯逐字稿；Whisper 真實辨識待測"],
                  [
                    "Qwen3-TTS MLX / XTTS",
                    "隔離程序已接入，Mac 真機／音色未驗證",
                  ],
                  ["2D 人像", "RMS 振幅驅動嘴部；精確對嘴與音視偏差未測"],
                  ["人生記憶", "已審核文字 CRUD 與來源展示；非完整人生資料庫"],
                  ["macOS 透明浮動視窗", "尚未實作"],
                  ["家人長期使用", "監護人權限、加密、備份還原尚未驗證"],
                ].map(([a, b]) => (
                  <tr key={a}>
                    <td>{a}</td>
                    <td>{b}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </section>
        )}
        <audio
          ref={audio}
          muted={muted}
          onPlay={() => setPlaying(true)}
          onPause={() => setPlaying(false)}
          onEnded={() => setPlaying(false)}
        />
        <footer className="main-footer">
          DIGITALME <span>保存真實，坦誠生成。</span>
          <small>你的素材，由你保管。</small>
        </footer>
      </main>
    </div>
  );
}
createRoot(document.getElementById("root")!).render(<App />);
