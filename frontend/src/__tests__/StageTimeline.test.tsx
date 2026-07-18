import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { StageTimeline, cleanReason, nextStageLabel } from "../components/StageTimeline";

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

  it("renders a pulsing pending station with the next-stage label while running", () => {
    render(
      <StageTimeline
        frames={[{ stage: "retrieve" }, { stage: "generate_sql", attempt: 1 }]}
        running={true}
      />,
    );
    // after generate_sql, the next stage is validate → "Guardraile"
    const pending = screen.getByTestId("pending-station");
    expect(pending).toHaveTextContent("Guardraile");
    expect(pending.className).toContain("pending");
  });
});

describe("cleanReason", () => {
  it("strips the BigQuery URL and Job ID from a dry-run rejection", () => {
    const raw =
      "BigQuery odrzucił zapytanie: POST https://bigquery.googleapis.com/bigquery/v2/projects/taxi-chat-data/jobs?prettyPrint=false: Unrecognized name: trip_duration; Did you mean trip_duration_min? at [1:12] Location: None Job ID: 065f810b-ba78-4c56-be78-d44451d741ed";
    const cleaned = cleanReason(raw);
    expect(cleaned).toContain("Unrecognized name: trip_duration");
    expect(cleaned).toContain("Did you mean trip_duration_min");
    expect(cleaned).not.toContain("https://");
    expect(cleaned).not.toContain("Job ID");
    expect(cleaned).not.toContain("Location: None");
  });

  it("returns a classic guardrail reason unchanged", () => {
    const reason = "Tabela raw.trips jest poza dozwolonymi zbiorami danych (marts, staging).";
    expect(cleanReason(reason)).toBe(reason);
  });

  it("falls back to the wrapper alone when stripping leaves nothing", () => {
    const raw = "BigQuery odrzucił zapytanie: Job ID: 065f810b-ba78-4c56";
    const cleaned = cleanReason(raw);
    expect(cleaned).toBe("BigQuery odrzucił zapytanie:");
    expect(cleaned).not.toContain("Job ID");
  });
});

describe("nextStageLabel", () => {
  it("predicts the stage after the last completed frame", () => {
    expect(nextStageLabel([{ stage: "retrieve" }])).toBe("Generowanie SQL");
    expect(nextStageLabel([{ stage: "generate_sql", attempt: 1 }])).toBe("Guardraile");
    expect(nextStageLabel([{ stage: "validate", ok: true }])).toBe("BigQuery — wykonanie");
    expect(nextStageLabel([{ stage: "execute" }])).toBe("Piszę odpowiedź");
  });

  it("falls back to a generic label at the very start", () => {
    expect(nextStageLabel([])).toBe("Łączenie…");
  });

  it("predicts a retry after a failed validate", () => {
    expect(nextStageLabel([{ stage: "validate", ok: false, reason: "x" }])).toBe(
      "Generowanie SQL",
    );
  });
});
