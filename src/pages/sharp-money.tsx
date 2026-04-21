import { useState } from "react";
import { useListLineMovements, useListEvSignals } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { Input } from "@/components/ui/input";
import { Button } from "@/components/ui/button";
import { formatPercentage, formatOdds, cn } from "@/lib/utils";
import { Crosshair, ArrowDownRight, ArrowUpRight, Flame, Calculator, TrendingUp, ShieldCheck, AlertTriangle } from "lucide-react";
import { format } from "date-fns";
import { EVMarketFilter, type EVAnalysisResult } from "@/services/evMarketFilter";

// ------- Live EV Calculator -------
function EVCalculator() {
  const [americanOdds, setAmericanOdds] = useState<string>("-110");
  const [trueProbPct, setTrueProbPct] = useState<number>(55);
  const [bankroll, setBankroll] = useState<string>("1000");
  const [result, setResult] = useState<EVAnalysisResult | null>(null);

  const handleAnalyze = () => {
    const odds = parseFloat(americanOdds);
    const trueProb = trueProbPct / 100;
    const br = parseFloat(bankroll) || 1000;

    if (isNaN(odds) || isNaN(trueProb)) return;

    const decimalOdds = EVMarketFilter.americanToDecimal(odds);
    const analysis = EVMarketFilter.analyze(trueProb, decimalOdds, br, `American: ${americanOdds}`);
    setResult(analysis);
  };

  const signalColor = result?.isSharpBet
    ? "text-emerald-400 border-emerald-500/30 bg-emerald-500/10"
    : result
    ? "text-red-400 border-red-500/30 bg-red-500/10"
    : "";

  return (
    <div className="space-y-6">
      <Card className="bg-card/50 backdrop-blur border-border/50">
        <CardHeader>
          <CardTitle className="flex items-center gap-2 text-base font-display">
            <Calculator className="w-4 h-4 text-primary" /> ASA v5.0 // Live EV Calculator
          </CardTitle>
          <p className="text-xs text-muted-foreground">
            Input market odds + your true probability estimate to get EV, Kelly sizing, and maker price.
          </p>
        </CardHeader>
        <CardContent className="space-y-6">
          {/* INPUTS */}
          <div className="grid grid-cols-1 sm:grid-cols-3 gap-4">
            <div className="space-y-1.5">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Market Odds (American)
              </label>
              <Input
                value={americanOdds}
                onChange={(e) => setAmericanOdds(e.target.value)}
                placeholder="-110"
                className="font-mono text-lg font-bold"
              />
              <p className="text-[10px] text-muted-foreground">e.g. -110, +145, -220</p>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                True Win Probability: <span className="text-primary">{trueProbPct}%</span>
              </label>
              <input
                type="range"
                min={1}
                max={99}
                value={trueProbPct}
                onChange={(e) => setTrueProbPct(Number(e.target.value))}
                className="w-full accent-primary h-2 mt-3"
              />
              <div className="flex justify-between text-[10px] text-muted-foreground">
                <span>1%</span><span>50%</span><span>99%</span>
              </div>
            </div>

            <div className="space-y-1.5">
              <label className="text-xs font-bold text-muted-foreground uppercase tracking-wider">
                Bankroll ($)
              </label>
              <Input
                value={bankroll}
                onChange={(e) => setBankroll(e.target.value)}
                placeholder="1000"
                className="font-mono text-lg font-bold"
              />
              <p className="text-[10px] text-muted-foreground">Used for Kelly stake sizing</p>
            </div>
          </div>

          <Button onClick={handleAnalyze} className="w-full font-black tracking-widest uppercase">
            <Crosshair className="w-4 h-4 mr-2" /> Analyze Edge
          </Button>

          {/* RESULT PANEL */}
          {result && (
            <div className="space-y-4 pt-2 animate-in fade-in duration-300">
              {/* Signal Badge */}
              <div className={`flex items-center justify-between p-4 rounded-xl border ${signalColor}`}>
                <div className="flex items-center gap-3">
                  {result.isSharpBet
                    ? <TrendingUp className="w-5 h-5" />
                    : <AlertTriangle className="w-5 h-5" />}
                  <span className="font-black text-lg tracking-widest">{result.signal}</span>
                </div>
                <span className="font-mono text-xs opacity-70">{result.context}</span>
              </div>

              {/* Stats Grid */}
              <div className="grid grid-cols-2 sm:grid-cols-3 gap-3">
                {[
                  { label: "Market Implied", value: result.marketImplied, highlight: false },
                  { label: "True Probability", value: result.trueProbability, highlight: true },
                  { label: "Edge (EV%)", value: result.edgePct, highlight: result.isSharpBet },
                  { label: "Expected Value", value: result.expectedValue, highlight: result.isSharpBet },
                  { label: "Kelly Stake", value: result.kellyStake, highlight: result.isSharpBet },
                  { label: "Maker Price", value: result.limitOrder.makerAmerican, highlight: false },
                ].map(({ label, value, highlight }) => (
                  <div
                    key={label}
                    className={cn(
                      "p-3 rounded-xl border",
                      highlight
                        ? "bg-primary/10 border-primary/30"
                        : "bg-muted/20 border-border/50"
                    )}
                  >
                    <p className="text-[10px] text-muted-foreground font-bold uppercase tracking-wider mb-1">{label}</p>
                    <p className={cn("font-black text-lg font-mono", highlight && "text-primary")}>{value}</p>
                  </div>
                ))}
              </div>

              {/* Limit Order Strategy */}
              <div className="bg-muted/10 border border-border/50 rounded-xl p-4">
                <div className="flex items-center gap-2 mb-2">
                  <ShieldCheck className="w-4 h-4 text-primary" />
                  <span className="text-xs font-bold text-muted-foreground uppercase tracking-wider">Limit Order Strategy</span>
                </div>
                <p className="text-sm font-medium">{result.limitOrder.strategy}</p>
              </div>
            </div>
          )}
        </CardContent>
      </Card>

      {/* Quick EV Reference Table */}
      <Card className="bg-card/50 backdrop-blur border-border/50">
        <CardHeader>
          <CardTitle className="text-sm font-display text-muted-foreground uppercase tracking-wider">
            Quick Reference: Sharp Edge Thresholds
          </CardTitle>
        </CardHeader>
        <CardContent>
          <Table>
            <TableHeader>
              <TableRow className="border-border/50">
                <TableHead>Edge</TableHead>
                <TableHead>Classification</TableHead>
                <TableHead>Action</TableHead>
                <TableHead className="text-right">Kelly Fraction</TableHead>
              </TableRow>
            </TableHeader>
            <TableBody>
              {[
                { edge: "< 0%",    cls: "NO VALUE",     action: "Skip / Fade",         kelly: "0%",    color: "text-muted-foreground" },
                { edge: "0–4%",    cls: "WEAK EDGE",    action: "Wait for line move",   kelly: "< 1%",  color: "text-yellow-400" },
                { edge: "4–8%",    cls: "SHARP VALUE",  action: "Quarter Kelly",        kelly: "1–3%",  color: "text-emerald-400" },
                { edge: "8–15%",   cls: "STRONG VALUE", action: "Half Kelly",           kelly: "3–8%",  color: "text-emerald-300" },
                { edge: "> 15%",   cls: "ALPHA LOCK",   action: "Full Kelly (capped)",  kelly: "8%+",   color: "text-blue-400" },
              ].map((row) => (
                <TableRow key={row.edge} className="border-border/50">
                  <TableCell className="font-mono font-bold">{row.edge}</TableCell>
                  <TableCell>
                    <Badge variant="outline" className={cn("font-bold text-xs", row.color)}>
                      {row.cls}
                    </Badge>
                  </TableCell>
                  <TableCell className="text-sm text-muted-foreground">{row.action}</TableCell>
                  <TableCell className={cn("text-right font-mono font-bold text-xs", row.color)}>
                    {row.kelly}
                  </TableCell>
                </TableRow>
              ))}
            </TableBody>
          </Table>
        </CardContent>
      </Card>
    </div>
  );
}

// ------- Main Page -------
export default function SharpMoney() {
  const { data: lineMovements, isLoading: loadingLines } = useListLineMovements();
  const { data: evSignals, isLoading: loadingEv } = useListEvSignals();

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Crosshair className="w-8 h-8 text-primary" /> Sharp Money Tracker
        </h2>
        <p className="text-muted-foreground mt-1">
          Live EV calculator, syndicate movements, and steam plays.
        </p>
      </div>

      <Tabs defaultValue="calculator" className="w-full">
        <TabsList className="grid w-full max-w-lg grid-cols-3 mb-6">
          <TabsTrigger value="calculator" className="font-display text-sm">
            EV Calculator
          </TabsTrigger>
          <TabsTrigger value="ev" className="font-display text-sm">
            ASA EV Filter
          </TabsTrigger>
          <TabsTrigger value="lines" className="font-display text-sm">
            Line Movement
          </TabsTrigger>
        </TabsList>

        {/* ---- LIVE EV CALCULATOR (New, always functional) ---- */}
        <TabsContent value="calculator">
          <EVCalculator />
        </TabsContent>

        {/* ---- ASA EV SIGNALS (from DB, currently seeded empty) ---- */}
        <TabsContent value="ev">
          <Card className="bg-card/50 backdrop-blur border-border/50 overflow-hidden">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-black/40">
                  <TableRow className="border-border/50">
                    <TableHead>Matchup</TableHead>
                    <TableHead>Sport</TableHead>
                    <TableHead>Bet Side</TableHead>
                    <TableHead>Signal</TableHead>
                    <TableHead className="text-right">EV Edge</TableHead>
                    <TableHead className="text-right">Maker Price</TableHead>
                    <TableHead className="text-right">Kelly</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingEv ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-8">Loading...</TableCell>
                    </TableRow>
                  ) : !evSignals?.length ? (
                    <TableRow>
                      <TableCell colSpan={7} className="text-center py-12 text-muted-foreground">
                        <Crosshair className="w-8 h-8 mx-auto mb-3 opacity-30" />
                        <p className="font-bold">No signals ingested yet.</p>
                        <p className="text-xs mt-1">Use the EV Calculator tab to analyze picks manually.</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    (evSignals as Record<string, unknown>[]).map((s, i) => (
                      <TableRow key={i} className="border-border/50 hover:bg-muted/10">
                        <TableCell className="font-medium whitespace-nowrap">{String(s.awayTeam)} @ {String(s.homeTeam)}</TableCell>
                        <TableCell className="text-muted-foreground">{String(s.sport)}</TableCell>
                        <TableCell className="font-bold">{String(s.betSide) || "—"}</TableCell>
                        <TableCell>
                          <Badge variant="outline" className={cn("font-bold",
                            s.signal === "SHARP" && "text-emerald-400 border-emerald-500 bg-emerald-500/10",
                            s.signal === "FADE"  && "text-red-400 border-red-500 bg-red-500/10"
                          )}>{String(s.signal)}</Badge>
                        </TableCell>
                        <TableCell className={cn("text-right font-bold", Number(s.evEdgePct) > 0 ? "text-emerald-400" : "text-foreground")}>
                          {formatPercentage(Number(s.evEdgePct))}
                        </TableCell>
                        <TableCell className="text-right font-medium">{formatOdds(Number(s.makerPrice))}</TableCell>
                        <TableCell className="text-right text-primary font-bold">{formatPercentage(Number(s.kellyFraction))}</TableCell>
                      </TableRow>
                    ))
                  )}
                </TableBody>
              </Table>
            </div>
          </Card>
        </TabsContent>

        {/* ---- LINE MOVEMENT (from DB, currently seeded empty) ---- */}
        <TabsContent value="lines">
          <Card className="bg-card/50 backdrop-blur border-border/50 overflow-hidden">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-black/40">
                  <TableRow className="border-border/50">
                    <TableHead>Time</TableHead>
                    <TableHead>Bookmaker</TableHead>
                    <TableHead>Type</TableHead>
                    <TableHead>Open</TableHead>
                    <TableHead>Current</TableHead>
                    <TableHead>Move</TableHead>
                    <TableHead>Sharp Action</TableHead>
                    <TableHead className="text-right">Pub %</TableHead>
                    <TableHead className="text-right">Money %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingLines ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-8">Loading...</TableCell>
                    </TableRow>
                  ) : !lineMovements?.length ? (
                    <TableRow>
                      <TableCell colSpan={9} className="text-center py-12 text-muted-foreground">
                        <TrendingUp className="w-8 h-8 mx-auto mb-3 opacity-30" />
                        <p className="font-bold">No line movements tracked yet.</p>
                        <p className="text-xs mt-1">Line movement data populates as games approach tipoff.</p>
                      </TableCell>
                    </TableRow>
                  ) : (
                    (lineMovements as Record<string, unknown>[]).map((move, i) => {
                      const diff = (Number(move.currentLine) || 0) - (Number(move.openingLine) || 0);
                      return (
                        <TableRow key={i} className="border-border/50 hover:bg-muted/10">
                          <TableCell className="text-muted-foreground text-sm whitespace-nowrap">
                            {format(new Date(String(move.recordedAt)), "MM/dd HH:mm")}
                          </TableCell>
                          <TableCell className="font-medium">{String(move.bookmaker)}</TableCell>
                          <TableCell>{String(move.lineType)}</TableCell>
                          <TableCell>{formatOdds(Number(move.openingLine))}</TableCell>
                          <TableCell className="font-bold text-foreground">{formatOdds(Number(move.currentLine))}</TableCell>
                          <TableCell>
                            {diff !== 0 && (
                              <span className={cn("flex items-center text-xs font-bold", diff > 0 ? "text-emerald-400" : "text-red-400")}>
                                {diff > 0 ? <ArrowUpRight className="w-3 h-3 mr-1" /> : <ArrowDownRight className="w-3 h-3 mr-1" />}
                                {Math.abs(diff)}
                              </span>
                            )}
                          </TableCell>
                          <TableCell>
                            <div className="flex gap-2">
                              {move.sharpAction !== "NONE" && (
                                <Badge variant="outline" className="border-blue-500 text-blue-400 bg-blue-500/10">{String(move.sharpAction)}</Badge>
                              )}
                              {Boolean(move.steamMove) && (
                                <Badge className="bg-orange-500 text-white border-none flex items-center gap-1">
                                  <Flame className="w-3 h-3" /> Steam
                                </Badge>
                              )}
                              {Boolean(move.reverseLineMovement) && (
                                <Badge variant="outline" className="border-red-500 text-red-400 bg-red-500/10">RLM</Badge>
                              )}
                            </div>
                          </TableCell>
                          <TableCell className="text-right text-muted-foreground">
                            {formatPercentage(Number(move.publicBettingPct))}
                          </TableCell>
                          <TableCell className={cn("text-right font-bold", Number(move.moneyPct) > 60 ? "text-emerald-400" : "text-foreground")}>
                            {formatPercentage(Number(move.moneyPct))}
                          </TableCell>
                        </TableRow>
                      );
                    })
                  )}
                </TableBody>
              </Table>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
