# Security

Preprint Radar is a static site on GitHub Pages, built from a pipeline that GitHub Actions
runs: there is no server, no account and no cookie, and what a reader keeps (reading list,
saved searches, settings) stays in their browser.

## Reporting a vulnerability

Write to [titouanlegourrierec@kaist.ac.kr](mailto:titouanlegourrierec@kaist.ac.kr), the
contact of the site's About page, with what you found and how to reproduce it, rather than
in public.

What counts: anything that lets the site run a script or load something it should not (the
titles, abstracts and links it shows come from arXiv and other services; a reading list can
be imported and a folder opened from a link), a way into the workflows or the secrets they
hold, or the data they publish being altered.

The site is always the latest `main`; fixes go there, and into the next release.

## Wrong data

A wrong affiliation or author, or a paper of yours you would like removed, is not a security
issue: write to the same address with its arXiv identifier, as About says, or, for data
that is not about you, open a *Wrong data* issue.
