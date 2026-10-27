# Trends: the topics of the titles

How `trends.py` finds the topics of a category's titles, which rise, cool or are new
(PROD-20), and what `trends.json` and `topics.json` hold ([data-format.md](data-format.md)
has their fields).

## Where it runs

`make trends`, offline, under a minute: a step of `archive.yml` after the archive. It reads
the archive's catalog (`.cache/catalog/<category>.jsonl.gz`, every paper since 2010) and
the citation counts it cached (valid 7 days), and rewrites both files. Without the counts,
the topics have no impact nor key papers, and the files' source is `arXiv` alone.

## Topics (`title_phrases`)

- **Titles only.** A title says what a paper is about; an abstract also names its tools,
  datasets and baselines. Counted in abstracts too, a paper has 9.4 topics instead of 2.1,
  CLIP rises while fewer papers are about it, and the vocabulary leads with "state of the
  art" and "extensive experiments".
- **A phrase** is one to four words of a title, six parts at most once hyphens split them
  ("vision-language-action model": two words, four parts). It starts and ends with a whole
  word ("Semi-Supervised Medical Image Segmentation" never says "supervised medical
  image") and stops at punctuation (`_BREAK_RE`).
- It neither starts nor ends with a function word ("for"), nor ends with a modifier
  ("aware", "guided", "based") or a field's acronym ("feed-forward 3D"), nor holds a year,
  nor is made of generic words alone (`_GENERIC`: "efficient", "learning", "model").
- **Its key** is its lower-case words, the last one singular (`_singular`, which leaves
  "series", "robotics", "bias", "lens" alone). An acronym loses a plural's lower-case "s"
  only ("VLMs" is "vlm", "3DGS" and "MOTS" stay). The site keys a search the same way,
  both languages reading `tests/fixtures/singular-cases.json`.
- **Its name** is how titles most often write it: an acronym keeps its capitals, a short
  word in capitals stays so ("3D"), the rest is lower case. An acronym has two capitals or
  more and ten characters at most ("NeRF", "3DGS"); "BENCHMARK" is none.
- **A word alone** is listed only as an acronym: words alone that name nothing
  ("evidence", "advancing") filled half of each list when tried. The explorer has them all.
- **The vocabulary** is the phrases at least 0.015% of the papers say (`VOCABULARY_SHARE`),
  5 at least: 32 papers for cs.CV's 210,010, about 6,600 phrases.

## Synonyms (`topic_groups`)

A topic holds the phrases that say the same, and a paper counts once for it; otherwise a
spelling is a trend ("VLM" rose while "vision-language model" held). Three rules, which
make about 100 topics of two phrases or more for cs.CV:

- **Spellings**: phrases equal once their spaces go ("multi-modal", "multimodal"; "U-Net",
  "UNet").
- **"-modeling"**: "world modeling" is "world model". No other "-ing" is its base:
  "imaging" is not "image", nor "tracking" "track".
- **Acronyms** (`acronym_definitions`): in each abstract, the words before an acronym in
  parentheses, in the same sentence, ending with the shortest run whose characters hold
  the acronym's in order, the first starting a word (Schwartz and Hearst, 2003):
  "Vision-Language-Action (VLA)" defines "vision-language-action". An abstract counts once
  an acronym. The acronym joins the phrase when at least 10 abstracts define it
  (`DEFINITIONS_MIN`), 60% of those that do (`DEFINITION_SHARE`), and the phrase is in the
  vocabulary: LLM, CNN, NeRF, VLA or 3DGS join theirs; "AR" (augmented reality 272 times,
  autoregressive 238) joins none.

A topic is keyed and named by its phrase that most titles say, an acronym alone only
without another, and shows the acronym it holds: "vision-language-action (VLA)". Its
`also` lists its other keys, which the site's search, note and explorer accept, as do the
links of older weeks. A topic is listed when one of its phrases would be.

## Rising, cooling and new (`trends.json`)

- **Windows** (`WINDOWS`): `quarter`, the last 90 days against the same days a year
  before, which the conferences' seasons do not bias; `year`, the last 365 days against
  the 365 before. A paper counts on the day it first appeared, cross-lists included.
- **Ranked** with at least 0.3% of the recent period's papers in the quarter and 0.15% in
  the year, 10 at least (`RANK_MIN`), so that the thresholds follow the category's size.
- **Lift**: `(recent share + added) / (earlier share + added)`, `added` being the share of
  a few papers (a third of the minimum, 3 at least), so that one paper becoming six does
  not lead and a share that holds lifts by exactly 1. A topic rises above 1, the highest
  first, and cools below 1, the lowest first, 25 at most (`LIST_SIZE`). Each window writes
  its `added`, so that the site shows the figure that orders its lists.
- **New**: a topic whose first month with 3 papers (`FIRST_PAPERS`) is within the last 12,
  with half the minimum in the recent period; the most papers first, 15 at most.
- **One phrase a topic** (`_distinct`): two phrases sharing half the papers either has, or
  one holding 80% of its papers in the other while being 40% of it (`NESTED`,
  `NESTED_SHARE`), are one topic, named by the more specific in the place of the first:
  "visual token pruning" over "visual token" and "token pruning". A topic holding an
  acronym is the most specific.
- **Each listed topic** keeps its counts of the last 37 months (`MONTHS`), its papers in
  each period, its first month, its impact and its key papers:
  - impact: the share of its papers of 3 to 15 months before the last month that are
    among the most cited tenth of their month, with 20 such papers at least
    (`IMPACT_MIN_PAPERS`); 10% is an average topic;
  - key papers: its three most cited of the last 12 months, cited at least once.

## The explorer (`topics.json`)

Every topic of the vocabulary, its papers a month since 2010, with the category's papers
a month: the explorer draws a share of the papers, not a count, since cs.CV grew from
about 25 papers a month in 2010 to 3,300 in 2026. One topic a line: 2.3 MB, 400 KB
gzipped, loaded only when the explorer opens. `trends.json` is about 60 KB.

## Calibration on cs.CV

On the catalog to 2026-10-20 (about 40 seconds):

- Rising over 90 days: world action model 0 → 67 papers (impact 92%), world model 40 →
  258, VLA 48 → 138; cooling: feature fusion 31 → 7, semi-supervised 68 → 25 (impact 4%),
  diffusion model 266 → 125. Over the year, segment anything model, convolutional neural
  networks and NeRF cool.
- Impacts range from 92% (world action model) to 2% (action recognition).
- The explorer: Mamba peaked in March 2025, NeRF in March 2023, GAN in March 2021.

## Limits

- Synonyms the rules miss stay apart: an acronym with two meanings ("AR"), one too few
  abstracts define, a word and its "-ing" ("detector", "detection").
- A possessive is two words: "bird's-eye view" is "bird s eye view" (`_WORD_RE`).
- A word alone that is no acronym never enters the lists, however new ("Mamba" in 2024):
  the explorer shows it.
