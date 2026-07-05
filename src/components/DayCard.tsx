import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Layers, Target, ShieldCheck, RefreshCw } from "lucide-react";
import { useMutation } from "@tanstack/react-query";
import { cn } from "@/lib/utils";

/* ─── Types mirror scripts/bank_builder.py output — real model numbers only ─── */
interface DayCardLeg {
  match: string;
  selection: string;
  decimal: number;
  prob: number;
  min_odds: number;
}

interface DayCardTicket {
  legs: DayCardLeg[];
  combined: number;
  joint_prob: number;
  min_combined: number;
  ev_pct: number;
  lane: string;
}

interface DayCardSingle {
  match: string;
  selection: string;
  decimal: number;
  prob: number;
  ev_pct: number;
  stake_pct: number;
  min_odds: number;
  stake_usd?: number;
}

interface DayCardData {
  tickets: DayCardTicket[];
  singles: DayCardSingle[];
  pass: boolean;
  note: string;
}

const BANKROLL_KEY = "caveman_bankroll";
// F1 excluded: outright race markets don't fit the ML/day-card shape.
const SUPPORTED = ["SOCCER", "NBA", "WNBA", "NFL", "MLB", "NHL", "TENNIS"];

/* Bet on Stake only when its on-screen price clears this floor. */
function StakeFloor({ floor }: { floor: number }) {
  return (
    <span className="font-mono text-xs font-black text-primary whitespace-nowrap">
      STAKE ≥ {floor.toFixed(2)}
    </span>
  );
}

export function DayCard({ sport }: { sport: string }) {
  const [bankroll, setBankroll] = useState(
    () => localStorage.getItem(BANKROLL_KEY) ?? "200",
  );

  const { mutate: build, data, isPending, error } = useMutation({
    mutationFn: async () => {
      const bank = Number(bankroll) > 0 ? Number(bankroll) : undefined;
      if (bank) localStorage.setItem(BANKROLL_KEY, String(bank));
      const res = await fetch("/api/bank-builder", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ live: true, sport, bankroll: bank }),
      });
      if (!res.ok) {
        const body = await res.json().catch(() => null) as { message?: string } | null;
        throw new Error(body?.message || `Day card failed (${res.status})`);
      }
      const json = await res.json() as { data: DayCardData };
      return json.data;
    },
  });

  if (!SUPPORTED.includes(sport)) return null;
  const isSoccer = sport === "SOCCER";

  return (
    <Card className="border-primary/20 bg-card/60">
      <CardHeader className="flex flex-row items-center justify-between gap-4 space-y-0">
        <CardTitle className="flex items-center gap-2 text-sm font-black uppercase tracking-widest">
          <Layers className="h-4 w-4 text-primary" />
          Day Card — Bank Builder
          <Badge className="bg-primary/10 text-primary border-primary/20 text-[9px] font-black">
            3–5X LANE + KELLY SINGLES
          </Badge>
        </CardTitle>
        <div className="flex items-center gap-2">
          <span className="text-[10px] font-mono text-muted-foreground uppercase">Bank $</span>
          <Input
            value={bankroll}
            onChange={(e) => setBankroll(e.target.value.replace(/[^0-9.]/g, ""))}
            className="h-8 w-20 font-mono text-xs"
            inputMode="decimal"
          />
          <Button
            size="sm"
            onClick={() => build()}
            disabled={isPending}
            className="h-8 font-black tracking-widest text-[10px] uppercase"
          >
            {isPending ? <RefreshCw className="h-3 w-3 animate-spin" /> : "Build"}
          </Button>
        </div>
      </CardHeader>

      <CardContent className="space-y-5">
        {error != null && (
          <p className="text-xs font-mono text-red-400">
            {error instanceof Error ? error.message : "Failed — is the live odds key set?"}
          </p>
        )}

        {!data && !isPending && error == null && (
          <p className="text-xs text-muted-foreground">
            {isSoccer
              ? "One click: live slate → devig → Poisson → the day's ticket and Kelly-sized singles, each with its Stake price floor."
              : `One click: live ${sport} slate → Pinnacle fair line → best price across books → ticket and Kelly-sized singles with Stake floors.`}
            {" "}Uses one Odds API request, cached 10 min.
          </p>
        )}

        {data?.pass && data.tickets.length === 0 && data.singles.length === 0 && (
          <div className="rounded-xl border border-white/10 bg-white/5 p-4">
            <p className="text-sm font-black uppercase tracking-wide">Pass. Bet nothing today.</p>
            <p className="text-xs text-muted-foreground mt-1">{data.note}</p>
          </div>
        )}

        {/* ── Tickets: the 3-5x growth lane ── */}
        {data?.tickets.map((t, i) => (
          <div key={i} className="rounded-xl border border-primary/25 bg-primary/5 p-4 space-y-2">
            <div className="flex items-center justify-between">
              <span className="flex items-center gap-2 text-sm font-black uppercase">
                <Target className="h-4 w-4 text-primary" />
                Ticket x{t.combined.toFixed(2)}
                {t.lane !== "target" && (
                  <Badge variant="outline" className="text-[9px]">OFF-LANE {t.lane.toUpperCase()}</Badge>
                )}
              </span>
              <span className="font-mono text-xs">
                win {(t.joint_prob * 100).toFixed(0)}% · EV {t.ev_pct > 0 ? "+" : ""}{t.ev_pct.toFixed(1)}%
              </span>
            </div>
            {t.legs.map((l, j) => (
              <div key={j} className="flex items-center justify-between gap-2 text-sm">
                <span className="font-bold truncate">{l.selection}
                  <span className="text-muted-foreground font-normal text-xs ml-2">{l.match}</span>
                </span>
                <span className="flex items-center gap-3 shrink-0">
                  <span className="font-mono text-xs">{l.decimal.toFixed(2)}</span>
                  <StakeFloor floor={l.min_odds} />
                </span>
              </div>
            ))}
            <p className="text-[10px] font-mono text-muted-foreground pt-1 border-t border-white/10">
              playable while combined ≥ {t.min_combined.toFixed(2)} on Stake
            </p>
          </div>
        ))}

        {/* ── Strong singles: bet more, sized by quarter-Kelly ── */}
        {data?.singles.map((s, i) => (
          <div key={i} className="rounded-xl border border-white/10 bg-white/5 p-4">
            <div className="flex items-center justify-between gap-2">
              <span className="flex items-center gap-2 text-sm font-black uppercase truncate">
                <ShieldCheck className="h-4 w-4 text-primary shrink-0" />
                {s.selection}
                <span className="text-muted-foreground font-normal text-xs normal-case truncate">{s.match}</span>
              </span>
              {s.stake_usd != null && (
                <span className="font-mono text-lg font-black text-primary shrink-0">${s.stake_usd.toFixed(0)}</span>
              )}
            </div>
            <div className={cn("flex items-center gap-4 mt-2 font-mono text-xs text-muted-foreground")}>
              <span>win {(s.prob * 100).toFixed(0)}%</span>
              <span>EV +{s.ev_pct.toFixed(1)}%</span>
              <span>{s.stake_pct.toFixed(1)}% of bank</span>
              <StakeFloor floor={s.min_odds} />
            </div>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}
