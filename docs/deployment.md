# Deploying your own copy

The workflows run the pipeline and publish the site on GitHub Pages; a copy of the
repository can follow other arXiv categories. The site and all of `data/` are public,
authors and affiliations included, even from a private repository.

A GitHub fork never runs the data workflows on schedule, so that turning its Actions on
does not crawl arXiv daily: only runs started by hand or dispatched go on. For daily runs,
push a copy instead.

1. Push the repository to GitHub.
2. In *Settings → Pages*, set *Source* to **GitHub Actions**.
3. In *Settings → Secrets and variables → Actions → Variables*, optionally set:
   - `PREPRINT_RADAR_CATEGORIES`: space-separated categories (default `cs.CV`);
   - `PREPRINT_RADAR_CONTACT`: your e-mail address, sent to arXiv in the User-Agent
     (default: the repository's URL);
   - `PREPRINT_RADAR_ARCHIVE_BUDGET`: how many papers older than 12 months the archive keeps
     per category (default 22000);
   - `PREPRINT_RADAR_ARCHIVE_PRUNE`: `true` to delete day files older than 12 months, for a
     rolling year of them (default `false`).

   Under *Secrets*, optionally set `SEMANTIC_SCHOLAR_API_KEY`, a free
   [Semantic Scholar API key](https://www.semanticscholar.org/product/api): without it the
   weekly archive takes hours instead of about 40 minutes.
4. Run *Update data* once by hand (*Actions → Update data → Run workflow*). A first run reads
   at most 600 HTML pages, one every 15 s (about 2.5 hours); later runs read the rest, and
   a daily run then takes about 40 minutes. Its *since* field (YYYY-MM-DD) collects older
   days instead.
5. Run *Archive* once by hand too, or *Highly cited* and *Trends* stay empty until Sunday.
   Its first run harvests arXiv's catalog (about 45 minutes) before the citation counts.
6. For runs on time, have an outside scheduler dispatch both workflows: GitHub starts
   scheduled runs hours late, so their own schedules are fallbacks four hours later
   ([operations.md](operations.md#the-outside-scheduler)).

*Update data* then runs every weekday and *Archive* every Sunday; each commits its data
and redeploys the site. *Deploy site* also runs on every push to `web/` or `data/`.
