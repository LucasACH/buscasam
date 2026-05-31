import { afterEach, describe, expect, it } from "vitest";

import robots, { dynamic } from "./robots";

const originalBaseUrl = process.env.BUSCASAM_BASE_URL;

afterEach(() => {
  if (originalBaseUrl === undefined) {
    delete process.env.BUSCASAM_BASE_URL;
  } else {
    process.env.BUSCASAM_BASE_URL = originalBaseUrl;
  }
});

describe("robots metadata route", () => {
  it("forces runtime evaluation", () => {
    expect(dynamic).toBe("force-dynamic");
  });

  it("resolves the public base URL on each invocation", () => {
    process.env.BUSCASAM_BASE_URL = "https://buscasam.example/";
    expect(robots().sitemap).toBe("https://buscasam.example/sitemap.xml");

    process.env.BUSCASAM_BASE_URL = "https://runtime.example";
    expect(robots().sitemap).toBe("https://runtime.example/sitemap.xml");
  });

  it("falls back to localhost for local development", () => {
    delete process.env.BUSCASAM_BASE_URL;
    expect(robots().sitemap).toBe("http://localhost:3000/sitemap.xml");
  });
});
