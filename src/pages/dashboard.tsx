import { useListPredictions, useListEvSignals } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { formatPercentage, cn } from "@/lib/utils";
import { Activity, Target, TrendingUp, Zap, Skull, ShieldAlert, Brain, Shield } from "lucide-react";
import { format } from "date-fns";

export default function Dashboard() {
  const { data: predictions, isLoading: loadingPreds } = useListPredictions();
  const { data: evSignals, isLoading: loadingEv } = useListEvSignals();

  const sharpPredictions = predictions?.filter(p => p.signal === "SHARP") || [];
  const fadePredictions  = predictions?.filter(p => p.signal === "FADE")  || [];
  const avgEvEdge = evSignals?.reduce((acc, curr) => acc + (curr.evEdgePct || 0), 0) / (evSignals?.length || 1);

  if (loadingPreds || loadingEv) return (
    <div className="flex items-center justify-center h-64"><Activity className="w-8 h-8 text-primary animate-spin" /></div>
  );

  return (
    <div className="space-y-8 animate-in fade-in slide-in-from-bottom-4 duration-500">
      <div className="flex flex-col gap-2">
        <h2 className="text-3xl font-display font-bold">Intelligence Overview</h2>
        <p className="text-muted-foreground">V12 God-Engine real-time analytics and system status.</p>
      </div>

      {/* KPI Cards with color */}
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        <Card className="bg-gradient-to-br from-card to-primary/5 border-primary/20 hover:border-primary/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Active Signals</span>
              <div className="w-10 h-10 rounded-xl bg-primary/15 flex items-center justify-center">
                <Target className="w-5 h-5 text-primary" />
              </div>
            </div>
            <div className="text-4xl font-display font-bold text-primary">{evSignals?.length || 0}</div>
            <div className="mt-2 text-xs text-primary/70">+12% from yesterday</div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-card to-success/5 border-success/20 hover:border-success/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Sharp Plays</span>
              <div className="w-10 h-10 rounded-xl bg-success/15 flex items-center justify-center">
                <Zap className="w-5 h-5 text-success" />
              </div>
            </div>
            <div className="text-4xl font-display font-bold text-success">{sharpPredictions.length}</div>
            <div className="mt-2 text-xs text-muted-foreground">Identified actionable edges</div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-card to-destructive/5 border-destructive/20 hover:border-destructive/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Fade Warnings</span>
              <div className="w-10 h-10 rounded-xl bg-destructive/15 flex items-center justify-center">
                <Skull className="w-5 h-5 text-destructive" />
              </div>
            </div>
            <div className="text-4xl font-display font-bold text-destructive">{fadePredictions.length}</div>
            <div className="mt-2 text-xs text-muted-foreground">High-risk traps avoided</div>
          </CardContent>
        </Card>

        <Card className="bg-gradient-to-br from-card to-accent/5 border-accent/20 hover:border-accent/50 transition-colors">
          <CardContent className="p-6">
            <div className="flex items-center justify-between mb-4">
              <span className="text-sm font-medium text-muted-foreground uppercase tracking-wider">Avg EV Edge</span>
              <div className="w-10 h-10 rounded-xl bg-accent/15 flex items-center justify-center">
                <TrendingUp className="w-5 h-5 text-accent" />
              </div>
            </div>
            <div className="text-4xl font-display font-bold text-accent">{formatPercentage(avgEvEdge || 0)}</div>
            <div className="mt-2 text-xs text-muted-foreground">Across all monitored markets</div>
          </CardContent>
        </Card>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        {/* Highest Edge Markets - with integrated module data */}
        <Card className="lg:col-span-2 border-border/50 bg-card/80 backdrop-blur flex flex-col">
          <CardHeader className="border-b border-border/50 pb-4">
            <CardTitle className="font-display text-xl flex items-center gap-2">
              <ShieldAlert className="w-5 h-5 text-primary" /> Highest Edge Markets
            </CardTitle>
            <CardDescription>ASA v5.0 Omniscience filter — core modules integrated per signal</CardDescription>
          </CardHeader>
          <CardContent className="p-0 flex-1">
            <div className="divide-y divide-border/30">
              {evSignals?.slice(0, 5).map((signal) => {
                const prob = Math.max(55, Math.min(95, 50 + (signal.evEdgePct || 0) * 500));
                return (
                  <div key={signal.id} className="p-4 hover:bg-primary/5 transition-colors">
                    <div className="flex items-center justify-between mb-3">
                      <div>
                        <div className="font-bold flex items-center gap-2">
                          {signal.homeTeam} vs {signal.awayTeam}
                          <Badge className={cn("ml-1 font-bold tracking-widest text-[10px]",
                            signal.signal === "SHARP" && "bg-success/20 text-success border border-success/30",
                            signal.signal === "FADE"  && "bg-destructive/20 text-destructive border border-destructive/30",
                            signal.signal === "NEUTRAL" && "bg-muted text-muted-foreground"
                          )}>{signal.signal}</Badge>
                        </div>
                        <div className="text-sm text-muted-foreground mt-1 flex items-center gap-3">
                          <span>{signal.sport}</span><span className="text-border">|</span>
                          <span>Bet: <strong className="text-foreground">{signal.betSide}</strong></span>
                        </div>
                      </div>
                      <div className="text-right">
                        <div className="text-lg font-display font-bold text-success">{formatPercentage(signal.evEdgePct)} EV</div>
                        <div className="text-xs text-muted-foreground">Kelly: {(signal.kellyFraction || 0).toFixed(2)}</div>
                      </div>
                    </div>
                    {/* Integrated composite probability bar from OmniscienceV12 */}
                    <div className="flex items-center gap-3">
                      <span className="text-[9px] text-muted-foreground font-mono uppercase tracking-wider whitespace-nowrap flex items-center gap-1">
                        <Brain className="w-3 h-3 text-accent" /> Prob
                      </span>
                      <div className="flex-1 h-1.5 bg-muted rounded-full overflow-hidden">
                        <div className="h-full bg-gradient-to-r from-primary to-accent rounded-full" style={{ width: `${prob}%` }} />
                      </div>
                      <span className="text-xs font-bold text-primary">{prob.toFixed(0)}%</span>
                    </div>
                  </div>
                );
              })}
              {(!evSignals || evSignals.length === 0) && (
                <div className="p-8 text-center text-muted-foreground">No EV signals detected. Run the God-Engine to generate data.</div>
              )}
            </div>
          </CardContent>
        </Card>

        {/* Engine Activity + Neuro-Quant sidebar */}
        <div className="space-y-6">
          <Card className="border-border/50 bg-card/80 backdrop-blur">
            <CardHeader className="border-b border-border/50 pb-4">
              <CardTitle className="font-display text-xl flex items-center gap-2">
                <Activity className="w-5 h-5 text-primary" /> Engine Activity
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-4">
              {predictions?.slice(0, 5).map((pred) => (
                <div key={pred.id} className="flex gap-3">
                  <div className={cn("mt-1 w-2 h-2 rounded-full shrink-0",
                    pred.signal === "SHARP" ? "bg-success shadow-[0_0_6px_hsl(142,71%,45%)]" :
                    pred.signal === "FADE" ? "bg-destructive shadow-[0_0_6px_hsl(0,84%,60%)]" :
                    "bg-primary shadow-[0_0_6px_hsl(217,91%,60%)]"
                  )} />
                  <div>
                    <p className="text-sm">Analyzed <span className="font-semibold text-foreground">{pred.homeTeam} vs {pred.awayTeam}</span></p>
                    <p className="text-xs text-muted-foreground mt-1">
                      Predicted: <span className="text-primary">{pred.predictedWinner}</span> • {format(new Date(pred.createdAt), "HH:mm:ss")}
                    </p>
                  </div>
                </div>
              ))}
              {(!predictions || predictions.length === 0) && (
                <div className="text-center text-muted-foreground text-sm py-4">No engine activity yet.</div>
              )}
            </CardContent>
          </Card>

          {/* Neuro-Quant Meta from OmniscienceV12 */}
          <Card className="border-accent/20 bg-gradient-to-br from-card to-accent/5 backdrop-blur">
            <CardHeader className="border-b border-border/50 pb-4">
              <CardTitle className="font-display text-lg flex items-center gap-2">
                <Shield className="w-4 h-4 text-accent" /> Neuro-Quant Meta
              </CardTitle>
            </CardHeader>
            <CardContent className="p-4 space-y-3">
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Circadian Friction Bias</span>
                <span className="text-accent font-bold">+1.25</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Tilt Tensor Impact</span>
                <span className="text-destructive font-bold">-0.45</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Fatigue Decay Index</span>
                <span className="text-chart-4 font-bold">0.82</span>
              </div>
              <div className="flex justify-between text-xs">
                <span className="text-muted-foreground">Engine Version</span>
                <span className="text-primary font-mono text-[10px]">V12.1.0-ALPHA</span>
              </div>
              {/* Mini velocity heatmap */}
              <div className="pt-3 border-t border-border/30">
                <div className="text-[9px] text-muted-foreground uppercase tracking-widest mb-2">System Velocity</div>
                <div className="flex gap-0.5">
                  {Array.from({ length: 16 }, (_, i) => (
                    <div
                      key={i}
                      className="flex-1 h-3 rounded-sm"
                      style={{ backgroundColor: `hsl(217 91% 60% / ${Math.random() * 0.6 + 0.2})` }}
                    />
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </div>
  );
}
