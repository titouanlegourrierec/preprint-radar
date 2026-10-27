# Contributing

Thank you for helping. Preprint Radar is maintained by one person, so small, focused
contributions are the easiest to take.

## Issues

- **Bug**: something on the site or in the pipeline that does not work. A link to the site
  in the state where it happens helps most: the search, the view and the period are all in
  it.
- **Wrong data**: an affiliation, institution, venue or code link that a paper's own page
  contradicts. Give its arXiv identifier.
- **Idea**: a need first, a way to meet it if you have one.

Data about you (your name, your affiliation, a paper of yours to remove) is better written
to the contact on the site's About page than in a public issue. Report a vulnerability
privately, as [SECURITY.md](../SECURITY.md) says.

## Pull requests

1. Open an issue first for anything larger than a fix, so that we agree on the approach.
2. Set up the project ([development.md](development.md)) and keep the change to one thing.
3. Add tests for the new behavior, and update the docs that describe it.
4. Run `make check`; CI runs the same, then the smoke test of the built site.
5. Add an entry under `## Unreleased` in `CHANGELOG.md` if a user would notice the change.

`data/` is written by the pipeline: change the code that writes it rather than the files.
A change to how affiliations are read comes with the real page that needs it, as a fixture
([extraction.md](extraction.md)).

Contributions are under the project's [MIT license](../LICENSE).
