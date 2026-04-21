import { useState } from "react";
import { Card, CardContent } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Trophy, TrendingDown, DollarSign, Percent, Filter } from "lucide-react";
import { cn } from "@/lib/utils";

const TRADES = [
  { id: 't001', date: '2026-04-15', matchup: 'Mets vs Braves', selection: 'Mets ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't002', date: '2026-04-15', matchup: 'Padres vs Dodgers', selection: 'Padres ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't003', date: '2026-04-15', matchup: 'NBA 5-Leg Parlay', selection: 'Multi-team spread parlay', outcome: 'LOSS', edge: 'SHARP' },
  { id: 't004', date: '2026-04-15', matchup: 'UFC Fight Night', selection: 'Favorite ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't005', date: '2026-04-15', matchup: 'Marlins vs Cubs', selection: 'Cubs -1.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't006', date: '2026-04-14', matchup: 'Celtics vs Heat', selection: 'Celtics -5.5', outcome: 'WIN', edge: 'SHARP' },
  { id: 't007', date: '2026-04-14', matchup: 'Knicks vs Pacers', selection: 'Over 224.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't008', date: '2026-04-14', matchup: 'Real Madrid vs Arsenal', selection: 'Real Madrid ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't009', date: '2026-04-13', matchup: 'Warriors vs Lakers', selection: 'Warriors ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't010', date: '2026-04-13', matchup: 'Inter Miami vs LAFC', selection: 'LAFC +0.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't011', date: '2026-04-12', matchup: 'Rangers vs Devils', selection: 'Rangers ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't012', date: '2026-04-12', matchup: 'Man City vs Arsenal (EPL)', selection: 'Man City -0.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't013', date: '2026-04-11', matchup: 'Suns vs Nuggets', selection: 'Under 228', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't014', date: '2026-04-11', matchup: 'Sablenka vs Navarro (Tennis)', selection: 'Sabalenka ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't015', date: '2026-04-10', matchup: 'Barcelona vs Atletico', selection: 'Barcelona ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't016', date: '2026-04-09', matchup: 'NBA 4-Leg SGP', selection: 'LeBron 30+ pts + Lakers ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't017', date: '2026-04-09', matchup: 'Blue Jays vs Red Sox', selection: 'Red Sox +1.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't018', date: '2026-04-08', matchup: 'Steele vs Alcaraz (Tennis)', selection: 'Alcaraz -3.5', outcome: 'WIN', edge: 'SHARP' },
  { id: 't019', date: '2026-04-08', matchup: 'UFC 312 - Main Event', selection: 'Underdog ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't020', date: '2026-04-07', matchup: 'Pirates vs Phillies', selection: 'Phillies -1.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't021', date: '2026-04-06', matchup: 'Cavaliers vs Bucks', selection: 'Cavaliers -3', outcome: 'WIN', edge: 'SHARP' },
  { id: 't022', date: '2026-04-06', matchup: 'Grizzlies vs Pelicans', selection: 'Grizzlies +4.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't023', date: '2026-04-05', matchup: 'Soccer 3-Leg Parlay', selection: 'Man City + Liverpool + Bayern ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't024', date: '2026-04-04', matchup: 'Spurs vs OKC', selection: 'OKC -7.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't025', date: '2026-04-04', matchup: 'Royals vs White Sox', selection: 'Royals ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't026', date: '2026-04-03', matchup: 'Djokovic vs Zverev (Tennis)', selection: 'Djokovic ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't027', date: '2026-04-03', matchup: 'Sinner vs Alcaraz (Tennis)', selection: 'Alcaraz ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't028', date: '2026-04-02', matchup: 'Warriors vs Clippers', selection: 'Warriors +3', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't029', date: '2026-04-01', matchup: 'UCL Bayern vs PSG', selection: 'PSG +1', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't030', date: '2026-03-31', matchup: 'NBA 5-Leg Parlay', selection: 'Celtics, Nuggets, OKC, Bucks, Cavs covers', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't031', date: '2026-03-30', matchup: 'Venezuela vs Dominican Republic (WBC)', selection: 'Venezuela ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't032', date: '2026-03-29', matchup: 'Tennis 7-Leg Parlay', selection: 'Sinner, Alcaraz, Medvedev, Swiatek, Sabalenka, Rybakina, Gauff ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't033', date: '2026-03-28', matchup: 'Timberwolves vs Thunder', selection: 'Under 214', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't034', date: '2026-03-27', matchup: 'Pelicans vs Rockets', selection: 'Rockets ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't035', date: '2026-03-26', matchup: 'Soccer 2-Leg Parlay', selection: 'Real Madrid + Ajax ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't036', date: '2026-03-25', matchup: 'Mets vs Yankees', selection: 'Mets +1.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't037', date: '2026-03-24', matchup: 'Suns vs Spurs', selection: 'Suns -9.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't038', date: '2026-03-23', matchup: 'Medvedev vs Hurkacz (Tennis)', selection: 'Medvedev ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't039', date: '2026-03-22', matchup: 'UCL Chelsea vs Real Madrid', selection: 'Real Madrid +0.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't040', date: '2026-03-21', matchup: 'NBA 3-Leg SGP Lakers', selection: 'LeBron 25+ pts, Lakers ML, Over 220', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't041', date: '2026-03-20', matchup: 'Sinner vs Fritz (Tennis)', selection: 'Sinner -4.5', outcome: 'WIN', edge: 'SHARP' },
  { id: 't042', date: '2026-03-19', matchup: 'NBA 5-Leg Spread Parlay', selection: 'Celtics -5.5, Cavs -4, Bucks -3, OKC -8.5, Nuggets -6', outcome: 'WIN', edge: 'SHARP' },
  { id: 't043', date: '2026-03-18', matchup: 'Inter Miami vs Columbus', selection: 'Inter Miami ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't044', date: '2026-03-17', matchup: 'Venezuela ML (Baseball)', selection: 'Venezuela ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't045', date: '2026-03-16', matchup: 'UCL Man City vs Juventus', selection: 'Man City ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't046', date: '2026-03-15', matchup: 'Alcaraz vs Rublev (Tennis)', selection: 'Alcaraz ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't047', date: '2026-03-14', matchup: 'Pacers vs Knicks', selection: 'Over 228.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't048', date: '2026-03-13', matchup: 'Soccer Parlay 3-Leg', selection: 'Liverpool + Man United + Arsenal ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't049', date: '2026-03-12', matchup: 'Bucks vs Bulls', selection: 'Bucks -9', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't050', date: '2026-03-11', matchup: 'WBC Puerto Rico vs Cuba', selection: 'Puerto Rico ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't051', date: '2026-03-10', matchup: 'Suns vs Warriors', selection: 'Under 228', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't052', date: '2026-03-09', matchup: 'UCL Barcelona vs Dortmund', selection: 'Barcelona -1', outcome: 'WIN', edge: 'SHARP' },
  { id: 't053', date: '2026-03-08', matchup: 'Gauff vs Swiatek (Tennis)', selection: 'Swiatek ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't054', date: '2026-03-07', matchup: 'Timberwolves vs Nuggets', selection: 'Nuggets -4.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't055', date: '2026-03-06', matchup: 'NBA 4-Leg Parlay', selection: 'Celtics, Heat, Bucks, Cavs ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't056', date: '2026-03-05', matchup: 'Santos vs Flamengo (Brazil)', selection: 'Flamengo ML', outcome: 'WIN', edge: 'SHARP' },
  { id: 't057', date: '2026-03-05', matchup: 'Draper vs Dimitrov (Tennis)', selection: 'Dimitrov ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't058', date: '2026-04-16', matchup: 'Braves vs Cardinals', selection: 'Braves ML', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't059', date: '2026-04-16', matchup: 'Nets vs Pistons', selection: 'Pistons +7.5', outcome: 'LOSS', edge: 'NEUTRAL' },
  { id: 't060', date: '2026-04-14', matchup: 'Raptors vs Bulls', selection: 'Under 218', outcome: 'LOSS', edge: 'NEUTRAL' },
];

const sportIcon = (matchup: string) => {
  const m = matchup.toLowerCase();
  if (m.includes("tennis") || /alcaraz|sinner|djokovic|medvedev|swiatek|sabalenka|gauff|fritz|rublev|zverev|navarro|draper|hurkacz|rybakina/i.test(m)) return "🎾";
  if (m.includes("ufc") || m.includes("mma")) return "🥊";
  if (m.includes("soccer") || m.includes("ucl") || m.includes("madrid") || m.includes("barcelona") || m.includes("arsenal") || m.includes("liverpool") || m.includes("city") || m.includes("ajax") || m.includes("psg") || m.includes("dortmund") || m.includes("miami") || m.includes("lafc") || m.includes("flamengo") || m.includes("santos") || m.includes("epl") || m.includes("inter") || m.includes("chelsea") || m.includes("juventus") || m.includes("man united") || m.includes("atletico") || m.includes("columbus")) return "⚽";
  if (m.includes("wbc") || m.includes("venezuela") || m.includes("dominican") || m.includes("puerto rico") || m.includes("mets") || m.includes("padres") || m.includes("marlins") || m.includes("yankees") || m.includes("braves") || m.includes("cubs") || m.includes("pirates") || m.includes("phillies") || m.includes("dodgers") || m.includes("royals") || m.includes("white sox") || m.includes("blue jays") || m.includes("red sox") || m.includes("cardinals") || m.includes("baseball")) return "⚾";
  if (m.includes("nhl") || m.includes("rangers") || m.includes("devils")) return "🏒";
  return "🏀";
};

type FilterType = "ALL" | "WIN" | "LOSS";

export default function History() {
  const [filter, setFilter] = useState<FilterType>("ALL");

  const wins = TRADES.filter((t) => t.outcome === "WIN").length;
  const losses = TRADES.filter((t) => t.outcome === "LOSS").length;
  const total = TRADES.length;
  const wr = ((wins / total) * 100).toFixed(1);

  const sharpWins = TRADES.filter((t) => t.outcome === "WIN" && t.edge === "SHARP").length;
  const sharpTotal = TRADES.filter((t) => t.edge === "SHARP").length;
  const sharpWr = sharpTotal > 0 ? ((sharpWins / sharpTotal) * 100).toFixed(0) : "0";

  const filtered = filter === "ALL" ? TRADES : TRADES.filter((t) => t.outcome === filter);

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Trophy className="w-8 h-8 text-primary" /> Betting History
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">All tracked wagers — each parlay counts as 1 bet.</p>
      </div>

      {/* Stats row */}
      <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
        <Card className="bg-green-500/10 border-green-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <Trophy className="w-5 h-5 text-green-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-green-400">{wins}</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Wins</p>
          </CardContent>
        </Card>
        <Card className="bg-red-500/10 border-red-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <TrendingDown className="w-5 h-5 text-red-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-red-400">{losses}</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Losses</p>
          </CardContent>
        </Card>
        <Card className="bg-primary/10 border-primary/30">
          <CardContent className="pt-5 pb-4 text-center">
            <Percent className="w-5 h-5 text-primary mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-primary">{wr}%</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Win Rate</p>
          </CardContent>
        </Card>
        <Card className="bg-yellow-500/10 border-yellow-500/30">
          <CardContent className="pt-5 pb-4 text-center">
            <DollarSign className="w-5 h-5 text-yellow-400 mx-auto mb-1" />
            <p className="text-3xl font-display font-bold text-yellow-400">{sharpWr}%</p>
            <p className="text-xs uppercase tracking-wider text-muted-foreground">Sharp W%</p>
          </CardContent>
        </Card>
      </div>

      {/* Filter */}
      <div className="flex items-center gap-3">
        <Filter className="w-4 h-4 text-muted-foreground" />
        {(["ALL", "WIN", "LOSS"] as FilterType[]).map((f) => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border transition-all",
              filter === f
                ? "bg-primary text-primary-foreground border-primary"
                : "border-border text-muted-foreground hover:border-primary/50"
            )}
          >
            {f === "ALL" ? `All (${total})` : f === "WIN" ? `Wins (${wins})` : `Losses (${losses})`}
          </button>
        ))}
      </div>

      {/* Trade list */}
      <div className="space-y-3">
        {filtered.map((trade) => {
          const won = trade.outcome === "WIN";
          return (
            <Card
              key={trade.id}
              className={cn(
                "border transition-colors",
                won ? "border-green-500/20 bg-green-500/5" : "border-red-500/10 bg-card/50"
              )}
            >
              <CardContent className="py-3 px-4 flex items-center justify-between gap-4">
                <div className="flex items-center gap-3 min-w-0">
                  <span className="text-xl shrink-0">{sportIcon(trade.matchup)}</span>
                  <div className="min-w-0">
                    <p className="font-medium text-sm leading-tight truncate">{trade.matchup}</p>
                    {trade.selection && (
                      <p className="text-xs text-muted-foreground truncate">{trade.selection}</p>
                    )}
                  </div>
                </div>
                <div className="flex items-center gap-3 shrink-0">
                  {trade.edge === "SHARP" && (
                    <Badge className="bg-yellow-500/10 text-yellow-400 border-yellow-500/20 text-[10px] hidden sm:flex">
                      SHARP
                    </Badge>
                  )}
                  <Badge
                    className={cn(
                      "text-xs font-bold",
                      won
                        ? "bg-green-500/15 text-green-400 border-green-500/30"
                        : "bg-red-500/10 text-red-400 border-red-500/20"
                    )}
                  >
                    {won ? "WIN" : "LOSS"}
                  </Badge>
                  <span className="text-xs text-muted-foreground hidden sm:block">
                    {new Date(trade.date).toLocaleDateString("en-US", { month: "short", day: "numeric" })}
                  </span>
                </div>
              </CardContent>
            </Card>
          );
        })}
        {filtered.length === 0 && (
          <div className="py-12 text-center border border-dashed border-border rounded-xl">
            <p className="text-muted-foreground">No trades found.</p>
          </div>
        )}
      </div>
    </div>
  );
}
