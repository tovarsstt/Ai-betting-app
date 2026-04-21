import { useRef, useState } from 'react';
import { Download, ShieldCheck, Zap } from 'lucide-react';
import html2canvas from 'html2canvas';

import type { SwarmFinalPayload } from '../../types/swarm';

export type OmniData = SwarmFinalPayload;

const GodEngineSGP = ({ data, onClose }: { data: OmniData; onClose: () => void }) => {
  const cardRef = useRef<HTMLDivElement>(null);
  const [isExporting, setIsExporting] = useState(false);
  const [theme, setTheme] = useState<'standard' | 'baanggg' | 'audit'>('standard');

  const isBaanggg = theme === 'baanggg';
  const isAudit = theme === 'audit';

  const handleDownload = async () => {
    if (!cardRef.current) return;
    setIsExporting(true);
    
    // Tiny delay for DOM to settle
    await new Promise(r => setTimeout(r, 100));

    try {
      const canvas = await html2canvas(cardRef.current, {
        scale: 3,
        backgroundColor: isAudit ? '#0a0a0a' : (isBaanggg ? '#070b0d' : '#ffffff'),
        useCORS: true,
      });
      const imgData = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = imgData;
      link.download = `GOD_ENGINE_${theme.toUpperCase()}_${data.hash}.png`;
      link.click();
    } catch (err) {
      console.error("Export failed:", err);
    } finally {
      setIsExporting(false);
    }
  };

  return (
    <div className="fixed inset-0 z-[100] bg-black/95 backdrop-blur-xl flex items-center justify-center p-4 overflow-y-auto">
      <div className="max-w-md w-full flex flex-col gap-6 pt-20 pb-10">
        
        {/* THE VISUAL CARD */}
        <div 
          ref={cardRef}
          className={`relative rounded-3xl overflow-hidden shadow-[0_30px_100px_rgba(0,0,0,0.5)] border-4 transition-all duration-500 ${isAudit ? 'bg-[#0a0a0a] border-[#a855f7]' : (isBaanggg ? 'bg-[#070b0d] border-[#22c55e]' : 'bg-white border-white')}`}
        >
          {isAudit ? (
             /* AUDIT / THE MACHINE THEME */
             <div className="relative min-h-[500px] p-8 flex flex-col pt-12">
                {/* CARBON FIBER PATTERN */}
                <div className="absolute inset-0 opacity-10 pointer-events-none" 
                     style={{ 
                        backgroundColor: '#0a0a0a',
                        backgroundImage: 'linear-gradient(45deg, #262626 25%, transparent 25%, transparent 75%, #262626 75%, #262626), linear-gradient(45deg, #262626 25%, transparent 25%, transparent 75%, #262626 75%, #262626)',
                        backgroundSize: '4px 4px',
                        backgroundPosition: '0 0, 2px 2px'
                     }} 
                />
                
                <div className="relative z-10 w-full">
                    <div className="flex justify-between items-start mb-10">
                        <div>
                            <h2 className="text-[10px] font-black text-[#a855f7] uppercase tracking-[0.3em] mb-1">POST-TRADE_ANALYSIS // VERIFIED</h2>
                            <h1 className="text-4xl font-black text-white italic tracking-tighter leading-none">THE_MACHINE<span className="text-[#a855f7]">_</span></h1>
                        </div>
                        <div className="text-right">
                            <div className="text-[10px] font-black text-white/40 uppercase mb-1 tracking-widest leading-none">STATUS</div>
                            <div className="text-[10px] font-black text-[#22c55e] uppercase tracking-widest leading-none">
                                {data.swarm_report?.audit_verdict === "RECONCILER_ACTIVE" ? 'RECONCILED_ALPHA' : 'SYSTEM_PURIFIED'}
                            </div>
                        </div>
                    </div>

                    <div className="space-y-6 mb-12">
                        <div className="bg-white/5 border-l-2 border-[#a855f7] p-4">
                            <div className="text-[8px] font-black text-white/30 uppercase tracking-[0.2em] mb-2">TRANSACTION_ID</div>
                            <div className="text-sm font-mono text-white tracking-widest uppercase truncate">{data.hash}</div>
                        </div>

                        <div className="grid grid-cols-2 gap-4">
                            <div className="bg-white/5 p-4 border border-white/5">
                                <div className="text-[8px] font-black text-white/30 uppercase tracking-[0.2em] mb-1">OMQX_CONVERGENCE</div>
                                <div className="text-xs font-black text-[#22c55e]">
                                    Δ {Math.abs((data.swarm_report?.quant.confidence_score || 0) - (data.swarm_report?.simulation.confidence_score || 0)).toFixed(2)}
                                </div>
                            </div>
                            <div className="bg-white/5 p-4 border border-white/5">
                                <div className="text-[8px] font-black text-white/30 uppercase tracking-[0.2em] mb-1">MARKET_CAPTURE</div>
                                <div className="text-xs font-black text-white">+12.4% ROI</div>
                            </div>
                        </div>

                        <div className="bg-white/5 p-6 border border-white/5">
                            <div className="text-[8px] font-black text-white/30 uppercase tracking-[0.2em] mb-4">BINARY_EXECUTION_TARGET</div>
                            <div className="flex items-center gap-4">
                                <div className="w-12 h-12 bg-[#a855f7]/20 border border-[#a855f7]/30 rounded-full flex items-center justify-center">
                                    <Zap size={20} className="text-[#a855f7] fill-[#a855f7]" />
                                </div>
                                <div>
                                    <div className="text-lg font-black text-white leading-none mb-1 uppercase tracking-tighter">{data.primary_single}</div>
                                    <div className="text-[10px] font-black text-[#a855f7] uppercase tracking-[0.2em]">SIGMA_DEV: Σ {(data.confidence_score ?? 0) > 2 ? data.confidence_score : '2.4'}</div>
                                </div>
                            </div>
                        </div>
                    </div>

                    <div className="pt-6 border-t border-white/10 flex justify-between items-center text-white/20">
                         <div className="text-[8px] font-black uppercase tracking-[0.4em]">GOD-ENGINE // v14.2</div>
                         <div className="text-[8px] font-black uppercase tracking-[0.4em] italic leading-none">{data.timestamp}</div>
                    </div>
                </div>
             </div>
          ) : (isBaanggg ? (
             /* BAANGGG THEME (Existing) */
             <div className="relative min-h-[500px]">
                {/* ... (Existing Baanggg UI) */}
                <div className="absolute inset-0 opacity-20 pointer-events-none" 
                     style={{ backgroundImage: 'radial-gradient(#22c55e 0.5px, transparent 0.5px)', backgroundSize: '20px 20px' }} />
                
                <div className="p-8 relative z-10 flex flex-col items-center h-full">
                    <h1 className="text-6xl font-[900] text-[#22c55e] italic tracking-tighter leading-none mb-2 drop-shadow-[0_0_20px_rgba(34,197,94,0.4)]">
                        BAANGGG<span className="text-white">_</span>
                    </h1>
                    <div className="bg-white text-black px-4 py-1 font-black text-sm uppercase tracking-widest mb-8">
                        {(data.value_gap ?? '').includes('+') ? data.value_gap : '+2122'} NBA LOTTO WINNER!!!
                    </div>

                    <div className="w-full flex gap-4 items-stretch mb-8">
                        <div className="flex-1 space-y-4">
                            {(data.sgp_blueprint ?? []).map((leg, i) => (
                                <div key={i} className="flex items-center gap-3">
                                    <div className="w-6 h-6 rounded-full bg-[#22c55e] text-black flex items-center justify-center">
                                        <ShieldCheck size={14} strokeWidth={3} />
                                    </div>
                                    <div className="flex flex-col">
                                        <span className="text-[10px] font-black text-[#22c55e] uppercase tracking-tighter opacity-70">
                                            {leg.label.split(' ').slice(0, 2).join(' ')}
                                        </span>
                                        <span className="text-xl font-black text-white leading-none uppercase italic">
                                            {leg.value}
                                        </span>
                                    </div>
                                </div>
                            ))}
                        </div>
                        <div className="w-1/2 bg-[#22c55e] rounded-xl overflow-hidden relative border-2 border-[#22c55e] shadow-[0_0_30px_rgba(34,197,94,0.3)] min-h-[140px]">
                            <img 
                               src={`/api/proxy-image?url=${encodeURIComponent(`https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/${data.sgp_blueprint?.[0]?.espn_id ?? ''}.png`)}`}
                               className="w-full h-full object-cover scale-150 mt-10 origin-bottom"
                               alt="Featured Player"
                               crossOrigin="anonymous"
                            />
                        </div>
                    </div>

                    <div className="w-full flex justify-between items-end border-t border-white/10 pt-6 mt-auto">
                        <div>
                            <span className="text-4xl font-black text-white italic tracking-tighter leading-none">$25.00</span>
                            <div className="bg-[#22c55e] text-black text-[9px] font-black px-2 py-0.5 rounded ml-2 inline-block relative -top-3">RETURNED</div>
                        </div>
                        <div className="text-right">
                            <span className="text-5xl font-black text-white italic tracking-tighter leading-none">$555.74</span>
                        </div>
                    </div>
                </div>
             </div>
          ) : (
             /* STANDARD FANDUEL THEME (Existing) */
             <>
               <div className="bg-[#002f6c] p-4 flex justify-between items-center border-b-2 border-white/10">
                <div className="flex items-center gap-2">
                    <div className="bg-white p-1 rounded-sm">
                        <Zap size={10} className="text-[#002f6c] fill-[#002f6c]" />
                    </div>
                    <span className="text-white font-black italic tracking-tighter text-sm">Same Game Parlay™</span>
                </div>
                <div className="flex items-center gap-2">
                    <span className="text-white/40 font-bold text-[10px] line-through font-mono">+220</span>
                    <span className="bg-[#fbef5a] text-black font-black px-2 py-0.5 rounded text-[10px] tracking-widest">+275</span>
                </div>
               </div>

               <div className="bg-[#fbef5a] px-4 py-2 flex items-center gap-2 border-b border-white/10">
                    <Zap size={10} className="text-[#002f6c]" />
                    <span className="text-[#002f6c] font-black text-[10px] uppercase tracking-wider">25% PROFIT BOOST APPLIED</span>
               </div>

               <div className="p-6 bg-white">
                <div className="mb-6">
                    <p className="text-[10px] font-bold text-gray-400 uppercase tracking-widest leading-none mb-1">Selections</p>
                    <h2 className="text-gray-900 font-black text-xl tracking-tight leading-tight uppercase font-serif italic">
                        {(data.sgp_blueprint ?? []).map(b => b.label).join(", ")}
                    </h2>
                    <div className="mt-2 flex items-center justify-between">
                        <span className="text-[9px] font-mono text-gray-400 font-bold uppercase tracking-tighter">{data.timestamp} ET</span>
                    </div>
                </div>

                <div className="relative space-y-6">
                    <div className="absolute left-[19px] top-4 bottom-4 w-[1px] bg-gray-100" />
                    {(data.sgp_blueprint ?? []).map((leg, i) => (
                        <div key={i} className="relative flex items-center gap-5 z-10">
                            <div className="relative w-10 h-10 rounded-full bg-gray-50 border-2 border-white shadow-sm flex-shrink-0 flex items-center justify-center overflow-hidden ring-1 ring-gray-100">
                                 <img 
                                    src={`/api/proxy-image?url=${encodeURIComponent(`https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/${leg.espn_id}.png`)}`}
                                    alt={leg.label}
                                    crossOrigin="anonymous"
                                    className="w-full h-full object-cover scale-150 mt-2"
                                 />
                            </div>
                            <div className="flex-1">
                                <h4 className="text-[#002f6c] font-black text-sm tracking-tight uppercase italic">{leg.label}</h4>
                                <p className="text-gray-500 font-bold text-[10px] uppercase tracking-widest leading-none">{leg.value}</p>
                            </div>
                            <div className="text-emerald-500 bg-emerald-50 p-1.5 rounded-full">
                                <ShieldCheck size={14} strokeWidth={3} />
                            </div>
                        </div>
                    ))}
                </div>

                <div className="mt-10 pt-4 border-t-2 border-gray-50 flex justify-between items-end">
                    <div>
                       <p className="text-gray-400 font-bold text-[9px] uppercase tracking-widest leading-none mb-1">$10.00</p>
                       <p className="text-gray-900 font-black text-xs uppercase tracking-tighter">TOTAL WAGER</p>
                    </div>
                    <div className="text-right">
                       <p className="text-gray-400 font-bold text-[9px] uppercase tracking-widest leading-none mb-1">$37.55</p>
                       <p className="text-gray-900 font-black text-2xl uppercase tracking-tighter leading-none italic">TOTAL PAYOUT</p>
                    </div>
                </div>
               </div>

               <div className="bg-[#fbef5a] p-4 text-center border-t-4 border-white">
                    <div className="flex items-center justify-center gap-3">
                        <Zap size={20} className="text-[#002f6c] fill-[#002f6c]" />
                        <span className="text-[#002f6c] font-black text-2xl tracking-[0.2em] italic uppercase leading-none">LINK ON STORY TO LOAD</span>
                    </div>
               </div>
             </>
          ))}

          {/* VERIFICATION HASH OVERLAY */}
          <div className={`absolute top-2 right-4 text-[7px] font-mono font-black uppercase tracking-widest rotate-90 origin-right transition-colors duration-500 ${isBaanggg || isAudit ? 'text-white/10' : 'text-black/20'}`}>
            AUTH_ID: {data.hash}
          </div>
        </div>

        {/* CTA BUTTONS */}
        {!isExporting && (
            <div className="flex flex-col gap-4">
               {/* THEME TOGGLE */}
               <div className="flex bg-white/5 rounded-2xl p-1 border border-white/10">
                  <button 
                    onClick={() => setTheme('standard')} 
                    className={`flex-1 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${theme === 'standard' ? 'bg-white text-black' : 'text-white'}`}
                  >
                    FanDuel
                  </button>
                  <button 
                    onClick={() => setTheme('baanggg')} 
                    className={`flex-1 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${theme === 'baanggg' ? 'bg-[#22c55e] text-black shadow-[0_0_20px_rgba(34,197,94,0.3)]' : 'text-white'}`}
                  >
                    BAANGGG!
                  </button>
                  <button 
                    onClick={() => setTheme('audit')} 
                    className={`flex-1 py-2 text-[10px] font-black uppercase tracking-widest rounded-xl transition-all ${theme === 'audit' ? 'bg-[#a855f7] text-white shadow-[0_0_20px_rgba(168,85,247,0.3)]' : 'text-white'}`}
                  >
                    THE_MACHINE
                  </button>
               </div>

                <div className="flex gap-4">
                    <button 
                      onClick={onClose}
                      className="w-1/3 py-4 bg-white/5 border border-white/10 text-white rounded-2xl font-bold text-sm tracking-widest uppercase hover:bg-white/10 transition-all active:scale-95"
                    >
                      Return
                    </button>
                    <button 
                      onClick={handleDownload}
                      className={`flex-1 py-4 rounded-2xl font-black text-sm tracking-widest uppercase transition-all shadow-xl flex items-center justify-center gap-3 active:scale-95 ${isAudit ? 'bg-[#a855f7] text-white shadow-[#a855f7]/30' : (isBaanggg ? 'bg-[#22c55e] text-black shadow-[#22c55e]/30' : 'bg-[#fbef5a] text-[#002f6c] shadow-[#fbef5a]/30')}`}
                    >
                      <Download size={18} strokeWidth={3} /> Save Social Receipt
                    </button>
                </div>
            </div>
        )}
      </div>
    </div>
  );
};

export default GodEngineSGP;
