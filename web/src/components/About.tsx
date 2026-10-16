import { CONTACT_EMAIL, reportLink } from "../report";

const CORRECTION_LINK = reportLink();

/** What the site is, where its data comes from, how to get it corrected, and privacy. */
export function About() {
  // Whether this build counts visits (UX-47): its page then holds Cloudflare's script.
  const counted = document.querySelector("script[data-cf-beacon]") !== null;
  return (
    <main class="about" id="main">
      <h2>About Preprint Radar</h2>
      <p>
        Preprint Radar follows the papers announced on arXiv in Computer Vision and Pattern
        Recognition (cs.CV) every weekday, and keeps the most cited older ones. It lets you search
        them, and see who wrote them and where. It is a personal project, not affiliated with arXiv.
      </p>

      <h3>Where the data comes from</h3>
      <ul>
        <li>Titles, authors, abstracts and dates: arXiv's listings, refreshed every weekday.</li>
        <li>
          Affiliations: as declared by the submitter, or read automatically from the HTML version of
          the paper. This is best effort: some are missing, and some can be wrong, such as a name
          read as an institution, or an author placed at a co-author's institution.
        </li>
        <li>
          Institutions: matched with the{" "}
          <a href="https://ror.org">Research Organization Registry</a>, or named by rules of our own
          where it has no match (acronyms, companies, the main part of an address).
        </li>
        <li>
          Venues: read in the authors' comments ("Accepted to ECCV 2026"), else where the paper was
          published according to <a href="https://www.semanticscholar.org">Semantic Scholar</a>,
          which also gives the DOI of the published version, refreshed every week.
        </li>
        <li>
          Highly cited papers: chosen every week by citations per year of age, from the counts of{" "}
          <a href="https://www.semanticscholar.org">Semantic Scholar</a>, and, for the last 12
          months, by citations per month of age. Their affiliations come from{" "}
          <a href="https://openalex.org">OpenAlex</a>, for the paper or its published version, else
          from the HTML version of the paper. A paper its authors withdrew from arXiv is never among
          them, and is marked Withdrawn elsewhere.
        </li>
        <li>
          Code: the repository, or the models, data or demo on Hugging Face, that a paper links in
          its abstract or comments, with its stars on <a href="https://github.com">GitHub</a> (likes
          on <a href="https://huggingface.co">Hugging Face</a>), refreshed every week. A repository
          other papers link too, or a folder of a larger one, is marked shared: its stars are not
          the paper's alone, and Most starred ranks it last.
        </li>
        <li>
          Countries, on the world map of Rankings: those of the institutions, as{" "}
          <a href="https://openalex.org">OpenAlex</a> places them, refreshed every weekday; a paper
          of several countries counts a share for each. The map and populations are{" "}
          <a href="https://www.naturalearthdata.com">Natural Earth</a>'s (public domain).
        </li>
      </ul>

      <h3>Following a lab or a venue</h3>
      <p>
        Every institution of the recent papers, and each major venue, has an Atom feed of its papers
        of the last 60 days, for a feed reader: filter the papers on an institution (click its name)
        or a major venue, and follow the link under the filters. Your feed reader then asks this
        site for it; nothing else is involved.
      </p>

      <h3>Corrections and removal</h3>
      <p>
        If a paper of yours shows a wrong affiliation or author, or you would like it removed from
        the site, write to <a href={CORRECTION_LINK}>{CONTACT_EMAIL}</a> with its arXiv identifier.
        The correction is made in the stored data, so it stays.
      </p>

      <h3>Privacy</h3>
      <ul>
        {counted ? (
          <li>
            No account, no cookies. Visits are counted by Cloudflare Web Analytics, whose script is
            the only thing the site loads from another website: it stores nothing in your browser,
            and reports each page's address without what follows a <code>?</code> or a{" "}
            <code>#</code> (your search, a shared folder), the site you came from, and your browser,
            device and country, as counts. See{" "}
            <a href="https://www.cloudflare.com/web-analytics/">Cloudflare Web Analytics</a>.
          </li>
        ) : (
          <li>No account, no cookies, no analytics: the site loads nothing from other websites.</li>
        )}
        <li>
          Your reading list, saved searches, the papers you marked seen, the day of your last visit,
          your theme and display settings are kept in your browser (local storage), and never sent
          anywhere.
        </li>
        <li>
          The site is hosted on GitHub Pages. As for any website, GitHub receives the address of
          each page you open, and here addresses include your search words and filters, so that a
          search can be shared as a link; a folder's link names its papers after a <code>#</code>,
          which browsers do not send. See the{" "}
          <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">
            GitHub privacy statement
          </a>
          .
        </li>
        <li>
          Links to arXiv, GitHub, Hugging Face and others take you to those sites, under their own
          terms.
        </li>
      </ul>
    </main>
  );
}
