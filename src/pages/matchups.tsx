import { useState } from "react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { Cpu, Zap, Target, TrendingUp } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { useAnalyzeUnified } from "../hooks/useApi";
import type { SwarmFinalPayload, SwarmAgentData } from "../types/swarm";

const SPORTS = ["NBA", "MLB", "NFL", "NHL", "SOCCER", "TENNIS", "UFC"];

function AgentCard({ title, agentData, color }: { title: string; agentData: SwarmAgentData; color: string }) {
  if (!agentData) return null;
  return (
    <Card className={cn("border overflow-hidden", `border-${color}-500/30 bg-${color}-500/5`)}>
      <CardHeader className={cn("border-b pb-4", `bg-${color}-500/10 border-${color}-500/20`)}>
        <div className="flex justify-between items-start gap-3">
          <div className="min-w-0">
            <CardTitle className={cn("font-display flex items-center gap-2 text-sm uppercase tracking-widest", `text-${color}-400`)}>
              <Cpu className="w-4 h-4 shrink-0" /> {title}
            </CardTitle>
            <p className="font-bold text-lg mt-1 text-foreground leading-tight">{agentData.primary_single}</p>
          </div>
          {agentData.confidence_score && (
            <Badge className={cn("shrink-0 text-base py-1 px-3", `bg-${color}-500/20 text-${color}-400 border-${color}-500/30`)}>
              {Math.round(agentData.confidence_score * 100)}%
            </Badge>
          )}
        </div>
        {agentData.value_gap && (
          <p className={cn("text-xs font-mono font-bold mt-2", `text-${color}-300`)}>{agentData.value_gap}</p>
        )}
      </CardHeader>
      <CardContent className="pt-5 space-y-4">
        {agentData.sgp_blueprint?.map((leg, i) => (
          <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-background/40 border border-border/50">
            <div className={cn("p-1.5 rounded-md border shrink-0", `bg-${color}-500/10 border-${color}-500/20`)}>
              <Target className={cn("w-4 h-4", `text-${color}-400`)} />
            </div>
            <div className="min-w-0">
              <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{leg.label}</p>
              <p className="font-bold text-foreground">{leg.value}</p>
              <p className="text-xs text-muted-foreground mt-0.5 leading-relaxed">{leg.rationale}</p>
            </div>
          </div>
        ))}
        {agentData.omni_report && (
          <div className="p-3 rounded-lg bg-muted/30 border border-border text-sm">
            <p className="text-muted-foreground leading-relaxed italic">"{agentData.omni_report}"</p>
          </div>
        )}
      </CardContent>
    </Card>
  );
}

export default function Matchups() {
  const analyzeMutation = useAnalyzeUnified();
  const [matchupText, setMatchupText] = useState("");
  const [sport, setSport] = useState("NBA");
  const [results, setResults] = useState<SwarmFinalPayload | null>(null);

  const handleAnalyze = () => {
    if (!matchupText.trim()) {
      toast.error("Enter a matchup first");
      return;
    }
    setResults(null);
    toast.loading("3-agent swarm running…", { id: "swarm" });
    analyzeMutation.mutate({ sport, matchup: matchupText.trim() }, {
      onSuccess: (data) => {
        toast.success("Analysis locked in", { id: "swarm" });
        setResults(data);
        setMatchupText("");
      },
      onError: (err) => {
        toast.error(err.message || "Engine error", { id: "swarm" });
      }
    });
  };

  return (
    <div className="space-y-8 animate-in fade-in duration-500 pb-24">
      {/* Header */}
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Cpu className="w-8 h-8 text-primary" /> AI Matchup Analyzer
        </h2>
        <p className="text-muted-foreground mt-1">
          3-agent swarm: Quant + Situational + Executive Synthesis
        </p>
      </div>

      {/* Input card */}
      <Card className="border-primary/40 bg-primary/5 relative overflow-hidden">
        {analyzeMutation.isPending && (
          <div className="absolute inset-0 bg-background/60 backdrop-blur-sm z-10 flex flex-col items-center justify-center gap-3">
            <Cpu className="w-10 h-10 text-primary animate-pulse" />
            <p className="font-display font-bold text-lg tracking-widest text-primary">ANALYZING…</p>
          </div>
        )}
        <CardContent className="pt-6 space-y-4">
          {/* Sport pills */}
          <div>
            <p className="text-xs font-bold uppercase tracking-wider text-muted-foreground mb-2">Sport</p>
            <div className="flex flex-wrap gap-2">
              {SPORTS.map(s => (
                <button
                  key={s}
                  onClick={() => setSport(s)}
                  className={cn(
                    "px-3 py-1 rounded-full text-xs font-bold border transition-colors",
                    sport === s
                      ? "bg-primary text-primary-foreground border-primary"
                      : "bg-background border-border text-muted-foreground hover:border-primary/50"
                  )}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>

          {/* Matchup input */}
          <div className="flex gap-3">
            <Input
              value={matchupText}
              onChange={e => setMatchupText(e.target.value)}
              placeholder="e.g. Warriors vs Lakers, Sinner vs Alcaraz…"
              className="flex-1"
              onKeyDown={e => e.key === "Enter" && handleAnalyze()}
            />
            <Button
              onClick={handleAnalyze}
              disabled={analyzeMutation.isPending}
              className="font-bold tracking-widest shrink-0"
            >
              <Zap className="w-4 h-4 mr-1.5" /> ANALYZE
            </Button>
          </div>
        </CardContent>
      </Card>

      {/* Results */}
      {results && (
        <div className="space-y-6 animate-in fade-in slide-in-from-bottom-4 duration-500">
          {/* Hash */}
          <div className="flex items-center gap-3 py-3 border-b border-border">
            <TrendingUp className="w-5 h-5 text-primary" />
            <span className="font-display font-bold text-primary tracking-widest text-sm">
              SWARM RESULT — {results.hash}
            </span>
          </div>

          {/* Final pick (exec layer) */}
          <Card className="border-emerald-500/40 bg-emerald-500/5">
            <CardHeader className="bg-emerald-500/10 border-b border-emerald-500/20 pb-4">
              <CardTitle className="font-display text-emerald-400 flex items-center gap-2 text-sm uppercase tracking-widest">
                <Target className="w-4 h-4" /> Executive Verdict
              </CardTitle>
              <p className="font-black text-2xl text-foreground mt-1">{results.primary_single}</p>
              <div className="flex items-center gap-3 mt-2">
                <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                  {results.value_gap}
                </Badge>
                {results.confidence_score && (
                  <Badge className="bg-emerald-500/20 text-emerald-400 border-emerald-500/30">
                    Confidence {Math.round(results.confidence_score * 100)}%
                  </Badge>
                )}
              </div>
            </CardHeader>
            <CardContent className="pt-4">
              {results.sgp_blueprint?.map((leg, i) => (
                <div key={i} className="flex items-start gap-3 p-3 rounded-lg bg-background/40 border border-border/50 mb-3">
                  <div className="bg-emerald-500/10 border border-emerald-500/20 p-1.5 rounded-md shrink-0">
                    <Target className="w-4 h-4 text-emerald-400" />
                  </div>
                  <div>
                    <p className="text-[10px] font-bold uppercase tracking-widest text-muted-foreground">{leg.label}</p>
                    <p className="font-bold text-foreground">{leg.value}</p>
                    <p className="text-xs text-muted-foreground mt-0.5">{leg.rationale}</p>
                  </div>
                </div>
              ))}
              <p className="text-sm text-muted-foreground italic mt-2">"{results.swarm_report?.audit_verdict}"</p>
            </CardContent>
          </Card>

          {/* Agent breakdown */}
          <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">
            <AgentCard title="Quant Agent" agentData={results.swarm_report?.quant} color="purple" />
            <AgentCard title="Situational Agent" agentData={results.swarm_report?.simulation} color="blue" />
          </div>
        </div>
      )}
    </div>
  );
}
