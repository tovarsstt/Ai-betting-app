import { useQuery } from "@tanstack/react-query";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Flag } from "lucide-react";

/* ─── Types mirror scripts/fetch_cfb_data.py output ─── */
interface CfbTeamSide {
  team: string;
  rank: number | null;
  record: string | null;
  score: string | null;
}

interface CfbOdds {
  provider: string | null;
  details: string | null;
  over_under: number | null;
  home_ml?: string;
  away_ml?: string;
}

interface CfbGame {
  name: string;
  date: string;
  status: string;
  home: CfbTeamSide;
  away: CfbTeamSide;
  odds: CfbOdds | null;
}

interface CfbBoardData {
  week: number | null;
  n_games: number;
  games: CfbGame[];
}

const OCHRE = "#C8860A";

function teamLabel(side: CfbTeamSide): string {
  return side.rank ? `#${side.rank} ${side.team}` : side.team;
}

export function CfbBoard() {
  const { data, isLoading, error } = useQuery({
    queryKey: ["cfb-board"],
    queryFn: async (): Promise<CfbBoardData> => {
      const res = await fetch("/api/cfb-board");
      const body = await res.json();
      if (!res.ok) throw new Error(body?.error ?? `HTTP ${res.status}`);
      return body.data as CfbBoardData;
    },
    staleTime: 15 * 60_000,
  });

  const ranked = (data?.games ?? [])
    .filter((g) => g.home.rank || g.away.rank || g.odds)
    .sort((a, b) => {
      const ra = Math.min(a.home.rank ?? 99, a.away.rank ?? 99);
      const rb = Math.min(b.home.rank ?? 99, b.away.rank ?? 99);
      return ra - rb;
    })
    .slice(0, 12);

  return (
    <Card className="border-[#2C2C2C] bg-[#1A1A1A]">
      <CardHeader className="pb-3">
        <CardTitle className="flex items-center gap-2 text-sm font-black uppercase tracking-widest text-[#F5F0E8]">
          <Flag className="h-4 w-4" style={{ color: OCHRE }} />
          College Football — Semana {data?.week ?? "…"}
        </CardTitle>
        <p className="text-[11px] text-muted-foreground">
          ESPN free (ranks AP, récords, línea DraftKings embebida). Sin modelo local — motor
          sharp-anchor.
        </p>
      </CardHeader>
      <CardContent>
        {isLoading && <p className="text-xs text-muted-foreground">Cargando tablero…</p>}
        {error != null && (
          <p className="text-xs text-[#B5533C]">{error instanceof Error ? error.message : String(error)}</p>
        )}
        {data && ranked.length === 0 && (
          <p className="text-xs text-muted-foreground">Sin juegos con ranking o línea esta semana.</p>
        )}
        {ranked.length > 0 && (
          <div className="divide-y divide-[#2C2C2C]">
            {ranked.map((g, i) => (
              <div key={i} className="flex items-center justify-between gap-3 py-2 text-xs">
                <div className="min-w-0 flex-1 text-[#F5F0E8]">
                  <div className="truncate font-bold">
                    {teamLabel(g.away)} @ {teamLabel(g.home)}
                  </div>
                  <div className="text-[10px] text-muted-foreground">
                    {g.away.record ?? "0-0"} · {g.home.record ?? "0-0"} · {g.status}
                  </div>
                </div>
                {g.odds && (
                  <div className="shrink-0 text-right font-mono tabular-nums" style={{ color: OCHRE }}>
                    <div className="font-bold">{g.odds.details}</div>
                    {g.odds.over_under != null && (
                      <div className="text-[10px] text-muted-foreground">O/U {g.odds.over_under}</div>
                    )}
                  </div>
                )}
              </div>
            ))}
          </div>
        )}
      </CardContent>
    </Card>
  );
}
