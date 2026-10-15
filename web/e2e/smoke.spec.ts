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

test("the index loads once, preloaded with the page", async ({ page }) => {
  const requests: string[] = [];
  const warnings: string[] = [];
  page.on("request", (request) => {
    if (new URL(request.url()).pathname.endsWith("/data/index.json")) {
      requests.push(request.url());
    }
  });
  // Chromium says when a fetch cannot take a preload (its credentials mode, `crossorigin`),
  // at once, and when a preload goes unused, a few seconds after the page's load.
  page.on("console", (message) => {
    if (/preload/i.test(message.text())) warnings.push(message.text());
  });
  await page.goto("./");
  // The build kept index.html's preload as written (PERF-14).
  await expect(page.locator('link[rel="preload"][href="./data/index.json"]')).toHaveAttribute(
    "crossorigin",
    "",
  );
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  // data.ts's fetch takes the preload's response: one request, not two.
  expect(requests).toHaveLength(1);
  expect(warnings).toEqual([]);
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

test("older days past the budget are searched, and a card loads its abstract", async ({ page }) => {
  const errors = watchErrors(page);
  // Built with a budget of 3 papers: 2026-09-24 comes from its month's search shard (PERF-1).
  await page.goto("./");
  await expect(page.getByText("4 cs.CV papers")).toBeVisible();
  await page.locator(".period-picker__trigger").click();
  await expect(page.locator(".period-picker__note")).toContainText(
    "titles, authors, affiliations and venues over 1 older day too",
  );
  await page.keyboard.press("Escape");
  await page.getByRole("searchbox", { name: "Search papers" }).fill("computable");
  const card = page.locator("article.paper").filter({ hasText: "Computable Numbers" });
  await expect(card).toHaveCount(1);
  await expect(card).not.toContainText("On diffusion, with an application.");
  await card.getByRole("button", { name: "More" }).click();
  await expect(card).toContainText("On diffusion, with an application.");
  expect(errors).toEqual([]);
});

test("a card shows the stars of its code, and Most starred ranks by them", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?paper=2609.00001");
  // Merged by the build from code.json (PROD-18).
  const card = page.locator("article.paper--target");
  await expect(card.locator(".stars")).toHaveText("★ 42 GitHub stars +5 this week");
  // Its Code link shows the logo of the site it links (UX-28), named by its text alone.
  await expect(
    card.getByRole("link", { name: "Code", exact: true }).locator("svg"),
  ).toHaveAttribute("data-icon", "github");
  await page.goto("./");
  await page.getByRole("button", { name: "Most starred" }).click();
  await expect(page).toHaveURL(/sort=stars/);
  await expect(page.locator("article.paper").first()).toContainText(
    "Gaussian Splatting for Analytical Engines",
  );
  expect(errors).toEqual([]);
});

test("the most cited papers of the last 12 months, apart from the archive's years", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?view=cited");
  await page.getByRole("button", { name: "Last 12 months (2 papers)" }).click();
  await expect(page).toHaveURL(/year=last-12-months/);
  await expect(
    page.getByText(/2 of 2 highly cited cs\.CV papers first published since/),
  ).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Tabulating Machines for Open-Vocabulary Detection" }),
  ).toBeVisible();
  // A paper no day file holds: its link opens it there (PROD-11).
  await page.goto("./?view=cited&year=last-12-months&paper=2511.00001");
  const card = page.locator("article.paper--target");
  await expect(card).toContainText("Tabulating Machine Company");
  await expect(card).toContainText("80 citations");
  // One that left the list, chosen again every week, is said to be missing.
  await page.goto("./?view=cited&year=last-12-months&paper=2510.00009");
  await expect(page.getByText(/not among the highly cited papers shown/)).toBeVisible();
  expect(errors).toEqual([]);
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

test("a card's own Seen button hands the focus on as x does", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await page.getByRole("checkbox", { name: "Hide seen" }).check();
  const first = page.locator("article.paper").first();
  const id = await first.getAttribute("data-arxiv-id");
  await first.getByRole("button", { name: "Seen" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("3 of 4 cs.CV papers")).toBeVisible();
  const focused = page.locator("article.paper:focus");
  await expect(focused).toHaveCount(1);
  expect(await focused.getAttribute("data-arxiv-id")).not.toBe(id);
});

test("folding a seen paper a link opened hands the focus on", async ({ page }) => {
  await page.goto("./?paper=2609.00002");
  await page.getByRole("checkbox", { name: "Hide seen" }).check();
  const target = page.locator('article.paper[data-arxiv-id="2609.00002"]');
  await target.focus();
  // Seen, the paper the link opened stays while it is open...
  await page.keyboard.press("x");
  await expect(target.getByRole("button", { name: "Seen" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  // ...and leaves once folded, its focus going to the card now at its place.
  await page.keyboard.press("o");
  await expect(page.getByText("3 of 4 cs.CV papers")).toBeVisible();
  await expect(target).toHaveCount(0);
  const focused = page.locator("article.paper:focus");
  await expect(focused).toHaveCount(1);
});

test("a card's +N shows the rest, and its first name takes the focus", async ({ page }) => {
  const errors = watchErrors(page);
  await page.route("**/data/cs.CV/2026-09-25.json", async (route) => {
    const response = await route.fetch();
    const day = await response.json();
    day.papers[0].authors = Array.from({ length: 8 }, (_, index) => `Author ${index + 1}`);
    day.papers[0].author_affiliations = null;
    await route.fulfill({ response, json: day });
  });
  await page.goto("./");
  const card = page.locator('article.paper[data-arxiv-id="2609.00001"]');
  await card.getByRole("button", { name: "+2 more authors" }).click();
  await expect(card.getByRole("button", { name: "Author 7" })).toBeFocused();
  await expect(card.getByRole("button", { name: "Author 8" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("Back and Forward between a typed name and a clicked one keep the history", async ({
  page,
}) => {
  await page.goto("./?author=gra");
  await page.getByRole("button", { name: "Grace Hopper" }).first().click();
  await expect(page).toHaveURL(/by=Grace/);
  const entries = await page.evaluate("history.length");
  await page.goBack();
  await expect(page).toHaveURL(/author=gra/);
  // Past the typing pause, nothing was pushed over the entry Forward leads to.
  await page.waitForTimeout(400);
  expect(await page.evaluate("history.length")).toBe(entries);
  await page.goForward();
  await expect(page).toHaveURL(/by=Grace/);
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
  await expect(page.locator("article.paper")).toHaveCount(1);
  // The Export menu of the other lists (SRCH-16), Import and Export JSON beside it.
  await expect(page.getByRole("button", { name: "Import" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export JSON" })).toBeVisible();
  await page.locator(".export-menu__toggle").click();
  const menu = page.locator(".export-menu__items");
  for (const format of ["BibTeX", "CSV", "RIS", "Markdown"]) {
    await expect(menu.getByRole("button", { name: format, exact: true })).toBeVisible();
  }
  const download = page.waitForEvent("download");
  await menu.getByRole("button", { name: "RIS", exact: true }).click();
  expect((await download).suggestedFilename()).toBe("reading-list.ris");
  expect(errors).toEqual([]);
});

test("a paper the page cannot draw shows a message, not a blank page", async ({ page }) => {
  const errors = watchErrors(page);
  // A day whose first paper has no author list, which no card can draw.
  await page.route("**/data/cs.CV/2026-09-25.json", async (route) => {
    const response = await route.fetch();
    const day = await response.json();
    day.papers[0].authors = null;
    await route.fulfill({ response, json: day });
  });
  await page.goto("./");
  await expect(page.getByRole("alert")).toContainText("this view could not be displayed");
  await expect(page.getByRole("button", { name: "Reload" })).toBeVisible();
  // The view alone failed: the tabs still lead elsewhere.
  await page.getByRole("link", { name: "About", exact: true }).click();
  await expect(page.getByRole("heading", { name: "About Preprint Radar" })).toBeVisible();
  expect(errors.length).toBeGreaterThan(0);
});

test("a view that failed draws again for another period, or Back", async ({ page }) => {
  await page.route("**/data/cs.CV/2026-09-25.json", async (route) => {
    const response = await route.fetch();
    const day = await response.json();
    day.papers[0].authors = null;
    await route.fulfill({ response, json: day });
  });
  await page.goto("./?from=2026-09-24");
  await expect(page.getByText("1 of 1 cs.CV paper")).toBeVisible();
  await page.locator(".period-picker__trigger").click();
  await page.getByRole("button", { name: "Last week" }).click();
  await expect(page.getByRole("alert")).toContainText("this view could not be displayed");
  await page.goBack();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("1 of 1 cs.CV paper")).toBeVisible();
});
