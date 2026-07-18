import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageTimeline } from "../components/StageTimeline";

describe("StageTimeline (mockup C1)", () => {
  it("renders OK status for successful validate and the reason for rejection", () => {
    render(
      <StageTimeline
        frames={[
          { stage: "retrieve" },
          { stage: "generate_sql", attempt: 1 },
          {
            stage: "validate",
            ok: false,
            reason: "Tabela raw.trips jest poza dozwolonymi zbiorami danych",
          },
          { stage: "generate_sql", attempt: 2 },
          { stage: "validate", ok: true },
        ]}
        running={false}
      />,
    );
    expect(screen.getByText("ODRZUCONE")).toBeInTheDocument();
    expect(screen.getByText(/raw\.trips/)).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("SQL — próba 2")).toBeInTheDocument();
  });

  it("marks the last row as pending while running", () => {
    render(<StageTimeline frames={[{ stage: "retrieve" }]} running={true} />);
    expect(screen.getByText("…")).toBeInTheDocument();
  });
});
