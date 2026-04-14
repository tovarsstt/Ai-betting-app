import React, { useRef, useState, useEffect } from 'react';
import html2canvas from 'html2canvas';
import { Download, Settings, X } from 'lucide-react';

// ─── Brand Config (persisted to localStorage) ───────────────────────────────

export interface BrandConfig {
  handle: string;       // @yourhandle
  name: string;         // "Your Brand"
  accentColor: string;  // hex
  tagline: string;      // "AI-Powered Picks" etc.
}

const DEFAULT_BRAND: BrandConfig = {
  handle: '@YourHandle',
  name: 'GOD ENGINE PICKS',
  accentColor: '#00CC44',
  tagline: 'AI-Powered Sports Intelligence',
};

export function loadBrand(): BrandConfig {
  try {
    const stored = localStorage.getItem('brandConfig');
    if (stored) return { ...DEFAULT_BRAND, ...JSON.parse(stored) };
  } catch { /* ignore */ }
  return DEFAULT_BRAND;
}

export function saveBrand(cfg: BrandConfig) {
  localStorage.setItem('brandConfig', JSON.stringify(cfg));
}

// ─── Brand Setup Modal ────────────────────────────────────────────────────────

export function BrandSetupModal({ onSave }: { onSave: (cfg: BrandConfig) => void }) {
  const [cfg, setCfg] = useState<BrandConfig>(loadBrand());

  const PRESET_COLORS = ['#00CC44', '#00CCFF', '#FFD700', '#FF4444', '#AA44FF', '#FF8C00'];

  return (
    <div className="fixed inset-0 z-[9999] flex items-center justify-center bg-black/80 p-4">
      <div className="bg-[#0A0D14] border border-white/10 rounded-2xl p-6 w-full max-w-md space-y-5">
        <h2 className="text-white font-black text-xl tracking-widest uppercase">Your Brand</h2>
        <p className="text-white/50 text-xs">This appears on every card you export.</p>

        <div className="space-y-3">
          <div>
            <label className="text-white/40 text-[10px] uppercase tracking-widest block mb-1">Handle (shown on card)</label>
            <input
              className="w-full bg-white/5 border border-white/10 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              value={cfg.handle}
              onChange={e => setCfg(c => ({ ...c, handle: e.target.value }))}
              placeholder="@yourhandle"
            />
          </div>
          <div>
            <label className="text-white/40 text-[10px] uppercase tracking-widest block mb-1">Brand Name</label>
            <input
              className="w-full bg-white/5 border border-white/10 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              value={cfg.name}
              onChange={e => setCfg(c => ({ ...c, name: e.target.value }))}
              placeholder="GOD ENGINE PICKS"
            />
          </div>
          <div>
            <label className="text-white/40 text-[10px] uppercase tracking-widest block mb-1">Tagline</label>
            <input
              className="w-full bg-white/5 border border-white/10 text-white rounded-lg px-3 py-2 text-sm focus:outline-none focus:border-white/30"
              value={cfg.tagline}
              onChange={e => setCfg(c => ({ ...c, tagline: e.target.value }))}
              placeholder="AI-Powered Sports Intelligence"
            />
          </div>
          <div>
            <label className="text-white/40 text-[10px] uppercase tracking-widest block mb-2">Accent Color</label>
            <div className="flex gap-2 items-center">
              {PRESET_COLORS.map(color => (
                <button
                  key={color}
                  onClick={() => setCfg(c => ({ ...c, accentColor: color }))}
                  className="w-8 h-8 rounded-full transition-all hover:scale-110"
                  style={{
                    backgroundColor: color,
                    boxShadow: cfg.accentColor === color ? `0 0 0 3px white, 0 0 0 5px ${color}` : 'none'
                  }}
                />
              ))}
              <input
                type="color"
                value={cfg.accentColor}
                onChange={e => setCfg(c => ({ ...c, accentColor: e.target.value }))}
                className="w-8 h-8 rounded-full cursor-pointer border-none bg-transparent"
              />
            </div>
          </div>
        </div>

        <button
          onClick={() => { saveBrand(cfg); onSave(cfg); }}
          className="w-full py-3 rounded-xl font-black tracking-widest uppercase text-black text-sm"
          style={{ backgroundColor: cfg.accentColor }}
        >
          Save & Apply to All Cards
        </button>
      </div>
    </div>
  );
}

// ─── Shared download helper ───────────────────────────────────────────────────

async function downloadCard(el: HTMLElement, filename: string) {
  window.getSelection()?.removeAllRanges();
  const editables = el.querySelectorAll('[contenteditable]');
  editables.forEach(e => { e.setAttribute('data-bak', 'true'); e.removeAttribute('contenteditable'); });
  try {
    const canvas = await html2canvas(el, { scale: 3, useCORS: true, allowTaint: true, logging: false, backgroundColor: null });
    const link = document.createElement('a');
    link.download = filename;
    link.href = canvas.toDataURL('image/png', 1.0);
    link.click();
  } finally {
    editables.forEach(e => { e.setAttribute('contenteditable', 'true'); e.removeAttribute('data-bak'); });
  }
}

// ─── Pick of the Day Card ─────────────────────────────────────────────────────

export interface PickCardData {
  sport: string;           // "NBA" | "MLB" | "NFL" | "TENNIS" etc.
  playerName: string;      // "DERIK QUEEN"
  pickLine: string;        // "35+ POINTS + REBOUNDS + ASSISTS"
  odds?: string;           // "-115"
  headshotUrl?: string;    // ESPN CDN or proxied URL
  matchup?: string;        // "Lakers vs Warriors"
  ev?: string;             // "+6.3%"
  confidence?: number;     // 0–1
}

export interface PickCardProps {
  data: PickCardData;
  brand: BrandConfig;
  format: '1x1' | '4x5' | '9x16';
  onClose: () => void;
}

const FORMAT_DIMS: Record<string, { w: number; h: number; aspect: string }> = {
  '1x1':  { w: 380, h: 380,  aspect: 'aspect-square'   },
  '4x5':  { w: 380, h: 475,  aspect: 'aspect-[4/5]'    },
  '9x16': { w: 340, h: 604,  aspect: 'aspect-[9/16]'   },
};

export const PickOfTheDayCard: React.FC<PickCardProps> = ({ data, brand, format, onClose }) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const fileInputRef = useRef<HTMLInputElement>(null);
  const [headshotSrc, setHeadshotSrc] = useState<string | null>(data.headshotUrl || null);
  const dims = FORMAT_DIMS[format];
  const ac = brand.accentColor;
  const is916 = format === '9x16';

  useEffect(() => {
    if (data.headshotUrl && !data.headshotUrl.startsWith('data:')) {
      setHeadshotSrc(`/api/proxy-image?url=${encodeURIComponent(data.headshotUrl)}`);
    }
  }, [data.headshotUrl]);

  const handleDownload = () => {
    if (cardRef.current) downloadCard(cardRef.current, `pick-${data.sport}-${Date.now()}.png`);
  };

  const SPORT_COLORS: Record<string, string> = {
    NBA: '#C9082A', MLB: '#002D72', NFL: '#013369',
    TENNIS: '#3D9970', SOCCER: '#1A6B3C', NHL: '#000099',
  };
  const sportColor = SPORT_COLORS[data.sport?.toUpperCase()] || '#333';

  return (
    <div className="flex flex-col items-center gap-4">
      {/* Card */}
      <div
        ref={cardRef}
        className={`${dims.aspect} relative overflow-hidden flex flex-col bg-[#05070D] font-sans`}
        style={{ width: dims.w, maxWidth: '100%' }}
      >
        {/* Background glow */}
        <div className="absolute inset-0 pointer-events-none"
          style={{ background: `radial-gradient(ellipse at 70% 40%, ${ac}22 0%, transparent 65%)` }} />

        {/* Sport badge */}
        <div className="relative z-10 flex items-center justify-between px-5 pt-4 pb-2">
          <div
            className="px-3 py-1 rounded-full text-white font-black text-[11px] tracking-[0.2em] uppercase"
            style={{ backgroundColor: sportColor }}
          >
            {data.sport} PICK OF THE DAY
          </div>
          {data.matchup && (
            <span className="text-white/30 text-[10px] font-mono tracking-wider truncate max-w-[140px]">{data.matchup}</span>
          )}
        </div>

        {/* Player headshot area */}
        <div className="relative flex-1 flex items-center justify-center overflow-hidden">
          {headshotSrc ? (
            <>
              {/* Glow behind player */}
              <div className="absolute inset-0" style={{ background: `radial-gradient(ellipse at center bottom, ${ac}30 0%, transparent 70%)` }} />
              <img
                src={headshotSrc}
                alt={data.playerName}
                crossOrigin="anonymous"
                className="relative z-10 h-full object-contain object-bottom drop-shadow-2xl"
                style={{ filter: `drop-shadow(0 0 30px ${ac}50)` }}
                onClick={() => fileInputRef.current?.click()}
              />
            </>
          ) : (
            <button
              onClick={() => fileInputRef.current?.click()}
              className="flex flex-col items-center gap-2 text-white/20 hover:text-white/40 transition-colors"
            >
              <div className="w-24 h-24 rounded-full border-2 border-dashed border-white/20 flex items-center justify-center text-3xl">
                📸
              </div>
              <span className="text-[10px] uppercase tracking-widest">Tap to add photo</span>
            </button>
          )}
        </div>
        <input ref={fileInputRef} type="file" accept="image/*" className="hidden"
          onChange={e => { const f = e.target.files?.[0]; if (f) { const r = new FileReader(); r.onloadend = () => setHeadshotSrc(r.result as string); r.readAsDataURL(f); }}} />

        {/* Pick info panel */}
        <div className="relative z-10 px-5 pb-2">
          {/* Player name */}
          <p
            className="text-white/60 font-bold tracking-[0.15em] uppercase text-xs mb-1 outline-none"
            contentEditable suppressContentEditableWarning
          >
            {data.playerName}
          </p>

          {/* The Pick — biggest text */}
          <h1
            className="text-white font-black uppercase leading-[1.0] tracking-tight outline-none"
            style={{ fontSize: is916 ? '2rem' : '1.65rem', textShadow: `0 0 30px ${ac}80` }}
            contentEditable suppressContentEditableWarning
          >
            {data.pickLine}
          </h1>

          {/* Stats row */}
          <div className="flex items-center gap-4 mt-3 mb-2">
            {data.odds && (
              <div className="flex flex-col">
                <span className="text-white/40 text-[9px] uppercase tracking-widest">Odds</span>
                <span className="text-white font-black text-sm font-mono">{data.odds}</span>
              </div>
            )}
            {data.ev && (
              <div className="flex flex-col">
                <span className="text-white/40 text-[9px] uppercase tracking-widest">EV</span>
                <span className="font-black text-sm font-mono" style={{ color: ac }}>{data.ev}</span>
              </div>
            )}
            {data.confidence != null && (
              <div className="flex flex-col">
                <span className="text-white/40 text-[9px] uppercase tracking-widest">Confidence</span>
                <span className="font-black text-sm font-mono" style={{ color: ac }}>
                  {Math.round(data.confidence * 100)}%
                </span>
              </div>
            )}
            {/* Divider line */}
            <div className="flex-1 h-px" style={{ backgroundColor: `${ac}30` }} />
          </div>
        </div>

        {/* Footer branding */}
        <div
          className="relative z-10 flex items-center justify-between px-5 py-3"
          style={{ borderTop: `1px solid ${ac}25`, backgroundColor: `${ac}08` }}
        >
          <div className="flex flex-col">
            <span className="text-white font-black text-xs tracking-widest uppercase">{brand.name}</span>
            <span className="font-mono text-[10px]" style={{ color: ac }}>{brand.handle}</span>
          </div>
          <div
            className="px-3 py-1 rounded-full text-black font-black text-[10px] tracking-widest uppercase"
            style={{ backgroundColor: ac }}
            contentEditable suppressContentEditableWarning
          >
            TAIL THIS 🔒
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 w-full" style={{ maxWidth: dims.w }}>
        <button onClick={onClose} className="flex-1 py-3 bg-white/5 border border-white/10 text-white rounded-xl font-bold text-xs tracking-widest uppercase hover:bg-white/10 transition-colors">
          Close
        </button>
        <button onClick={handleDownload} className="flex-[2] py-3 text-black rounded-xl font-black text-xs tracking-widest uppercase flex items-center justify-center gap-2 transition-all shadow-lg hover:brightness-110"
          style={{ backgroundColor: ac }}>
          <Download size={14} strokeWidth={3} /> Save Card
        </button>
      </div>
    </div>
  );
};

// ─── WIN / CASHED Card ────────────────────────────────────────────────────────

export interface WinCardData {
  picks: Array<{ text: string; odds?: string }>;
  stake: string;       // "$25.00"
  payout: string;      // "$132.84"
  sport?: string;
  matchup?: string;
}

export interface WinCardProps {
  data: WinCardData;
  brand: BrandConfig;
  format: '1x1' | '4x5' | '9x16';
  onClose: () => void;
}

export const WinCard: React.FC<WinCardProps> = ({ data, brand, format, onClose }) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const dims = FORMAT_DIMS[format];
  const ac = brand.accentColor;
  const is916 = format === '9x16';

  const handleDownload = () => {
    if (cardRef.current) downloadCard(cardRef.current, `cashed-${Date.now()}.png`);
  };

  return (
    <div className="flex flex-col items-center gap-4">
      <div
        ref={cardRef}
        className={`${dims.aspect} relative overflow-hidden flex flex-col font-sans`}
        style={{ width: dims.w, maxWidth: '100%', backgroundColor: ac }}
      >
        {/* Subtle noise texture overlay */}
        <div className="absolute inset-0 opacity-[0.06]"
          style={{ backgroundImage: 'url("data:image/svg+xml,%3Csvg viewBox=\'0 0 200 200\' xmlns=\'http://www.w3.org/2000/svg\'%3E%3Cfilter id=\'n\'%3E%3CfeTurbulence type=\'fractalNoise\' baseFrequency=\'0.9\' numOctaves=\'4\' stitchTiles=\'stitch\'/%3E%3C/filter%3E%3Crect width=\'100%25\' height=\'100%25\' filter=\'url(%23n)\'/%3E%3C/svg%3E")', backgroundSize: 'cover' }} />

        {/* Confetti dots */}
        <div className="absolute inset-0 overflow-hidden pointer-events-none">
          {['#fff', '#000', '#fff8', '#0008'].map((c, i) =>
            Array.from({ length: 8 }, (_, j) => (
              <div key={`${i}-${j}`} className="absolute rounded-full"
                style={{ width: 4 + (j % 3) * 3, height: 4 + (j % 3) * 3, backgroundColor: c, opacity: 0.3 + (j % 4) * 0.15,
                  top: `${(i * 23 + j * 13) % 90}%`, left: `${(i * 31 + j * 17) % 95}%` }} />
            ))
          )}
        </div>

        {/* Content */}
        <div className="relative z-10 flex-1 flex flex-col justify-between p-6">

          {/* Header */}
          <div className="text-center">
            <div
              className="text-black font-black uppercase tracking-[0.05em] leading-none mb-1 outline-none"
              style={{ fontSize: is916 ? '3.5rem' : '2.8rem' }}
              contentEditable suppressContentEditableWarning
            >
              BANKED! 🤑
            </div>
            <div className="text-black/60 font-black text-sm tracking-[0.3em] uppercase">
              {data.sport || 'WINNING'} TICKET CASHED
            </div>
          </div>

          {/* Picks list */}
          <div className="space-y-2 my-4">
            {data.picks.map((pick, i) => (
              <div key={i} className="flex items-center gap-3">
                <div className="w-6 h-6 rounded-full bg-black/20 flex items-center justify-center shrink-0">
                  <span className="text-black font-black text-xs">✓</span>
                </div>
                <span
                  className="text-black font-black uppercase text-sm leading-tight outline-none flex-1"
                  contentEditable suppressContentEditableWarning
                >
                  {pick.text}
                </span>
                {pick.odds && <span className="text-black/60 font-mono text-xs shrink-0">{pick.odds}</span>}
              </div>
            ))}
          </div>

          {/* Payout box */}
          <div className="bg-black/20 rounded-2xl p-4 flex items-center justify-between">
            <div className="text-center">
              <p className="text-black/50 text-[9px] uppercase tracking-widest font-bold">Staked</p>
              <p className="text-black font-black text-xl outline-none" contentEditable suppressContentEditableWarning>
                {data.stake}
              </p>
            </div>
            <div className="text-black/40 font-black text-2xl">→</div>
            <div className="text-center">
              <p className="text-black/50 text-[9px] uppercase tracking-widest font-bold">Returned</p>
              <p className="text-black font-black text-2xl outline-none" contentEditable suppressContentEditableWarning>
                {data.payout}
              </p>
            </div>
          </div>

          {/* Footer */}
          <div className="flex items-center justify-between mt-3">
            <div>
              <p className="text-black font-black text-xs tracking-widest uppercase">{brand.name}</p>
              <p className="text-black/60 font-mono text-[10px]">{brand.handle}</p>
            </div>
            <div className="bg-black/20 px-3 py-1.5 rounded-full">
              <span className="text-black font-black text-[10px] tracking-widest uppercase">
                Free Picks ↑ Link in Bio
              </span>
            </div>
          </div>
        </div>
      </div>

      {/* Actions */}
      <div className="flex gap-3 w-full" style={{ maxWidth: dims.w }}>
        <button onClick={onClose} className="flex-1 py-3 bg-white/5 border border-white/10 text-white rounded-xl font-bold text-xs tracking-widest uppercase hover:bg-white/10 transition-colors">
          Close
        </button>
        <button onClick={handleDownload} className="flex-[2] py-3 text-black rounded-xl font-black text-xs tracking-widest uppercase flex items-center justify-center gap-2 transition-all shadow-lg hover:brightness-110"
          style={{ backgroundColor: ac }}>
          <Download size={14} strokeWidth={3} /> Save Card
        </button>
      </div>
    </div>
  );
};

// ─── Card Studio (full-screen modal housing all card types) ──────────────────

type CardType = 'pick' | 'win';

interface CardStudioProps {
  type: CardType;
  pickData?: PickCardData;
  winData?: WinCardData;
  onClose: () => void;
}

export const CardStudio: React.FC<CardStudioProps> = ({ type, pickData, winData, onClose }) => {
  const [brand, setBrand] = useState<BrandConfig>(loadBrand());
  const [format, setFormat] = useState<'1x1' | '4x5' | '9x16'>('4x5');
  const [showBrandSetup, setShowBrandSetup] = useState(false);

  const formats: Array<{ key: '1x1' | '4x5' | '9x16'; label: string }> = [
    { key: '1x1', label: 'Square (IG)' },
    { key: '4x5', label: 'Portrait (IG)' },
    { key: '9x16', label: 'Story / TikTok' },
  ];

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-black/95 p-4 gap-4 overflow-y-auto">

      {showBrandSetup && (
        <BrandSetupModal onSave={cfg => { setBrand(cfg); setShowBrandSetup(false); }} />
      )}

      {/* Controls */}
      <div className="flex items-center gap-3 flex-wrap justify-center">
        <div className="flex gap-1 bg-white/5 rounded-full p-1">
          {formats.map(f => (
            <button key={f.key} onClick={() => setFormat(f.key)}
              className={`px-4 py-1.5 rounded-full text-xs font-bold tracking-wider transition-all ${format === f.key ? 'bg-white text-black' : 'text-white/50 hover:text-white'}`}>
              {f.label}
            </button>
          ))}
        </div>
        <button onClick={() => setShowBrandSetup(true)}
          className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 border border-white/10 text-white/60 rounded-full text-xs font-bold hover:text-white transition-colors">
          <Settings size={12} /> {brand.handle}
        </button>
        <button onClick={onClose} className="flex items-center gap-1.5 px-3 py-1.5 bg-white/5 border border-white/10 text-white/60 rounded-full text-xs hover:text-white transition-colors">
          <X size={12} />
        </button>
      </div>

      <p className="text-white/30 text-[10px] font-mono">✏️ Click any text to edit before saving</p>

      {/* Card */}
      {type === 'pick' && pickData && (
        <PickOfTheDayCard data={pickData} brand={brand} format={format} onClose={onClose} />
      )}
      {type === 'win' && winData && (
        <WinCard data={winData} brand={brand} format={format} onClose={onClose} />
      )}
    </div>
  );
};
