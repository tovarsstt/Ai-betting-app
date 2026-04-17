import { useState } from "react";
import { useIngestMatchup } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Zap, Target, Share2, Download, TrendingUp, CheckCircle2 } from "lucide-react";
import { toast } from "sonner";
import { SocialShareCard } from "@/components/Modules/SocialShareCard";
import { ParlayShareCard } from "@/components/Modules/ParlayShareCard";

const SPORTS = ["NBA", "MLB", "NFL", "NHL", "NCAAB", "Soccer", "Tennis", "UFC"];

type ShareState =
  | { type: "social"; data: any; pick?: any }
  | { type: "parlay"; data: any }
  | null;

function PickCard({
  title,
  badge,
  data,
  onShareSocial,
  onShareParlay,
}: {
  title: string;
  badge: string;
  data: any;
  onShareSocial: () => void;
  onShareParlay: () => void;
}) {
  const cog = data?.cognitiveData || data;
  if (!cog?.suggested_side) return null;

  const confidence = cog.confidence_score
    ? Math.round(cog.confidence_score * 100)
    : null;

  return (
    <Card className="border-primary/30 bg-card overflow-hidden animate-in fade-in slide-in-from-bottom-4 duration-500">
      <CardHeader className="bg-primary/10 border-b border-primary/20 pb-4">
        <div className="flex justify-between items-center">
          <div className="flex items-center gap-2">
            <Target className="w-4 h-4 text-primary" />
            <CardTitle className="text-sm font-bold uppercase tracking-widest text-primary">{title}</CardTitle>
          </div>
          <Badge className="bg-primary/20 text-primary border border-primary/30 text-xs">{badge}</Badge>
        </div>
        <p className="text-xs text-muted-foreground mt-1">{cog.matchup}</p>
      </CardHeader>

      <CardContent className="pt-5 space-y-4">
        {/* Main Pick */}
        <div className="p-4 rounded-xl bg-background/70 border border-border">
          <p className="text-xs uppercase tracking-wider text-muted-foreground mb-1">Recommended Play</p>
          <p className="font-display text-lg font-bold leading-tight">{cog.suggested_side}</p>
          {cog.targetOdds && (
            <span className="inline-block mt-2 px-2 py-0.5 rounded bg-primary/10 text-primary text-sm font-mono font-bold border border-primary/20">
              {cog.targetOdds}
            </span>
          )}
        </div>

        {/* Stats row */}
        <div className="grid grid-cols-3 gap-3">
          {confidence !== null && (
            <div className="text-center p-2 rounded-lg bg-muted/30 border border-border">
              <p className="text-[10px] uppercase text-muted-foreground">Confidence</p>
              <p className="font-mono font-bold text-primary text-sm">{confidence}%</p>
            </div>
          )}
          {cog.alphaEdge && (
            <div className="text-center p-2 rounded-lg bg-muted/30 border border-border">
              <p className="text-[10px] uppercase text-muted-foreground">EV Edge</p>
              <p className="font-mono font-bold text-green-400 text-sm">{cog.alphaEdge}</p>
            </div>
          )}
          {cog.ultronDominanceScore && (
            <div className="text-center p-2 rounded-lg bg-muted/30 border border-border">
              <p className="text-[10px] uppercase text-muted-foreground">Score</p>
              <p className="font-mono font-bold text-primary text-sm">{cog.ultronDominanceScore}/100</p>
            </div>
          )}
        </div>

        {/* Rationale */}
        {cog.rationale && (
          <div className="p-3 rounded-lg bg-muted/20 border border-border text-xs text-muted-foreground leading-relaxed">
            {cog.rationale}
          </div>
        )}

        {/* Share buttons */}
        <div className="flex gap-2 pt-1">
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs border-primary/30 text-primary hover:bg-primary/10"
            onClick={onShareSocial}
          >
            <Download className="w-3 h-3 mr-1.5" /> Social Card
          </Button>
          <Button
            size="sm"
            variant="outline"
            className="flex-1 text-xs border-muted-foreground/30 hover:bg-muted/20"
            onClick={onShareParlay}
          >
            <Share2 className="w-3 h-3 mr-1.5" /> Share Parlay
          </Button>
        </div>
      </CardContent>
    </Card>
  );
}

export default function Matchups() {
  const ingestMutation = useIngestMatchup();
  const [matchupText, setMatchupText] = useState("");
  const [sport, setSport] = useState("NBA");
  const [results, setResults] = useState<any>(null);
  const [shareCard, setShareCard] = useState<ShareState>(null);

  const handleAnalyze = () => {
    if (!matchupText.trim()) {
      toast.error("Enter a matchup first (e.g. Warriors vs Lakers)");
      return;
    }

    setResults(null);
    toast.loading("Analyzing matchup...", { id: "analyze" });

    ingestMutation.mutate(
      { sport, matchup: matchupText, trueProbability: 0.55, marketDecimalOdds: 1.9 },
      {
        onSuccess: (data) => {
          toast.success("Analysis complete!", { id: "analyze" });
          setResults(data);
          setMatchupText("");
        },
        onError: (err: any) => {
          toast.error(err.message || "Analysis failed", { id: "analyze" });
        },
      }
    );
  };

  const getCog = (key: "standard" | "sgp" | "slate") =>
    results?.[key]?.cognitiveData || results?.[key] || null;

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <TrendingUp className="w-8 h-8 text-primary" /> Analyze Matchup
        </h2>
        <p className="text-muted-foreground mt-1 text-sm">
          Enter a sport and matchup — the engine delivers your picks instantly.
        </p>
      </div>

      {/* Input Card */}
      <Card className="border-primary/40 bg-primary/5 shadow-lg shadow-primary/10">
        {ingestMutation.isPending && (
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm z-10 flex flex-col items-center justify-center rounded-xl">
            <Zap className="w-10 h-10 text-primary animate-pulse mb-3" />
            <p className="font-display font-bold tracking-widest text-primary text-lg">ANALYZING...</p>
          </div>
        )}
        <CardContent className="pt-6 space-y-5 relative">
          {/* Sport selector */}
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Select Sport</p>
            <div className="flex flex-wrap gap-2">
              {SPORTS.map((s) => (
                <button
                  key={s}
                  onClick={() => setSport(s)}
                  className={`px-4 py-1.5 rounded-full text-xs font-bold uppercase tracking-wider border transition-all ${
                    sport === s
                      ? "bg-primary text-primary-foreground border-primary shadow-[0_0_10px_rgba(0,255,255,0.3)]"
                      : "bg-transparent text-muted-foreground border-border hover:border-primary/50 hover:text-foreground"
                  }`}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Matchup input + button */}
          <div className="flex flex-col sm:flex-row gap-3">
            <Input
              value={matchupText}
              onChange={(e) => setMatchupText(e.target.value)}
              onKeyDown={(e) => e.key === "Enter" && handleAnalyze()}
              placeholder={`${sport} matchup — e.g. Warriors vs Lakers`}
              className="flex-1 border-border/60 bg-background/50"
            />
            <Button
              onClick={handleAnalyze}
              disabled={ingestMutation.isPending}
              className="font-bold tracking-widest bg-primary hover:bg-primary/90 text-primary-foreground sm:w-36 h-10"
            >
              <Zap className="w-4 h-4 mr-2" /> ANALYZE
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results && (
        <div className="space-y-6">
          <div className="flex items-center gap-3 pb-2 border-b border-border">
            <CheckCircle2 className="w-5 h-5 text-green-500" />
            <h3 className="text-lg font-display font-bold">Picks Ready</h3>
            <Badge variant="outline" className="text-xs">{sport}</Badge>
          </div>

          <div className="grid grid-cols-1 lg:grid-cols-3 gap-5">
            <PickCard
              title="Standard Pick"
              badge="Best Bet"
              data={getCog("standard")}
              onShareSocial={() =>
                setShareCard({ type: "social", data: getCog("standard") })
              }
              onShareParlay={() =>
                setShareCard({ type: "parlay", data: getCog("standard") })
              }
            />
            <PickCard
              title="Same-Game Parlay"
              badge="SGP"
              data={getCog("sgp")}
              onShareSocial={() =>
                setShareCard({ type: "social", data: getCog("sgp") })
              }
              onShareParlay={() =>
                setShareCard({ type: "parlay", data: getCog("sgp") })
              }
            />
            <PickCard
              title="Slate Parlay"
              badge="Multi-Game"
              data={getCog("slate")}
              onShareSocial={() =>
                setShareCard({ type: "social", data: getCog("slate") })
              }
              onShareParlay={() =>
                setShareCard({ type: "parlay", data: getCog("slate") })
              }
            />
          </div>
        </div>
      )}

      {/* Social card modals */}
      {shareCard?.type === "social" && (
        <SocialShareCard
          data={shareCard.data}
          specificPick={shareCard.pick}
          onClose={() => setShareCard(null)}
        />
      )}
      {shareCard?.type === "parlay" && (
        <ParlayShareCard
          data={shareCard.data}
          onClose={() => setShareCard(null)}
        />
      )}
    </div>
  );
}
