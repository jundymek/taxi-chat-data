import { render, screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { describe, expect, it, vi } from "vitest";
import { QuestionForm } from "../components/QuestionForm";

describe("QuestionForm", () => {
  it("submits a trimmed question when enabled", async () => {
    const onAsk = vi.fn();
    render(<QuestionForm disabled={false} onAsk={onAsk} />);
    await userEvent.type(screen.getByLabelText("Question"), "  How many trips?  {Enter}");
    expect(onAsk).toHaveBeenCalledWith("How many trips?");
  });

  it("does not resubmit while disabled (Enter is a no-op during a request)", async () => {
    const onAsk = vi.fn();
    render(<QuestionForm disabled={true} onAsk={onAsk} />);
    // The input stays editable so text is preserved, but Enter must not fire.
    await userEvent.type(screen.getByLabelText("Question"), "How many trips?{Enter}");
    expect(onAsk).not.toHaveBeenCalled();
  });
});
