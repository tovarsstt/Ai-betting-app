import { useState } from "react";
import { Button } from "@/components/ui/button";
import { ScanLine } from "lucide-react";

const OCHRE = "#C8860A";

interface LegResult { label: string; prob: number | null; note: string; decimal: number | null }
interface BlockResult {
  sgp: boolean; decimal: number | null; prob: number | null; need: number | null;
  ev_pct: number | null; corr_factor: number; corr_games: number; legs: LegResult[];
}
interface TicketResult {
  header: string; decimal: number | null; stake: number | null; payout: number | null;
  blocks: BlockResult[]; unpriced: string[];
  prob_all?: number; need?: number; ev_pct?: number; weakest?: string | null;
  hits_dist?: Record<string, number>;
  prob_all_if_unpriced_fair?: number; ev_pct_if_unpriced_fair?: number;
}
interface SlipPayload { season: number; week: number; tickets: TicketResult[] }

function pct(x: number | null | undefined): string {
  if (x == null) return "—";
  return x >= 0.01 || x === 0 ? `${(x * 100).toFixed(1)}%` : `${(x * 100).toFixed(3)}%`;
}

function Ev({ v }: { v: number | null | undefined }) {
  if (v == null) return null;
  const good = v > 0;
  return (
    <span className="text-[10px] font-black font-mono px-2 py-0.5"
      style={{ color: good ? "#22c55e" : "#9ca3af", border: `1px solid ${good ? "rgba(34,197,94,0.3)" : "rgba(255,255,255,0.08)"}` }}>
      EV {good ? "+" : ""}{v.toFixed(1)}%
    </span>
  );
}

function Ticket({ t }: { t: TicketResult }) {
  const hits = t.hits_dist ? Object.entries(t.hits_dist).sort((a, b) => Number(b[0]) - Number(a[0])) : [];
  return (
    <div className="border border-white/10 bg-white/[0.02] p-4 space-y-3">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <div className="font-bold text-sm">{t.header} @ {t.decimal}</div>
          <div className="text-[11px] text-muted-foreground">stake {t.stake ?? "?"} · pays {t.payout ?? "?"}</div>
        </div>
        {t.prob_all != null && (
          <div className="text-right">
            <div className="text-3xl font-black tabular-nums" style={{ color: OCHRE }}>{pct(t.prob_all)}</div>
            <div className="text-[9px] uppercase tracking-widest text-muted-foreground">
              all legs hit · needs {pct(t.need)} <Ev v={t.ev_pct} />
            </div>
          </div>
        )}
      </div>

      <div className="space-y-2">
        {t.blocks.map((b, i) => (
          <div key={i} className="border-l-2 pl-3" style={{ borderColor: b.prob != null && b.need != null && b.prob >= b.need ? "#22c55e" : "rgba(255,255,255,0.12)" }}>
            <div className="flex flex-wrap items-center gap-3 text-sm">
              <span className="font-black tabular-nums w-14">{pct(b.prob)}</span>
              <span className="font-bold">{b.sgp ? "Same game" : b.legs[0]?.label}</span>
              <span className="text-[11px] text-muted-foreground font-mono">@{b.decimal} · needs {pct(b.need)}</span>
              <Ev v={b.ev_pct} />
            </div>
            {(b.sgp || b.legs.some(l => l.prob == null)) && b.legs.map((l, j) => (
              <div key={j} className="text-[11px] text-muted-foreground pl-14">
                <span className="text-foreground/80">{pct(l.prob)}</span> {l.label} — {l.note}
              </div>
            ))}
            {!b.sgp && b.legs[0]?.prob != null && (
              <div className="text-[11px] text-muted-foreground pl-14">{b.legs[0].note}</div>
            )}
            {b.sgp && b.corr_games > 0 && (
              <div className="text-[10px] text-muted-foreground/70 pl-14">
                correlation ×{b.corr_factor} measured over {b.corr_games} shared games
              </div>
            )}
          </div>
        ))}
      </div>

      {hits.length > 0 && (
        <div className="text-[11px] text-muted-foreground font-mono">
          legs hit: {hits.map(([k, v]) => `${k}: ${pct(v)}`).join(" · ")}
          {t.weakest && <> · weakest: <span className="text-foreground">{t.weakest}</span></>}
        </div>
      )}
      {t.prob_all_if_unpriced_fair != null && (
        <div className="text-[11px] text-muted-foreground">
          If unpriced legs are exactly fair at the book price: all hit {pct(t.prob_all_if_unpriced_fair)} · EV {t.ev_pct_if_unpriced_fair?.toFixed(1)}%
        </div>
      )}
      {t.unpriced.length > 0 && (
        <div className="text-[11px]" style={{ color: OCHRE }}>
          Not priced (no model — not guessed): {t.unpriced.join(", ")}
        </div>
      )}
    </div>
  );
}

export default function SlipCheckPage() {
  const [text, setText] = useState("");
  const [data, setData] = useState<SlipPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  async function check() {
    setLoading(true);
    setError(null);
    try {
      const res = await fetch("/api/price-slip", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ text }),
      });
      const body = await res.json();
      if (!res.ok || !body.success) throw new Error(body.error || `${res.status}`);
      setData(body.data);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="space-y-6">
      <div>
        <h2 className="text-2xl font-display font-black uppercase tracking-wide flex items-center gap-3">
          <ScanLine className="w-6 h-6" style={{ color: OCHRE }} />
          Slip Check
        </h2>
        <p className="text-xs text-muted-foreground uppercase tracking-widest mt-1">
          Paste your Stake ticket. Real hit chance per leg and for the whole ticket. Win % first, EV second.
        </p>
      </div>

      <textarea value={text} onChange={e => setText(e.target.value)} rows={10}
        placeholder={"4 Multi tramo\n7,23\nSeattle Seahawks (-6.5)\nHándicap (incl. prórroga)\n1,65\n..."}
        className="w-full bg-white/[0.03] border border-white/10 p-3 font-mono text-xs focus:outline-none focus:border-[#C8860A]" />
      <Button onClick={check} disabled={loading || !text.trim()}
        style={{ background: OCHRE, color: "#1A1A1A" }} className="font-black uppercase tracking-widest">
        {loading ? "Simulating..." : "Check slip"}
      </Button>
      {error && <p className="text-sm text-red-400">Slip check failed: {error}</p>}

      {data && (
        <div className="space-y-4">
          <p className="text-[10px] text-muted-foreground/60 font-mono">
            NFL {data.season} week {data.week} · spreads/ML/totals = Judge margin model · props = real 2025-26 game logs, recency weighted · 21+ entertainment only
          </p>
          {data.tickets.map((t, i) => <Ticket key={i} t={t} />)}
          {!data.tickets.length && <p className="text-sm text-muted-foreground">No ticket found in that text.</p>}
        </div>
      )}
    </div>
  );
}
