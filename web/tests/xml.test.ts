import { describe, expect, it } from "vitest";
import { xmlText } from "../src/xml";

describe("xmlText", () => {
  it("escapes markup and quotes", () => {
    expect(xmlText('Ada & "Bob" <Lab>')).toBe("Ada &amp; &quot;Bob&quot; &lt;Lab&gt;");
  });

  it("drops what XML refuses, and keeps tabs, line breaks and any script", () => {
    expect(xmlText("a\u0000b\u0007c￾d")).toBe("abcd");
    expect(xmlText("a\tb\nc\rd")).toBe("a\tb\nc\rd");
    expect(xmlText("王小明 🙂")).toBe("王小明 🙂");
    // Half of a surrogate pair alone.
    expect(xmlText("x\uD800y")).toBe("xy");
  });
});
