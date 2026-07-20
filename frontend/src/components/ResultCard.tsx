import { useEffect, useState } from "react";
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
 * The last column holding a finite number in every row, or null. 1C draws a
 * magnitude bar beside the measure; picking the LAST numeric column favours the
 * aggregate in a typical `SELECT dimension, AVG(x)` shape.
 */
export function barColumn(rows: Record<string, unknown>[], columns: string[]): string | null {
  const numeric = columns.filter((c) =>
    rows.every((r) => typeof r[c] === "number" && Number.isFinite(r[c] as number)),
  );
  return numeric.length ? numeric[numeric.length - 1] : null;
}

/**
 * Bar width as a CSS percentage, scaled against the largest magnitude in the
 * column. Uses absolute values so negatives still render, and returns "0%" when
 * every value is zero (no meaningful ratio) rather than dividing by zero.
 */
export function barWidth(value: number, values: number[]): string {
  const peak = Math.max(...values.map((v) => Math.abs(v)));
  if (!peak) return "0%";
  return `${Math.round((Math.abs(value) / peak) * 100)}%`;
}

/** "Copy" control for the SQL block, confirming in place for two seconds. */
function CopySql({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);
  // Clear the confirmation on unmount too, so a timer never fires into a card
  // that has already been replaced by the next question's result.
  useEffect(() => {
    if (!copied) return;
    const timer = setTimeout(() => setCopied(false), 2000);
    return () => clearTimeout(timer);
  }, [copied]);
  return (
    <button
      type="button"
      className="ml-auto cursor-pointer border-0 bg-transparent p-0 text-[10.5px] font-medium text-accent outline-none hover:text-accent-deep focus-visible:outline-2 focus-visible:outline-accent focus-visible:outline-offset-2"
      onClick={() => {
        // Older/insecure contexts have no clipboard API; stay silent rather
        // than throwing, since copying is a convenience, not the card's job.
        void navigator.clipboard?.writeText(sql).then(
          () => setCopied(true),
          () => undefined,
        );
      }}
    >
      {copied ? "Skopiowano" : "Kopiuj"}
    </button>
  );
}

/**
 * 1C result panel: the prose answer, metadata chips (attempts / GB / model), a
 * dry-run-verified SQL block, and the rows table with inline magnitude bars.
 * A refusal renders the reason and no table. Presentational only; the label,
 * scan, and bar helpers above are pure and unit-tested.
 */
export function ResultCard({ result }: ResultCardProps) {
  const columns = result.rows.length ? Object.keys(result.rows[0]) : [];
  const visible = result.rows.slice(0, 50);
  const bar = barColumn(visible, columns);
  const barValues = bar ? visible.map((r) => r[bar] as number) : [];
  return (
    <section className="mt-3.5 overflow-hidden rounded-lg border border-hair bg-panel">
      <div className="px-4 pb-2.5 pt-3.5">
        <p className="m-0 text-[14px] leading-[1.55] text-ink">{result.answer}</p>
        {result.refused && result.reason ? (
          <p className="mb-0 mt-2 text-[12.5px] leading-normal text-err">{result.reason}</p>
        ) : null}
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          <span className="rounded-[5px] border border-hair px-2 py-0.5 font-mono text-[10.5px] font-medium text-muted">
            {result.attempts} {result.attempts === 1 ? "próba" : "próby"}
          </span>
          <span className="rounded-[5px] border border-hair px-2 py-0.5 font-mono text-[10.5px] font-medium text-muted">
            {formatScan(result.scanned_gb)}
          </span>
          <span className="rounded-[5px] border border-hair px-2 py-0.5 font-mono text-[10.5px] font-medium text-muted">
            {result.model.split(":")[0]}
          </span>
        </div>
      </div>
      {result.sql ? (
        <>
          <div className="flex items-center border-y border-hair bg-subtle px-4 py-1.5">
            <span className="font-mono text-[10px] font-semibold tracking-[0.09em] text-faint">
              WYGENEROWANY SQL · SPRAWDZONY DRY-RUNEM
            </span>
            <CopySql sql={result.sql} />
          </div>
          <pre className="m-0 overflow-x-auto bg-code px-4 py-3 font-mono text-[11.5px] leading-[1.65] text-ink-soft">
            {result.sql}
          </pre>
        </>
      ) : null}
      {columns.length ? (
        <div className="border-t border-hair">
          {/* A wide SELECT * must scroll inside the panel, not overflow and
              break its border — same rule as the SQL <pre> above. */}
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-[12px] [font-variant-numeric:tabular-nums]">
              <thead>
                <tr className="bg-subtle">
                  {columns.map((c) => (
                    <th
                      key={c}
                      className="whitespace-nowrap px-4 py-[7px] text-left font-mono text-[10px] font-semibold tracking-[0.07em] text-faint uppercase"
                    >
                      {columnLabel(c, columns)}
                    </th>
                  ))}
                  {/* Claims the leftover width so the label/value columns stay
                      shrink-to-fit and the bars share one common track. */}
                  {bar ? <th className="w-full min-w-[120px] px-4" /> : null}
                </tr>
              </thead>
              <tbody>
                {visible.map((row, i) => (
                  <tr key={i} className="border-t border-hair-soft">
                    {columns.map((c) => (
                      <td
                        key={c}
                        className={`whitespace-nowrap px-4 py-1.5 ${
                          c === bar ? "text-right font-mono font-medium text-ink" : "text-ink"
                        }`}
                      >
                        {String(row[c])}
                      </td>
                    ))}
                    {bar ? (
                      <td className="w-full px-4 py-1.5">
                        <span className="block h-2 rounded-sm bg-[#eef1f6]">
                          <span
                            className="block h-2 rounded-sm bg-accent"
                            style={{ width: barWidth(row[bar] as number, barValues) }}
                          />
                        </span>
                      </td>
                    ) : null}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <div className="border-t border-hair-soft px-4 py-[7px] text-[11px] text-faint">
            {result.rows.length > 50
              ? `${visible.length} z ${result.rows.length} wierszy`
              : `${result.rows.length} ${result.rows.length === 1 ? "wiersz" : "wierszy"} · pełny wynik`}
          </div>
        </div>
      ) : null}
    </section>
  );
}
