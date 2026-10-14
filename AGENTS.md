# DigitalMe — AI Agent Development Rules

> 任何 coding agent（ChatGPT Work / Codex / Claude Code）開始前，先讀 README 和 docs；本 repo 為 public。

## Non-negotiable
1. Preserve the founder's original intent: authentic voice + conversational AI + floating talking avatar + curated memory/legacy.
2. Never commit real voice recordings, face photographs, speaker embeddings, transcripts, family identities, API keys, tokens, or private memories. Prefer synthetic fixtures. Respect `.gitignore`.
3. Do not claim implementation/test success unless tools have actually run and produced evidence.
4. Keep XTTS legacy in its **own pinned Python 3.11 environment**; known `transformers==4.37.2` was the working fix for missing `GPT2InferenceModel.generate`. Do not indiscriminately delete working venv or model caches.
5. Separate model-independent orchestration from adapters; no vendor SDK imports inside core/domain.
6. AI-generated content must be identifiable as AI; original source evidence must be distinguishable from generated statements, especially for a child audience.
7. Do not use misleading language suggesting AI is literally the living person or is conscious.

## Workflow
- Audit repo and host environment → design smallest MVP → implement → run unit/integration/E2E → capture sanitized screenshots / audio test evidence → review failure modes → commit → report.
- Before destructive operations (deleting caches, replacing local environment, moving personal files), back up and obtain explicit user consent.
- Use `requirements.lock` / `uv.lock` or equivalent; record Python, torch, torchaudio, transformers, TTS and OS/arch.
- Establish `make dev`, `make test`, `make smoke` or equivalent; CI must work with mock speech + fake LLM without secrets.
- Maintain `docs/STATUS.md` as observed state: implemented / tested / blocked / not started.
- For every acceptance criterion, attach test command, outcome, commit hash, timestamp, and source log to evidence matrix. Verify dashboard against raw artifacts.
- Do not mark a phase done solely because an agent says it looks good; require reproducible proof.

## Priorities
P0: text → cloned voice → audio-reactive avatar → microphone STT → multi-turn AI.
P1: floating transparent macOS window + more accurate mouth sync + memory sources.
P2: life archive, trusted family access, long-term storage, rich avatar.

## Open Questions
- What minimal set of owner-approved memory records should be imported?
- Which physical Mac will serve as long-running host?
- Which TTS engine best preserves Taiwanese Mandarin after a family blind listen test?
- How will succession permissions, backups, deletion and encryption keys be managed?
