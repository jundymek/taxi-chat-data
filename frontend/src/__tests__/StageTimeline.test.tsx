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
            reason: "Table raw.trips is outside the allowed datasets",
          },
          { stage: "generate_sql", attempt: 2 },
          { stage: "validate", ok: true },
        ]}
        running={false}
      />,
    );
    expect(screen.getByText("REJECTED")).toBeInTheDocument();
    expect(screen.getByText(/raw\.trips/)).toBeInTheDocument();
    expect(screen.getAllByText("OK").length).toBeGreaterThanOrEqual(3);
    expect(screen.getByText("SQL — attempt 2")).toBeInTheDocument();
  });

  it("renders a pulsing pending station with the next-stage label while running", () => {
    render(
      <StageTimeline
        frames={[{ stage: "retrieve" }, { stage: "generate_sql", attempt: 1 }]}
        running={true}
      />,
    );
    // after generate_sql, the next stage is validate → "Guardrails"
    const pending = screen.getByTestId("pending-station");
    expect(pending).toHaveTextContent("Guardrails");
    expect(pending.className).toContain("run");
  });
});

describe("cleanReason", () => {
  it("strips the BigQuery URL and Job ID from a dry-run rejection", () => {
    const raw =
      "BigQuery rejected the query: POST https://bigquery.googleapis.com/bigquery/v2/projects/taxi-chat-data/jobs?prettyPrint=false: Unrecognized name: trip_duration; Did you mean trip_duration_min? at [1:12] Location: None Job ID: 065f810b-ba78-4c56-be78-d44451d741ed";
    const cleaned = cleanReason(raw);
    expect(cleaned).toContain("Unrecognized name: trip_duration");
    expect(cleaned).toContain("Did you mean trip_duration_min");
    expect(cleaned).not.toContain("https://");
    expect(cleaned).not.toContain("Job ID");
    expect(cleaned).not.toContain("Location: None");
  });

  it("strips the tail when google-cloud puts it on separate lines", () => {
    // Observed live: BadRequest renders Location/Job ID as their own lines, so
    // a non-dotAll `.*` stopped at the first newline and left the noise in.
    const raw =
      "BigQuery rejected the query: Unrecognized name: t at [1:94]\nLocation: None\nJob ID: e852ee68-b355-404d-b860-e9c7eb28ab50";
    const cleaned = cleanReason(raw);
    expect(cleaned).toBe("BigQuery rejected the query: Unrecognized name: t");
    expect(cleaned).not.toContain("Location");
    expect(cleaned).not.toContain("Job ID");
  });

  it("returns a classic guardrail reason unchanged", () => {
    const reason = "Table raw.trips is outside the allowed datasets (marts, staging).";
    expect(cleanReason(reason)).toBe(reason);
  });

  it("falls back to the wrapper alone when stripping leaves nothing", () => {
    const raw = "BigQuery rejected the query: Job ID: 065f810b-ba78-4c56";
    const cleaned = cleanReason(raw);
    expect(cleaned).toBe("BigQuery rejected the query:");
    expect(cleaned).not.toContain("Job ID");
  });
});

describe("nextStageLabel", () => {
  it("predicts the stage after the last completed frame", () => {
    expect(nextStageLabel([{ stage: "retrieve" }])).toBe("Generating SQL");
    expect(nextStageLabel([{ stage: "generate_sql", attempt: 1 }])).toBe("Guardrails");
    expect(nextStageLabel([{ stage: "validate", ok: true }])).toBe("BigQuery — execution");
    expect(nextStageLabel([{ stage: "execute" }])).toBe("Writing answer");
  });

  it("falls back to a generic label at the very start", () => {
    expect(nextStageLabel([])).toBe("Connecting…");
  });

  it("predicts a retry after a failed validate", () => {
    expect(nextStageLabel([{ stage: "validate", ok: false, reason: "x" }])).toBe(
      "Generating SQL",
    );
  });
});
