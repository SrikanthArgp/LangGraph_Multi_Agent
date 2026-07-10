import { describe, expect, test } from "vitest";

describe("CI verify — deliberate failure", () => {
  test("this is expected to fail", () => {
    expect(1).toBe(2);
  });
});
