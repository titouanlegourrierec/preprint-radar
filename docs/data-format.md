# The data format

What `data/` holds, file by file and field by field, for anyone who reads it: the site,
a script, another project (DOC-10). The pipeline writes it (`store/paper_store.py`), the
site serves it, and `make validate` checks it against this contract (`store/validate.py`).
`tests/unit/test_data_format_doc.py` fails when a field of a record or a file of the store
is missing here.

## Where to read it

- The repository's `data/`, as the workflows commit it: once a weekday for the papers, on
  Sundays for the archive and the weekly counts.
- The site, which serves the same files under `data/`:
  `https://titouanlegourrierec.github.io/preprint-radar/data/index.json`,
  `…/data/cs.CV/2026-10-26.json`. Its files carry a few fields more, which the build
  merges in (below, [The site's additions](#the-sites-additions)), and files of its own
  (citation and search shards, feeds) that are not part of this format.

## Conventions

- Files are UTF-8 JSON objects. Each has `schema_version`, 1 today, and every file of a
  category its `category` ("cs.CV").
- A day is `YYYY-MM-DD`, a month `YYYY-MM`, a moment ISO 8601 in UTC to the second
  (`2026-10-25T06:44:27+00:00`). `generated_at` is when the file was written, `source` the
  services its values came from ("Semantic Scholar", "GitHub, Hugging Face").
- An arXiv id has no version: `2610.32977`.
- In a paper record, `null` means "not retrieved yet", which the pipeline tries again, and
  an empty list "tried, nothing found". An optional field is absent when unknown, or false
  for a flag.
- A paper is in one day file at most, that of the first day it was announced (a cross-list
  announced again later stays there). The archive and `top-recent.json` hold the cited
  papers, with the day file's record for one a day file holds.
- Files are rewritten whole. Readers should ignore fields and files they do not know: new
  ones come without notice (see [Versions](#versions)).

## Layout

```text
data/
├── index.json                    # what the store holds: days, archive years, counts
└── cs.CV/
    ├── 2026-10-26.json           # the papers announced that day (a rolling year)
    ├── archive/2017.json         # the most cited older papers, by year of first appearance
    ├── top-recent.json           # the 1,000 most cited papers of the last 12 months
    ├── citations.json            # Semantic Scholar's citation count of every stored paper
    ├── citation-gains.json       # what each gained in the last week
    ├── cohorts.json              # each year's papers as their citations rank them
    ├── scholar.json              # published versions: DOI, venue, author ids
    ├── code.json                 # the GitHub stars or Hub likes of the code papers link
    ├── countries.json            # the country of each institution, by ROR id
    ├── trends.json               # the topics of the titles that rise, cool or are new
    └── topics.json               # every topic's papers a month since 2010
```

## `index.json`

- `generated_at`.
- `categories`: for each category, its days, the newest first, each `{"date", "count"}`
  (the papers of that day file).
- `archives` (optional): for each category with an archive, its years, the newest first,
  each `{"year", "count"}`.
- `top_recent` (optional): for each category, `{"since", "count"}` of its `top-recent.json`.

## Papers

### Day files: `<category>/<YYYY-MM-DD>.json`

`{"schema_version", "category", "date", "papers": [record, …]}`: the papers arXiv announced
in the category that day, new submissions and cross-lists. A day
without announcement has no file. The store keeps a rolling year of days: older ones leave,
their most cited papers entering the archive. A day file changes after its day as its
papers are enriched (abstracts, affiliations, institutions) or read again by a newer
extraction.

### Archive: `<category>/archive/<YYYY>.json`

`{"schema_version", "category", "year", "papers": [record, …]}`: the papers kept for their
citations, by year of first appearance on arXiv, from 2010, rewritten each week. A paper
is kept when it ranks within a budget of the category's papers by citations per year of
age (22,000 for cs.CV, about 20 citations a year); withdrawn papers never are
([archive.md](archive.md)). Its `announced` is its first appearance. A paper that entered
from a day file keeps that record; one built from arXiv's catalog has its affiliations and
institutions from OpenAlex, and no `html_url` unless its page was read for affiliations
OpenAlex lacked.

### `<category>/top-recent.json`

`{"schema_version", "category", "since", "papers": [record, …]}`: the 1,000 most cited
papers first announced from `since` (the last 12 months), by citations per month of age,
rewritten each week. Those of the day files are their records there.

### The paper record

| Field | Type | Meaning |
|---|---|---|
| `arxiv_id` | string | Its arXiv id, without version. |
| `announced` | day | The day arXiv first announced it in the category. |
| `title` | string | Its title, LaTeX markup kept as written (`$^2$`). |
| `authors` | strings | Its authors' names, in order. |
| `primary_subject` | string or `null` | Its primary subject: "Computer Vision and Pattern Recognition (cs.CV)". |
| `subjects` | strings | All its subjects, the primary one included. |
| `comments` | string or `null` | The authors' comments: venue, pages, project page. |
| `journal_ref` | string or `null` | The journal reference its authors gave. |
| `venue` | string or `null` | The venue its comments say it was accepted at ("CVPR 2026"), workshops named as such. |
| `cross_list_from` | string or `null` | The category it is cross-listed from, when it is a cross-list. |
| `html_url` | string or `null` | Its HTML rendering on arXiv, when there is one: where its affiliations were read. |
| `abstract` | string or `null` | Its abstract as plain text, arXiv's LaTeX made readable: a formula still holding markup keeps its dollars. |
| `affiliations` | strings or `null` | Its authors' affiliations, deduplicated, as written: never an e-mail nor a URL. |
| `author_affiliations` | lists or `null` | For each author, the indices of their own affiliations in `affiliations`; `null` for an author the page does not place, and altogether when it places none. |
| `institutions` | strings or `null` | Parallel to `affiliations`: the institution each belongs to (ROR's name, OpenAlex's in the archive, a company's subsidiaries as the company), `null` for one that names none. |
| `institution_ids` | strings (optional) | Parallel to `institutions`: the ROR id of each ("00f54p054"), `null` without one. |
| `extractor` | number (optional) | The version of the HTML extraction that read the affiliations. |
| `withdrawn` | `true` (optional) | Its comments say its authors or arXiv withdrew it. |
| `provenance` | object (optional) | Where `affiliations` came from and who named `institutions`, each `{"source", "at"}`: a source (`html`, `api` or `openalex` for affiliations; `ror` or `openalex` for institutions) and the day it was read, absent for older records. |
| `abs_url` | string | Its abstract page on arXiv. |
| `pdf_url` | string | Its PDF on arXiv. |

A record holding `author_affiliations` has one entry per author; one holding `institutions`
has one per affiliation, and so do its `institution_ids`. New affiliations reset the
institutions, their ids and their provenance to `null`, until they are named again.

### The site's additions

The site's day, archive and top-recent files add, from the weekly files below:

- `doi`: the DOI of its published version, from `scholar.json`.
- `author_ids`: Semantic Scholar's id of each author, from `scholar.json`, `null` for one
  whose name there is not the paper's at that place.
- `venue`: its published venue from `scholar.json` where its comments name none.
- `code`: the stars of the code it links, from `code.json`, where the link is still the
  one it gives.

Its `index.json` adds `versions`, a hash of each data file that the site asks for with it,
and `cohorts`, each category's `cohorts.json`.

## Counts and published versions

### `<category>/citations.json`

`{"schema_version", "category", "generated_at", "source", "counts": {arxiv_id: count}}`:
Semantic Scholar's citations of every stored paper (day files, archive and top-recent),
all versions counted. A paper it does not know yet (its first days) has none. The weekly
archive rewrites the file, dated; the daily run adds the new papers' counts, keeping the
date, which can postdate some counts by up to 6 days.

### `<category>/citation-gains.json`

`{"schema_version", "category", "since", "generated_at", "source", "gains": {arxiv_id:
gained}}`: the citations each paper gained between the counts of `since` and those of
`generated_at`, the last two weekly refreshes. Only papers that gained are listed.

### `<category>/cohorts.json`

`{"schema_version", "category", "generated_at", "source", "years": {YYYY: cohort}}`: for
each complete year since 2010, the category's papers of that year as their citations rank
them: `papers`, their number, and `top_1`, `top_5`, `top_10`, the citations of the last of
the most cited 1%, 5% and 10%. A paper of 2017 cited at least `top_1` times is in its
year's top 1%.

### `<category>/scholar.json`

`{"schema_version", "category", "generated_at", "source", "papers": {arxiv_id: record}}`:
what Semantic Scholar knows of every stored paper's published version, each field absent
when unknown:

- `doi`: the DOI of its published version (never arXiv's `10.48550/…`).
- `venue`: where it was published, named as the comments' venues are ("CVPR 2018",
  "Information Fusion 2024").
- `author_ids`: Semantic Scholar's id of each author, in order, `null` for one whose name
  there is not the paper's at that place; absent when its author list is not the paper's.

### `<category>/code.json`

`{"schema_version", "category", "generated_at", "since", "source", "papers": {arxiv_id:
record}}`, for each stored paper linking code, weekly:

- `url`: the link the paper gives, as its card shows it.
- `stars`: the stars of its GitHub repository, or `likes`: those of its Hugging Face page.
- `gained` (optional): the stars it gained since the refresh of `since`.
- `shared` (optional): the stars are not the paper's alone (other stored papers link the
  same repository, or it links a folder of one).

### `<category>/countries.json`

`{"schema_version", "category", "generated_at", "source", "institutions": {ror_id:
country}}`: the country of each institution the stored papers name, by its ROR id, from
OpenAlex: an ISO 3166-1 alpha-2 code ("US"), or `null` where OpenAlex places it nowhere.

## Topics

`trends.json` and `topics.json` hold the topics of the category's titles since 2010,
written each week; [trends.md](trends.md) says how they are counted.

### `<category>/trends.json`

`{"schema_version", "category", "generated_at", "source", "through", "start", "totals",
"windows", "topics"}`:

- `through`: the last day counted; `start`: the first month of `totals` and of each
  topic's `counts`, 37 months; `totals`: the category's papers each month.
- `windows`: `quarter` (the last 90 days against the same days a year before) and `year`
  (the last 365 days against the 365 before), each `{"days", "earlier", "recent",
  "papers", "rising", "cooling", "new", "added"}`: its two periods (first and last day), their
  papers, the keys of the topics of its three lists in order, and the share of the papers
  added to both of a topic's shares in its lift, which orders the lists:
  `(recent share + added) / (earlier share + added)`.
- `topics`: the topics the lists name, by key (lower case, the last word singular: "world
  model"), each `{"name", "counts", "windows", "first", "impact", "papers", "also"}`: its
  name as titles write it, with its acronym ("vision-language-action (VLA)"); its papers
  each month; its papers in each window's two periods; the first month three of its papers
  appeared in, or `null`; its impact, the share of its papers of 3 to 15 months before the
  last among the most cited tenth of their month (`null` with too few, or without counts);
  its three most cited papers of the last 12 months, each `{"id", "title", "citations"}`;
  and, optional, `also`, the keys of the other phrases it holds ("vla").

### `<category>/topics.json`

`{"schema_version", "category", "generated_at", "source", "through", "start", "totals",
"topics"}`, from January 2010: every topic of the titles, words alone too, by key, each
`{"name", "start", "counts", "also"}`: `start`, the index of its first month with a paper
among the file's months, and `counts`, its papers each month from that one to `through`;
`also` as above.

## Versions

`schema_version` is the format's version, 1 since the first file. A change that breaks a
reader of this page (a field removed, renamed or retyped, a meaning changed, a file moved)
raises it, in the same commit as the migration of every file, and is announced in the
[changelog](../CHANGELOG.md); the pipeline refuses a file of another version. Adding an
optional field or a file changes nothing: `institution_ids`, `provenance`, `withdrawn` and
`also` came that way. From release 1.0.0, a change that raises `schema_version` also
raises the project's major version.

## Licenses

The code is MIT; the data keeps its sources' terms (the README's
[Licenses](../README.md#licenses)): arXiv's metadata (titles, authors, abstracts,
comments) is CC0, each paper keeping the license its authors chose; ROR's and OpenAlex's
institutions and countries are CC0; citation counts, published versions and author ids
come from the Semantic Scholar API under its license agreement; stars and likes from
GitHub and the Hugging Face Hub.
