/**
 * Smoke test of the built site: the four things a broken deploy would break first. Run with
 * `npm run test:e2e` (or `make test-e2e`); `playwright.config.ts` builds and serves it.
 */
import { readFileSync } from "node:fs";
import { expect, type Page, test } from "@playwright/test";
import { CONTENT_SECURITY_POLICY } from "../tooling/content-security-policy";

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
  await page.locator(".period-picker__trigger").click();
  await page.getByRole("button", { name: "Keep adding new days" }).click();
  // The link no longer ends on 25 September: tomorrow's papers will join it (PROD-13).
  await expect(page).toHaveURL(/\?since=2026-09-24$/);
  await expect(page.locator(".period-picker__trigger")).toContainText("Since");
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
});

test("a day that fails to load is asked for again, then left out with a notice", async ({
  page,
}) => {
  const errors = watchErrors(page);
  // The latest day's first request is dropped, and answered the second time (SRCH-10).
  let dropped = false;
  await page.route("**/data/cs.CV/2026-09-25.json", async (route) => {
    if (dropped) return route.fallback();
    dropped = true;
    return route.abort("connectionreset");
  });
  // The older day's month fails until Retry.
  let shardDown = true;
  await page.route("**/data/cs.CV/search/2026-09.json", (route) =>
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

test("a card shows the stars of its code, and Most starred ranks by them", async ({ page }) => {
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
  await expect(page.getByText("4 of 4 cs.CV papers")).toBeVisible();
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
  expect(await page.evaluate("window.refused")).toEqual([]);
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
  await expect(
    page.getByRole("table", { name: "Institutions of the papers shown, by papers" }),
  ).toBeVisible();
  await expect(page.getByText(/in these 4 papers/)).toBeVisible();
  // Authors by citations, in the link, which opens them again (SRCH-13).
  await page.getByRole("button", { name: "Authors", exact: true }).click();
  await page.getByRole("button", { name: "Citations", exact: true }).click();
  await expect(page).toHaveURL(/\?view=rankings&rank=author&metric=citations$/);
  await page.reload();
  await expect(
    page.getByRole("table", { name: "Authors of the papers shown, by citations" }),
  ).toBeVisible();
  await expect(page.getByRole("rowheader").first()).toBeVisible();
  expect(errors).toEqual([]);
});

test("Rankings maps the countries of the papers shown", async ({ page }) => {
  const errors = watchErrors(page);
  await page.goto("./?view=rankings");
  // The sidebar's card opens the map, loaded then (UX-41).
  await page.getByRole("button", { name: /^World map/ }).click();
  await expect(page).toHaveURL(/rank=country/);
  await expect(page.getByRole("img", { name: /^World map of the countries/ })).toBeVisible();
  // A paper of two countries counts half for each.
  const table = page.getByRole("table", { name: "The countries of the papers shown, by papers" });
  await expect(table.getByRole("row", { name: /United Kingdom 1\.5/ })).toBeVisible();
  await expect(table.getByRole("row", { name: /United States of America 1\.5/ })).toBeVisible();
  // A country of the table is shown on the map.
  await table.getByRole("button", { name: "United Kingdom" }).click();
  await expect(page.locator('.world-map__shape--pinned[data-code="GB"]')).toHaveCount(1);
  await page.getByRole("button", { name: "Per million people" }).click();
  await expect(page).toHaveURL(/metric=per-million/);
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
  await page.getByRole("combobox", { name: "Folder" }).first().selectOption("To read");
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
  // Deleted, its papers stay saved.
  await folders.getByRole("button", { name: "Delete" }).click();
  await folders.getByRole("button", { name: "Delete" }).click();
  await expect(page.getByText("2 of 2 saved papers")).toBeVisible();
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
  await expect(cards.nth(1).getByRole("combobox", { name: "Folder" })).toHaveValue("To read");
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
