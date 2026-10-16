/**
 * Sharing a link (UX-49): on a phone, its system's share sheet (Messages, WhatsApp, Mail…),
 * the Web Share API; elsewhere, or when the sheet fails, the link copied, as before. A
 * phone is a device whose pointer is a finger: a laptop's browser may offer the API too,
 * where copying is what one expects.
 */

export interface ShareData {
  title: string;
  /** What goes before the link, for the apps that take a text (a message). */
  text: string;
  url: string;
}

/** What became of it: shared by the sheet, closed unshared, copied, or the clipboard refused. */
export type Shared = "shared" | "cancelled" | "copied" | "refused";

const FINGER = "(pointer: coarse)";

export async function shareLink(
  data: ShareData,
  nav: Pick<Navigator, "clipboard"> & Partial<Pick<Navigator, "share" | "canShare">> = navigator,
  phone: boolean = window.matchMedia(FINGER).matches,
): Promise<Shared> {
  if (phone && nav.share && (nav.canShare?.(data) ?? true)) {
    try {
      await nav.share(data);
      return "shared";
    } catch (error) {
      // Closed by the user; any other failure copies the link instead.
      if (error instanceof Error && error.name === "AbortError") return "cancelled";
    }
  }
  try {
    await nav.clipboard.writeText(data.url);
    return "copied";
  } catch {
    return "refused";
  }
}
