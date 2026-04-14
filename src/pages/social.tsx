import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Share2, Copy, Download, Zap, Instagram, Twitter, MessageSquare, RefreshCw, Sparkles } from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { SocialShareCard } from "@/components/Modules/SocialShareCard";
import { ParlayShareCard } from "@/components/Modules/ParlayShareCard";

type Theme = 'antigravity' | 'minimal' | 'default';
type CardMode = 'single' | 'parlay';

const PLATFORMS = [
  { key: "twitter", label: "X / Twitter", icon: Twitter, hashtags: "#BettingPicks #SportsBetting #SharpMoney #EV #AI" },
  { key: "instagram", label: "Instagram", icon: Instagram, hashtags: "#BettingTips #SportsBets #AlgoEdge #SharpMoney #Locks #AIBetting" },
  { key: "tiktok", label: "TikTok", icon: Sparkles, hashtags: "#BettingTikTok #SportsBetting #SharpMoney #FYP #BettingPicks" },
];

const CAPTION_TEMPLATES = {
  single: [
    `🧠 The God-Engine is LOCKED IN. This edge doesn't last long.\n\n{pick}\n\n{ev} EV detected. Tail or miss it. 🎯`,
    `📊 Algorithm Edge Detected:\n\n✅ {pick}\n\n💹 EV: {ev}\n🔬 Confidence: {confidence}%\n\nDon't fade the data. 🔒`,
    `💰 Today's premium release:\n\n🎯 {pick}\n\nMath says YES. The sharp money is already here. {ev} edge.\n\nFree plays ➡️ Link in bio`,
  ],
  parlay: [
    `🔥 SAME GAME PARLAY dropping NOW:\n\n{picks}\n\n💹 Combined EV: {ev}\nTail the algorithm 🤖`,
    `📈 AI-Generated SGP Alert:\n\n{picks}\n\n🧮 Kelly-sized. Vig-adjusted. Built different. {ev}`,
  ]
};

function generateCaption(template: string, data: any, picks: any[]): string {
  const pickLines = picks.map(p => `✅ ${p.lock_text} — ${p.lock_data}`).join('\n');
  const firstPick = picks[0];
  return template
    .replace('{pick}', firstPick ? `${firstPick.lock_text} — ${firstPick.lock_data}` : data.suggested_side || '')
    .replace('{picks}', pickLines)
    .replace('{ev}', data.vigAdjustedEv || data.alphaEdge || '+EV')
    .replace('{confidence}', data.confidence_score ? Math.round(data.confidence_score * 100).toString() : '75');
}

export default function Social() {
  const [lastResults, setLastResults] = useState<any>(null);
  const [cardMode, setCardMode] = useState<CardMode>('single');
  const [theme, setTheme] = useState<Theme>('antigravity');
  const [platform, setPlatform] = useState("twitter");
  const [captionIdx, setCaptionIdx] = useState(0);
  const [customCaption, setCustomCaption] = useState("");
  const [showCard, setShowCard] = useState(false);
  const [showParlay, setShowParlay] = useState(false);

  // Manual override form
  const [manual, setManual] = useState({
    matchup: "",
    pick: "",
    odds: "",
    ev: "",
    confidence: "",
  });

  useEffect(() => {
    try {
      const stored = localStorage.getItem('lastSimResults');
      if (stored) setLastResults(JSON.parse(stored));
    } catch {
      // ignore
    }
  }, []);

  const activeData = lastResults?.standard?.cognitiveData || lastResults?.standard || null;

  const currentPick = activeData
    ? {
        matchup: activeData.matchup,
        suggested_side: activeData.suggested_side,
        confidence_score: activeData.confidence_score,
        omni_vector_generation: activeData.omni_vector_generation,
        rationale: activeData.rationale,
        vigAdjustedEv: activeData.vigAdjustedEv || activeData.alphaEdge,
        alphaEdge: activeData.alphaEdge,
      }
    : null;

  const manualPick = manual.matchup && manual.pick
    ? {
        matchup: manual.matchup,
        suggested_side: manual.pick,
        confidence_score: manual.confidence ? parseFloat(manual.confidence) / 100 : 0.75,
        omni_vector_generation: [{ lock_type: "LOCK", tier: "S+", lock_text: manual.pick, lock_data: manual.odds || "ML" }],
        rationale: "Manual entry",
        vigAdjustedEv: manual.ev || "+EV",
        alphaEdge: manual.ev || "+EV",
      }
    : null;

  const displayData = manualPick || currentPick;

  const picks: any[] = Array.isArray(displayData?.omni_vector_generation) ? displayData.omni_vector_generation : [];
  const currentPlatform = PLATFORMS.find(p => p.key === platform)!;
  const templates = cardMode === 'parlay' ? CAPTION_TEMPLATES.parlay : CAPTION_TEMPLATES.single;
  const baseCaption = displayData ? generateCaption(templates[captionIdx % templates.length], displayData, picks) : "";
  const finalCaption = customCaption || (baseCaption ? `${baseCaption}\n\n${currentPlatform.hashtags}` : "");

  const copyCaption = () => {
    navigator.clipboard.writeText(finalCaption);
    toast.success("Caption copied!");
  };

  const cycleCaption = () => {
    setCaptionIdx(i => i + 1);
    setCustomCaption("");
  };

  return (
    <div className="space-y-6 animate-in fade-in duration-500">
      <div>
        <h2 className="text-3xl font-display font-bold flex items-center gap-3">
          <Share2 className="w-8 h-8 text-primary" /> Social Media Hub
        </h2>
        <p className="text-muted-foreground mt-1">
          Generate share cards and captions for your plays. Run a matchup first in the Engine to auto-load picks.
        </p>
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* LEFT: Source & Config */}
        <div className="space-y-4">

          {/* Engine Results Source */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base flex items-center gap-2">
                <Zap className="w-4 h-4 text-primary" /> Engine Pick Source
              </CardTitle>
              <CardDescription>
                {currentPick
                  ? `Last engine result loaded: ${currentPick.matchup}`
                  : "No engine results loaded. Run a simulation in Matchups, or enter manually below."}
              </CardDescription>
            </CardHeader>
            {currentPick && (
              <CardContent className="pt-0">
                <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 space-y-1">
                  <p className="font-bold text-sm">{currentPick.matchup}</p>
                  <p className="text-primary font-medium text-sm">{currentPick.suggested_side}</p>
                  <div className="flex gap-3 text-xs text-muted-foreground mt-2">
                    <span>EV: <strong className="text-success">{currentPick.vigAdjustedEv}</strong></span>
                    <span>Conf: <strong className="text-primary">{currentPick.confidence_score ? (currentPick.confidence_score * 100).toFixed(0) + '%' : '—'}</strong></span>
                    <span>Vectors: <strong>{picks.length}</strong></span>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Manual Entry */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base">Manual Entry</CardTitle>
              <CardDescription>Create a card without running the engine</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="grid grid-cols-2 gap-3">
                <Input
                  placeholder="Matchup (Lakers vs Warriors)"
                  value={manual.matchup}
                  onChange={e => setManual(m => ({ ...m, matchup: e.target.value }))}
                  className="border-border/50 text-sm"
                />
                <Input
                  placeholder="Pick (Lakers -3.5)"
                  value={manual.pick}
                  onChange={e => setManual(m => ({ ...m, pick: e.target.value }))}
                  className="border-border/50 text-sm"
                />
                <Input
                  placeholder="Odds (-110)"
                  value={manual.odds}
                  onChange={e => setManual(m => ({ ...m, odds: e.target.value }))}
                  className="border-border/50 text-sm"
                />
                <Input
                  placeholder="EV% (+6.3%)"
                  value={manual.ev}
                  onChange={e => setManual(m => ({ ...m, ev: e.target.value }))}
                  className="border-border/50 text-sm"
                />
              </div>
            </CardContent>
          </Card>

          {/* Platform & Theme */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base">Platform & Style</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Platform</p>
                <div className="flex gap-2 flex-wrap">
                  {PLATFORMS.map(p => (
                    <button
                      key={p.key}
                      onClick={() => setPlatform(p.key)}
                      className={cn(
                        "flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all",
                        platform === p.key
                          ? "bg-primary/20 text-primary border-primary/50"
                          : "bg-card border-border/50 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      <p.icon className="w-3.5 h-3.5" /> {p.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Card Theme</p>
                <div className="flex gap-2">
                  {(["antigravity", "minimal", "default"] as Theme[]).map(t => (
                    <button
                      key={t}
                      onClick={() => setTheme(t)}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-sm font-medium border capitalize transition-all",
                        theme === t
                          ? "bg-primary/20 text-primary border-primary/50"
                          : "bg-card border-border/50 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {t}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Card Mode</p>
                <div className="flex gap-2">
                  {(["single", "parlay"] as CardMode[]).map(m => (
                    <button
                      key={m}
                      onClick={() => setCardMode(m)}
                      className={cn(
                        "px-3 py-1.5 rounded-lg text-sm font-medium border capitalize transition-all",
                        cardMode === m
                          ? "bg-primary/20 text-primary border-primary/50"
                          : "bg-card border-border/50 text-muted-foreground hover:text-foreground"
                      )}
                    >
                      {m === "single" ? "Single Pick" : "Parlay / SGP"}
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT: Caption Generator */}
        <div className="space-y-4">
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <div className="flex justify-between items-center">
                <CardTitle className="font-display text-base flex items-center gap-2">
                  <MessageSquare className="w-4 h-4 text-primary" /> Caption Generator
                </CardTitle>
                <Button variant="ghost" size="sm" onClick={cycleCaption} className="text-muted-foreground h-8">
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> New Template
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              {displayData ? (
                <>
                  <textarea
                    className="w-full h-52 bg-background border border-border/50 rounded-lg p-3 text-sm text-foreground resize-none focus:outline-none focus:border-primary/50"
                    value={customCaption || finalCaption}
                    onChange={e => setCustomCaption(e.target.value)}
                    placeholder="Caption will appear here once you have a pick loaded..."
                  />
                  <div className="flex gap-2">
                    <Button onClick={copyCaption} className="flex-1 font-bold" variant="outline">
                      <Copy className="w-4 h-4 mr-2" /> Copy Caption
                    </Button>
                    {customCaption && (
                      <Button onClick={() => setCustomCaption("")} variant="ghost" size="sm" className="text-muted-foreground">
                        Reset
                      </Button>
                    )}
                  </div>
                  <p className="text-xs text-muted-foreground">
                    {(customCaption || finalCaption).length} characters · {platform === "twitter" ? "280 char limit on X" : "No limit on " + currentPlatform.label}
                  </p>
                </>
              ) : (
                <div className="h-52 flex flex-col items-center justify-center text-center text-muted-foreground">
                  <Share2 className="w-8 h-8 mb-3 opacity-30" />
                  <p className="text-sm">Load a pick from the engine or enter one manually to generate a caption.</p>
                </div>
              )}
            </CardContent>
          </Card>

          {/* Export Buttons */}
          <Card className="border-border/50 bg-card/50">
            <CardContent className="pt-4 space-y-3">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">Export Share Card</p>
              <Button
                className="w-full bg-primary/20 text-primary border border-primary/40 hover:bg-primary/30 font-bold"
                disabled={!displayData}
                onClick={() => setShowCard(true)}
              >
                <Download className="w-4 h-4 mr-2" />
                Open Single Pick Card
              </Button>
              <Button
                className="w-full bg-purple-500/20 text-purple-400 border border-purple-500/40 hover:bg-purple-500/30 font-bold"
                disabled={!displayData || picks.length === 0}
                onClick={() => setShowParlay(true)}
              >
                <Download className="w-4 h-4 mr-2" />
                Open Parlay / SGP Card
              </Button>
              <p className="text-xs text-muted-foreground text-center">
                Cards open in a full-screen preview where you can edit text and download as PNG
              </p>
            </CardContent>
          </Card>

          {/* Tips */}
          <Card className="border-border/50 bg-card/30">
            <CardContent className="pt-4">
              <p className="text-xs uppercase tracking-wider text-muted-foreground mb-3">Posting Tips</p>
              <ul className="space-y-2 text-sm text-muted-foreground">
                <li className="flex gap-2"><Badge variant="outline" className="text-xs shrink-0 h-5">X</Badge>Post between 6-9am or 5-8pm for max impressions</li>
                <li className="flex gap-2"><Badge variant="outline" className="text-xs shrink-0 h-5">IG</Badge>Use stories for quick picks, feed posts for parlays</li>
                <li className="flex gap-2"><Badge variant="outline" className="text-xs shrink-0 h-5">TK</Badge>Short video overlaying the card + voice gets 3x reach</li>
              </ul>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Share Card Modals */}
      {showCard && displayData && (
        <SocialShareCard
          data={displayData}
          theme={theme}
          onClose={() => setShowCard(false)}
        />
      )}
      {showParlay && displayData && (
        <ParlayShareCard
          data={displayData}
          onClose={() => setShowParlay(false)}
        />
      )}
    </div>
  );
}
