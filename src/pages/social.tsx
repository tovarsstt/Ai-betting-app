import { useState, useEffect } from "react";
import { Card, CardContent, CardHeader, CardTitle, CardDescription } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import {
  Share2, Copy, Zap, RefreshCw, Sparkles, Settings,
  Instagram, Twitter, Trophy, LayoutTemplate
} from "lucide-react";
import { toast } from "sonner";
import { cn } from "@/lib/utils";
import { CardStudio, type PickCardData, loadBrand, BrandSetupModal } from "@/components/Modules/PickCard";

const PLATFORMS = [
  { key: "twitter",   label: "X / Twitter",  icon: Twitter,   hashtags: "#BettingPicks #SportsBetting #SharpMoney #EV #AI #StakeBets" },
  { key: "instagram", label: "Instagram",     icon: Instagram, hashtags: "#BettingTips #SportsBets #AlgoEdge #SharpMoney #Locks #AIBetting #Stake" },
  { key: "tiktok",    label: "TikTok",        icon: Sparkles,  hashtags: "#BettingTikTok #SportsBetting #SharpMoney #FYP #BettingPicks #Stake" },
];

const CAPTION_TEMPLATES = {
  pick: [
    `🧠 God-Engine is LOCKED on this one.\n\n🎯 {pick}\n💹 EV: {ev}\n🔬 Confidence: {confidence}%\n\nStake it or fade it. 🔒`,
    `📊 Algorithm edge detected on Stake:\n\n✅ {pick}\n\n💰 The math doesn't lie. {ev} expected value.\nFree plays → Link in bio`,
    `🔥 Today's premium release:\n\n🎯 {pick}\n\nSharp money is already here. Tail the data. 📈\n\n{ev} EV · {confidence}% confidence`,
  ],
  parlay: [
    `🔥 SGP dropping NOW:\n\n{picks}\n\n💹 Combined EV: {ev}\nTail the algorithm 🤖`,
    `📈 AI-Generated Parlay:\n\n{picks}\n\n🧮 Kelly-sized. Vig-adjusted. Built different. {ev}`,
  ],
  win: [
    `🤑 BANKED!\n\n{picks}\n\n{stake} → {payout}\n\nFree picks every day → Link in bio 🔗`,
    `✅ CASHED AGAIN!\n\n{picks}\n\nStaked {stake}, returned {payout}\n\nThe algorithm NEVER misses 🧠`,
  ]
};

type CardMode = 'pick' | 'parlay' | 'win';
type StudioMode = 'pick' | 'win' | null;

function buildCaption(templates: string[], data: any, picks: any[], idx: number, stake?: string, payout?: string): string {
  const template = templates[idx % templates.length];
  const pickLines = picks.map(p => `✅ ${p.lock_text} — ${p.lock_data}`).join('\n');
  const firstPick = picks[0];
  return template
    .replace('{pick}', firstPick ? `${firstPick.lock_text} — ${firstPick.lock_data}` : data?.suggested_side || '')
    .replace('{picks}', pickLines || data?.suggested_side || '')
    .replace('{ev}', data?.vigAdjustedEv || data?.alphaEdge || '+EV')
    .replace('{confidence}', data?.confidence_score ? Math.round(data.confidence_score * 100).toString() : '75')
    .replace('{stake}', stake || '$25')
    .replace('{payout}', payout || '$100');
}

export default function Social() {
  const [lastResults, setLastResults] = useState<any>(null);
  const [cardMode, setCardMode] = useState<CardMode>('pick');
  const [platform, setPlatform] = useState("twitter");
  const [captionIdx, setCaptionIdx] = useState(0);
  const [customCaption, setCustomCaption] = useState("");
  const [studio, setStudio] = useState<StudioMode>(null);
  const [showBrandSetup, setShowBrandSetup] = useState(false);
  const [brand, setBrand] = useState(loadBrand());

  // Manual entry
  const [manual, setManual] = useState({ matchup: "", pick: "", odds: "", ev: "", confidence: "" });

  useEffect(() => {
    try {
      const stored = localStorage.getItem('lastSimResults');
      if (stored) setLastResults(JSON.parse(stored));
    } catch { /* ignore */ }
  }, []);

  const engineData = lastResults?.standard?.cognitiveData || lastResults?.standard || null;
  const manualData = manual.matchup && manual.pick ? {
    matchup: manual.matchup,
    suggested_side: manual.pick,
    confidence_score: manual.confidence ? parseFloat(manual.confidence) / 100 : 0.75,
    omni_vector_generation: [{ lock_type: "LOCK", tier: "S+", lock_text: manual.pick, lock_data: manual.odds || "ML" }],
    vigAdjustedEv: manual.ev || "+EV",
    alphaEdge: manual.ev || "+EV",
  } : null;

  const activeData = manualData || engineData;
  const picks: any[] = Array.isArray(activeData?.omni_vector_generation) ? activeData.omni_vector_generation : [];

  const currentPlatform = PLATFORMS.find(p => p.key === platform)!;
  const captionTemplates = CAPTION_TEMPLATES[cardMode];
  const baseCaption = activeData
    ? buildCaption(captionTemplates, activeData, picks, captionIdx) + '\n\n' + currentPlatform.hashtags
    : '';
  const finalCaption = customCaption || baseCaption;

  // Build PickCardData from active engine/manual data
  const pickCardData: PickCardData | null = activeData ? {
    sport: engineData?.sport || 'NBA',
    playerName: picks[0]?.lock_text?.split(' ').slice(0, 2).join(' ').toUpperCase() || 'PLAYER',
    pickLine: picks[0]?.lock_data || activeData.suggested_side || 'PICK',
    odds: picks[0]?.lock_type === 'PROP' ? picks[0]?.tier : manual.odds || undefined,
    headshotUrl: picks[0]?.headshot_url || undefined,
    matchup: activeData.matchup,
    ev: activeData.vigAdjustedEv || activeData.alphaEdge,
    confidence: activeData.confidence_score,
  } : null;

  return (
    <div className="space-y-6 animate-in fade-in duration-500 pb-20">

      {/* Header */}
      <div className="flex flex-col sm:flex-row justify-between items-start sm:items-center gap-4">
        <div>
          <h2 className="text-3xl font-display font-bold flex items-center gap-3">
            <Share2 className="w-8 h-8 text-primary" /> Social Media Hub
          </h2>
          <p className="text-muted-foreground mt-1">
            Create TikTok + Instagram cards for your picks. Run a simulation first or enter manually.
          </p>
        </div>
        <Button variant="outline" size="sm" onClick={() => setShowBrandSetup(true)} className="border-border/50 gap-2">
          <Settings className="w-4 h-4" />
          {brand.handle === '@YourHandle' ? 'Set Your Brand' : brand.handle}
        </Button>
      </div>

      {/* Brand prompt if not set */}
      {brand.handle === '@YourHandle' && (
        <Card className="border-yellow-500/30 bg-yellow-500/5">
          <CardContent className="pt-4 pb-4 flex items-center justify-between">
            <p className="text-sm text-yellow-400 font-medium">
              ⚡ Set your handle and brand name so it shows on every card
            </p>
            <Button size="sm" onClick={() => setShowBrandSetup(true)} className="bg-yellow-500 text-black hover:bg-yellow-400 font-bold">
              Set Brand
            </Button>
          </CardContent>
        </Card>
      )}

      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6">

        {/* LEFT col */}
        <div className="space-y-4">

          {/* Engine source */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base flex items-center gap-2">
                <Zap className="w-4 h-4 text-primary" /> Pick Source
              </CardTitle>
              <CardDescription>
                {engineData
                  ? `Engine result loaded: ${engineData.matchup}`
                  : 'No engine result yet. Run a simulation in Matchups, or enter manually below.'}
              </CardDescription>
            </CardHeader>
            {engineData && (
              <CardContent className="pt-0">
                <div className="p-3 rounded-lg bg-primary/5 border border-primary/20 space-y-1">
                  <p className="font-bold text-sm">{engineData.matchup}</p>
                  <p className="text-primary font-medium text-sm">{engineData.suggested_side}</p>
                  <div className="flex gap-3 text-xs text-muted-foreground mt-1">
                    <span>EV: <strong className="text-success">{engineData.vigAdjustedEv || engineData.alphaEdge}</strong></span>
                    <span>Conf: <strong className="text-primary">{engineData.confidence_score ? (engineData.confidence_score * 100).toFixed(0) + '%' : '—'}</strong></span>
                    <span>Picks: <strong>{picks.length}</strong></span>
                  </div>
                </div>
              </CardContent>
            )}
          </Card>

          {/* Manual entry */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base">Manual Entry</CardTitle>
              <CardDescription>Build a card without running the engine</CardDescription>
            </CardHeader>
            <CardContent className="grid grid-cols-2 gap-3">
              <Input placeholder="Matchup (Lakers vs Warriors)" value={manual.matchup}
                onChange={e => setManual(m => ({ ...m, matchup: e.target.value }))} className="border-border/50 text-sm col-span-2" />
              <Input placeholder="Pick / Stat line (35+ PRA)" value={manual.pick}
                onChange={e => setManual(m => ({ ...m, pick: e.target.value }))} className="border-border/50 text-sm col-span-2" />
              <Input placeholder="Odds (-115)" value={manual.odds}
                onChange={e => setManual(m => ({ ...m, odds: e.target.value }))} className="border-border/50 text-sm" />
              <Input placeholder="EV (+6.3%)" value={manual.ev}
                onChange={e => setManual(m => ({ ...m, ev: e.target.value }))} className="border-border/50 text-sm" />
            </CardContent>
          </Card>

          {/* Platform */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3"><CardTitle className="font-display text-base">Platform & Mode</CardTitle></CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Platform</p>
                <div className="flex gap-2 flex-wrap">
                  {PLATFORMS.map(p => (
                    <button key={p.key} onClick={() => setPlatform(p.key)}
                      className={cn("flex items-center gap-1.5 px-3 py-1.5 rounded-lg text-sm font-medium border transition-all",
                        platform === p.key ? "bg-primary/20 text-primary border-primary/50" : "bg-card border-border/50 text-muted-foreground hover:text-foreground")}>
                      <p.icon className="w-3.5 h-3.5" /> {p.label}
                    </button>
                  ))}
                </div>
              </div>
              <div>
                <p className="text-xs uppercase tracking-wider text-muted-foreground mb-2">Content Mode</p>
                <div className="flex gap-2">
                  {([['pick', 'Single Pick'], ['parlay', 'Parlay / SGP'], ['win', 'Win Recap']] as const).map(([key, label]) => (
                    <button key={key} onClick={() => setCardMode(key)}
                      className={cn("px-3 py-1.5 rounded-lg text-sm font-medium border transition-all",
                        cardMode === key ? "bg-primary/20 text-primary border-primary/50" : "bg-card border-border/50 text-muted-foreground hover:text-foreground")}>
                      {label}
                    </button>
                  ))}
                </div>
              </div>
            </CardContent>
          </Card>
        </div>

        {/* RIGHT col */}
        <div className="space-y-4">

          {/* Caption */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <div className="flex justify-between items-center">
                <CardTitle className="font-display text-base">Caption</CardTitle>
                <Button variant="ghost" size="sm" onClick={() => { setCaptionIdx(i => i + 1); setCustomCaption(''); }} className="h-8 text-muted-foreground">
                  <RefreshCw className="w-3.5 h-3.5 mr-1.5" /> New template
                </Button>
              </div>
            </CardHeader>
            <CardContent className="space-y-3">
              <textarea
                className="w-full h-44 bg-background border border-border/50 rounded-lg p-3 text-sm text-foreground resize-none focus:outline-none focus:border-primary/50"
                value={customCaption || finalCaption}
                onChange={e => setCustomCaption(e.target.value)}
                placeholder="Load a pick or enter one manually to generate a caption..."
              />
              <div className="flex gap-2">
                <Button variant="outline" onClick={() => { navigator.clipboard.writeText(customCaption || finalCaption); toast.success('Caption copied!'); }} className="flex-1 gap-2">
                  <Copy className="w-4 h-4" /> Copy
                </Button>
                {customCaption && <Button variant="ghost" size="sm" onClick={() => setCustomCaption('')} className="text-muted-foreground">Reset</Button>}
              </div>
              <p className="text-xs text-muted-foreground">{(customCaption || finalCaption).length} chars</p>
            </CardContent>
          </Card>

          {/* Card Export */}
          <Card className="border-border/50 bg-card/50">
            <CardHeader className="pb-3">
              <CardTitle className="font-display text-base flex items-center gap-2">
                <LayoutTemplate className="w-4 h-4 text-primary" /> Export Cards
              </CardTitle>
              <CardDescription>Square (1:1), Portrait (4:5), or TikTok/Story (9:16)</CardDescription>
            </CardHeader>
            <CardContent className="space-y-3">
              <Button
                className="w-full gap-2 font-bold"
                style={{ backgroundColor: brand.accentColor + '22', color: brand.accentColor, borderColor: brand.accentColor + '44' }}
                variant="outline"
                disabled={!activeData && !manual.pick}
                onClick={() => setStudio('pick')}
              >
                <Zap className="w-4 h-4" /> Open Pick of the Day Card
              </Button>
              <Button
                className="w-full gap-2 font-bold bg-green-500/20 text-green-400 border-green-500/40 hover:bg-green-500/30"
                variant="outline"
                onClick={() => setStudio('win')}
              >
                <Trophy className="w-4 h-4" /> Open Win / CASHED Card
              </Button>

              <div className="pt-2 space-y-1.5">
                <p className="text-xs text-muted-foreground font-medium">Posting Tips</p>
                <ul className="space-y-1 text-xs text-muted-foreground">
                  <li className="flex gap-2"><Badge variant="outline" className="text-[10px] h-4 shrink-0">TikTok</Badge>Use 9:16 format, overlay the card, add trending audio</li>
                  <li className="flex gap-2"><Badge variant="outline" className="text-[10px] h-4 shrink-0">IG Feed</Badge>Portrait 4:5 gets more real estate in the grid</li>
                  <li className="flex gap-2"><Badge variant="outline" className="text-[10px] h-4 shrink-0">IG Story</Badge>9:16 full-screen, add sticker polls ("Tail or Fade?")</li>
                  <li className="flex gap-2"><Badge variant="outline" className="text-[10px] h-4 shrink-0">X</Badge>Post card + caption as a thread for max reach</li>
                </ul>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>

      {/* Card Studio Modals */}
      {studio === 'pick' && pickCardData && (
        <CardStudio type="pick" pickData={pickCardData} onClose={() => setStudio(null)} />
      )}
      {studio === 'win' && (
        <CardStudio
          type="win"
          winData={{
            picks: picks.length > 0
              ? picks.map(p => ({ text: p.lock_text, odds: p.lock_data }))
              : [{ text: manual.pick || 'YOUR PICK HERE', odds: manual.odds }],
            stake: '$25.00',
            payout: '$132.84',
            sport: engineData?.sport || 'NBA',
            matchup: activeData?.matchup,
          }}
          onClose={() => setStudio(null)}
        />
      )}

      {/* Brand Setup */}
      {showBrandSetup && (
        <BrandSetupModal onSave={cfg => { setBrand(cfg); setShowBrandSetup(false); toast.success('Brand saved to all cards!'); }} />
      )}
    </div>
  );
}
