import { HealthBar } from "../components/HealthBar";
import { QuestionForm } from "../components/QuestionForm";
import { ResultCard } from "../components/ResultCard";
import { StageTimeline } from "../components/StageTimeline";
import { useChatStream } from "../hooks/useChatStream";
import { useHealth } from "../hooks/useHealth";

/**
 * Single-screen "Linia M" chat app (approved mockup C1). Composition only —
 * all request state lives in useChatStream; children are presentational.
 */
export default function App() {
  const { frames, result, error, running, ask } = useChatStream();
  const health = useHealth();
  return (
    <main className="min-h-screen">
      <header className="flex items-center gap-3 bg-ink px-[22px] py-[14px] text-white">
        <span className="flex h-[30px] w-[30px] flex-none items-center justify-center rounded-full bg-line font-bold text-ink">
          M
        </span>
        <h1 className="m-0 text-[1.05rem] font-bold">Chat with data — NYC Taxi</h1>
        <HealthBar state={health} />
      </header>
      <div className="mx-auto max-w-[620px] px-[22px] pb-[60px] pt-[22px]">
        <QuestionForm disabled={running} onAsk={ask} />
        {frames.length || running ? <StageTimeline frames={frames} running={running} /> : null}
        {error ? (
          <p className="border-2 border-err p-[12px_14px] font-bold text-err" role="alert">
            {error}
          </p>
        ) : null}
        {result ? <ResultCard result={result} /> : null}
      </div>
    </main>
  );
}
