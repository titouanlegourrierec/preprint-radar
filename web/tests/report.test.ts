import { describe, expect, it } from "vitest";
import { CONTACT_EMAIL, reportLink } from "../src/report";

function parts(link: string) {
  const url = new URL(link);
  return {
    to: url.pathname,
    subject: url.searchParams.get("subject"),
    body: url.searchParams.get("body") ?? "",
  };
}

describe("reportLink", () => {
  it("fills in the paper, and leaves the rest to write", () => {
    const { to, subject, body } = parts(
      reportLink({ arxiv_id: "2609.00001", title: "Fast  Gaussian\n Splatting & More" }),
    );
    expect(to).toBe(CONTACT_EMAIL);
    expect(subject).toBe("Preprint Radar: correction for arXiv:2609.00001");
    expect(body.split("\r\n").slice(0, 2)).toEqual([
      "Paper: Fast Gaussian Splatting & More",
      "https://arxiv.org/abs/2609.00001",
    ]);
    expect(body).toContain("What it should say:");
  });

  it("asks for the paper without one", () => {
    const { subject, body } = parts(reportLink());
    expect(subject).toBe("Preprint Radar: correction");
    expect(body.startsWith("arXiv identifier or link of the paper:")).toBe(true);
  });

  it("stays short enough for every mail client", () => {
    expect(reportLink({ arxiv_id: "2609.00001", title: "A".repeat(300) }).length).toBeLessThan(
      2000,
    );
  });
});
