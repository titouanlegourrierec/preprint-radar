import { describe, expect, it } from "vitest";
import html from "../index.html?raw";
import { SHARE_IMAGE_HEIGHT, SHARE_IMAGE_WIDTH, shareImageTags } from "../tooling/share-card";

describe("the card of a shared link (UX-49)", () => {
  it("names the site in the page's Open Graph tags", () => {
    for (const tag of [
      '<meta property="og:title" content="Preprint Radar" />',
      '<meta property="og:site_name" content="Preprint Radar" />',
      '<meta name="twitter:card" content="summary_large_image" />',
    ]) {
      expect(html).toContain(tag);
    }
    const description = /<meta name="description" content="([^"]+)"/.exec(html)?.[1];
    expect(html).toContain(`<meta property="og:description" content="${description}" />`);
  });

  it("gives its image an absolute address, under the site's path", () => {
    const tags = shareImageTags("https://example.github.io/preprint-radar");
    expect(tags[0]).toBe(
      '<meta property="og:image" content="https://example.github.io/preprint-radar/share.png" />',
    );
    expect(shareImageTags("https://example.github.io/preprint-radar/")[0]).toBe(tags[0]);
    expect(tags).toContain(`<meta property="og:image:width" content="${SHARE_IMAGE_WIDTH}" />`);
    expect(tags).toContain(`<meta property="og:image:height" content="${SHARE_IMAGE_HEIGHT}" />`);
    // A local build does not know where the site is: no image, which must be absolute.
    expect(shareImageTags(null)).toEqual([]);
  });
});
