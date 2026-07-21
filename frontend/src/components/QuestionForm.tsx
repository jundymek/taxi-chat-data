import { useEffect, useState } from "react";

interface QuestionFormProps {
  disabled: boolean;
  /**
   * Text to load into the field when a session is picked in the rail. `id` is
   * the identity of the PICK, not of the session — the caller changes it on
   * every click, so re-picking the session already shown still reloads its
   * text over whatever the user typed.
   */
  preset?: { id: number; question: string };
  onAsk: (question: string) => void;
}

/** The 1C ask box: a white panel with a flush dark "Ask" button. */
export function QuestionForm({ disabled, preset, onAsk }: QuestionFormProps) {
  const [question, setQuestion] = useState("");
  // Keyed on the pick id, not the text: typing is never clobbered until the
  // user actually clicks a session again, and re-picking the same one works.
  const presetId = preset?.id;
  const presetText = preset?.question;
  useEffect(() => {
    if (presetText !== undefined) setQuestion(presetText);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- the pick is the trigger
  }, [presetId]);
  return (
    <form
      className="flex rounded-lg border border-edge bg-panel shadow-[0_1px_2px_rgba(20,24,33,.05)] focus-within:border-accent"
      onSubmit={(e) => {
        e.preventDefault();
        // Guard on `disabled` too: otherwise Enter in the field resubmits and
        // aborts an in-flight request even though the button is disabled.
        if (!disabled && question.trim()) onAsk(question.trim());
      }}
    >
      <input
        className="min-w-0 flex-1 border-0 bg-transparent px-3.5 py-[11px] text-[13.5px] text-ink outline-none placeholder:text-faint"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Ask a question about taxi trips…"
        aria-label="Question"
      />
      {/* Disabled uses an explicit colour pair, not opacity: fading white on
          near-black drops the label to ~1.5:1, unreadable while you wait. */}
      <button
        className="m-1.5 cursor-pointer rounded-md border-0 bg-ink px-4 text-[12px] font-semibold text-white outline-none hover:bg-ink-soft focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2 disabled:cursor-default disabled:bg-hair-soft disabled:text-muted"
        type="submit"
        disabled={disabled || !question.trim()}
      >
        Ask
      </button>
    </form>
  );
}
