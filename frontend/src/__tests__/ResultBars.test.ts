import { describe, expect, it } from "vitest";
import { barColumn, barWidth } from "../components/ResultCard";

describe("barColumn", () => {
  it("picks the last fully-numeric column", () => {
    const rows = [
      { borough: "Manhattan", trips: 10, avg_fare: 19.84 },
      { borough: "Queens", trips: 8, avg_fare: 17.12 },
    ];
    expect(barColumn(rows, ["borough", "trips", "avg_fare"])).toBe("avg_fare");
  });

  it("ignores a column that is only sometimes numeric", () => {
    const rows = [{ v: 1 }, { v: null }];
    expect(barColumn(rows, ["v"])).toBeNull();
  });

  it("ignores non-finite values so NaN never yields a bar", () => {
    const rows = [{ v: Number.NaN }, { v: 2 }];
    expect(barColumn(rows, ["v"])).toBeNull();
  });

  it("returns null when nothing is numeric", () => {
    expect(barColumn([{ b: "Bronx" }], ["b"])).toBeNull();
  });

  it("returns null for an empty result", () => {
    expect(barColumn([], [])).toBeNull();
  });
});

describe("barWidth", () => {
  it("scales against the largest value", () => {
    expect(barWidth(20, [20, 10, 5])).toBe("100%");
    expect(barWidth(10, [20, 10, 5])).toBe("50%");
  });

  it("scales negatives by magnitude rather than dropping them", () => {
    expect(barWidth(-10, [-10, 5])).toBe("100%");
  });

  it("returns 0% when every value is zero instead of dividing by zero", () => {
    expect(barWidth(0, [0, 0])).toBe("0%");
  });
});
