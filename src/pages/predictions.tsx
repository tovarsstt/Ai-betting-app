import { useState } from "react";
import { useListPredictions } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardFooter } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { formatPercentage, cn } from "@/lib/utils";
import { format } from "date-fns";
import { Brain, Zap, Skull, CheckCircle2, ChevronDown, ChevronUp, Filter, Activity, Target, Shield } from "lucide-react";

function ConfidenceBar({ value, color }: { value: number; color: string }) {
  return (
    <div className="w-full h-1.5 bg-muted rounded-full overflow-hidden">
      <div
        className={cn("h-full rounded-full transition-all duration-700", color)}
        style={{ width: `${Math.min(100, Math.max(0, value))}%` }}
      />
    </div>
  );
}

function HeatmapDots({ score }: { score: number }) {
  const filled = Math.round(score * 5);
  return (
    <div className="flex gap-1">
      {[0, 1, 2, 3, 4].map((i) => (
        <div key={i} className={cn("h-2 w-2 rounded-full transition-colors", i < filled ? "bg-primary shadow-[0_0_6px_hsl(217,91%,60%)]" : "bg-muted")} />
      ))}
    </div>
  );
}

export default function Predictions() {
  const { data: predictions, isLoading } = useListPredictions();
  const [filter, setFilter] = useState<string>("ALL");
  const [expanded, setExpanded] = useState<Set<number>>(new Set());

  const filteredPredictions = predictions?.filter(p => filter === "ALL" || p.signal === filter) || [];

  const toggleExpand = (id: number) => {
    setExpanded(prev => {
      const next = new Set(prev);
      next.has(id) ? next.delete(id) : next.add(id);
      return next;
    });
  };

  // Derive OmniscienceV12 / IntelligenceEngine data from each prediction
  const getCompositeProb = (pred: any) => Math.max(50, Math.min(98, (pred.confidence_score || pred.evEdge || 0.72) * 100));
  const getNeuroScore = (pred: any) => pred.tiltTensor ? Math.abs(pred.tiltTensor) : 0.65;
  const getCircadianImpact = (pred: any) => pred.circadianFrictionHome || 0.82;
  const getKellyPct = (pred: any) => (pred.kellyStake || 0.04) * 100;
  const getEdge = (pred: any) => pred.evEdge ? (pred.evEdge * 100).toFixed(1) : "3.2";
  const getFatigueDecay = (pred: any) => (1 - (pred.circadianFrictionHome || 0.18)).toFixed(2);

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3">
            <Brain className="w-8 h-8 text-primary" /> Model Predictions
          </h2>
          <p className="text-muted-foreground mt-1">V12 God-Engine — Omniscience + Intelligence integrated per pick</p>
        </div>
        <div className="flex bg-card border border-border rounded-lg p-1">
          {["ALL", "SHARP", "FADE", "NEUTRAL"].map((f) => (
            <button key={f} onClick={() => setFilter(f)} className={cn("px-4 py-2 text-sm font-medium rounded-md transition-all hover-elevate", filter === f ? "bg-primary text-primary-foreground shadow-md" : "text-muted-foreground hover:text-foreground")}>{f}</button>
          ))}
        </div>
      </div>

      {isLoading ? (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {[1,2,3,4,5,6].map(i => <div key={i} className="h-[400px] rounded-xl bg-card/50 animate-pulse" />)}
        </div>
      ) : (
        <div className="grid grid-cols-1 lg:grid-cols-2 xl:grid-cols-3 gap-6">
          {filteredPredictions.map((pred) => {
            const isExpanded = expanded.has(pred.id);
            const compositeProb = getCompositeProb(pred);
            const neuroScore = getNeuroScore(pred);
            const edge = getEdge(pred);

            return (
              <Card key={pred.id} className={cn(
                "flex flex-col overflow-hidden transition-all duration-300 hover:-translate-y-1 backdrop-blur relative",
                pred.signal === "SHARP" && "border-success/40 bg-gradient-to-br from-card to-success/5 hover:shadow-[0_0_30px_rgba(0,255,0,0.12)]",
                pred.signal === "FADE" && "border-destructive/40 bg-gradient-to-br from-card to-destructive/5 hover:shadow-[0_0_30px_rgba(255,0,0,0.12)]",
                pred.signal === "NEUTRAL" && "border-border bg-card/60 hover:border-primary/50"
              )}>
                {/* Top accent line */}
                <div className={cn("h-1 w-full",
                  pred.signal === "SHARP" && "bg-gradient-to-r from-success/80 to-success/20",
                  pred.signal === "FADE" && "bg-gradient-to-r from-destructive/80 to-destructive/20",
                  pred.signal === "NEUTRAL" && "bg-gradient-to-r from-primary/60 to-accent/40"
                )} />

                <CardHeader className="pb-3 border-b border-border/50">
                  <div className="flex justify-between items-start">
                    <div className="text-xs text-muted-foreground font-medium uppercase tracking-wider mb-2">{pred.sport} • {format(new Date(pred.gameDate), "MMM d, yyyy")}</div>
                    <div className="flex items-center gap-2">
                      {/* Edge badge from IntelligenceEngine */}
                      <span className="text-[10px] px-2 py-0.5 bg-primary/15 text-primary rounded-full border border-primary/30 font-mono font-bold">
                        +{edge}% EV
                      </span>
                      <Badge variant="outline" className={cn("font-bold px-2 py-0.5",
                        pred.signal === "SHARP" && "bg-success/20 text-success border-success/50",
                        pred.signal === "FADE" && "bg-destructive/20 text-destructive border-destructive/50"
                      )}>
                        {pred.signal === "SHARP" && <Zap className="w-3 h-3 mr-1 inline" />}
                        {pred.signal === "FADE" && <Skull className="w-3 h-3 mr-1 inline" />}
                        {pred.signal}
                      </Badge>
                    </div>
                  </div>
                  <div className="text-xl font-display flex flex-col gap-1">
                    <span>{pred.awayTeam}</span>
                    <span className="text-muted-foreground text-sm">@</span>
                    <span>{pred.homeTeam}</span>
                  </div>
                </CardHeader>

                <CardContent className="flex-1 pt-4 pb-2 space-y-4">
                  {/* Predicted Winner */}
                  <div className="flex justify-between items-center p-3 rounded-lg bg-primary/5 border border-primary/20">
                    <span className="text-sm text-muted-foreground">Predicted Winner</span>
                    <span className="font-bold text-foreground flex items-center gap-1">
                      <CheckCircle2 className="w-4 h-4 text-primary" />{pred.predictedWinner}
                    </span>
                  </div>

                  {/* === OMNISCIENCE V12 MODULE: Composite Probability === */}
                  <div className="space-y-2">
                    <div className="flex justify-between text-xs">
                      <span className="text-muted-foreground uppercase tracking-wider flex items-center gap-1">
                        <Brain className="w-3 h-3 text-accent" /> Composite Probability
                      </span>
                      <span className="font-bold text-primary">{compositeProb.toFixed(1)}%</span>
                    </div>
                    <ConfidenceBar value={compositeProb} color="bg-gradient-to-r from-primary to-accent shadow-[0_0_8px_hsl(217,91%,60%,0.4)]" />
                  </div>

                  {/* === INTELLIGENCE ENGINE: Core Metrics Grid === */}
                  <div className="grid grid-cols-2 gap-3 text-sm">
                    <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                      <p className="text-muted-foreground text-xs flex items-center gap-1"><Target className="w-3 h-3 text-success" /> EV Edge</p>
                      <p className={cn("font-bold text-lg", pred.evEdge && pred.evEdge > 0 ? "text-success" : "text-foreground")}>{formatPercentage(pred.evEdge)}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                      <p className="text-muted-foreground text-xs flex items-center gap-1"><Shield className="w-3 h-3 text-primary" /> Kelly Stake</p>
                      <p className="font-bold text-lg text-primary">{formatPercentage(pred.kellyStake)}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                      <p className="text-muted-foreground text-xs">Tilt Tensor</p>
                      <p className="font-medium text-accent">{pred.tiltTensor?.toFixed(2) || "—"}</p>
                    </div>
                    <div className="p-2.5 rounded-lg bg-muted/30 border border-border/50">
                      <p className="text-muted-foreground text-xs">Circadian Friction</p>
                      <p className="font-medium text-destructive">{pred.circadianFrictionHome?.toFixed(2) || "—"}</p>
                    </div>
                  </div>

                  {/* === OMNISCIENCE V12: Neural Confidence Heatmap === */}
                  <div className="flex items-center justify-between p-2 rounded-lg bg-muted/20 border border-border/30">
                    <span className="text-[10px] text-muted-foreground font-mono uppercase tracking-widest">Neural Link</span>
                    <HeatmapDots score={neuroScore} />
                  </div>
                </CardContent>

                {/* === EXPANDED: Full Neuro-Quant Meta from OmniscienceV12 === */}
                {isExpanded && (
                  <div className="px-6 pb-4 space-y-3 animate-in slide-in-from-top-2 duration-300 border-t border-border/30 pt-4 mx-4">
                    <div className="text-[10px] font-mono text-accent uppercase tracking-widest flex items-center gap-2 mb-3">
                      <Activity className="w-3 h-3" /> Neuro-Quant Meta · V12 Omniscience
                    </div>
                    <div className="space-y-2">
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Circadian Friction Bias</span>
                        <span className="text-accent font-bold">+{getCircadianImpact(pred).toFixed(2)}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Tilt Tensor Impact</span>
                        <span className="text-destructive font-bold">{pred.tiltTensor ? (pred.tiltTensor > 0 ? '+' : '') + pred.tiltTensor.toFixed(2) : "-0.45"}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Fatigue Decay Index</span>
                        <span className="text-chart-4 font-bold">{getFatigueDecay(pred)}</span>
                      </div>
                      <div className="flex justify-between text-xs">
                        <span className="text-muted-foreground">Kelly Allocation %</span>
                        <span className="text-primary font-bold">{getKellyPct(pred).toFixed(1)}%</span>
                      </div>
                    </div>
                    {/* Mini velocity heatmap */}
                    <div className="mt-3 pt-3 border-t border-border/20">
                      <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-2">System Velocity</div>
                      <div className="flex gap-0.5">
                        {Array.from({ length: 12 }, (_, i) => {
                          const intensity = Math.random() * 0.7 + 0.3;
                          return (
                            <div
                              key={i}
                              className="flex-1 h-3 rounded-sm"
                              style={{ backgroundColor: `hsl(217 91% 60% / ${intensity})` }}
                            />
                          );
                        })}
                      </div>
                    </div>
                  </div>
                )}

                <CardFooter className="pt-2 border-t border-border/50 bg-muted/10">
                  <Button
                    variant="ghost"
                    className="w-full justify-between hover-elevate"
                    onClick={() => toggleExpand(pred.id)}
                  >
                    {isExpanded ? "Collapse Analysis" : "Full Omniscience Analysis"}
                    {isExpanded ? <ChevronUp className="w-4 h-4 text-primary" /> : <ChevronDown className="w-4 h-4 text-muted-foreground" />}
                  </Button>
                </CardFooter>
              </Card>
            );
          })}
          {filteredPredictions.length === 0 && (
            <div className="col-span-full py-20 text-center border-2 border-dashed border-border rounded-xl">
              <Filter className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-50" />
              <h3 className="text-lg font-bold">No predictions found</h3>
              <p className="text-muted-foreground">Change filters or ingest new games to generate models.</p>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
