import { describe, expect, it } from "vitest";
import { countryName, countryNamed } from "../src/country-names";

describe("countryName", () => {
  it("names a country by its code, in English, the code itself for an unknown one", () => {
    expect(countryName("FR")).toBe("France");
    expect(countryName("KR")).toBe("South Korea");
    expect(countryName("XX")).toBe("XX");
    expect(countryName("not a code")).toBe("not a code");
  });
});

describe("countryNamed (PROD-22)", () => {
  const codes = ["FR", "US", "GB", "KR", "CN"];

  it("finds the country a text names, however written", () => {
    expect(countryNamed("France", codes)).toBe("FR");
    expect(countryNamed("  france ", codes)).toBe("FR");
    expect(countryNamed("United States", codes)).toBe("US");
    expect(countryNamed("USA", codes)).toBe("US");
    expect(countryNamed("UK", codes)).toBe("GB");
    expect(countryNamed("Korea", codes)).toBe("KR");
  });

  it("names none that the papers at hand do not hold, nor for other words", () => {
    expect(countryNamed("Germany", codes)).toBeNull();
    expect(countryNamed("gaussian splatting", codes)).toBeNull();
    expect(countryNamed("", codes)).toBeNull();
  });
});
