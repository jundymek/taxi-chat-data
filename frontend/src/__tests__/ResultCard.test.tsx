import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultCard, columnLabel, formatScan } from "../components/ResultCard";

const RESULT = {
  answer: "The average tip was $4.16.",
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
    expect(screen.getByText(/\$4\.16/)).toBeInTheDocument();
    expect(screen.getByText("2 attempts")).toBeInTheDocument();
    expect(screen.getByText("Scanned 0.05 GB")).toBeInTheDocument();
    expect(screen.getByText("avg_tip")).toBeInTheDocument();
  });

  it("renders a technical f0_ column as a readable label", () => {
    render(<ResultCard result={{ ...RESULT, rows: [{ f0_: 6179 }] }} />);
    expect(screen.getByText("Result")).toBeInTheDocument();
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
          reason: "SELECT only.",
          answer: "I can't answer that safely.",
        }}
      />,
    );
    expect(screen.getByText(/can't answer/)).toBeInTheDocument();
    expect(screen.getByText(/SELECT only/)).toBeInTheDocument();
    expect(screen.queryByRole("table")).not.toBeInTheDocument();
  });
});

describe("columnLabel", () => {
  it("maps a single technical column to Result", () => {
    expect(columnLabel("f0_", ["f0_"])).toBe("Result");
  });
  it("numbers multiple technical columns", () => {
    expect(columnLabel("f0_", ["f0_", "f1_"])).toBe("Result 1");
    expect(columnLabel("f1_", ["f0_", "f1_"])).toBe("Result 2");
  });
  it("passes ordinary names through", () => {
    expect(columnLabel("avg_tip", ["avg_tip"])).toBe("avg_tip");
  });
});

describe("formatScan", () => {
  it("captions and rounds to 2 decimals", () => {
    expect(formatScan(0.048)).toBe("Scanned 0.05 GB");
    expect(formatScan(1.2345)).toBe("Scanned 1.23 GB");
  });
  it("shows <0.01 GB for tiny scans", () => {
    expect(formatScan(0.0004)).toBe("Scanned <0.01 GB");
    expect(formatScan(0)).toBe("Scanned <0.01 GB");
  });
});
