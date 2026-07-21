import { render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import App from "../app/App";

/** One `done` frame is enough: these tests are about the session rail, not the
 *  stream, and a completed request leaves the ask box enabled for the next. */
function sseResponse() {
  const frame =
    'event: stage\ndata: {"stage":"done","result":{"answer":"Done.","sql":"",' +
    '"rows":[],"scanned_gb":0.01,"attempts":1,"refused":false,"model":"gemma4"}}\n\n';
  return new Response(
    new ReadableStream({
      start(controller) {
        controller.enqueue(new TextEncoder().encode(frame));
        controller.close();
      },
    }),
    { status: 200 },
  );
}

async function ask(question: string) {
  const field = screen.getByLabelText("Question");
  await userEvent.clear(field);
  await userEvent.type(field, question);
  await userEvent.click(screen.getByRole("button", { name: "Ask" }));
  await waitFor(() => expect(screen.getByRole("button", { name: "Ask" })).toBeEnabled());
}

describe("App session rail", () => {
  beforeEach(() => {
    // /health is fetched on mount; the rail tests don't depend on its payload.
    vi.stubGlobal(
      "fetch",
      vi.fn((url: string) =>
        String(url).includes("/health")
          ? Promise.resolve(
              new Response('{"ollama":"ok","bigquery":"ok","chroma_index":"ok"}', {
                status: 200,
              }),
            )
          : Promise.resolve(sseResponse()),
      ),
    );
  });

  it("records each asked question, newest first", async () => {
    render(<App />);
    await ask("How many trips yesterday?");
    await ask("Average fare?");
    const rail = screen.getAllByRole("button", { name: /trips|fare/ });
    expect(rail.map((b) => b.textContent)).toEqual(["Average fare?", "How many trips yesterday?"]);
  });

  it("does not stack a repeat of the most recent question", async () => {
    render(<App />);
    await ask("How many trips yesterday?");
    await ask("How many trips yesterday?");
    expect(screen.getAllByRole("button", { name: "How many trips yesterday?" })).toHaveLength(1);
  });

  it("refills the ask box from a picked session", async () => {
    render(<App />);
    await ask("How many trips yesterday?");
    await ask("Average fare?");
    await userEvent.click(screen.getByRole("button", { name: "How many trips yesterday?" }));
    expect(screen.getByLabelText("Question")).toHaveValue("How many trips yesterday?");
  });

  it("reloads the active session's text over an edit when re-picked", async () => {
    render(<App />);
    await ask("How many trips yesterday?");
    const field = screen.getByLabelText("Question");
    await userEvent.clear(field);
    await userEvent.type(field, "edited");
    await userEvent.click(screen.getByRole("button", { name: "How many trips yesterday?" }));
    expect(field).toHaveValue("How many trips yesterday?");
  });
});
