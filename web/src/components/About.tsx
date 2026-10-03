import { CONTACT_EMAIL, reportLink } from "../report";

const CORRECTION_LINK = reportLink();

/** What the site is, where its data comes from, how to get it corrected, and privacy. */
export function About() {
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
          <a href="https://ror.org">Research Organization Registry</a>, or named by the site's own
          rules.
        </li>
        <li>
          Highly cited papers: chosen every week by citations per year of age, from the counts of{" "}
          <a href="https://www.semanticscholar.org">Semantic Scholar</a>. Their affiliations come
          from <a href="https://openalex.org">OpenAlex</a>.
        </li>
      </ul>

      <h3>Corrections and removal</h3>
      <p>
        If a paper of yours shows a wrong affiliation or author, or you would like it removed from
        the site, write to <a href={CORRECTION_LINK}>{CONTACT_EMAIL}</a> with its arXiv identifier.
        The correction is made in the stored data, so it stays.
      </p>

      <h3>Privacy</h3>
      <ul>
        <li>No account, no cookies, no analytics: the site loads nothing from other websites.</li>
        <li>
          Your reading list, saved searches, the papers you marked seen, the day of your last visit,
          your theme and display settings are kept in your browser (local storage), and never sent
          anywhere.
        </li>
        <li>
          The site is hosted on GitHub Pages. As for any website, GitHub receives the address of
          each page you open, and here addresses include your search words and filters, so that a
          search can be shared as a link. See the{" "}
          <a href="https://docs.github.com/site-policy/privacy-policies/github-general-privacy-statement">
            GitHub privacy statement
          </a>
          .
        </li>
        <li>
          Links to arXiv, Semantic Scholar and others take you to those sites, under their own
          terms.
        </li>
      </ul>
    </main>
  );
}
