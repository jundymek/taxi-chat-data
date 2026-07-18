import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultCard, columnLabel, formatScan } from "../components/ResultCard";

const RESULT = {
  answer: "Średni napiwek wynosił 4,16 USD.",
  sql: "SELECT 1",
  rows: [{ avg_tip: 4.16 }],
  scanned_gb: 0.048,
  attempts: 2,
  refused: false,
  model: "gemma4:latest",
};

describe("ResultCard", () => {
  it("shows the answer, chips and the rows table", () => {
    render(<ResultCard result={RESULT} />);
    expect(screen.getByText(/4,16 USD/)).toBeInTheDocument();
    expect(screen.getByText("2 próby")).toBeInTheDocument();
    expect(screen.getByText("Przeskanowano 0.05 GB")).toBeInTheDocument();
    expect(screen.getByText("avg_tip")).toBeInTheDocument();
  });

  it("renders a technical f0_ column as a readable label", () => {
    render(<ResultCard result={{ ...RESULT, rows: [{ f0_: 6179 }] }} />);
    expect(screen.getByText("Wynik")).toBeInTheDocument();
    expect(screen.queryByText("f0_")).not.toBeInTheDocument();
    expect(screen.getByText("6179")).toBeInTheDocument();
  });

  it("renders a refusal without a rows table", () => {
    render(
      <ResultCard
        result={{
          ...RESULT,
          refused: true,
          rows: [],
          reason: "Tylko SELECT.",
          answer: "Nie umiem bezpiecznie odpowiedzieć.",
        }}
      />,
    );
    expect(screen.getByText(/Nie umiem/)).toBeInTheDocument();
    expect(screen.getByText(/Tylko SELECT/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("columnLabel", () => {
  it("maps a single technical column to Wynik", () => {
    expect(columnLabel("f0_", ["f0_"])).toBe("Wynik");
  });
  it("numbers multiple technical columns", () => {
    expect(columnLabel("f0_", ["f0_", "f1_"])).toBe("Wynik 1");
    expect(columnLabel("f1_", ["f0_", "f1_"])).toBe("Wynik 2");
  });
  it("passes ordinary names through", () => {
    expect(columnLabel("avg_tip", ["avg_tip"])).toBe("avg_tip");
  });
});

describe("formatScan", () => {
  it("captions and rounds to 2 decimals", () => {
    expect(formatScan(0.048)).toBe("Przeskanowano 0.05 GB");
    expect(formatScan(1.2345)).toBe("Przeskanowano 1.23 GB");
  });
  it("shows <0.01 GB for tiny scans", () => {
    expect(formatScan(0.0004)).toBe("Przeskanowano <0.01 GB");
    expect(formatScan(0)).toBe("Przeskanowano <0.01 GB");
  });
});
