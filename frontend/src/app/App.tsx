import { useCallback, useRef, useState } from "react";
import { HealthBar } from "../components/HealthBar";
import { QuestionForm } from "../components/QuestionForm";
import { ResultCard } from "../components/ResultCard";
import { Sidebar, type Session } from "../components/Sidebar";
import { StageTimeline } from "../components/StageTimeline";
import { useChatStream } from "../hooks/useChatStream";
import { useHealth } from "../hooks/useHealth";

/**
 * Two-column operations console (design direction 1C): a session rail beside
 * the working column — ask box, stage stream, result. Composition only; request
 * state lives in useChatStream and children stay presentational.
 *
 * Sessions are the questions asked in this tab. There is no history endpoint,
 * so the list is in-memory: picking one refills the ask box, it does not
 * restore that question's result.
 */
export default function App() {
  const { frames, result, error, running, ask } = useChatStream();
  const health = useHealth();
  const [sessions, setSessions] = useState<Session[]>([]);
  const [active, setActive] = useState<Session | null>(null);
  const nextId = useRef(1);
  // Bumped on every rail click so re-picking the session already showing still
  // reloads its text over whatever the user typed in the meantime.
  const [pickCount, setPickCount] = useState(0);
  const pick = useCallback((session: Session) => {
    setActive(session);
    setPickCount((n) => n + 1);
  }, []);

  const handleAsk = useCallback(
    (question: string) => {
      const session = { id: nextId.current++, question };
      // Keep newest first, and collapse a repeat of the most recent question
      // instead of stacking duplicate rail entries.
      setSessions((prev) =>
        prev[0]?.question === question ? prev : [session, ...prev].slice(0, 30),
      );
      setActive(session);
      void ask(question);
    },
    [ask],
  );


  return (
    <div className="flex min-h-screen flex-col bg-shell sm:flex-row">
      <Sidebar sessions={sessions} activeId={active?.id ?? null} onSelect={pick} />
      <main className="min-w-0 flex-1 px-[22px] pb-6 pt-[18px]">
        <div className="mx-auto max-w-[760px]">
          <div className="mb-3.5 flex items-center gap-2.5">
            <h1 className="m-0 text-[13px] font-semibold text-ink">New question</h1>
            <HealthBar state={health} />
          </div>
          <QuestionForm
            disabled={running}
            preset={active ? { id: pickCount, question: active.question } : undefined}
            onAsk={handleAsk}
          />
          {frames.length || running ? (
            <StageTimeline frames={frames} running={running} />
          ) : null}
          {error ? (
            <p
              className="mt-3.5 rounded-lg border border-warn-line bg-warn-bg px-[13px] py-[9px] text-[12px] leading-normal text-warn"
              role="alert"
            >
              {error}
            </p>
          ) : null}
          {result ? <ResultCard result={result} /> : null}
        </div>
      </main>
    </div>
  );
}
