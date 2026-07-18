import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { ResultCard } from "../components/ResultCard";

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
    expect(screen.getByText("0.0480 GB")).toBeInTheDocument();
    expect(screen.getByText("avg_tip")).toBeInTheDocument();
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
