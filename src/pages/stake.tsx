import { useState } from "react";
import { useListPlays, useCreatePlay, useUpdatePlay } from "../hooks/useApi";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { DollarSign, Clock, CheckCircle2, XCircle, Copy, Plus, BarChart2, Share2 } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { format } from "date-fns";
import { CardStudio } from "@/components/Modules/PickCard";

const OUTCOME_STYLES: Record<string, string> = {
  WIN: "bg-success/20 text-success border-success/40",
  LOSS: "bg-destructive/20 text-destructive border-destructive/40",
  PENDING: "bg-yellow-500/20 text-yellow-400 border-yellow-500/40",
  VOID: "bg-muted text-muted-foreground border-border",
};

const OUTCOME_ICONS: Record<string, React.ElementType> = {
  WIN: CheckCircle2,
  LOSS: XCircle,
  PENDING: Clock,
  VOID: DollarSign,
};

function PlaysStats({ plays }: { plays: any[] }) {
  const settled = plays.filter(p => p.actualOutcome !== 'PENDING' && p.actualOutcome !== 'VOID');
  const wins = settled.filter(p => p.actualOutcome === 'WIN').length;
  const losses = settled.filter(p => p.actualOutcome === 'LOSS').length;
  const winRate = settled.length > 0 ? (wins / settled.length) * 100 : 0;
  const totalEv = plays.reduce((acc, p) => acc + (p.mathEv || 0), 0);
  const pending = plays.filter(p => p.actualOutcome === 'PENDING').length;

  return (
    <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 mb-6">
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Win Rate</p>
          <p className={cn("text-2xl font-display font-bold", winRate >= 55 ? "text-success" : winRate >= 45 ? "text-foreground" : "text-destructive")}>
            {winRate.toFixed(0)}%
          </p>
          <p className="text-xs text-muted-foreground mt-1">{wins}W - {losses}L</p>
        </CardContent>
      </Card>
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Total Plays</p>
          <p className="text-2xl font-display font-bold">{plays.length}</p>
          <p className="text-xs text-muted-foreground mt-1">{pending} pending</p>
        </CardContent>
      </Card>
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Avg EV%</p>
          <p className={cn("text-2xl font-display font-bold", totalEv / Math.max(plays.length, 1) > 0 ? "text-success" : "text-foreground")}>
            {plays.length > 0 ? (totalEv / plays.length).toFixed(1) : "0.0"}%
          </p>
          <p className="text-xs text-muted-foreground mt-1">per play</p>
        </CardContent>
      </Card>
      <Card className="bg-card/50 border-border/50">
        <CardContent className="p-4">
          <p className="text-xs text-muted-foreground uppercase tracking-wider mb-1">Settled</p>
          <p className="text-2xl font-display font-bold">{settled.length}</p>
          <p className="text-xs text-muted-foreground mt-1">of {plays.length} tracked</p>
        </CardContent>
      </Card>
    </div>
  );
}

export default function Stake() {
  const { data: plays = [], isLoading } = useListPlays();
  const createPlay = useCreatePlay();
  const updatePlay = useUpdatePlay();

  const [form, setForm] = useState({
    matchup: "",
    selection: "",
    odds: "",
    stake: "",
    ev: "",
  });
  const [filter, setFilter] = useState<"ALL" | "PENDING" | "WIN" | "LOSS">("ALL");
  const [showForm, setShowForm] = useState(false);
  const [winCardPlay, setWinCardPlay] = useState<any>(null);

  const filteredPlays = plays.filter(p =>
    filter === "ALL" || p.actualOutcome === filter
  );

  const handleAddPlay = async () => {
    if (!form.matchup || !form.selection) {
      toast.error("Matchup and selection are required");
      return;
    }
    await createPlay.mutateAsync({
      matchup: form.matchup,
      selection: form.selection,
      alphaEdge: form.odds || undefined,
      kellySizing: form.stake || undefined,
      mathEv: form.ev ? parseFloat(form.ev) : undefined,
      actualOutcome: "PENDING",
    });
    setForm({ matchup: "", selection: "", odds: "", stake: "", ev: "" });
    setShowForm(false);
    toast.success("Play logged to Stake tracker");
  };

  const handleSettle = (id: string, outcome: "WIN" | "LOSS" | "VOID") => {
    updatePlay.mutate({ id, outcome }, {
      onSuccess: () => toast.success(`Play marked as ${outcome}`),
    });
  };

  const handleCopySlip = (play: any) => {
    const text = `🎯 ${play.matchup}\n📌 ${play.selection}\n💰 Odds: ${play.alphaEdge || 'N/A'}\n📊 EV: ${play.mathEv ? play.mathEv.toFixed(1) + '%' : 'N/A'}\n🔬 Stake: ${play.kellySizing || 'N/A'}`;
    navigator.clipboard.writeText(text);
    toast.success("Bet slip copied to clipboard");
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3">
            <DollarSign className="w-8 h-8 text-primary" /> Stake Tracker
          </h2>
          <p className="text-muted-foreground mt-1">
            Log and track your Stake.com plays. Monitor your win rate and EV over time.
          </p>
        </div>
        <Button
          onClick={() => setShowForm(!showForm)}
          className="bg-primary hover:bg-primary/90 font-bold tracking-wider"
        >
          <Plus className="w-4 h-4 mr-2" /> Log New Play
        </Button>
      </div>

      {/* Add Play Form */}
      {showForm && (
        <Card className="border-primary/40 bg-primary/5 animate-in fade-in slide-in-from-top-4 duration-300">
          <CardHeader className="pb-3">
            <CardTitle className="font-display text-primary flex items-center gap-2">
              <Plus className="w-5 h-5" /> New Stake Play
            </CardTitle>
            <CardDescription>Log a bet you're placing or placed on Stake.com</CardDescription>
          </CardHeader>
          <CardContent className="space-y-4">
            <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Matchup *</label>
                <Input
                  value={form.matchup}
                  onChange={e => setForm(f => ({ ...f, matchup: e.target.value }))}
                  placeholder="Lakers vs Warriors"
                  className="border-border/50"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Pick / Selection *</label>
                <Input
                  value={form.selection}
                  onChange={e => setForm(f => ({ ...f, selection: e.target.value }))}
                  placeholder="Lakers -3.5, Over 224.5..."
                  className="border-border/50"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Odds (American)</label>
                <Input
                  value={form.odds}
                  onChange={e => setForm(f => ({ ...f, odds: e.target.value }))}
                  placeholder="-110, +150..."
                  className="border-border/50"
                />
              </div>
              <div className="space-y-1.5">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">Stake Amount ($)</label>
                <Input
                  value={form.stake}
                  onChange={e => setForm(f => ({ ...f, stake: e.target.value }))}
                  placeholder="50.00"
                  className="border-border/50"
                />
              </div>
              <div className="space-y-1.5 sm:col-span-2">
                <label className="text-xs font-bold uppercase tracking-wider text-muted-foreground">EV% (from engine)</label>
                <Input
                  value={form.ev}
                  onChange={e => setForm(f => ({ ...f, ev: e.target.value }))}
                  placeholder="6.3"
                  className="border-border/50"
                />
              </div>
            </div>
            <div className="flex gap-3 pt-2">
              <Button variant="outline" onClick={() => setShowForm(false)} className="flex-1">
                Cancel
              </Button>
              <Button
                onClick={handleAddPlay}
                disabled={createPlay.isPending}
                className="flex-[2] bg-primary hover:bg-primary/90 font-bold"
              >
                {createPlay.isPending ? "Logging..." : "Log to Stake Tracker"}
              </Button>
            </div>
          </CardContent>
        </Card>
      )}

      {/* Stats */}
      {plays.length > 0 && <PlaysStats plays={plays} />}

      {/* Filter Tabs */}
      <div className="flex gap-2">
        {(["ALL", "PENDING", "WIN", "LOSS"] as const).map(f => (
          <button
            key={f}
            onClick={() => setFilter(f)}
            className={cn(
              "px-4 py-2 text-sm font-bold rounded-lg transition-all border",
              filter === f
                ? "bg-primary text-primary-foreground border-primary"
                : "bg-card border-border/50 text-muted-foreground hover:text-foreground"
            )}
          >
            {f}
            <span className="ml-1.5 text-xs opacity-70">
              ({f === "ALL" ? plays.length : plays.filter(p => p.actualOutcome === f).length})
            </span>
          </button>
        ))}
      </div>

      {/* Win Card Studio — pops up when you settle a WIN or tap the share icon */}
      {winCardPlay && (
        <CardStudio
          type="win"
          winData={{
            picks: [{ text: winCardPlay.selection, odds: winCardPlay.alphaEdge }],
            stake: winCardPlay.kellySizing ? `$${winCardPlay.kellySizing}` : '$25.00',
            payout: winCardPlay.kellySizing ? `$${(parseFloat(winCardPlay.kellySizing) * 4.5).toFixed(2)}` : '$100.00',
            sport: 'STAKE',
            matchup: winCardPlay.matchup,
          }}
          onClose={() => setWinCardPlay(null)}
        />
      )}

      {/* Plays List */}
      {isLoading ? (
        <div className="space-y-3">
          {[1, 2, 3].map(i => <div key={i} className="h-24 rounded-xl bg-card/50 animate-pulse" />)}
        </div>
      ) : filteredPlays.length > 0 ? (
        <div className="space-y-3">
          {filteredPlays.map((play: any) => {
            const Icon = OUTCOME_ICONS[play.actualOutcome] || Clock;
            return (
              <Card
                key={play.id}
                className={cn(
                  "border-border/50 bg-card/60 backdrop-blur transition-all",
                  play.actualOutcome === 'WIN' && "border-success/20",
                  play.actualOutcome === 'LOSS' && "border-destructive/20",
                )}
              >
                <CardContent className="p-4">
                  <div className="flex items-start justify-between gap-4">
                    <div className="flex-1 min-w-0">
                      <div className="flex items-center gap-2 mb-1">
                        <Badge variant="outline" className={cn("text-xs font-bold border", OUTCOME_STYLES[play.actualOutcome])}>
                          <Icon className="w-3 h-3 mr-1 inline" />
                          {play.actualOutcome}
                        </Badge>
                        <span className="text-xs text-muted-foreground font-mono">
                          {play.timestamp ? format(new Date(play.timestamp), "MMM d, HH:mm") : "—"}
                        </span>
                      </div>
                      <p className="font-bold text-foreground truncate">{play.matchup}</p>
                      <p className="text-sm text-primary font-medium mt-0.5 truncate">{play.selection}</p>
                      <div className="flex items-center gap-4 mt-2 text-xs text-muted-foreground">
                        {play.alphaEdge && <span>Odds: <strong className="text-foreground">{play.alphaEdge}</strong></span>}
                        {play.kellySizing && <span>Stake: <strong className="text-foreground">${play.kellySizing}</strong></span>}
                        {play.mathEv != null && (
                          <span>EV: <strong className={play.mathEv > 0 ? "text-success" : "text-destructive"}>{play.mathEv.toFixed(1)}%</strong></span>
                        )}
                      </div>
                    </div>
                    <div className="flex flex-col gap-2 shrink-0">
                      <Button
                        variant="ghost"
                        size="sm"
                        onClick={() => handleCopySlip(play)}
                        className="text-muted-foreground hover:text-foreground h-8 px-2"
                      >
                        <Copy className="w-3.5 h-3.5" />
                      </Button>
                      {play.actualOutcome === 'PENDING' && (
                        <div className="flex gap-1">
                          <Button
                            size="sm"
                            onClick={() => { handleSettle(play.id, "WIN"); setWinCardPlay(play); }}
                            className="h-7 px-2 text-xs bg-success/20 text-success hover:bg-success/30 border-success/30"
                            variant="outline"
                          >
                            W
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleSettle(play.id, "LOSS")}
                            className="h-7 px-2 text-xs bg-destructive/20 text-destructive hover:bg-destructive/30 border-destructive/30"
                            variant="outline"
                          >
                            L
                          </Button>
                          <Button
                            size="sm"
                            onClick={() => handleSettle(play.id, "VOID")}
                            className="h-7 px-2 text-xs"
                            variant="outline"
                          >
                            V
                          </Button>
                        </div>
                      )}
                      {play.actualOutcome === 'WIN' && (
                        <Button
                          size="sm"
                          variant="ghost"
                          onClick={() => setWinCardPlay(play)}
                          className="h-7 px-2 text-success hover:text-success/80"
                          title="Create win card"
                        >
                          <Share2 className="w-3.5 h-3.5" />
                        </Button>
                      )}
                    </div>
                  </div>
                </CardContent>
              </Card>
            );
          })}
        </div>
      ) : (
        <div className="py-20 text-center border-2 border-dashed border-border rounded-xl">
          <BarChart2 className="w-12 h-12 text-muted-foreground mx-auto mb-4 opacity-30" />
          <h3 className="text-lg font-bold text-muted-foreground">
            {filter === "ALL" ? "No plays logged yet" : `No ${filter} plays`}
          </h3>
          <p className="text-sm text-muted-foreground mt-1">
            {filter === "ALL"
              ? "Log your first Stake.com bet above to start tracking."
              : "Change the filter to see other plays."}
          </p>
        </div>
      )}
    </div>
  );
}
