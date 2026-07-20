import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { Sidebar } from "../components/Sidebar";
import { healthSummary } from "../components/HealthBar";

const SESSIONS = [
  { id: 2, question: "Średnia opłata wg dzielnicy" },
  { id: 1, question: "Ile kursów wczoraj?" },
];

describe("Sidebar", () => {
  it("invites the first question when there is no history", () => {
    render(<Sidebar sessions={[]} activeId={null} onSelect={() => {}} />);
    expect(screen.getByText(/pojawią się tutaj/i)).toBeInTheDocument();
  });

  it("lists sessions and marks the active one", () => {
    render(<Sidebar sessions={SESSIONS} activeId={2} onSelect={() => {}} />);
    const active = screen.getByRole("button", { name: "Średnia opłata wg dzielnicy" });
    expect(active).toHaveAttribute("aria-current", "true");
    expect(screen.getByRole("button", { name: "Ile kursów wczoraj?" })).not.toHaveAttribute(
      "aria-current",
    );
  });

  it("reports the picked session", async () => {
    const onSelect = vi.fn();
    render(<Sidebar sessions={SESSIONS} activeId={null} onSelect={onSelect} />);
    await userEvent.click(screen.getByRole("button", { name: "Ile kursów wczoraj?" }));
    expect(onSelect).toHaveBeenCalledWith(SESSIONS[1]);
  });
});

describe("healthSummary", () => {
  it("reports an all-clear when every dependency is ok", () => {
    expect(healthSummary({ ollama: "ok", bigquery: "ok", chroma_index: "ok" })).toBe(
      "wszystkie usługi OK",
    );
  });

  it("names the dependencies that are down", () => {
    expect(healthSummary({ ollama: "ok", bigquery: "down", chroma_index: "missing" })).toBe(
      "BigQuery, Indeks — brak połączenia",
    );
  });
});
