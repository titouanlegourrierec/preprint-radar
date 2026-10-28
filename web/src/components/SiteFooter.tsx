import { REPOSITORY_URL } from "../report";
import { Attribution } from "./Attribution";

/** The sources the data comes from, and the ways to the About page and the code. */
export function SiteFooter({ onAbout }: { onAbout: () => void }) {
  return (
    <footer class="site-footer muted">
      <Attribution /> Refreshed every weekday; this project is not affiliated with arXiv.{" "}
      <a
        href="?view=about"
        onClick={(event) => {
          event.preventDefault();
          onAbout();
        }}
      >
        About the data, corrections and privacy
      </a>
      {" · "}
      <a href={REPOSITORY_URL} target="_blank" rel="noopener noreferrer">
        Source code on GitHub
      </a>
      .
    </footer>
  );
}
