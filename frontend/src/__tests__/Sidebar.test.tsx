import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "../components/Sidebar";
import { healthSummary } from "../components/HealthBar";

const SESSIONS = [
  { id: 2, question: "Average fare by borough" },
  { id: 1, question: "How many trips yesterday?" },
];

describe("Sidebar", () => {
  it("invites the first question when there is no history", () => {
    render(<Sidebar sessions={[]} activeId={null} onSelect={() => {}} />);
    expect(screen.getByText(/will appear here/i)).toBeInTheDocument();
  });

  it("lists sessions and marks the active one", () => {
    render(<Sidebar sessions={SESSIONS} activeId={2} onSelect={() => {}} />);
    const active = screen.getByRole("button", { name: "Average fare by borough" });
    expect(active).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "How many trips yesterday?" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("reports the picked session", async () => {
    const onSelect = vi.fn();
    render(<Sidebar sessions={SESSIONS} activeId={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: "How many trips yesterday?" }));
    expect(onSelect).toHaveBeenCalledWith(SESSIONS[1]);
  });
});

describe("healthSummary", () => {
  it("reports an all-clear when every dependency is ok", () => {
    expect(healthSummary({ ollama: "ok", bigquery: "ok", chroma_index: "ok" })).toBe(
      "all services OK",
    );
  });

  it("names the dependencies that are down", () => {
    expect(healthSummary({ ollama: "ok", bigquery: "down", chroma_index: "missing" })).toBe(
      "BigQuery, Index — unreachable",
    );
  });
});
