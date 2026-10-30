import AxeBuilder from "@axe-core/playwright";
import { type Page, expect, test } from "@playwright/test";

async function ask(page: Page, question: string) {
  await page.getByRole("textbox", { name: "Câu hỏi của bạn" }).fill(question);
  await page.getByRole("button", { name: "Hỏi", exact: true }).click();
  await expect(page.getByRole("region", { name: "Câu trả lời" })).toHaveAttribute(
    "aria-busy",
    "false",
  );
}

async function seriousA11yViolations(page: Page) {
  const results = await new AxeBuilder({ page }).analyze();
  return results.violations
    .filter((v) => v.impact === "serious" || v.impact === "critical")
    .map((v) => `${v.id}: ${v.nodes.map((n) => `${n.target.join(" ")} ${n.failureSummary}`).join(", ")}`);
}

test("asking streams an answer with citations that open the verbatim text", async ({ page }) => {
  await page.goto("/");

  await ask(page, "Điều kiện chuyển nhượng quyền sử dụng đất");

  const answer = page.getByRole("region", { name: "Câu trả lời" });
  await expect(answer).toContainText("được chuyển nhượng khi có Giấy chứng nhận");
  await expect(page.getByRole("list", { name: "Căn cứ pháp lý" })).toContainText("Điều 188");

  await answer.getByRole("button", { name: "Xem nguồn 1" }).click();
  const panel = page.getByRole("dialog");
  await expect(panel.getByRole("heading")).toContainText("Điều 188.");
  await expect(panel).toContainText("khi có các điều kiện sau đây");
  await page.keyboard.press("Escape");
  await expect(panel).toBeHidden();

  await page.getByRole("button", { name: "Câu trả lời hữu ích" }).click();
  await expect(page.getByRole("status")).toHaveText("Cảm ơn bạn đã góp ý.");
});

test("a situation shows the conclusion and the facts to add", async ({ page }) => {
  await page.goto("/");

  await ask(page, "Tôi muốn bán đất chưa có sổ đỏ được không?");

  await expect(page.getByRole("region", { name: "Kết luận" })).toContainText("Không được");
  await expect(page.getByRole("region", { name: "Thông tin nên bổ sung" })).toContainText(
    "Đất có đang tranh chấp không",
  );
});

test("an out-of-scope question is refused", async ({ page }) => {
  await page.goto("/");

  await ask(page, "Ngày mai thời tiết Hà Nội thế nào?");

  await expect(page.getByRole("region", { name: "Câu trả lời" })).toContainText(
    "nằm ngoài phạm vi",
  );
  await expect(page.getByRole("list", { name: "Căn cứ pháp lý" })).toHaveCount(0);
});

test("history survives a reload and reopens an answer", async ({ page }) => {
  await page.goto("/");
  await ask(page, "Điều kiện chuyển nhượng quyền sử dụng đất");

  await page.reload();
  const history = page.getByRole("navigation", { name: "Lịch sử câu hỏi" });
  await history.getByRole("button", { name: /Điều kiện chuyển nhượng/ }).click();

  await expect(page.getByRole("region", { name: "Câu trả lời" })).toContainText(
    "được chuyển nhượng khi có Giấy chứng nhận",
  );
});

test("the page still works when the browser blocks storage", async ({ page }) => {
  await page.addInitScript(() => {
    Object.defineProperty(window, "localStorage", {
      get() {
        throw new DOMException("blocked", "SecurityError");
      },
    });
  });
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  await page.goto("/");

  await ask(page, "Điều kiện chuyển nhượng quyền sử dụng đất");

  await expect(page.getByRole("region", { name: "Câu trả lời" })).toContainText("Giấy chứng nhận");
  expect(errors).toEqual([]);
});

test.describe("on a 375px phone", () => {
  test.use({ viewport: { width: 375, height: 740 }, isMobile: true, hasTouch: true });

  test("nothing scrolls sideways, before and after an answer", async ({ page }) => {
    const overflow = () =>
      page.evaluate(() => document.documentElement.scrollWidth - document.documentElement.clientWidth);
    await page.goto("/");
    expect(await overflow()).toBeLessThanOrEqual(0);

    await ask(page, "Tôi muốn bán đất chưa có sổ đỏ được không?");

    expect(await overflow()).toBeLessThanOrEqual(0);
  });
});

test("no serious or critical accessibility violations", async ({ page }) => {
  await page.goto("/");
  expect(await seriousA11yViolations(page)).toEqual([]);

  await ask(page, "Tôi muốn bán đất chưa có sổ đỏ được không?");
  expect(await seriousA11yViolations(page)).toEqual([]);

  await page.getByRole("button", { name: "Xem nguồn 1" }).first().click();
  const panel = page.getByRole("dialog");
  await expect(panel).toContainText("khi có các điều kiện");
  // Colours are only final once the slide-in animation has finished.
  await panel.evaluate((el) =>
    Promise.all(el.getAnimations({ subtree: true }).map((animation) => animation.finished)),
  );
  expect(await seriousA11yViolations(page)).toEqual([]);
});
