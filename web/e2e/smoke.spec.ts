/**
 * Smoke test of the built site: the four things a broken deploy would break first. Run with
 * `npm run test:e2e` (or `make test-e2e`); `playwright.config.ts` builds and serves it.
 */
import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { CONTENT_SECURITY_POLICY } from "../tooling/content-security-policy";

/** The latest day file of the smoke test's store, asked for with or without its version (PERF-8). */
const DAY_FILE = /\/data\/cs\.CV\/2026-09-25\.json(?:\?|$)/;

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
  // Each data file with the version the build gave it in the site's index (PERF-8).
  const dayFile = page.waitForRequest(/\/data\/cs\.CV\/2026-09-25\.json\?v=[0-9a-f]{10}$/);
  await page.goto("./");
  await dayFile;
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await expect(
    page.getByRole("heading", { name: "Gaussian Splatting for Analytical Engines" }),
  ).toBeVisible();
  // The way to the code, from every view's top bar and the footer.
  for (const link of [
    page.getByRole("link", { name: "GitHub repository" }),
    page.getByRole("link", { name: "Source code on GitHub" }),
  ]) {
    await expect(link).toHaveAttribute(
      "href",
      "https://github.com/titouanlegourrierec/preprint-radar",
    );
  }
  expect(errors).toEqual([]);
});

test("a copied BibTeX keeps its badge and says the key to cite (UX-53)", async ({ page }) => {
  const errors = watchErrors(page);
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await page.goto("./");
  const card = page.locator("article.paper", {
    has: page.getByRole("heading", { name: "Gaussian Splatting for Analytical Engines" }),
  });
  const bibtex = card.getByRole("button", { name: "BibTeX", exact: true });
  const width = (await bibtex.boundingBox())?.width ?? 0;
  await bibtex.click();
  const entry = String(await page.evaluate("navigator.clipboard.readText()"));
  const key = /^@\w+\{([^,]+),/.exec(entry)?.[1] ?? "";
  expect(key).not.toBe("");
  await expect(card.getByRole("status")).toHaveText(`BibTeX copied: cite it as ${key}`);
  await expect(card.locator(".action__tip")).toHaveText(`\\cite{${key}}`);
  // The badge keeps its name and its width: its neighbours do not move.
  expect((await bibtex.boundingBox())?.width).toBeCloseTo(width, 1);
  expect(errors).toEqual([]);
});

test("the days since the last visit say so, and where they end (UX-54)", async ({ page }) => {
  const errors = watchErrors(page);
  await page.addInitScript(() =>
    localStorage.setItem("preprint-radar:last-visit:cs.CV", "2026-09-24"),
  );
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const headings = page.locator("summary.day-heading");
  await expect(headings.nth(0)).toContainText("New");
  await expect(headings.nth(1)).not.toContainText("New");
  await expect(page.getByText("Already here at your last visit")).toBeVisible();
  await expect(page.getByText("End of the list · 4 papers")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a saved search says so and keeps the focus; pressed again, it is forgotten (UX-59)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?q=compiler");
  await expect(page.getByText("1 of 4 cs.CV papers")).toBeVisible();
  await page.getByRole("button", { name: "Save this search" }).click();
  const saved = page.getByRole("button", { name: "Saved", exact: true });
  await expect(saved).toHaveAttribute("aria-pressed", "true");
  await expect(saved).toBeFocused();
  // The search shown, pressed in the list.
  const list = page.locator(".saved-searches__list");
  await expect(list.getByRole("button", { pressed: true })).toHaveCount(1);
  await saved.click();
  await expect(page.getByRole("button", { name: "Save this search" })).toBeFocused();
  await expect(list).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("a venue's badge shows that venue's papers alone (UX-64)", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=cited&year=2017");
  const card = page.locator("article.paper").filter({ hasText: "Attention for Looms" });
  await card.getByRole("button", { name: "NeurIPS 2017" }).click();
  await expect(page).toHaveURL(/venue=NeurIPS\+2017/);
  // The card stays folded: its badge is a control, not the card's text.
  await expect(card.locator(".paper__more")).toHaveAttribute("aria-expanded", "false");
  await expect(page.getByText("1 of 1 highly cited cs.CV paper")).toBeVisible();
  expect(errors).toEqual([]);
});

test("papers by the country of their institutions, from a search or Rankings (PROD-22)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  // Its institutions' ROR ids, as countries.json places them, merged by the build.
  await page.goto("./?country=US");
  await expect(page.getByText("2 of 4 cs.CV papers")).toBeVisible();
  await expect(
    page.getByRole("button", { name: "Remove the filter in United States" }),
  ).toBeVisible();
  // A search naming a country offers it.
  await page.goto("./?q=united+kingdom");
  await page
    .getByRole("button", { name: /^Show the 2 papers with an institution in United Kingdom$/ })
    .click();
  await expect(page).toHaveURL(/\?country=GB$/);
  await expect(page.getByText("2 of 4 cs.CV papers")).toBeVisible();
  // So does a country pinned in Rankings.
  await page.goto("./?view=rankings&rank=country");
  await page.getByRole("button", { name: "United States" }).click();
  await page.getByRole("button", { name: "Show the papers of United States" }).click();
  await expect(page).toHaveURL(/[?&]country=US$/);
  await expect(page).not.toHaveURL(/view=/);
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
  // Dated by its month, arXiv's catalog giving no day (META-5).
  await expect(archived.getByTitle(/^Dated by month/)).toHaveText("Jun 2017");
  // With what scholar.json knows, merged by the build: its published venue and DOI (META-1).
  await expect(archived).toContainText("NeurIPS 2017");
  await expect(archived.getByRole("link", { name: "DOI" })).toHaveAttribute(
    "href",
    "https://doi.org/10.0000/looms.2017",
  );
  // Its place among its year's papers, from cohorts.json in the site's index (decision 22).
  await expect(
    archived.getByTitle(/^Among the 1% most cited of the 5,701 cs.CV papers/),
  ).toHaveText("Top 1% of 2017");
});

test("older days past the budget are searched, and a card loads its abstract", async ({ page }) => {
  const errors = watchErrors(page);
  // Built with a budget of 3 papers: 2026-09-24 comes from its month's search shard (PERF-1).
  await page.goto("./");
  await expect(page.getByText("4 cs.CV papers")).toBeVisible();
  await page.getByRole("button", { name: /^Period: / }).click();
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

test("a search of every stored paper finds what the period does not hold (PROD-21)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?q=looms");
  await expect(page.getByText("No paper matches in this period.")).toBeVisible();
  await page.getByRole("button", { name: "Search all stored papers" }).click();
  await expect(page).toHaveURL(/\?q=looms&scope=all$/);
  // The day files, the most cited of the last 12 months and the archive, each paper once.
  await expect(page.getByText("1 of 6 stored cs.CV papers")).toBeVisible();
  const card = page.locator("article.paper").filter({ hasText: "Attention for Looms" });
  await expect(card.getByTitle(/^Dated by month/)).toHaveText("Jun 2017");
  // The period's button names it, chosen beside the presets; a preset leaves it.
  const period = page.getByRole("button", { name: /^Period: All stored papers/ });
  await period.click();
  const store = page.getByRole("button", { name: "All papers", exact: true });
  await expect(store).toHaveAttribute("aria-pressed", "true");
  await page.getByRole("button", { name: "Last week" }).click();
  await expect(page).toHaveURL(/\?q=looms$/);
  await expect(page.getByText("No paper matches in this period.")).toBeVisible();
  // Chosen there, it glows once, then shimmers while chosen (PROD-21).
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "All papers", exact: true }).click();
  await expect(page).toHaveURL(/\?q=looms&scope=all$/);
  await expect(page.locator(".period-picker__trigger--launch")).toBeVisible();
  await expect(page.locator(".period-picker__trigger--launch")).toHaveCount(0);
  await expect(page.getByText("1 of 6 stored cs.CV papers")).toBeVisible();
  expect(errors).toEqual([]);
});

test("Rankings rank every stored paper, chosen as Papers search them (PROD-21)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?view=rankings");
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "All papers", exact: true }).click();
  await expect(page).toHaveURL(/\?view=rankings&scope=all$/);
  await expect(page.getByText("6 of 6 stored cs.CV papers")).toBeVisible();
  await expect(page.locator("table.rankings__table tbody tr").first()).toBeVisible();
  // The archive's years leave it.
  await page.getByRole("button", { name: /^Highly cited/ }).click();
  await page.getByRole("button", { name: /^2017, 1 paper/ }).click();
  await expect(page).toHaveURL(/year=2017/);
  await expect(page).not.toHaveURL(/scope=all/);
  expect(errors).toEqual([]);
});

test("Highly cited without a match offers other years and every stored paper (UX-55)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?view=cited&year=2017&q=analytical");
  await expect(page.getByText("No highly cited paper of 2017 matches.")).toBeVisible();
  await page.getByRole("button", { name: "Search the last 12 months" }).click();
  await expect(page).toHaveURL(/year=last-12-months/);
  await expect(
    page.getByRole("heading", { name: "Gaussian Splatting for Analytical Engines" }),
  ).toBeVisible();
  // Every stored paper, with the same words, in Papers.
  await page.goto("./?view=cited&year=2017&q=computable");
  await expect(page.getByText("No highly cited paper of 2017 matches.")).toBeVisible();
  await page.getByRole("button", { name: "Search all stored papers" }).click();
  await expect(page).toHaveURL(/\?q=computable&scope=all$/);
  await expect(page.getByText("1 of 6 stored cs.CV papers")).toBeVisible();
  expect(errors).toEqual([]);
});

test("a click on a folded card opens it, not one on its controls", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const card = page.locator("article.paper").first();
  const more = card.locator(".paper__more");
  // Its own buttons keep their action (UX-34).
  await card.getByRole("button", { name: "Seen" }).click();
  await expect(more).toHaveAttribute("aria-expanded", "false");
  await card.locator(".paper__meta").click({ position: { x: 4, y: 4 } });
  await expect(more).toHaveAttribute("aria-expanded", "true");
  // Open, it stays open to a click on its text; Less folds it.
  await card.locator(".paper__abstract").click();
  await expect(more).toHaveAttribute("aria-expanded", "true");
  await more.click();
  await expect(more).toHaveAttribute("aria-expanded", "false");
  expect(errors).toEqual([]);
});

test("the sidebar folds, the papers the whole width, and stays so", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const sidebar = page.locator("#sidebar");
  await expect(sidebar).toBeVisible();
  // Folded, it is out of sight and of the tab order; the choice is remembered (UX-35).
  await page.getByRole("button", { name: "Hide the filters" }).click();
  await expect(sidebar).toBeHidden();
  await page.reload();
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await expect(sidebar).toBeHidden();
  await page.getByRole("button", { name: "Show the filters" }).click();
  await expect(sidebar).toBeVisible();
  expect(errors).toEqual([]);
});

test("the calendar picks a day from the keyboard", async ({ page }) => {
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const trigger = page.getByRole("button", { name: /^Period: / });
  await expect(trigger).not.toHaveAttribute("aria-controls");
  await trigger.click();
  await expect(trigger).toHaveAttribute("aria-controls");
  // One day takes Tab, the period's last; the arrows move to the others (UX-14).
  await page.locator('.period-picker__day[tabindex="0"]').focus();
  await expect(page.locator(".period-picker__day:focus")).toHaveAttribute("data-day", "2026-09-25");
  await page.keyboard.press("ArrowLeft");
  await expect(page.locator(".period-picker__day:focus")).toHaveAttribute("data-day", "2026-09-24");
  await page.keyboard.press("Enter");
  await page.keyboard.press("Enter");
  await expect(page).toHaveURL(/\?from=2026-09-24$/);
  await expect(page.getByText("1 of 1 cs.CV paper")).toBeVisible();
});

test("a range to the latest day keeps adding new days, as a since link", async ({ page }) => {
  await page.goto("./?from=2026-09-24&to=2026-09-25");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "Keep adding new days" }).click();
  // The link no longer ends on 25 September: tomorrow's papers will join it (PROD-13).
  await expect(page).toHaveURL(/\?since=2026-09-24$/);
  await expect(page.getByRole("button", { name: /^Period: / })).toContainText("Since");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
});

test("a day that fails to load is asked for again, then left out with a notice", async ({
  page,
}) => {
  const errors = watchErrors(page);
  // The latest day's first request is dropped, and answered the second time (SRCH-10).
  let dropped = false;
  await page.route(DAY_FILE, async (route) => {
    if (dropped) return route.fallback();
    dropped = true;
    return route.abort("connectionreset");
  });
  // The older day's month fails until Retry.
  let shardDown = true;
  await page.route(/\/data\/cs\.CV\/search\/2026-09\.json(?:\?|$)/, (route) =>
    shardDown ? route.fulfill({ status: 503, body: "" }) : route.fallback(),
  );
  await page.goto("./");
  await expect(page.getByText("3 of 3 cs.CV papers")).toBeVisible();
  const notice = page.getByRole("alert");
  await expect(notice).toContainText("could not be loaded: they are not shown");
  shardDown = false;
  await notice.getByRole("button", { name: "Retry" }).click();
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  await expect(page.getByRole("alert")).toHaveCount(0);
  // The failed requests are the browser's own errors; the page logs none.
  expect(errors.filter((error) => !error.includes("Failed to load resource"))).toEqual([]);
});

test("a card shows the stars of its code, and Most starred and Rising stars rank by them", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?paper=2609.00001");
  // Merged by the build from code.json (PROD-18).
  const card = page.locator("article.paper--target");
  await expect(card.locator(".stars")).toHaveText("42 GitHub stars +5 this week");
  await expect(card.locator('.stars svg[data-icon="star-filled"]')).toHaveCount(1);
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
  // Its stars gained in the week (code.json's `gained`) rank it first in Rising stars too.
  await page.getByRole("button", { name: "Rising stars" }).click();
  await expect(page).toHaveURL(/sort=rising-stars/);
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
  // The years are chosen as in the graph's chip (UX-33): a year of the grid, or a preset.
  await page.getByRole("button", { name: /^Highly cited/ }).click();
  await expect(page.getByRole("button", { name: /^2017, 1 paper/ })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  await page.getByRole("button", { name: "Last 12 months" }).click();
  await expect(page).toHaveURL(/year=last-12-months/);
  await expect(
    page.getByText(/2 of 2 highly cited cs\.CV papers first published since/),
  ).toBeVisible();
  // Each card says its rank, the first ones in medal colors (UX-36).
  const cards = page.locator("article.paper");
  await expect(cards.nth(0).locator(".paper__rank--gold")).toHaveText("Rank 1");
  await expect(cards.nth(1).locator(".paper__rank--silver")).toHaveText("Rank 2");
  // How they are chosen is said behind the (i) beside the count.
  await page.getByRole("button", { name: "About these papers" }).click();
  await expect(page.getByText(/by citations per month of age/)).toBeVisible();
  await page.keyboard.press("Escape");
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

test("the Content-Security-Policy refuses nothing the site does", async ({ page }) => {
  const errors = watchErrors(page);
  // In the page (e2e has no DOM types): what the policy refused, and a theme forced.
  await page.addInitScript({
    content: `
      window.refused = [];
      document.addEventListener("securitypolicyviolation", (event) =>
        window.refused.push(event.violatedDirective + " " + event.blockedURI));
      localStorage.setItem("preprint-radar:theme", "dark");
    `,
  });
  await page.goto("./");
  await expect(page.locator('meta[http-equiv="Content-Security-Policy"]')).toHaveAttribute(
    "content",
    CONTENT_SECURITY_POLICY,
  );
  // public/theme.js ran before first paint: the theme forced with the toggle (SEC-1).
  await expect(page.locator("html")).toHaveAttribute("data-theme", "dark");
  // The logo, inline, named once, leads home; the favicons are the site's own (UX-48).
  await expect(page.getByRole("link", { name: "Preprint Radar" })).toHaveAttribute("href", "./");
  await expect(page.locator('link[rel="icon"][type="image/svg+xml"]')).toHaveAttribute(
    "href",
    "./favicon.svg",
  );
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  // A formula drawn as MathML, without the style its accent gets from Temml (UX-69).
  const compiler = page.locator("article.paper").filter({ hasText: "A Compiler for Neural" });
  await compiler.getByRole("button", { name: "More" }).click();
  await expect(compiler.locator(".paper__abstract math")).toHaveCount(1);
  // A saved paper's star bursts and flies to its tab, placed from the script (UX-37).
  await page.getByRole("button", { name: "Save to reading list" }).first().click();
  await expect(page.locator(".save-burst")).toHaveCount(1);
  await expect(page.locator(".save-flight")).toHaveCount(0);
  await page.goto("./?view=graph");
  await expect(page.locator("canvas.graph__canvas")).toBeVisible();
  await page.goto("./?view=cited&year=2017");
  await expect(page.getByText("Attention for Looms")).toBeVisible();
  // The world map's chunk: its shapes, a hatching pattern, a tooltip placed from the script.
  await page.goto("./?view=rankings&rank=country");
  await expect(page.getByRole("img", { name: /^World map of the countries/ })).toBeVisible();
  await page.locator('[data-code="GB"]').hover();
  await expect(page.locator(".world-map__tip")).toBeVisible();
  // Zoomed, and as a globe, its transforms and gradient (UX-43).
  await page.getByRole("button", { name: "Zoom in" }).click();
  await page.getByRole("button", { name: "Globe" }).click();
  await expect(page.locator(".world-map__sea")).toBeVisible();
  // A topic's chart, its tooltip placed from the script (PROD-20).
  await page.goto("./?view=trends&topic=world+model");
  await page.locator(".chart__svg").hover();
  await expect(page.locator(".chart__tip")).toBeVisible();
  expect(await page.evaluate("window.refused")).toEqual([]);
  expect(errors).toEqual([]);
});

test("Trends lists the topics that rise, and opens one with its papers (PROD-20)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./");
  await page.getByRole("link", { name: "Trends", exact: true }).click();
  await expect(page).toHaveURL(/\?view=trends$/);
  const rising = page.getByRole("region", { name: "Rising" });
  await expect(rising.getByRole("listitem")).toHaveCount(2);
  await expect(page.getByRole("region", { name: "Cooling" })).toContainText(
    "Semi-supervised segmentation",
  );
  await rising.getByRole("link", { name: /^World model ×/ }).click();
  await expect(page).toHaveURL(/\?view=trends&topic=world\+model$/);
  const topic = page.getByRole("region", { name: "World model" });
  await expect(topic).toContainText(
    "32 papers in the last 90 days, 2 in the same days a year before",
  );
  // Its most cited papers of the last 12 months, the most cited first.
  await expect(topic.getByRole("link", { name: "World Models of Cities" }).first()).toHaveAttribute(
    "href",
    "https://arxiv.org/abs/2601.10000",
  );
  // The chart's values, as a table.
  await topic.getByRole("button", { name: "Show as a table" }).click();
  await expect(topic.getByRole("row", { name: /^Oct 2026, to 20 Oct 2026/ })).toBeVisible();
  // The 12 months replace the entry; the topic stays open.
  await page.getByRole("button", { name: "12 months", exact: true }).click();
  await expect(page).toHaveURL(/\?view=trends&window=year&topic=world\+model$/);
  await expect(topic).toContainText("in the last 12 months");
  // Its papers, searched in the Papers view; Back comes to the topic.
  await topic.getByRole("link", { name: /^Its papers since/ }).click();
  // Its synonyms with it.
  await expect(page.getByRole("searchbox", { name: "Search papers" })).toHaveValue(
    '"world model" OR "world models" OR "world modeling" OR "world modelings"',
  );
  await expect(page).toHaveURL(
    /\?q=%22world\+model%22\+OR\+%22world\+models%22\+OR\+%22world\+modeling%22\+OR\+%22world\+modelings%22&since=2025-10-21$/,
  );
  await page.goBack();
  await expect(page).toHaveURL(/\?view=trends&window=year&topic=world\+model$/);
  await expect(page.getByRole("region", { name: "World model" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("a search that names a rising topic says so, and links to its trend (PROD-20)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto("./?q=World+Models");
  const note = page.getByText("“World model” is a rising topic of the titles");
  await expect(note).toContainText("over the last 90 days against the same days a year before");
  await page.getByRole("link", { name: "See its trend" }).click();
  await expect(page).toHaveURL(/view=trends&topic=world\+model$/);
  await expect(page.getByRole("region", { name: "World model" })).toBeVisible();
  // A synonym names its topic.
  await page.goto("./?q=world+modeling");
  await expect(page.getByText("“World model” is a rising topic of the titles")).toBeVisible();
  // No note for words that name no listed topic, nor for a key every object has.
  await page.goto("./?q=punched+cards");
  await expect(page.getByText("1 of 4 cs.CV papers")).toBeVisible();
  await expect(page.getByText("topic of the titles")).toHaveCount(0);
  await page.goto("./?q=constructor");
  await expect(page.getByRole("searchbox", { name: "Search papers" })).toHaveValue("constructor");
  await expect(page.getByText("topic of the titles")).toHaveCount(0);
  expect(errors).toEqual([]);
});

test("the explorer loads every topic only when asked, and draws them by quarter (PROD-20)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  const asked: string[] = [];
  page.on("request", (request) => asked.push(new URL(request.url()).pathname));
  await page.goto("./?view=trends&topic=world+model");
  const explorer = page.getByRole("region", { name: "Explore a topic" });
  await expect(explorer.getByRole("button", { name: "World model", exact: true })).toBeVisible();
  // Its 400 kB wait for the field or a topic to draw.
  expect(asked.filter((path) => path.endsWith("/topics.json"))).toEqual([]);
  const field = explorer.getByRole("combobox", { name: "Find a topic to draw" });
  await field.fill("mamb");
  // The topic typed first, then the longer ones holding it.
  await expect(explorer.getByRole("option").first()).toHaveText(/^Mamba\s*30 papers$/);
  await expect(explorer.getByRole("option").nth(1)).toContainText("Mamba for");
  await field.press("Enter");
  await expect(page).toHaveURL(/\?view=trends&topic=world\+model&compare=mamba$/);
  // The topic opened adds itself, as the second line.
  await page.getByRole("button", { name: "Compare in the explorer" }).click();
  await expect(page).toHaveURL(/&compare=mamba%2Cworld\+model$/);
  await expect(explorer.getByRole("list", { name: "Topics drawn" })).toContainText(
    "MambaWorld model",
  );
  await explorer.getByRole("button", { name: "Show as a table" }).click();
  await expect(explorer.getByRole("row", { name: /^2024 Q1/ })).toBeVisible();
  await explorer.getByRole("button", { name: "Remove Mamba" }).click();
  await expect(page).toHaveURL(/&compare=world\+model$/);
  expect(asked.filter((path) => path.endsWith("/topics.json"))).toHaveLength(1);
  expect(errors).toEqual([]);
});

test("a year the archive does not hold names the year shown in the link, in place", async ({
  page,
}) => {
  await page.goto("./");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
  const entries = await page.evaluate("history.length");
  await page.goto("./?view=cited&year=2005&paper=1706.00001");
  // The archive holds 2017 alone: the link says so, keeping the paper (SRCH-20).
  await expect(page).toHaveURL(/\?view=cited&paper=1706\.00001&year=2017$/);
  await expect(page.locator("article.paper--target")).toContainText("Attention for Looms");
  expect(await page.evaluate("history.length")).toBe(Number(entries) + 1);
  await page.goBack();
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
});

test("the graph draws on a canvas", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=graph");
  await expect(page.locator("canvas.graph__canvas")).toBeVisible();
  await expect(page.getByText(/institutions?/i).first()).toBeVisible();
  // The layout runs in a worker, which sends the positions until they settle.
  await expect(page.locator('canvas.graph__canvas[data-layout="settled"]')).toBeVisible();
  // The papers are chosen with the floating chips (UX-29): the period chip holds the
  // presets and the calendar, the highly cited chip the archive's years, the venue chip
  // the venues. The data notes sit behind the (i), and / finds a node.
  const papers = page.getByRole("region", { name: "Papers" });
  await papers.getByRole("button", { name: /^Papers:/ }).click();
  await expect(page.getByRole("button", { name: "Latest day" })).toBeVisible();
  await page.keyboard.press("Escape");
  await papers.getByRole("button", { name: /^Highly cited/ }).click();
  await expect(page.getByRole("button", { name: "All years" })).toBeVisible();
  await page.keyboard.press("Escape");
  await expect(papers.getByRole("combobox", { name: "Venue" })).toBeVisible();
  await expect(page.getByRole("region", { name: "Graph settings" })).toBeVisible();
  // The intro card sits over the (i) until it is read.
  await page.getByRole("button", { name: "Got it" }).click();
  await page.getByRole("button", { name: "About the data" }).click();
  await expect(page.getByText(/Affiliations known for/)).toBeVisible();
  await page.keyboard.press("Escape");
  await page.keyboard.press("/");
  await expect(page.getByRole("combobox", { name: "Find a node by name" })).toBeFocused();
  expect(errors).toEqual([]);
});

test("the graph of an archive year lists its papers in Highly cited", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=graph&year=2017");
  await expect(page.locator('canvas.graph__canvas[data-layout="settled"]')).toBeVisible();
  // The Find field selects the match and shows its details, without touching the canvas.
  const find = page.getByRole("combobox", { name: "Find a node by name" });
  await find.fill("Lyon");
  await find.press("Enter");
  await page.getByRole("button", { name: "Show its paper" }).click();
  await expect(page).toHaveURL(/view=cited/);
  await expect(page).toHaveURL(/year=2017/);
  await expect(page.getByRole("heading", { name: "Attention for Looms" })).toBeVisible();
  expect(errors).toEqual([]);
});

test("counts that arrive once the graph is laid out leave it in place (PERF-7)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  // The year's counts wait until its graph has settled.
  let release = () => {};
  const held = new Promise<void>((resolve) => {
    release = resolve;
  });
  await page.route(/\/data\/cs\.CV\/citations\/2017\.json(?:\?|$)/, async (route) => {
    await held;
    await route.fallback();
  });
  await page.goto("./?view=graph&year=2017");
  await expect(page.locator('canvas.graph__canvas[data-layout="settled"]')).toBeVisible();
  // From now on, whether the layout runs again.
  await page.evaluate(`(() => {
    const canvas = document.querySelector("canvas.graph__canvas");
    window.moved = false;
    new MutationObserver(() => {
      if (canvas.dataset.layout === "moving") window.moved = true;
    }).observe(canvas, { attributeFilter: ["data-layout"] });
  })()`);
  await page.getByRole("button", { name: "Got it" }).click();
  await page.getByRole("button", { name: "About the data" }).click();
  await expect(page.getByText(/Citations on Semantic Scholar/)).toHaveCount(0);
  release();
  // The data notes say where the counts come from once they are there.
  await expect(page.getByText(/Citations on Semantic Scholar/)).toBeVisible();
  await page.evaluate(
    "new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))",
  );
  expect(await page.evaluate("window.moved")).toBe(false);
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
  await page.route(DAY_FILE, async (route) => {
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
  await expect(
    page.getByRole("table", { name: "Institutions of the papers shown, by papers" }),
  ).toBeVisible();
  await expect(page.getByText(/in these 4 papers/)).toBeVisible();
  // Authors by citations, in the link, which opens them again (SRCH-13).
  await page.getByRole("button", { name: "Authors", exact: true }).click();
  await page.getByRole("group", { name: "By" }).getByRole("button", { name: "Citations" }).click();
  await expect(page).toHaveURL(/\?view=rankings&rank=author&metric=citations$/);
  await page.reload();
  await expect(
    page.getByRole("table", { name: "Authors of the papers shown, by citations" }),
  ).toBeVisible();
  await expect(page.getByRole("rowheader").first()).toBeVisible();
  // A column's header ranks by it (UX-42).
  await page
    .getByRole("columnheader", { name: "Papers" })
    .getByRole("button", { name: "Papers" })
    .click();
  await expect(page).toHaveURL(/\?view=rankings&rank=author&metric=papers$/);
  await expect(page.getByRole("columnheader", { name: "Papers" })).toHaveAttribute(
    "aria-sort",
    "descending",
  );
  expect(errors).toEqual([]);
});

test("Rankings maps the countries of the papers shown", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=rankings");
  // Countries open the map, loaded then (UX-41).
  await page.getByRole("button", { name: "Countries", exact: true }).click();
  await expect(page).toHaveURL(/rank=country/);
  await expect(page.getByRole("img", { name: /^World map of the countries/ })).toBeVisible();
  // A paper of two countries counts half for each.
  const table = page.getByRole("table", { name: "The countries of the papers shown, by papers" });
  await expect(table.getByRole("row", { name: /United Kingdom 1\.5/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /United States of America 1\.5/ })).toBeVisible();
  // A country of the table is shown on the map.
  await table.getByRole("button", { name: "United Kingdom" }).click();
  await expect(page.locator('.world-map__shape--pinned[data-code="GB"]')).toHaveCount(1);
  await expect(page.locator(".world-map__tip")).toContainText("United Kingdom");
  // Its header ranks the table by a column (UX-42).
  await table.getByRole("button", { name: "Per million people" }).click();
  await expect(page).toHaveURL(/metric=per-million/);
  await expect(
    page.getByRole("table", { name: "The countries of the papers shown, by per million people" }),
  ).toBeVisible();
  // The map zooms, and turns into a globe, which this browser remembers (UX-43).
  const map = page.locator(".world-map__svg > g");
  await expect(map).toHaveAttribute("transform", "translate(0 0) scale(1)");
  await page.getByRole("button", { name: "Zoom in" }).click();
  await expect(map).not.toHaveAttribute("transform", "translate(0 0) scale(1)");
  await page.getByRole("button", { name: "Globe" }).click();
  await expect(page.locator(".world-map__sea")).toBeVisible();
  await expect(page.locator('[data-code="GB"]')).toHaveCount(1);
  await page.reload();
  await expect(page.locator(".world-map__sea")).toBeVisible();
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
  // The Export menu of the other lists (SRCH-16), the library's Import and Export beside it.
  await expect(page.getByRole("button", { name: "Import library" })).toBeVisible();
  await expect(page.getByRole("button", { name: "Export library" })).toBeVisible();
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

test("the reading list's folders group saved papers, and stay", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  const saves = page.getByRole("button", { name: "Save to reading list" });
  await saves.nth(0).click();
  await saves.nth(1).click();
  await page.getByRole("link", { name: "Reading list (2)" }).click();
  // A folder is made in the sidebar, and a paper put in it from its card (UX-38).
  const folders = page.getByRole("navigation", { name: "Folders" });
  await folders.getByRole("button", { name: "New folder" }).click();
  const name = page.getByRole("textbox", { name: "The new folder's name" });
  await expect(name).toBeFocused();
  await name.fill("To read");
  await name.press("Enter");
  // Its card's menu puts a paper in it (UX-45).
  await page.getByRole("button", { name: "Folder", exact: true }).first().click();
  await page.getByRole("checkbox", { name: "To read" }).check();
  await page.keyboard.press("Escape");
  await folders.getByRole("button", { name: /^To read/ }).click();
  await expect(page).toHaveURL(/folder=To\+read/);
  await expect(page.getByText("1 of 1 saved paper in “To read”")).toBeVisible();
  await expect(page.locator("article.paper")).toHaveCount(1);
  // Kept in this browser, and exported with the papers.
  await page.reload();
  await expect(page.getByText("1 of 1 saved paper in “To read”")).toBeVisible();
  const download = page.waitForEvent("download");
  await page.getByRole("button", { name: "Export library" }).click();
  const file = JSON.parse(readFileSync(await (await download).path(), "utf8"));
  expect(file.folders).toEqual([{ name: "To read", papers: [expect.any(String)] }]);
  // A folder alone, which Import library brings back (UX-44).
  const exported = page.waitForEvent("download");
  await folders.getByRole("button", { name: "Export" }).click();
  const folderFile = await exported;
  expect(folderFile.suggestedFilename()).toBe("reading-list-to-read.json");
  const alone = JSON.parse(readFileSync(await folderFile.path(), "utf8"));
  expect([alone.papers.length, alone.folders]).toEqual([1, file.folders]);
  // Deleted, its papers stay saved.
  await folders.getByRole("button", { name: "Delete" }).click();
  await folders.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("2 of 2 saved papers")).toBeVisible();
  await page.locator('input[type="file"]').setInputFiles(await folderFile.path());
  await expect(page.getByText("0 papers added, 1 already saved; 1 folder added.")).toBeVisible();
  await expect(folders.getByRole("button", { name: /^To read 1$/ })).toBeVisible();
  expect(errors).toEqual([]);
});

test("the reading list's own order, arranged by Alt+arrows or a drag", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./");
  const saves = page.getByRole("button", { name: "Save to reading list" });
  await saves.nth(1).click();
  await saves.nth(0).click();
  await page.getByRole("link", { name: "Reading list (2)" }).click();
  // My order, the list's default (UX-39): the paper saved last first.
  await expect(page.getByRole("button", { name: "My order" })).toHaveAttribute(
    "aria-pressed",
    "true",
  );
  const cards = page.locator("article.paper");
  const first = await cards.nth(0).getAttribute("data-arxiv-id");
  await cards.nth(0).focus();
  await page.keyboard.press("Alt+ArrowDown");
  await expect(cards.nth(1)).toHaveAttribute("data-arxiv-id", first ?? "");
  await expect(cards.nth(1)).toBeFocused();
  // Kept in this browser.
  await page.reload();
  await expect(cards.nth(1)).toHaveAttribute("data-arxiv-id", first ?? "");
  // A card dragged by its handle onto a folder goes in it.
  const folders = page.getByRole("navigation", { name: "Folders" });
  await folders.getByRole("button", { name: "New folder" }).click();
  const name = page.getByRole("textbox", { name: "The new folder's name" });
  await expect(name).toBeFocused();
  await name.fill("To read");
  await name.press("Enter");
  await cards
    .nth(1)
    .locator(".paper__grip")
    .dragTo(folders.getByRole("button", { name: /^To read/ }));
  await expect(folders.getByRole("button", { name: /^To read/ })).toHaveText(/1$/);
  // And in another too, from its menu: a paper is in as many folders as one likes (UX-45).
  await folders.getByRole("button", { name: "New folder" }).click();
  await page.getByRole("textbox", { name: "The new folder's name" }).fill("Later");
  await page.getByRole("textbox", { name: "The new folder's name" }).press("Enter");
  await cards.nth(1).getByRole("button", { name: "To read", exact: true }).click();
  await page.getByRole("checkbox", { name: "Later" }).check();
  await expect(cards.nth(1).getByRole("button", { name: "2 folders" })).toBeVisible();
  await expect(folders.getByRole("button", { name: /^To read/ })).toHaveText(/1$/);
  await expect(folders.getByRole("button", { name: /^Later/ })).toHaveText(/1$/);
  // Dragged onto All saved from a folder, it leaves that one only.
  await folders.getByRole("button", { name: /^Later/ }).click();
  await cards
    .nth(0)
    .locator(".paper__grip")
    .dragTo(folders.getByRole("button", { name: /^All saved/ }));
  await expect(folders.getByRole("button", { name: /^Later/ })).toHaveText(/0$/);
  await expect(folders.getByRole("button", { name: /^To read/ })).toHaveText(/1$/);
  expect(errors).toEqual([]);
});

test("a folder's link shows its papers, which the reading list then keeps (UX-46)", async ({
  page,
}) => {
  const errors = watchErrors(page);
  await page.goto(
    "./?view=reading-list#folder=Shared%20set&papers=2609.00002,1706.00001,2501.99999",
  );
  // Found in the site's data, a recent paper and an archived one; the other on arXiv.
  await expect(
    page.getByText("“Shared set”, a folder shared with you: 2 papers; 1 other is not in", {
      exact: false,
    }),
  ).toBeVisible();
  await expect(page.getByRole("link", { name: "2501.99999" })).toHaveAttribute(
    "href",
    "https://arxiv.org/abs/2501.99999",
  );
  await expect(page.locator("article.paper")).toHaveCount(2);
  // Another order keeps the link's fragment.
  await page.getByRole("button", { name: "Newest" }).click();
  await expect(page).toHaveURL(/sort=newest&view=reading-list#folder=Shared%20set&papers=/);
  await page.getByRole("button", { name: "Add to my reading list" }).click();
  await expect(page).toHaveURL(/folder=Shared\+set$/);
  await expect(page.getByText("2 papers in “Shared set”, 2 newly saved.")).toBeVisible();
  await expect(page.getByRole("link", { name: "Reading list (2)" })).toBeVisible();
  const folders = page.getByRole("navigation", { name: "Folders" });
  await expect(folders.getByRole("button", { name: /^Shared set 2$/ })).toBeVisible();
  // Its own Share copies the link again, the papers in the list's order.
  await page.context().grantPermissions(["clipboard-read", "clipboard-write"]);
  await folders.getByRole("button", { name: "Share", exact: true }).click();
  await expect(folders.getByRole("button", { name: "Link copied" })).toBeVisible();
  expect(await page.evaluate("navigator.clipboard.readText()")).toMatch(
    /\?view=reading-list#folder=Shared%20set&papers=2609\.00002,1706\.00001$/,
  );
  expect(errors).toEqual([]);
});

test("a paper the page cannot draw shows a message, not a blank page", async ({ page }) => {
  const errors = watchErrors(page);
  // A day whose first paper has no author list, which no card can draw.
  await page.route(DAY_FILE, async (route) => {
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
  await page.route(DAY_FILE, async (route) => {
    const response = await route.fetch();
    const day = await response.json();
    day.papers[0].authors = null;
    await route.fulfill({ response, json: day });
  });
  await page.goto("./?from=2026-09-24");
  await expect(page.getByText("1 of 1 cs.CV paper")).toBeVisible();
  await page.getByRole("button", { name: /^Period: / }).click();
  await page.getByRole("button", { name: "Last week" }).click();
  await expect(page.getByRole("alert")).toContainText("this view could not be displayed");
  await page.goBack();
  await expect(page.getByRole("alert")).toHaveCount(0);
  await expect(page.getByText("1 of 1 cs.CV paper")).toBeVisible();
});
