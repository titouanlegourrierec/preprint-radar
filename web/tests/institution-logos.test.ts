import { describe, expect, it } from "vitest";
import {
  contentProblems,
  cropSvg,
  isJpeg,
  type LogosManifest,
  logoFileName,
  logoPaths,
  logoProblems,
  pngSize,
  svgProblems,
  tidySvg,
  wikiFile,
  wikiFileQueries,
  withLogos,
} from "../tooling/logos";

const SQUARE =
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 2 2"><path d="M0 0h2v2H0z"/></svg>';
// A stand-in for SHA-256, which the build passes: the content's length, in hexadecimal, first.
const sha256 = (bytes: Uint8Array) => bytes.length.toString(16).padEnd(64, "0");
const encode = (text: string) => new TextEncoder().encode(text);

/** A PNG's signature and header, enough for its size. */
function png(width: number, height: number): Uint8Array {
  const bytes = new Uint8Array(33);
  bytes.set([0x89, 0x50, 0x4e, 0x47, 0x0d, 0x0a, 0x1a, 0x0a, 0, 0, 0, 13, 73, 72, 68, 82]);
  const view = new DataView(bytes.buffer);
  view.setUint32(16, width);
  view.setUint32(20, height);
  return bytes;
}

describe("svgProblems (PROD-23)", () => {
  it("takes a plain drawing, its own gradients and references included", () => {
    expect(svgProblems(SQUARE)).toEqual([]);
    expect(
      svgProblems(
        '<?xml version="1.0"?>\n<svg viewBox="0 0 2 2" xmlns:xlink="http://www.w3.org/1999/xlink">' +
          '<defs><linearGradient id="g"/></defs><path fill="url(#g)" d="M0 0h2v2z"/>' +
          '<use xlink:href="#g"/></svg>\n',
      ),
    ).toEqual([]);
  });

  it("refuses what could run, load or link, served from the site's origin", () => {
    const holding = (inner: string) => svgProblems(`<svg viewBox="0 0 2 2">${inner}</svg>`);
    expect(holding("<script>alert(1)</script>")).toEqual(["holds a script"]);
    expect(holding('<path onload="alert(1)"/>')).toEqual(["holds an event handler"]);
    expect(holding("<foreignObject/>")).toEqual(["holds a foreignObject"]);
    expect(holding('<image href="https://example.org/a.png"/>')).toEqual([
      "holds an element that loads or links",
      "refers outside itself (https://example.org/a.png)",
    ]);
    expect(holding('<set attributeName="fill" to="red"/>')).toEqual(["holds an animation"]);
    expect(holding("<style>@import 'a.css';</style>")).toEqual(["holds an @import"]);
    expect(holding('<path fill="url(https://example.org/a)"/>')).toEqual([
      "refers outside itself (https://example.org/a)",
    ]);
    expect(holding('<use href="javascript:alert(1)"/>')).toContain("holds a javascript: URL");
    expect(svgProblems('<!DOCTYPE svg [<!ENTITY a "b">]><svg viewBox="0 0 1 1"></svg>')).toEqual([
      "holds a DOCTYPE or an entity",
    ]);
  });

  it("wants an SVG that scales", () => {
    expect(svgProblems('<svg width="2" height="2"><path d="M0 0h2v2z"/></svg>')).toEqual([
      "no viewBox on its root, so it cannot scale",
    ]);
    expect(svgProblems("<html><body>Not found</body></html>")).toEqual(["not an SVG"]);
  });
});

describe("contentProblems", () => {
  it("takes a PNG of 64 px a side or more", () => {
    expect(pngSize(png(192, 96))).toEqual({ width: 192, height: 96 });
    expect(pngSize(encode(SQUARE))).toBeNull();
    expect(contentProblems("png", png(64, 64))).toEqual([]);
    expect(contentProblems("png", png(48, 48))).toEqual(["48×48 px, below 64 px a side"]);
    expect(contentProblems("png", encode(SQUARE))).toEqual(["not a PNG"]);
  });

  it("refuses a file larger than a logo", () => {
    const large = encode(`<svg viewBox="0 0 1 1"><!--${"x".repeat(100_000)}--></svg>`);
    expect(contentProblems("svg", large)).toEqual([
      `${large.length} bytes, past the 100000 of a logo`,
    ]);
  });
});

describe("logoProblems", () => {
  const file = logoFileName("Stanford University", "svg", sha256(encode(SQUARE)));
  const manifest: LogosManifest = {
    logos: {
      "Stanford University": {
        file,
        source: "https://commons.wikimedia.org/wiki/File:Square.svg",
        license: "Public domain, trademarked",
      },
    },
  };
  const read = (name: string) => (name === file ? encode(SQUARE) : null);

  it("passes listed, safe files named after their content", () => {
    expect(file).toMatch(/^stanford-university-[0-9a-f]{8}\.svg$/);
    expect(logoProblems(manifest, [file], read, sha256)).toEqual([]);
  });

  it("names each problem's institution or file", () => {
    const stale = file.replace(/-[0-9a-f]{8}\./, "-00000000.");
    const wrong: LogosManifest = {
      logos: {
        "Stanford University": { file: stale, source: "http://stanford.edu", license: " " },
        MIT: { file: "mit.svg", source: "https://mit.edu", license: "Trademark" },
        Google: { file: "google-12345678.png", source: "https://google.com", license: "PD" },
      },
    };
    expect(
      logoProblems(
        wrong,
        [file, "orphan-12345678.svg"],
        (name) => read(name.replace(stale, file)),
        sha256,
      ),
    ).toEqual([
      "Stanford University: no https source",
      "Stanford University: no license",
      `Stanford University: ${stale} is not its content's hash`,
      "MIT: mit.svg is not named <name>-<hash>.svg or .png",
      "Google: google-12345678.png is missing",
      `${file} is not in logos.json`,
      "orphan-12345678.svg is not in logos.json",
    ]);
  });
});

describe("logoFileName", () => {
  it("makes a slug of the name, accents and punctuation gone", () => {
    expect(logoFileName("Université Paris-Saclay", "png", "abcdef0123")).toBe(
      "universite-paris-saclay-abcdef01.png",
    );
    expect(logoFileName("University of California, Berkeley", "svg", "0".repeat(64))).toBe(
      "university-of-california-berkeley-00000000.svg",
    );
  });
});

describe("tidySvg", () => {
  it("drops the DOCTYPE an editor writes by default, which declares nothing", () => {
    const saved =
      '<?xml version="1.0"?>\n<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" ' +
      '"http://www.w3.org/Graphics/SVG/1.1/DTD/svg11.dtd">\n<svg viewBox="0 0 2 2"></svg>';
    expect(tidySvg(saved)).toBe('<?xml version="1.0"?>\n<svg viewBox="0 0 2 2"></svg>');
    expect(svgProblems(tidySvg(saved))).toEqual([]);
  });

  it("keeps a DOCTYPE that declares entities, which the check refuses", () => {
    const declaring =
      '<!DOCTYPE svg PUBLIC "-//W3C//DTD SVG 1.1//EN" "svg11.dtd" [<!ENTITY ns "x">]>' +
      '<svg viewBox="0 0 2 2"></svg>';
    expect(tidySvg(declaring)).toBe(declaring);
    expect(svgProblems(tidySvg(declaring))).toEqual(["holds a DOCTYPE or an entity"]);
  });

  it("gives a root sized without a viewBox one, in CSS pixels", () => {
    expect(tidySvg('<svg width="321" height="166px"><path/></svg>')).toBe(
      '<svg viewBox="0 0 321 166" width="321" height="166px"><path/></svg>',
    );
    expect(tidySvg('<svg height="248.02pt" width="162pt"></svg>')).toBe(
      '<svg viewBox="0 0 216 330.693" height="248.02pt" width="162pt"></svg>',
    );
    // Sized in a unit with no pixels, or not at all: left for the check to refuse.
    expect(tidySvg('<svg width="100%" height="100%"></svg>')).toBe(
      '<svg width="100%" height="100%"></svg>',
    );
    expect(tidySvg(SQUARE)).toBe(SQUARE);
  });
});

describe("cropSvg", () => {
  it("sets the root's viewBox and drops its fixed size", () => {
    expect(
      cropSvg('<svg width="54pt" height="14pt" viewBox="0 0 54 14"><path/></svg>', "0 0 16.2 14"),
    ).toBe('<svg viewBox="0 0 16.2 14"><path/></svg>');
    expect(cropSvg("<svg><path/></svg>", "1,1,21,21")).toBe(
      '<svg viewBox="1 1 21 21"><path/></svg>',
    );
  });

  it("refuses what is not a viewBox", () => {
    expect(() => cropSvg(SQUARE, "0 0 16")).toThrow(/is not a viewBox/);
    expect(() => cropSvg(SQUARE, "0 0 0 14")).toThrow(/is not a viewBox/);
    expect(() => cropSvg("<html></html>", "0 0 1 1")).toThrow("not an SVG");
  });
});

describe("the wikis' API", () => {
  const asked = (page: string) =>
    wikiFileQueries(page).map((query) => {
      const url = new URL(query);
      return `${url.host} ${url.searchParams.get("titles")}`;
    });

  it("asks Commons, then the page's own wiki, about the file it shows, in any language", () => {
    expect(asked("https://commons.wikimedia.org/wiki/File:Google_%22G%22_logo.svg")).toEqual([
      'commons.wikimedia.org File:Google_"G"_logo.svg',
    ]);
    expect(asked("https://rw.wikipedia.org/wiki/Dosiye:CMU_logo_stack_cmyk_red.jpg")).toEqual([
      "commons.wikimedia.org File:CMU_logo_stack_cmyk_red.jpg",
      "rw.wikipedia.org File:CMU_logo_stack_cmyk_red.jpg",
    ]);
    expect(asked("https://de.wikipedia.org/wiki/Datei:Universit%C3%A4t_Hongkong_Logo.svg")).toEqual(
      [
        "commons.wikimedia.org File:Universität_Hongkong_Logo.svg",
        "de.wikipedia.org File:Universität_Hongkong_Logo.svg",
      ],
    );
    expect(
      asked(
        "https://en.wikipedia.org/wiki/Seoul_National_University#/media/File:Seoul_national_university_emblem.svg",
      ),
    ).toEqual([
      "commons.wikimedia.org File:Seoul_national_university_emblem.svg",
      "en.wikipedia.org File:Seoul_national_university_emblem.svg",
    ]);
  });

  it("asks nothing about an article without a file shown, nor another site", () => {
    expect(asked("https://en.wikipedia.org/wiki/Seoul_National_University")).toEqual([]);
    expect(asked("https://www.stanford.edu/logo.svg")).toEqual([]);
  });

  const answer = (extmetadata: object, descriptionurl?: string) => ({
    query: {
      pages: {
        "1": {
          imageinfo: [
            {
              url: "https://upload.wikimedia.org/wikipedia/commons/4/44/Microsoft_logo.svg?utm_source=commons",
              descriptionurl,
              extmetadata,
            },
          ],
        },
      },
    },
  });

  it("gives the original file, its own page and its license, trademark said", () => {
    expect(
      wikiFile(
        answer(
          { LicenseShortName: { value: "Public domain" }, Restrictions: { value: "trademarked" } },
          "https://commons.wikimedia.org/wiki/File:Microsoft_logo.svg",
        ),
      ),
    ).toEqual({
      url: "https://upload.wikimedia.org/wikipedia/commons/4/44/Microsoft_logo.svg",
      page: "https://commons.wikimedia.org/wiki/File:Microsoft_logo.svg",
      license: "Public domain, trademarked",
      nonFree: false,
    });
    expect(wikiFile(answer({ LicenseShortName: { value: "CC BY-SA 4.0" } }))?.license).toBe(
      "CC BY-SA 4.0",
    );
    expect(wikiFile({ query: { pages: { "-1": { missing: "" } } } })).toBeNull();
  });

  it("says when a wiki shows a file under fair use only", () => {
    expect(wikiFile(answer({ NonFree: { value: "true" } }))?.nonFree).toBe(true);
    expect(wikiFile(answer({ LicenseShortName: { value: "Fair use" } }))?.nonFree).toBe(true);
  });
});

describe("isJpeg", () => {
  it("knows a JPEG by its signature", () => {
    expect(isJpeg(new Uint8Array([0xff, 0xd8, 0xff, 0xe0]))).toBe(true);
    expect(isJpeg(png(64, 64))).toBe(false);
    expect(isJpeg(encode(SQUARE))).toBe(false);
  });
});

describe("the site's index", () => {
  it("gives each logo's path under the site's logos/", () => {
    const manifest: LogosManifest = {
      logos: { Google: { file: "google-ed9087d7.svg", source: "https://a.org", license: "PD" } },
    };
    const logos = logoPaths(manifest);
    expect(logos).toEqual({ Google: "logos/google-ed9087d7.svg" });
    expect(JSON.parse(withLogos('{"categories":{}}', logos))).toEqual({
      categories: {},
      logos,
    });
    expect(withLogos('{"categories":{}}', {})).toBe('{"categories":{}}');
  });
});
