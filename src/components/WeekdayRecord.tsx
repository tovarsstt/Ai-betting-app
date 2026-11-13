import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";

// Weekday record from the user's own settled Stake bets (GET /api/stake-history/weekday?day=Thu).
// Shows ROI per day plus, for the selected day, how much of the result is explained by WHAT was bet (mix) vs chance (permutation p).
interface DowRow { dow: string; bets: number; staked: number; net: number; roi: number; hit: number; sgm_share: number }
interface WeekdayData {
  n: number; range: [string, string]; overall_roi: number; day: string;
  by_dow: DowRow[];
  perm: { obs_roi: number; p_value_lower: number };
  boot_ci: [number, number];
  mix: { expected_roi_given_mix: number; actual_roi: number; other_days_roi: number };
  day_by_sport: Record<string, { n: number; roi: number }>;
}
const ES: Record<string, string> = { Mon: "Lun", Tue: "Mar", Wed: "Mié", Thu: "Jue", Fri: "Vie", Sat: "Sáb", Sun: "Dom" };
const pct = (x: number) => `${x >= 0 ? "+" : ""}${(x * 100).toFixed(0)}%`;

export default function WeekdayRecord({ day = "Thu" }: { day?: string }) {
  const q = useQuery({
    queryKey: ["stake-weekday", day],
    queryFn: async () => {
      const r = await fetch(`/api/stake-history/weekday?day=${day}`);
      if (!r.ok) throw new Error(String(r.status));
      return (await r.json()).data as WeekdayData;
    },
    staleTime: 10 * 60_000,
  });
  if (q.isLoading) return <p className="text-xs text-muted-foreground">Calculando rendimiento por día…</p>;
  if (q.isError || !q.data) return <p className="text-xs text-muted-foreground">Historial de Stake no disponible (corre scripts/stake_history.py parse).</p>;
  const d = q.data;
  const max = Math.max(...d.by_dow.map((r) => Math.abs(r.roi)), 0.01);
  const worstSport = Object.entries(d.day_by_sport).filter(([, v]) => v.n >= 10).sort((a, b) => a[1].roi - b[1].roi)[0];
  return (
    <Card className="border-white/10 bg-white/[0.02]">
      <CardHeader className="pb-2">
        <CardTitle className="text-xs font-black uppercase tracking-[0.25em] text-muted-foreground">
          Rendimiento por día · {d.n} apuestas ({d.range[0]} → {d.range[1]})
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="space-y-1">
          {d.by_dow.map((r) => (
            <div key={r.dow} className="flex items-center gap-2 text-xs tabular-nums">
              <span className={`w-8 ${r.dow === day ? "font-bold" : "text-muted-foreground"}`}>{ES[r.dow]}</span>
              <div className="relative h-3 flex-1 bg-white/[0.03]">
                <div
                  className={`absolute top-0 h-3 ${r.roi >= 0 ? "left-1/2 bg-emerald-500/70" : "right-1/2 bg-red-500/70"}`}
                  style={{ width: `${(Math.abs(r.roi) / max) * 50}%` }}
                />
              </div>
              <span className={`w-12 text-right ${r.roi >= 0 ? "text-emerald-400" : "text-red-400"}`}>{pct(r.roi)}</span>
              <span className="w-24 text-right text-muted-foreground">{r.bets} · ${r.net.toFixed(0)}</span>
            </div>
          ))}
        </div>
        <ul className="space-y-1 text-xs text-muted-foreground">
          <li>
            {ES[d.day]}: <b className="text-foreground">{pct(d.mix.actual_roi)}</b> vs {pct(d.mix.other_days_roi)} el resto. Por lo que se apuesta (tipo, patas, cuota) se esperaba{" "}
            {pct(d.mix.expected_roi_given_mix)}; el resto es deporte/mercado y varianza.
          </li>
          {worstSport && (
            <li>
              Peor deporte en {ES[d.day]}: <b className="text-foreground">{worstSport[0]}</b> {pct(worstSport[1].roi)} ({worstSport[1].n} apuestas).
            </li>
          )}
          <li>
            Probabilidad de verlo por azar: {(d.perm.p_value_lower * 100).toFixed(0)}% · intervalo 95%: {pct(d.boot_ci[0])} a {pct(d.boot_ci[1])}.
          </li>
        </ul>
      </CardContent>
    </Card>
  );
}
