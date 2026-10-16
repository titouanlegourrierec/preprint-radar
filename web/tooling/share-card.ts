/**
 * The card a link to the site shows where it is shared (UX-49): Slack, WhatsApp, iMessage,
 * X, LinkedIn and the like read Open Graph tags from the page, without running its script,
 * so every link (a paper, a search, a folder) shows the same card, the site's. `index.html`
 * holds its title and description; the build adds its image, `public/share.png` (the logo,
 * 1200 by 630), whose address must be absolute, and so is known only when the build is given
 * the site's (`PREPRINT_RADAR_SITE_URL`, as the Atom feeds are).
 */

export const SHARE_IMAGE = "share.png";
export const SHARE_IMAGE_WIDTH = 1200;
export const SHARE_IMAGE_HEIGHT = 630;

/** The card's image tags, for the head of `index.html`; none without the site's address. */
export function shareImageTags(siteUrl: string | null): string[] {
  if (siteUrl === null) return [];
  const image = new URL(SHARE_IMAGE, siteUrl.replace(/\/?$/, "/")).toString();
  return [
    `<meta property="og:image" content="${image}" />`,
    `<meta property="og:image:width" content="${SHARE_IMAGE_WIDTH}" />`,
    `<meta property="og:image:height" content="${SHARE_IMAGE_HEIGHT}" />`,
    `<meta property="og:image:alt" content="Preprint Radar" />`,
  ];
}
