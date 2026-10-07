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
  const archived = page.locator("article.paper--target");
  await expect(archived).toContainText("Attention for Looms");
  // With what scholar.json knows, merged by the build: its published venue and DOI (META-1).
  await expect(archived).toContainText("NeurIPS 2017");
  await expect(archived.getByRole("link", { name: "DOI" })).toHaveAttribute(
    "href",
    "https://doi.org/10.0000/looms.2017",
  );
});

test("the graph draws on a canvas", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=graph");
  await expect(page.locator("canvas.graph__canvas")).toBeVisible();
  await expect(page.getByText(/institutions?/i).first()).toBeVisible();
  // The layout runs in a worker, which sends the positions until they settle.
  await expect(page.locator('canvas.graph__canvas[data-layout="settled"]')).toBeVisible();
  expect(errors).toEqual([]);
});

test("the graph of an archive year lists its papers in Highly cited", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=graph&year=2017");
  await expect(page.locator('canvas.graph__canvas[data-layout="settled"]')).toBeVisible();
  // The Highlight field selects the match and shows its details, without touching the canvas.
  const highlight = page.getByRole("combobox", { name: "Highlight nodes by name" });
  await highlight.fill("Lyon");
  await highlight.press("Enter");
  await page.getByRole("button", { name: "Show its paper" }).click();
  await expect(page).toHaveURL(/view=cited/);
  await expect(page).toHaveURL(/year=2017/);
  await expect(page.getByRole("heading", { name: "Attention for Looms" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("marking a paper seen while seen papers are hidden moves the focus to the next one", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const hideSeen = page.getByRole("checkbox", { name: "Hide seen" });
  await hideSeen.check();
  // Keys typed in a form control are its own: leave the checkbox first.
  await hideSeen.blur();
  const focused = page.locator("article.paper:focus");
  await page.keyboard.press("j");
  await expect(focused).toHaveCount(1);
  const first = await focused.getAttribute("data-arxiv-id");
  await page.keyboard.press("x");
  await expect(page.getByText("3 of 4 cs.CV papers")).toBeVisible();
  // The card now at its place has the focus, so that j and x go on (UX-23).
  await expect(focused).toHaveCount(1);
  expect(await focused.getAttribute("data-arxiv-id")).not.toBe(first);
  expect(errors).toEqual([]);
});

test("a card's own Mark seen button hands the focus on as x does", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await page.getByRole("checkbox", { name: "Hide seen" }).check();
  const first = page.locator("article.paper").first();
  const id = await first.getAttribute("data-arxiv-id");
  await first.getByRole("button", { name: "Mark seen" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("3 of 4 cs.CV papers")).toBeVisible();
  const focused = page.locator("article.paper:focus");
  await expect(focused).toHaveCount(1);
  expect(await focused.getAttribute("data-arxiv-id")).not.toBe(id);
});

test("Rankings lists the institutions of the papers shown", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=rankings");
  await expect(page.getByRole("table")).toBeVisible();
  await expect(page.getByText(/in these 4 papers/)).toBeVisible();
  expect(errors).toEqual([]);
});

test("a saved paper is in the reading list, which exports it", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await page
    .locator("article.paper")
    .first()
    .getByRole("button", { name: "Save to reading list" })
    .click();
  await page.getByRole("link", { name: "Reading list (1)" }).click();
  await expect(page.getByText("1 of 1 saved paper")).toBeVisible();
  await expect(page.getByRole("button", { name: "Export BibTeX" })).toBeVisible();
  await expect(page.locator("article.paper")).toHaveCount(1);
  expect(errors).toEqual([]);
});
