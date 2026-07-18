import type { ChatResult } from "../types";

interface ResultCardProps {
  result: ChatResult;
}

const TECH_COL = /^f\d+_$/; // BigQuery auto-name for an unaliased SELECT expr.

/** Human label for a table column. Technical BigQuery names (f0_, f1_, …)
 *  become "Wynik" (single) or "Wynik N" (several); other names pass through. */
export function columnLabel(key: string, allKeys: string[]): string {
  if (!TECH_COL.test(key)) return key;
  const tech = allKeys.filter((k) => TECH_COL.test(k));
  if (tech.length <= 1) return "Wynik";
  return `Wynik ${tech.indexOf(key) + 1}`;
}

/** Captioned scan size in GB, 2 decimals; tiny scans as "<0.01 GB". */
export function formatScan(gb: number): string {
  const size = gb < 0.01 ? "<0.01 GB" : `${gb.toFixed(2)} GB`;
  return `Przeskanowano ${size}`;
}

/**
 * C1 result card: ink-bordered panel with the Polish answer, metadata chips
 * (attempts / GB scanned / model), a collapsible SQL block, and the rows table.
 * A refusal renders the reason and no table. Presentational only; label logic
 * lives in the exported pure helpers above.
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
            {formatScan(result.scanned_gb)}
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
          // A wide SELECT * (many columns) must scroll inside the card, not
          // overflow and break its border — same pattern as the SQL <pre> above.
          <div className="mt-2 overflow-x-auto">
            <table className="w-full border-collapse text-[0.85rem] [font-variant-numeric:tabular-nums]">
              <thead>
                <tr>
                  {columns.map((c) => (
                    <th
                      key={c}
                      className="whitespace-nowrap bg-ink px-2 py-[5px] text-left text-[0.75rem] tracking-[0.08em] text-white"
                    >
                      {columnLabel(c, columns)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {result.rows.slice(0, 50).map((row, i) => (
                  <tr key={i}>
                    {columns.map((c) => (
                      <td
                        key={c}
                        className="whitespace-nowrap border-b border-[#ddd] px-2 py-1.5 font-mono"
                      >
                        {String(row[c])}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    </section>
  );
}
