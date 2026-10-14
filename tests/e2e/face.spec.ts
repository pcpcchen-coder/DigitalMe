import {
  test,
  expect,
} from "../../apps/web/node_modules/@playwright/test/index.js";
import path from "node:path";
const evidence = path.resolve("../../evidence");

test("stereo demo reconstructs embedded GLB, deforms, speaks, and applies to conversation", async ({
  page,
}) => {
  const errors: string[] = [];
  page.on("pageerror", (e) => errors.push(e.message));
  await page.goto("/");
  await page.getByRole("button", { name: "人臉模型建立" }).click();
  await page.getByRole("button", { name: "載入合成雙目示範" }).click();
  await expect(page.getByText("虛擬相機校正（合成測試）")).toBeVisible();
  await page.getByRole("button", { name: "建立曲面與說話形變 GLB" }).click();
  await expect(page.locator(".face-viewer")).toHaveAttribute(
    "data-ready",
    "true",
    { timeout: 15000 },
  );
  await expect(page.getByText("合成深度曲面 · 非本人模型")).toBeVisible();
  await expect(page.locator(".face-viewer")).toHaveAttribute(
    "data-textures",
    "1",
  );
  const slider = page.getByLabel("手動張嘴測試");
  await slider.focus();
  await slider.press("End");
  await expect
    .poll(() => page.locator(".face-viewer").getAttribute("data-applied-jaw"))
    .toBe("1.000");
  await page.screenshot({
    path: path.join(evidence, "face-builder.png"),
    fullPage: true,
  });
  await page
    .getByLabel("模型試音文字")
    .fill(
      "合成測試音訊：這是一段供模型嘴型測試使用的比較長的文字，確保播放器有足夠時間提供可觀測的說話動畫。",
    );
  await page.getByRole("button", { name: "語音與模型連動測試" }).click();
  await expect
    .poll(async () =>
      parseFloat(
        (await page.locator(".face-viewer").getAttribute("data-applied-jaw")) ||
          "0",
      ),
    )
    .toBeGreaterThan(0.1);
  await page.getByRole("button", { name: "中斷模型試音" }).click();
  await expect
    .poll(() => page.locator(".face-viewer").getAttribute("data-applied-jaw"))
    .toBe("0.000");
  await page.getByRole("button", { name: "套用到對話人像" }).click();
  await expect(page.locator(".avatar-card .face-viewer")).toHaveAttribute(
    "data-ready",
    "true",
  );
  await page.getByRole("button", { name: "開始對話" }).click();
  await expect(page.locator(".conversation article")).toHaveCount(1);
  await expect
    .poll(async () =>
      parseFloat(
        (await page.locator(".face-viewer").getAttribute("data-applied-jaw")) ||
          "0",
      ),
    )
    .toBeGreaterThan(0.1);
  await page.screenshot({
    path: path.join(evidence, "face-speaking.png"),
    fullPage: true,
  });
  await page.getByRole("button", { name: "中斷", exact: true }).click();
  await page.getByRole("button", { name: "移除 3D 模型" }).click();
  await expect(page.locator(".portrait-area")).toBeVisible();
  expect(errors).toEqual([]);
});

test("face workflow requires ownership, real calibration and handles camera denial", async ({
  page,
}) => {
  await page.addInitScript(() => {
    navigator.mediaDevices.getUserMedia = async () => {
      throw new DOMException("denied", "NotAllowedError");
    };
  });
  await page.goto("/");
  await page.getByRole("button", { name: "人臉模型建立" }).click();
  await expect(
    page.getByRole("button", { name: "建立私人掃描" }),
  ).toBeDisabled();
  await page.getByLabel("我有權建立此人臉模型").check();
  await page.getByLabel("已確認單一同步 SBS").check();
  await page.getByRole("button", { name: "建立私人掃描" }).click();
  await expect(
    page.getByRole("button", { name: "建立曲面與說話形變 GLB" }),
  ).toBeDisabled();
  await page.getByRole("button", { name: "連接／切換攝影機" }).click();
  await expect(page.getByRole("alert")).toContainText("允許相機權限");
  await page.getByRole("button", { name: "刪除此掃描與模型" }).click();
  await expect(page.getByRole("status").first()).toContainText("已刪除");
});
