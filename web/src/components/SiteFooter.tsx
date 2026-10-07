/** The sources the data comes from, and the way to the About page. */
export function SiteFooter({ onAbout }: { onAbout: () => void }) {
  return (
    <footer class="site-footer muted">
      Data from <a href="https://arxiv.org">arXiv</a>, refreshed every weekday. Thank you to arXiv
      for use of its open access interoperability. This project is not affiliated with arXiv.
      Citation counts from <a href="https://www.semanticscholar.org">Semantic Scholar</a>,
      institutions from the <a href="https://ror.org">Research Organization Registry</a> and{" "}
      <a href="https://openalex.org">OpenAlex</a>.{" "}
      <a
        href="?view=about"
        onClick={(event) => {
          event.preventDefault();
          onAbout();
        }}
      >
        About the data, corrections and privacy
      </a>
      .
    </footer>
  );
}
