import { describe, expect, it } from "vitest";
import { CONTENT_SECURITY_POLICY, contentSecurityPolicy } from "../tooling/content-security-policy";
import { analyticsToken, BEACON_URL, beaconTag, REPORT_URL } from "../tooling/web-analytics";

const TOKEN = "0123456789abcdef0123456789abcdef";

describe("Cloudflare Web Analytics (UX-47)", () => {
  it("is on with a token only, which a malformed value fails", () => {
    expect(analyticsToken(undefined)).toBeNull();
    expect(analyticsToken("  ")).toBeNull();
    expect(analyticsToken(` ${TOKEN}\n`)).toBe(TOKEN);
    // A value that would break out of the snippet's attribute.
    expect(() => analyticsToken(`${TOKEN}'><script>`)).toThrow("not a Cloudflare Web Analytics");
    expect(() => analyticsToken("short")).toThrow();
  });

  it("writes the snippet as Cloudflare's", () => {
    expect(beaconTag(TOKEN)).toBe(
      `<script type="module" src="https://static.cloudflareinsights.com/beacon.min.js" data-cf-beacon='{"token": "${TOKEN}"}'></script>`,
    );
  });

  it("lets the policy allow its script and report, nothing else", () => {
    expect(CONTENT_SECURITY_POLICY).toBe(contentSecurityPolicy(false));
    expect(CONTENT_SECURITY_POLICY).not.toContain("cloudflare");
    const counted = contentSecurityPolicy(true).split("; ");
    expect(counted).toContain(`script-src 'self' ${BEACON_URL}`);
    expect(counted).toContain(`connect-src 'self' ${REPORT_URL}`);
    expect(counted).toContain("default-src 'self'");
    expect(counted).toHaveLength(CONTENT_SECURITY_POLICY.split("; ").length);
  });
});
