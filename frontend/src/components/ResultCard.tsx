import type { ChatResult } from "../types";

interface ResultCardProps {
  result: ChatResult;
}

/**
 * C1 result card: ink-bordered panel with the Polish answer, metadata chips
 * (attempts / GB scanned / model), a collapsible SQL block, and the rows table.
 * A refusal renders the reason and no table. Presentational only.
 */
export function ResultCard({ result }: ResultCardProps) {
  const columns = result.rows.length ? Object.keys(result.rows[0]) : [];
  return (
    <section className="mt-[22px] border-2 border-ink">
      <header className="bg-ink px-[14px] py-2 text-[0.78rem] uppercase tracking-[0.12em] text-white">
        Wynik kursu
      </header>
      <div className="px-[18px] py-4">
        <p className="m-0 mb-3 text-[1.3rem] leading-[1.4]">{result.answer}</p>
        {result.refused && result.reason ? (
          <p className="text-[0.9rem] text-err">{result.reason}</p>
        ) : null}
        <div className="mb-3 flex flex-wrap gap-2">
          <span className="rounded-full border-[1.5px] border-line bg-line px-3 py-0.5 text-xs font-bold">
            {result.attempts} {result.attempts === 1 ? "próba" : "próby"}
          </span>
          <span className="rounded-full border-[1.5px] border-ink px-3 py-0.5 text-xs font-bold">
            {result.scanned_gb.toFixed(4)} GB
          </span>
          <span className="rounded-full border-[1.5px] border-ink px-3 py-0.5 text-xs font-bold">
            {result.model.split(":")[0]}
          </span>
        </div>
        {result.sql ? (
          <details>
            <summary className="cursor-pointer text-[0.8rem] font-bold uppercase tracking-[0.06em]">
              Użyty SQL
            </summary>
            <pre className="overflow-x-auto bg-[#f4f4f4] p-3 font-mono text-[0.8rem] leading-[1.5]">
              {result.sql}
            </pre>
          </details>
        ) : null}
        {columns.length ? (
          <table className="mt-2 w-full border-collapse text-[0.85rem] [font-variant-numeric:tabular-nums]">
            <thead>
              <tr>
                {columns.map((c) => (
                  <th
                    key={c}
                    className="bg-ink px-2 py-[5px] text-left text-[0.75rem] tracking-[0.08em] text-white"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {result.rows.slice(0, 50).map((row, i) => (
                <tr key={i}>
                  {columns.map((c) => (
                    <td key={c} className="border-b border-[#ddd] px-2 py-1.5 font-mono">
                      {String(row[c])}
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        ) : null}
      </div>
    </section>
  );
}
