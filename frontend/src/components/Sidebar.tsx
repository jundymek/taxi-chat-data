export interface Session {
  id: number;
  question: string;
}

interface SidebarProps {
  sessions: Session[];
  activeId: number | null;
  onSelect: (session: Session) => void;
}

/**
 * 1C console rail: the product mark, the section nav, and the list of questions
 * asked so far. Sessions live in memory for the lifetime of the tab — there is
 * no history endpoint, so nothing here is persisted or restored.
 *
 * Below `sm` the rail would crowd the working column, so it collapses to a
 * full-width strip above it; from `sm` up it is the fixed 196px column of 1C.
 */
export function Sidebar({ sessions, activeId, onSelect }: SidebarProps) {
  return (
    <aside className="flex w-full flex-none flex-col border-b border-hair bg-panel sm:w-[196px] sm:border-b-0 sm:border-r">
      <div className="flex items-center gap-2 border-b border-hair px-4 py-[14px]">
        <span className="flex h-[22px] w-[22px] items-center justify-center rounded font-mono text-[10px] font-bold text-brand bg-ink">
          tc
        </span>
        <span className="text-[12.5px] font-semibold text-ink">taxi-chat-data</span>
      </div>
      <div className="px-4 pb-1.5 pt-[14px] font-sans text-[10px] font-semibold tracking-[0.09em] text-faint">
        SESJE
      </div>
      {sessions.length ? (
        <ul className="flex list-none flex-col gap-px px-2 py-0">
          {sessions.map((session) => (
            <li key={session.id}>
              <button
                type="button"
                onClick={() => onSelect(session)}
                aria-current={session.id === activeId ? "true" : undefined}
                className={`w-full cursor-pointer rounded-md border-0 px-2.5 py-1.5 text-left text-[11.5px] leading-[1.35] outline-none focus-visible:outline-2 focus-visible:outline-accent focus-visible:-outline-offset-2 ${
                  session.id === activeId
                    ? "bg-[#eef0f4] font-medium text-ink"
                    : "bg-transparent text-muted hover:bg-shell"
                }`}
              >
                {session.question}
              </button>
            </li>
          ))}
        </ul>
      ) : (
        <p className="m-0 px-[18px] text-[11.5px] leading-[1.45] text-faint">
          Zadane pytania pojawią się tutaj.
        </p>
      )}
    </aside>
  );
}
