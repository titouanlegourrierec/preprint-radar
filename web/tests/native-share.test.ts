import { describe, expect, it, vi } from "vitest";
import { shareLink } from "../src/native-share";

const DATA = { title: "A paper", text: "A paper", url: "https://example.org/?paper=2610.00001" };

/** A navigator whose share sheet ends as `sheet` says, and whose clipboard `copies` or not. */
function device(sheet: "shares" | "closed" | "fails" | null, copies = true) {
  const clipboard = {
    writeText: vi.fn(async () => {
      if (!copies) throw new Error("denied");
    }),
  } as unknown as Clipboard;
  const share = vi.fn(async () => {
    if (sheet === "closed") throw new DOMException("closed", "AbortError");
    if (sheet === "fails") throw new DOMException("not allowed", "NotAllowedError");
  });
  return sheet === null ? { clipboard } : { clipboard, share, canShare: () => true };
}

describe("shareLink (UX-49)", () => {
  it("opens a phone's share sheet", async () => {
    const nav = device("shares");
    expect(await shareLink(DATA, nav, true)).toBe("shared");
    expect(nav.share).toHaveBeenCalledWith(DATA);
    expect(nav.clipboard.writeText).not.toHaveBeenCalled();
    expect(await shareLink(DATA, device("closed"), true)).toBe("cancelled");
  });

  it("copies the link elsewhere, or when the sheet fails", async () => {
    const laptop = device("shares");
    expect(await shareLink(DATA, laptop, false)).toBe("copied");
    expect(laptop.share).not.toHaveBeenCalled();
    expect(laptop.clipboard.writeText).toHaveBeenCalledWith(DATA.url);
    expect(await shareLink(DATA, device("fails"), true)).toBe("copied");
    expect(await shareLink(DATA, device(null), true)).toBe("copied");
    expect(await shareLink(DATA, device(null, false), false)).toBe("refused");
  });
});
