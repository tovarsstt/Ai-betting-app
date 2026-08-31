import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Radio } from "lucide-react";
import { useMutation } from "@tanstack/react-query";

/* ─── Types mirror scripts/soccer_live.py + edge_api /soccer-live ─── */
interface LiveLineEv {
  market: string;
  line: number;
  side: string;
  price: number;
  ev_cold?: number;
  ev_tempo?: number;
  error?: string;
}

interface LiveScanData {
  status: string;
  error?: string;
  live?: { minute: number; score: string; total_sot?: number | null; status?: string; event?: string };
  tempo_mult?: number;
  probs?: Record<string, number>;
  lines?: LiveLineEv[];
  market_anchor_note?: string;
}

const OCHRE = "#C8860A";
const LEAGUES = [
  "Serie A",
  "Premier League",
  "La Liga",
  "Bundesliga",
  "Ligue 1",
  "Champions League",
  "Europa League",
];
// Rows shown from the probs dict: label -> key. Bet info dominates.
const PROB_ROWS: Array<[string, string]> = [
  ["Local gana", "home"],
  ["Empate", "draw"],
  ["Visita gana", "away"],
  ["Local DNB", "home_dnb"],
  ["Visita DNB", "away_dnb"],
  ["1X", "home_dc"],
  ["X2", "away_dc"],
  ["Over 1.5", "over_1_5"],
  ["Over 2.5", "over_2_5"],
  ["Over 3.5", "over_3_5"],
  ["Under 3.5", "under_3_5"],
  ["BTTS sí", "btts"],
];
const FLOOR_MARGIN = 1.04; // Stake floor = fair price + 4% cushion

function pct(p: number): string {
  return `${(p * 100).toFixed(1)}%`;
}

function evColor(ev?: number): string {
  if (ev == null) return "#F5F0E8";
  if (ev > 0.02) return "#7BA05B";
  if (ev < -0.05) return "#B5533C";
  return "#F5F0E8";
}

export function LiveScan() {
  const [league, setLeague] = useState("Serie A");
  const [home, setHome] = useState("");
  const [away, setAway] = useState("");
  const [line, setLine] = useState("");
  const [price, setPrice] = useState("");
  const [side, setSide] = useState<"over" | "under">("over");

  const { mutate: scan, data, isPending, error } = useMutation({
    mutationFn: async (): Promise<LiveScanData> => {
      const lines =
        line && price
          ? [{ market: "total", line: parseFloat(line), price: parseFloat(price), side }]
          : [];
      const res = await fetch("/api/soccer-live", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ league, home, away, lines }),
      });
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
      return body.data as LiveScanData;
    },
  });

  const probs = data?.probs;

  return (
    <Card className="border-[#2C2C2C] bg-[#1A1A1A]">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-[#F5F0E8]">
          <Radio className="h-4 w-4" style={{ color: OCHRE }} />
          Live Scan — precio justo en vivo
        </CardTitle>
        <p className="text-[11px] text-muted-foreground">
          Poisson decaído por reloj + marcador real (ESPN). Nombres como en los ratings (ej.
          &quot;Roma&quot;, &quot;Vallecano&quot;).
        </p>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="flex flex-wrap gap-2">
          <select
            value={league}
            onChange={(e) => setLeague(e.target.value)}
            className="h-9 rounded-md border border-[#2C2C2C] bg-[#2C2C2C] px-2 text-xs text-[#F5F0E8]"
          >
            {LEAGUES.map((l) => (
              <option key={l}>{l}</option>
            ))}
          </select>
          <Input
            placeholder="Local"
            value={home}
            onChange={(e) => setHome(e.target.value)}
            className="h-9 w-32 text-xs"
          />
          <Input
            placeholder="Visita"
            value={away}
            onChange={(e) => setAway(e.target.value)}
            className="h-9 w-32 text-xs"
          />
          <Input
            placeholder="Línea (4.25)"
            value={line}
            onChange={(e) => setLine(e.target.value)}
            className="h-9 w-24 text-xs"
          />
          <Input
            placeholder="Cuota"
            value={price}
            onChange={(e) => setPrice(e.target.value)}
            className="h-9 w-20 text-xs"
          />
          <button
            onClick={() => setSide(side === "over" ? "under" : "over")}
            className="h-9 rounded-md border border-[#2C2C2C] px-2 text-xs font-bold uppercase text-[#F5F0E8]"
          >
            {side}
          </button>
          <Button
            onClick={() => scan()}
            disabled={isPending || !home || !away}
            className="h-9 bg-[#C8860A] text-xs font-black uppercase tracking-wider text-[#1A1A1A] hover:bg-[#a86f08]"
          >
            {isPending ? "Escaneando…" : "Scan"}
          </Button>
        </div>

        {error != null && (
          <p className="text-xs text-[#B5533C]">{error instanceof Error ? error.message : String(error)}</p>
        )}
        {data && data.status !== "OK" && (
          <p className="text-xs text-[#B5533C]">
            {data.status}: {data.error}
          </p>
        )}

        {data && data.status === "OK" && data.live && probs && (
          <div className="space-y-2">
            <div className="flex items-baseline gap-3">
              <span className="text-2xl font-black tabular-nums text-[#F5F0E8]">{data.live.score}</span>
              <span className="text-xs text-muted-foreground">
                min {data.live.minute} · {data.live.status} · tempo x{data.tempo_mult?.toFixed(2)}
                {data.live.total_sot != null ? ` · ${data.live.total_sot} SOT` : ""}
              </span>
            </div>
            <table className="w-full text-xs">
              <thead>
                <tr className="text-left text-[10px] uppercase tracking-wider text-muted-foreground">
                  <th className="py-1">Mercado</th>
                  <th className="text-right">Prob</th>
                  <th className="text-right">Fair</th>
                  <th className="text-right">Piso Stake</th>
                </tr>
              </thead>
              <tbody>
                {PROB_ROWS.filter(([, k]) => probs[k] != null && probs[k] > 0.005 && probs[k] < 0.995).map(
                  ([label, k]) => (
                    <tr key={k} className="border-t border-[#2C2C2C] text-[#F5F0E8]">
                      <td className="py-1">{label}</td>
                      <td className="text-right font-mono tabular-nums">{pct(probs[k])}</td>
                      <td className="text-right font-mono tabular-nums">{(1 / probs[k]).toFixed(2)}</td>
                      <td className="text-right font-mono font-bold tabular-nums" style={{ color: OCHRE }}>
                        {((1 / probs[k]) * FLOOR_MARGIN).toFixed(2)}
                      </td>
                    </tr>
                  ),
                )}
              </tbody>
            </table>
            {data.lines && data.lines.length > 0 && (
              <div className="rounded-md border border-[#2C2C2C] p-2">
                {data.lines.map((l, i) => (
                  <div key={i} className="flex items-center justify-between text-xs text-[#F5F0E8]">
                    <span>
                      {l.side} {l.line} @ {l.price.toFixed(2)}
                    </span>
                    <span className="font-mono tabular-nums">
                      <span style={{ color: evColor(l.ev_cold) }}>frío {((l.ev_cold ?? 0) * 100).toFixed(1)}%</span>
                      {" · "}
                      <span style={{ color: evColor(l.ev_tempo) }}>
                        tempo {((l.ev_tempo ?? 0) * 100).toFixed(1)}%
                      </span>
                    </span>
                  </div>
                ))}
              </div>
            )}
            <p className="text-[10px] leading-snug text-muted-foreground">{data.market_anchor_note}</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}
