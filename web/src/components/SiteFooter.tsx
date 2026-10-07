import { Attribution } from "./Attribution";

/** The sources the data comes from, and the way to the About page. */
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
      .
    </footer>
  );
}
