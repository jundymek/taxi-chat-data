import { useState } from "react";

interface QuestionFormProps {
  disabled: boolean;
  onAsk: (question: string) => void;
}

/** The C1 ask box: 2px ink border, flush yellow "Zapytaj" button. */
export function QuestionForm({ disabled, onAsk }: QuestionFormProps) {
  const [question, setQuestion] = useState("");
  return (
    <form
      className="flex border-2 border-ink"
      onSubmit={(e) => {
        e.preventDefault();
        if (question.trim()) onAsk(question.trim());
      }}
    >
      <input
        className="flex-1 border-0 px-[14px] py-3 text-base outline-none focus-visible:outline-[3px] focus-visible:outline-line focus-visible:[outline-offset:-3px]"
        value={question}
        onChange={(e) => setQuestion(e.target.value)}
        placeholder="Zadaj pytanie o przejazdy taxi…"
        aria-label="Pytanie"
      />
      <button
        className="border-0 bg-line px-5 py-3 font-bold text-ink outline-none focus-visible:outline-[3px] focus-visible:outline-ink focus-visible:[outline-offset:-3px] disabled:cursor-default disabled:opacity-50"
        type="submit"
        disabled={disabled || !question.trim()}
      >
        Zapytaj
      </button>
    </form>
  );
}
