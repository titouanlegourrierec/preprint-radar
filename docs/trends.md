# Trends: the topics of the titles

How `trends.py` finds the topics of a category's papers, which rise, which cool, which are
new (PROD-20), and what `trends.json` and `topics.json` hold for the site. Read this
before changing `trends.py`, the `trends` command or those files. The failures and what to
do about them are in [operations.md](operations.md).

## Where it runs

`make trends` (`preprint-radar trends`), offline, under a minute: a step of `archive.yml`
after the archive, whose catalog (`.cache/catalog/<category>.jsonl.gz`, every paper of the
category since 2010 with its title) it reads, with the citation counts the archive cached
(`<category>.citations.jsonl`, valid 7 days). It writes both files whole each week. Without
the counts, the topics are counted without their impact and key papers, and the files say
their source is `arXiv` alone.

## Topics (`title_phrases`)

- Titles only: a title says what a paper is about, where an abstract also names its tools,
  datasets and baselines. Measured on 2026-10-21, the titles' topics counted where either
  the title or the abstract says them: a paper of the last 90 days has 9.4 topics instead
  of 2.1, and tools grow the most, CLIP from 33 to 511 papers, NeRF from 3 to 43, segment
  anything model from 2 to 40, against world model from 213 to 359. CLIP then rises
  (×1.24) where its titles cool (−31%): papers use it more, fewer are about it. The lists
  keep 9 of their 25 rising topics, 1 of their 25 cooling (which become the abstracts'
  style: "loss function", "network architecture", "simple yet effective"), and 4 new
  topics of 7, a phrase being written in abstracts before titles. A vocabulary of the
  abstracts' own phrases leads with "state of the art", "extensive experiments" and "code
  is available". The abstracts' pass took 41 s on 8 cores.
- A topic is a phrase of a title, one to four words and six parts at most once hyphens
  split them ("vision-language-action model" is two words, four parts). A phrase starts and
  ends with a whole word, so "Semi-Supervised Medical Image Segmentation" never says
  "supervised medical image", and stops at punctuation (`_BREAK_RE`: colons, commas,
  brackets, quotes, a dash between spaces): "VLMs Are Blind: Rethinking NeRF" never says
  "blind rethinking".
- A phrase neither starts nor ends with a function word ("for", "with"), nor ends with a
  modifier ("aware", "guided", "based": "geometry-aware" qualifies a topic) or a field's
  acronym ("feed-forward 3D" is a cut of "feed-forward 3D reconstruction"), nor holds a
  year; and it is not made of generic words ("efficient", "learning", "model", "survey",
  `_GENERIC`), function words and modifiers alone: "Deep Neural Networks for Large-Scale
  Datasets" says nothing. Each word is taken as written and singular.
- It is keyed by its lower-case words, the last one singular (`_singular`, which leaves
  alone what only looks plural: "series", "robotics", "bias", "lens"), and named as titles
  most often write it: an acronym keeps its capitals and loses its plural ("VLMs" is
  "VLM"), a short word in capitals stays so ("3D"), the rest is lower case.
- An acronym has two capitals or more and ten characters at most ("NeRF", "VLA", "3DGS"); a
  word of a title in capitals ("BENCHMARK") is none.
- A word alone is a topic of the lists only as an acronym: titles write too many words
  alone that name none ("evidence", "frozen", "advancing"), which filled half of each list
  when tried. The explorer has every word that is not generic ("mamba", "transformer").
- The vocabulary is the topics at least 0.015% of the papers say (`VOCABULARY_SHARE`), 5 at
  least: 32 papers for cs.CV's 210,010 since 2010, 6,635 phrases, 3,024 of them words alone.

## Synonyms (`topic_groups`)

A topic holds the phrases of the vocabulary that say the same, and a paper whose title says
any of them counts once for it. Without them a style was a trend: "VLM" rose in the 90 days
(77 → 162) while "vision-language model" held, and "multi-modal" cooled (115 → 62) as
"multimodal" took its place. Three rules, measured on the catalog of 2026-10-21, make 103
topics of two phrases or more, 47 of them with their acronym (6,528 topics in all):

- Spellings, the phrases the same once their spaces go: "multi-modal" and "multimodal",
  "real-time" and "realtime", "pre-training" and "pretraining", "U-Net" and "UNet", "6-DoF"
  and "6DoF".
- A phrase ending with "modeling" or "modelling" and the same with "model": "world
  modeling" is "world model", the field naming the models it builds. No other "-ing" is its
  base: "medical imaging" is not "medical image", nor "tracking" "track", nor "matching"
  "match", which a general rule merged when tried.
- An acronym and the phrase its abstracts define it as (`acronym_definitions`): in each
  abstract, the words before an acronym in parentheses, its plural "s" apart ("large language
  models (LLMs)"), within the same sentence, ending with the shortest run of them whose
  characters hold the acronym's in order, the first starting a word (Schwartz and Hearst,
  2003): "Vision-Language-Action (VLA)" is "vision-language-action". An abstract counts once
  an acronym. The acronym joins the phrase when at least 10 abstracts define it
  (`DEFINITIONS_MIN`), 60% of those that do (`DEFINITION_SHARE`), and the phrase is a topic
  of the titles: MRI, CNN, GAN, LLM, VLM, MLLM, NeRF, ViT, LoRA, VLA, BEV, RAG, 3DGS join
  theirs; "AR" (augmented reality 272 times, autoregressive 238), "CAD", "QA" and "ROI" join
  none.

A topic is keyed and named by its phrase that most titles say, an acronym alone only when it
has no other, with the acronym it holds the most said: "vision-language-action (VLA)",
"large language model (LLM)", while "U-Net" holds "UNet" without naming it. Its `also` lists
the keys of its other phrases, for the site: its search (`"vision language action" OR …
OR "vla" OR "vlas"`), its note, its explorer, and the links of older weeks. A topic is
ranked when one of its phrases is: "multimodal", a word alone, is because "multi-modal" is a
phrase.

## Rising, cooling and new (`trends.json`)

- Two windows (`WINDOWS`) compare a topic's share of the papers in two periods: `quarter`,
  the last 90 days against the same days a year before, which the conferences' seasons do
  not bias, and `year`, the last 365 days against the 365 before. A paper counts on the
  day it first appeared (`CatalogEntry.first_seen`), cross-lists included.
- A topic is ranked with at least 0.3% of the recent period's papers in the quarter (31 of
  10,476) and 0.15% in the year (59 of 39,330), 10 at least (`RANK_MIN`): the thresholds
  scale with the category.
- Its lift is `(now + a) / (then + a)`, its two shares with the share `a` of a few papers
  of the recent period added to each (a third of the minimum, 3 at least: 10 of 10,476 in
  the quarter), so that one paper becoming six does not lead, and a share that holds lifts
  by exactly 1. A topic rises with a lift above 1, the highest first, and cools below 1,
  the lowest first: a small category lists fewer than 25 (`LIST_SIZE`) rather than
  topics going the other way. Each window writes the share it added (`added`), so that the
  site says the lift that orders its lists, not the bare ratio, which would not follow it.
- New: a topic whose first month with 3 of its papers (`FIRST_PAPERS`) is within the last
  12, with half the minimum in the recent period; the most papers first, 15 at most.
- One phrase a topic (`_distinct`): two phrases sharing half their papers, of those either
  has, are one topic, and so are two one of which holds 80% of its papers in the other,
  being 40% of it (`NESTED`, `NESTED_SHARE`: "visual token pruning", 63 papers of the year,
  within "token pruning"'s 140). The more specific names it in the place of the first, even
  when ranked past the list's end: "visual token pruning" over "visual token" and "token
  pruning". A topic holding an acronym is the most specific: "vision-language-action (VLA)"
  over "vision-language-action model", which it holds.
- Each listed topic keeps its counts of the last 37 months (`MONTHS`, the file's `start`
  and `totals`), its papers in each window's two periods, its first month, its impact and
  its key papers:
  - The impact is the share of its papers of 3 to 15 months before the last month (old
    enough to be cited, recent enough to be the topic as it is now) that are among the most
    cited tenth of their own month, never-cited papers never among them; with 20 such
    papers at least (`IMPACT_MIN_PAPERS`), else none.
  - The key papers are its three most cited of the last 12 months, cited at least once.

## The explorer (`topics.json`)

Every topic of the vocabulary, its papers a month from its first since 2010 (`start`, an
index of the file's months), with the category's papers a month (`totals`), for the
site's explorer: a share of the papers, not a count, compares 2015 with 2026, cs.CV having
grown from about 25 papers a month in 2010 to 3,300 in 2026. One topic a line, compact: 2.3 MB,
400 KB gzipped, which the site loads only when the explorer opens; `trends.json` is 59 KB,
17 KB gzipped.

## Calibration on cs.CV (2026-10-21)

The catalog to 2026-10-20, the counts of the archive run that day, before synonyms (the last
item for what they changed).

- The quarter, 2026-07-23 to 2026-10-20 (10,476 papers) against 2025-07-23 to 2025-10-20
  (8,841):
  - Rising: world action model 0 → 67 (impact 92%), world model 32 → 213 (54%), video
    world model 1 → 42 (76%), long-horizon 7 → 62, streaming video 5 → 39, visual
    evidence 3 → 31, autoregressive video 4 → 34, self-distillation 5 → 36, world modeling
    8 → 45, visual token pruning 5 → 34, VLA 9 → 47, feed-forward 17 → 71, flow matching
    35 → 96, video generation 82 → 180, VLM 77 → 162.
  - Cooling: feature fusion 31 → 7, semi-supervised 68 → 25 (impact 4%), diffusion model
    266 → 125, transfer learning 31 → 13, multi-modal 115 → 62, data augmentation 32 → 14,
    continual learning 37 → 17, domain adaptation 49 → 28, CNN 44 → 25, knowledge
    distillation 48 → 30.
  - New: world action model (first month 2026-05), video world model (2025-12), visual
    evidence, self-evolving, latent world, streaming video understanding, autoregressive
    video generation.
- The year, 39,330 papers against 34,563: VLA 16 → 118, audio-video 9 → 63, spatial
  intelligence 16 → 62 rise; segment anything model 78 → 27, convolutional neural network
  114 → 48, diffusion model 1,239 → 723, state space model 123 → 75, radiance field 90 →
  57, contrastive learning 204 → 141 cool.
- The impact goes from 92% (world action model) to 2% (action recognition, domain
  generalization) and 0% (image-text). The key papers of "world model": Motus (2512.13030,
  335 citations), Cosmos 3 (2606.02800, 184), DreamDojo (2602.06949, 154).
- The explorer: Mamba, 465 papers since January 2024, peaked in March 2025 (25) and has
  128 in the last 12 months against 186 the 12 before; NeRF peaked in March 2023 (18), 15
  against 40; GAN in March 2021 (29); "world model" has 522 against 129.
- 40 seconds for the 210,010 titles.
- With synonyms (2026-10-27, the same catalog), 38 seconds, the abstracts' definitions
  included. World model, its "modeling" with it, is 40 → 258 in the quarter; VLA, with
  "vision-language-action", 48 → 138 (impact 61%), 106 → 403 in the year. The quarter's
  rising list loses VLM, which a style made rise, its cooling list "multi-modal", which a
  spelling made cool; "unmanned aerial vehicle (UAV)" and "computed tomography (CT)" rise,
  "large language model (LLM)" (244 → 165) and "multimodal large language model (MLLM)"
  cool, and "segment anything model (SAM)", "neural radiance field (NeRF)" and "generative
  adversarial network (GAN)" in the year.

## What it does not do

- Synonyms the rules miss stay topics of their own: an acronym two meanings share ("AR"),
  one too few abstracts define, a word and its "-ing" ("detector", "detection").
- An acronym ending with a capital S is keyed as a plural, as any last word: "3DGS" is
  "3dg", and "SDS" (score distillation sampling) is "SD" (stable diffusion), whose
  definitions then share no 60% and join neither.
- A title's possessive is two words: "bird's-eye view" is "bird s eye view" (`_WORD_RE`).
- A word alone that is no acronym never rises in the lists, however new ("Mamba" in 2024):
  the explorer shows it.
