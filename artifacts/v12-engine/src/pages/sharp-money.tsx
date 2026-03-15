import { useListLineMovements, useListEvSignals } from "@workspace/api-client-react";
import { Card } from "@/components/ui/card";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import { Table, TableBody, TableCell, TableHead, TableHeader, TableRow } from "@/components/ui/table";
import { formatPercentage, formatOdds, cn } from "@/lib/utils";
import { Crosshair, ArrowDownRight, ArrowUpRight, Flame } from "lucide-react";
import { format } from "date-fns";

export default function SharpMoney() {
  const { data: lineMovements, isLoading: loadingLines } = useListLineMovements();
  const { data: evSignals, isLoading: loadingEv } = useListEvSignals();

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3"><Crosshair className="w-8 h-8 text-primary" /> Sharp Money Tracker</h2>
        <p className="text-muted-foreground mt-1">Track syndicate movements, steam plays, and EV signals.</p>
      </div>

      <Tabs defaultValue="ev" className="w-full">
        <TabsList className="grid w-full max-w-md grid-cols-2 mb-6">
          <TabsTrigger value="ev" className="font-display text-base">ASA v5.0 EV Filter</TabsTrigger>
          <TabsTrigger value="lines" className="font-display text-base">Line Movement</TabsTrigger>
        </TabsList>

        <TabsContent value="ev">
          <Card className="bg-card/50 backdrop-blur border-border/50 overflow-hidden">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-black/40">
                  <TableRow className="border-border/50">
                    <TableHead>Matchup</TableHead><TableHead>Sport</TableHead><TableHead>Bet Side</TableHead>
                    <TableHead>Signal</TableHead><TableHead className="text-right">EV Edge</TableHead>
                    <TableHead className="text-right">Maker Price</TableHead><TableHead className="text-right">Kelly</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingEv ? <TableRow><TableCell colSpan={7} className="text-center py-8">Loading...</TableCell></TableRow>
                  : evSignals?.map((s) => (
                    <TableRow key={s.id} className="border-border/50 hover:bg-muted/10">
                      <TableCell className="font-medium whitespace-nowrap">{s.awayTeam} @ {s.homeTeam}</TableCell>
                      <TableCell className="text-muted-foreground">{s.sport}</TableCell>
                      <TableCell className="font-bold">{s.betSide || "—"}</TableCell>
                      <TableCell>
                        <Badge variant="outline" className={cn("font-bold",
                          s.signal === "SHARP" && "text-success border-success bg-success/10",
                          s.signal === "FADE"  && "text-destructive border-destructive bg-destructive/10"
                        )}>{s.signal}</Badge>
                      </TableCell>
                      <TableCell className={cn("text-right font-bold", s.evEdgePct && s.evEdgePct > 0 ? "text-success" : "text-foreground")}>{formatPercentage(s.evEdgePct)}</TableCell>
                      <TableCell className="text-right font-medium">{formatOdds(s.makerPrice)}</TableCell>
                      <TableCell className="text-right text-primary font-bold">{formatPercentage(s.kellyFraction)}</TableCell>
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </Card>
        </TabsContent>

        <TabsContent value="lines">
          <Card className="bg-card/50 backdrop-blur border-border/50 overflow-hidden">
            <div className="overflow-x-auto">
              <Table>
                <TableHeader className="bg-black/40">
                  <TableRow className="border-border/50">
                    <TableHead>Time</TableHead><TableHead>Bookmaker</TableHead><TableHead>Type</TableHead>
                    <TableHead>Open</TableHead><TableHead>Current</TableHead><TableHead>Move</TableHead>
                    <TableHead>Sharp Action</TableHead><TableHead className="text-right">Pub %</TableHead><TableHead className="text-right">Money %</TableHead>
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {loadingLines ? <TableRow><TableCell colSpan={9} className="text-center py-8">Loading...</TableCell></TableRow>
                  : lineMovements?.map((move) => {
                    const diff = (move.currentLine || 0) - (move.openingLine || 0);
                    return (
                      <TableRow key={move.id} className="border-border/50 hover:bg-muted/10">
                        <TableCell className="text-muted-foreground text-sm whitespace-nowrap">{format(new Date(move.recordedAt), "MM/dd HH:mm")}</TableCell>
                        <TableCell className="font-medium">{move.bookmaker}</TableCell>
                        <TableCell>{move.lineType}</TableCell>
                        <TableCell>{formatOdds(move.openingLine)}</TableCell>
                        <TableCell className="font-bold text-foreground">{formatOdds(move.currentLine)}</TableCell>
                        <TableCell>{diff !== 0 && <span className={cn("flex items-center text-xs font-bold", diff > 0 ? "text-success" : "text-destructive")}>{diff > 0 ? <ArrowUpRight className="w-3 h-3 mr-1" /> : <ArrowDownRight className="w-3 h-3 mr-1" />}{Math.abs(diff)}</span>}</TableCell>
                        <TableCell>
                          <div className="flex gap-2">
                            {move.sharpAction !== "NONE" && <Badge variant="outline" className="border-accent text-accent bg-accent/10">{move.sharpAction}</Badge>}
                            {move.steamMove && <Badge className="bg-orange-500 text-white border-none flex items-center gap-1"><Flame className="w-3 h-3" /> Steam</Badge>}
                            {move.reverseLineMovement && <Badge variant="outline" className="border-destructive text-destructive bg-destructive/10">RLM</Badge>}
                          </div>
                        </TableCell>
                        <TableCell className="text-right text-muted-foreground">{formatPercentage(move.publicBettingPct)}</TableCell>
                        <TableCell className={cn("text-right font-bold", move.moneyPct && move.moneyPct > 60 ? "text-success" : "text-foreground")}>{formatPercentage(move.moneyPct)}</TableCell>
                      </TableRow>
                    );
                  })}
                </TableBody>
              </Table>
            </div>
          </Card>
        </TabsContent>
      </Tabs>
    </div>
  );
}
