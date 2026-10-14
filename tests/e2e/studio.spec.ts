import {
  test,
  expect,
} from "../../apps/web/node_modules/@playwright/test/index.js";
import path from "node:path";
const evidence = path.resolve("../../evidence");

test("Chinese text, playable audio and RMS avatar, interrupt, clear", async ({
  page,
}) => {
  const failures: string[] = [];
  page.on("pageerror", (e) => failures.push(e.message));
  await page.goto("/");
  await expect(page.getByText("AI 數位分身", { exact: true })).toBeVisible();
  await page.screenshot({
    path: path.join(evidence, "ui-idle.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(1);
  await expect(
    page.getByText("沒有相關本人記憶", { exact: true }),
  ).toBeVisible();
  await page
    .getByRole("button", { name: "播放", exact: false })
    .first()
    .click();
  await expect(page.locator(".portrait-area")).toHaveClass(/speaking/);
  await expect
    .poll(() =>
      page
        .locator(".mouth")
        .evaluate((e) => parseFloat((e as HTMLElement).style.height)),
    )
    .toBeGreaterThan(7);
  await page.screenshot({
    path: path.join(evidence, "ui-speaking.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "中斷", exact: true }).click();
  await expect(page.locator(".portrait-area")).not.toHaveClass(/speaking/);
  await page.getByRole("button", { name: "靜音", exact: true }).click();
  await expect(page.locator("audio").first()).toHaveJSProperty("muted", true);
  await page.getByRole("button", { name: "清除對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(0);
  expect(failures).toEqual([]);
});

test("20 UI turns complete, latency visible, ten TTS requests", async ({
  page,
}) => {
  await page.goto("/");
  for (let i = 0; i < 20; i++) {
    await page.getByLabel("對話文字").fill(`合成測試第 ${i + 1} 輪：談談勇氣`);
    await page.getByRole("button", { name: "開始對話" }).click();
    await expect(page.locator(".conversation article")).toHaveCount(i + 1);
    await expect(page.getByRole("button", { name: "開始對話" })).toBeEnabled();
  }
  await expect(page.locator(".metrics")).toContainText("total_ms");
  await page.getByRole("button", { name: "文字轉語音", exact: true }).click();
  for (let i = 0; i < 10; i++) {
    const response = page.waitForResponse((r) => r.url().endsWith("/api/tts"));
    await page.getByRole("button", { name: "產生聲音" }).click();
    expect((await response).status()).toBe(200);
    await expect(page.getByRole("button", { name: "產生聲音" })).toBeEnabled();
  }
});

test("backend errors remain visible and user can recover", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("聲音引擎").selectOption("mlx");
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.getByRole("alert")).toContainText("VOICE_PROFILE_REQUIRED");
  await page.getByLabel("聲音引擎").selectOption("mock");
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(1);
});

test("synthetic MediaStream capture produces editable transcript, no automatic generation", async ({
  page,
}) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      const c = new AudioContext();
      const o = c.createOscillator();
      const d = c.createMediaStreamDestination();
      o.connect(d);
      o.start();
      await c.resume();
      return d.stream;
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "麥克風輸入" }).click();
  await expect(page.getByRole("button", { name: "停止錄音" })).toBeVisible();
  await page.waitForTimeout(400);
  await page.getByRole("button", { name: "停止錄音" }).click();
  await expect(page.getByLabel("對話文字")).toHaveValue(
    "這是模擬辨識文字，請修改後再送出。",
  );
  await expect(page.locator(".conversation article")).toHaveCount(0);
  await page.getByLabel("對話文字").fill("已修正的合成文字");
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(1);
});

test("denied microphone has text fallback (simulated permission rejection)", async ({
  page,
}) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("denied", "NotAllowedError");
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "麥克風輸入" }).click();
  await expect(page.getByRole("alert")).toContainText("直接輸入文字");
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(1);
});

test("cloud opt-in and owner-reviewed memory CRUD with original source", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByLabel("對話引擎").selectOption("openai");
  await expect(page.getByRole("button", { name: "開始對話" })).toBeDisabled();
  await page.getByLabel("同意將目前文字").check();
  await expect(page.getByRole("button", { name: "開始對話" })).toBeEnabled();
  await page.getByLabel("對話引擎").selectOption("mock");
  await page.getByRole("button", { name: "記憶與聲音" }).click();
  await page.getByLabel("記憶標題").fill("合成風箏");
  await page.getByLabel("記憶內容").fill("合成測試故事：一起做風箏。");
  await expect(
    page.getByRole("button", { name: "儲存本機記憶卡" }),
  ).toBeDisabled();
  await page.getByLabel("本人已確認").check();
  await page.getByRole("button", { name: "儲存本機記憶卡" }).click();
  await expect(page.getByRole("heading", { name: "合成風箏" })).toBeVisible();
  await page.getByRole("button", { name: "對話工作室" }).click();
  await page.getByLabel("參照已審核記憶").check();
  await page.getByLabel("對話文字").fill("風箏");
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".reply")).toContainText("留下的紀錄提到");
  await expect(page.locator("summary")).toContainText("合成風箏");
  await page.getByRole("button", { name: "記憶與聲音" }).click();
  await page.getByRole("button", { name: "撤回並清除對話" }).click();
  await expect(page.getByRole("heading", { name: "合成風箏" })).toHaveCount(0);
});

test("portrait remains in browser, mobile layout fits", async ({ page }) => {
  await page.goto("/");
  let uploads = 0;
  page.on("request", (r) => {
    if (r.method() === "POST") uploads++;
  });
  const png = Buffer.from(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAQAAAC1HAwCAAAAC0lEQVR42mP8/x8AAwMCAO+jRNkAAAAASUVORK5CYII=",
    "base64",
  );
  await page.getByLabel("選擇本機肖像").setInputFiles({
    name: "synthetic.png",
    mimeType: "image/png",
    buffer: png,
  });
  await expect(page.getByAltText("本機授權肖像")).toBeVisible();
  expect(uploads).toBe(0);
  await page.getByRole("button", { name: "移除", exact: true }).click();
  await page.setViewportSize({ width: 390, height: 844 });
  expect(
    await page.evaluate(() => document.documentElement.scrollWidth),
  ).toBeLessThanOrEqual(390);
  await page.screenshot({
    path: path.join(evidence, "ui-mobile.png"),
    fullPage: true,
  });
});

test("unsupported microphone is explicit and leaves text usable", async ({
  page,
}) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("unsupported", "NotSupportedError");
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "麥克風輸入" }).click();
  await expect(page.getByRole("alert")).toContainText("不支援錄音");
  await expect(page.getByLabel("對話文字")).toBeEditable();
});

test("synthetic reference upload, original recording disclosure, preview and deletion", async ({
  page,
}) => {
  await page.goto("/");
  await page.getByRole("button", { name: "記憶與聲音" }).click();
  await page.getByLabel("我有權使用並同意").check();
  const seconds = 4,
    rate = 16000,
    buf = Buffer.alloc(44 + seconds * rate * 2);
  buf.write("RIFF", 0);
  buf.writeUInt32LE(buf.length - 8, 4);
  buf.write("WAVEfmt ", 8);
  buf.writeUInt32LE(16, 16);
  buf.writeUInt16LE(1, 20);
  buf.writeUInt16LE(1, 22);
  buf.writeUInt32LE(rate, 24);
  buf.writeUInt32LE(rate * 2, 28);
  buf.writeUInt16LE(2, 32);
  buf.writeUInt16LE(16, 34);
  buf.write("data", 36);
  buf.writeUInt32LE(buf.length - 44, 40);
  await page
    .getByLabel("匯入聲音")
    .setInputFiles({
      name: "synthetic-silence.wav",
      mimeType: "audio/wav",
      buffer: buf,
    });
  await expect(page.getByText("本人留下的原聲 · 未合成")).toBeVisible();
  await expect(page.locator(".record audio")).toHaveJSProperty("readyState", 4);
  await page.getByRole("button", { name: "刪除聲音" }).click();
  await expect(page.locator(".record audio")).toHaveCount(0);
});
