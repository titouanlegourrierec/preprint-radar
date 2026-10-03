/**
 * Smoke test of the built site: the four things a broken deploy would break first. Run with
 * `npm run test:e2e` (or `make test-e2e`); `playwright.config.ts` builds and serves it.
 */
import { expect, type Page, test } from "@playwright/test";

/** Fail the test on any error the page logs or throws. */
function watchErrors(page: Page): string[] {
  const errors: string[] = [];
  page.on("pageerror", (error) => errors.push(error.message));
  page.on("console", (message) => {
    if (message.type() === "error") errors.push(message.text());
  });
  return errors;
}

test("the list shows the stored papers", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Gaussian Splatting for Analytical Engines" }),
  ).toBeVisible();
  expect(errors).toEqual([]);
});

test("a search narrows the list and goes into the URL", async ({ page }) => {
  await page.goto("./");
  await page.getByRole("searchbox", { name: "Search papers" }).fill("compiler");
  await expect(page.getByText("1 of 4 cs.CV papers")).toBeVisible();
  await expect(page).toHaveURL(/\?q=compiler/);
});

test("a paper link opens the paper", async ({ page }) => {
  await page.goto("./?from=2026-09-24&paper=2609.00004");
  const card = page.locator("article.paper--target");
  await expect(card).toContainText("Computable Numbers in Diffusion Models");
  await expect(card).toHaveClass(/paper--expanded/);
  // And an archived paper's link, its year of the Highly cited view (SRCH-5).
  await page.goto("./?view=cited&year=2017&paper=1706.00001");
  await expect(page.locator("article.paper--target")).toContainText("Attention for Looms");
});

test("the graph draws on a canvas", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=graph");
  await expect(page.locator("canvas.graph__canvas")).toBeVisible();
  await expect(page.getByText(/institutions?/i).first()).toBeVisible();
  expect(errors).toEqual([]);
});
