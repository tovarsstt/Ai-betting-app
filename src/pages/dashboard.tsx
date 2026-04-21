import {
  Zap,
  Cpu,
  TrendingUp,
  ShieldCheck,
  Search,
  Activity,
  Terminal,
  DollarSign
} from 'lucide-react';
import { ExecutionLog } from '@/components/Modules/ExecutionLog';
import GodEngineSGP, { type OmniData } from '@/components/Modules/GodEngineSGP';
import { AlphaSheet, type AlphaSheetData } from '@/components/Modules/AlphaSheet';
import { DeerTaskGraph } from '@/components/Modules/DeerTaskGraph';
import { QuantumTerminal } from '@/components/Modules/QuantumTerminal';
import { BankrollWidget } from '@/components/Modules/BankrollWidget';
import { toast } from 'sonner';
import { useState, useEffect } from 'react';
import { AnimatePresence, motion } from 'framer-motion';
import { quotaService } from '@/services/QuotaService';

export default function Dashboard() {
  const [view, setView] = useState<'terminal' | 'sheets' | 'quantum' | 'bankroll'>('terminal');
  const [matchup, setMatchup] = useState('');
  const [isAnalyzing, setIsAnalyzing] = useState(false);
  const [phase, setPhase] = useState(0);
  const [result, setResult] = useState<OmniData | null>(null);
  const [sheetData, setSheetData] = useState<AlphaSheetData | null>(null);
  const [showSGP, setShowSGP] = useState(false);
  const [quotaRemaining, setQuotaRemaining] = useState<number | null>(null);

  useEffect(() => {
    quotaService.initializeBudget(300).then(() =>
      quotaService.getRemainingBudget().then(setQuotaRemaining)
    );
  }, []);

  const handleAnalyze = async () => {
    if (!matchup) return toast.error("TARGET_MATCHUP_MISSING");
    
    setIsAnalyzing(true);
    setResult(null);
    
    try {
      setPhase(0); // PHASE 1: QUANT ASSASSIN
      const response = await fetch('/api/analyze-unified', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ matchup, sport: 'NBA' })
      });
      
      if (!response.ok) throw new Error("SYSTEM_FETCH_ERROR");
      
      const data = await response.json();
      
      // ORCHESTRATE PHASE STEPS (Deer-Flow Logic)
      await new Promise(r => setTimeout(r, 2000));
      setPhase(1); // PHASE 2: MIROFISH SIMULATION
      await new Promise(r => setTimeout(r, 2000));
      setPhase(2); // PHASE 3: OMQX_CONVERGENCE (OmO Protocol)
      await new Promise(r => setTimeout(r, 3000));
      setPhase(3); // PHASE 4: MARKET AUDITOR
      await new Promise(r => setTimeout(r, 2000));
      
      setResult(data);
      toast.success("SWARM_CONSENSUS_LOCKED");
    } catch (e: unknown) {
      toast.error("SWARM_ENGINE_TIMEOUT");
    } finally {
      setIsAnalyzing(false);
    }
  };

  const handleFetchSheet = async (targetSport: 'NBA' | 'MLB') => {
    setIsAnalyzing(true);
    setSheetData(null);
    
    try {
      const response = await fetch('/api/alpha-sheets', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ sport: targetSport })
      });
      
      if (!response.ok) throw new Error("SHEET_FETCH_ERROR");
      
      const data = await response.json();
      await new Promise(r => setTimeout(r, 3000));
      setSheetData(data);
      toast.success(`${targetSport} SHEET_LOADED`);
    } catch (err: unknown) {
      toast.error("SHEET_ENGINE_TIMEOUT");
    } finally {
      setIsAnalyzing(false);
    }
  };

  return (
    <div className="min-h-screen bg-[#070b0d] text-white p-6 relative overflow-hidden">
      {/* BACKGROUND EFFECTS */}
      <div className="absolute top-0 right-0 w-[800px] h-[800px] bg-blue-600/5 blur-[150px] rounded-full -translate-y-1/2 translate-x-1/2" />
      <div className="absolute bottom-0 left-0 w-[600px] h-[600px] bg-emerald-600/5 blur-[120px] rounded-full translate-y-1/2 -translate-x-1/2" />

      <div className="max-w-5xl mx-auto pt-12 relative z-10">
        
        {/* HEADER */}
        <div className="flex flex-col md:flex-row justify-between items-start md:items-end gap-6 mb-16">
          <div>
            <div className="flex items-center gap-2 mb-2">
                <div className="px-2 py-0.5 bg-blue-500/10 border border-blue-500/20 rounded text-[10px] font-black text-blue-400 tracking-widest uppercase italic">
                    V14.0 // God-Engine Core
                </div>
                <div className="px-2 py-0.5 bg-[#a855f7]/10 border border-[#a855f7]/20 rounded text-[10px] font-black text-[#a855f7] tracking-[0.2em] uppercase italic shadow-[0_0_15px_rgba(168,85,247,0.1)]">
                    KARPATHY_SKILLS: ACTIVE
                </div>
                <div className="h-2 w-2 rounded-full bg-emerald-400 animate-pulse" />
            </div>
            <h1 className="text-4xl sm:text-6xl font-black tracking-tighter uppercase italic leading-none">
              Omni-Terminal<span className="text-blue-500">_</span>
            </h1>
          </div>
          <div className="flex items-center gap-4">
               <div className="text-right">
                  <p className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Active Edge</p>
                  <p className="text-2xl font-black text-emerald-400">+14.2%</p>
               </div>
               <div className="h-10 w-px bg-white/10" />
               <div className="text-right">
                  <p className="text-[10px] text-gray-500 font-black uppercase tracking-widest">Confidence Score</p>
                  <p className="text-2xl font-black text-blue-400">94.2%</p>
               </div>
               {quotaRemaining !== null && (
                 <>
                   <div className="h-10 w-px bg-white/10" />
                   <div className="text-right">
                     <p className="text-[10px] text-gray-500 font-black uppercase tracking-widest">API Budget</p>
                     <p className={`text-lg font-black font-mono ${quotaRemaining < 50 ? 'text-red-400' : quotaRemaining < 150 ? 'text-yellow-400' : 'text-gray-300'}`}>
                       ${quotaRemaining.toFixed(2)}
                     </p>
                   </div>
                 </>
               )}
          </div>
        </div>

        {/* VIEW TOGGLE */}
        <div className="flex gap-4 mb-12">
            <button 
                onClick={() => setView('terminal')}
                className={`px-8 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all border ${view === 'terminal' ? 'bg-blue-600 border-blue-500 text-white shadow-[0_0_30px_rgba(37,99,235,0.3)]' : 'bg-white/5 border-white/10 text-gray-500'}`}
            >
                Unified Terminal
            </button>
            <button 
                onClick={() => setView('sheets')}
                className={`px-8 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all border ${view === 'sheets' ? 'bg-[#22c55e] border-[#22c55e] text-black shadow-[0_0_30px_rgba(34,197,94,0.3)]' : 'bg-white/5 border-white/10 text-gray-500'}`}
            >
                Daily Cheat Sheets
            </button>
            <button
                onClick={() => setView('quantum')}
                className={`px-8 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all border ${view === 'quantum' ? 'bg-[#a855f7] border-[#a855f7] text-white shadow-[0_0_30px_rgba(168,85,247,0.3)]' : 'bg-white/5 border-white/10 text-gray-500'}`}
            >
                Quantum Mission
            </button>
            <button
                onClick={() => setView('bankroll')}
                className={`px-8 py-3 rounded-2xl font-black text-xs uppercase tracking-widest transition-all border flex items-center gap-2 ${view === 'bankroll' ? 'bg-emerald-600 border-emerald-500 text-white shadow-[0_0_30px_rgba(16,185,129,0.3)]' : 'bg-white/5 border-white/10 text-gray-500'}`}
            >
                <DollarSign size={14} />
                Bankroll
            </button>
        </div>

        {view === 'terminal' ? (
           <>
              <div className="relative mb-12">
                  <div className="absolute inset-0 bg-blue-500/10 blur-[50px] rounded-full opacity-50" />
                  <div className={`relative bg-white/5 border border-white/10 rounded-[2.5rem] p-4 flex flex-col sm:flex-row items-center gap-4 transition-all duration-500 ${isAnalyzing ? 'border-blue-500/30' : ''}`}>
                      <div className="pl-6 text-gray-500">
                          <Search size={24} />
                      </div>
                      <input 
                        type="text" 
                        value={matchup}
                        onChange={(e) => setMatchup(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && handleAnalyze()}
                        placeholder="TARGET_MATCHUP (e.g. Lakers vs Celtics)"
                        className="flex-1 bg-transparent border-none outline-none text-2xl font-black tracking-tighter uppercase placeholder:text-gray-700 p-4"
                        disabled={isAnalyzing}
                      />
                      <button 
                        onClick={handleAnalyze}
                        disabled={isAnalyzing}
                        className="bg-blue-600 hover:bg-blue-500 text-white px-10 py-5 rounded-[2rem] font-black tracking-widest uppercase flex items-center gap-3 transition-all active:scale-95 disabled:bg-gray-800 disabled:text-gray-600"
                      >
                        {isAnalyzing ? <Activity className="animate-spin" /> : <Zap size={20} />}
                        Execute Analysis
                      </button>
                  </div>
              </div>
           </>
        ) : view === 'quantum' ? (
           <div className="mb-12 h-[600px] animate-in zoom-in duration-500">
               <QuantumTerminal />
           </div>
        ) : view === 'bankroll' ? (
           <div className="mb-12 animate-in fade-in duration-500 max-w-2xl">
               <BankrollWidget />
           </div>
        ) : (
           <div className="mb-12 flex gap-4">
              <button 
                onClick={() => handleFetchSheet('NBA')}
                className="bg-white/5 border border-white/10 hover:border-orange-500/50 p-6 rounded-[2rem] flex-1 transition-all group"
              >
                  <span className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-1">NBA Intelligence</span>
                  <span className="text-2xl font-black group-hover:text-orange-400">PROP LOTTO HUB</span>
              </button>
              <button 
                onClick={() => handleFetchSheet('MLB')}
                className="bg-white/5 border border-white/10 hover:border-emerald-500/50 p-6 rounded-[2rem] flex-1 transition-all group"
              >
                  <span className="block text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] mb-1">MLB Intelligence</span>
                  <span className="text-2xl font-black group-hover:text-emerald-400">DAILY DINGER SHEET</span>
              </button>
           </div>
        )}

        <AnimatePresence mode="wait">
          {isAnalyzing && (
            <motion.div 
              key="analyzing"
              initial={{ opacity: 0, y: 20 }}
              animate={{ opacity: 1, y: 0 }}
              exit={{ opacity: 0, y: -20 }}
              className="max-w-2xl mx-auto space-y-6"
            >
              <DeerTaskGraph activeNode={phase} />
              <ExecutionLog phase={phase} />
            </motion.div>
          )}

          {sheetData && view === 'sheets' && !isAnalyzing && (
              <AlphaSheet data={sheetData} />
          )}

          {result && view === 'terminal' && !isAnalyzing && (
            <motion.div 
              key="result"
              initial={{ opacity: 0, scale: 0.95 }}
              animate={{ opacity: 1, scale: 1 }}
              className="grid grid-cols-1 lg:grid-cols-3 gap-8"
            >
              {/* OMNI REPORT SIDE */}
              <div className="lg:col-span-2 space-y-8">
                <div className="bg-white/5 border border-white/10 rounded-[2rem] p-8 relative overflow-hidden">
                    <div className="absolute top-0 right-0 p-8 text-blue-500/10"><Cpu size={120} /></div>
                    <div className="flex items-center gap-3 mb-6">
                        <Terminal size={18} className="text-blue-500" />
                        <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Unified Diagnostic Payload</span>
                    </div>
                    <h3 className="text-3xl font-black tracking-tighter uppercase italic mb-6">
                        Single Strategy: <span className="text-emerald-400">{result.primary_single}</span>
                    </h3>
                    <p className="text-gray-400 text-lg leading-relaxed font-serif italic mb-8">
                        "{result.omni_report}"
                    </p>
                    <div className="grid grid-cols-2 gap-4">
                        <div className="bg-white/5 p-6 rounded-2xl border border-white/5">
                            <span className="text-[10px] text-gray-500 font-bold uppercase block mb-1">Value Gap</span>
                            <span className="text-2xl font-black text-emerald-400">{result.value_gap}</span>
                        </div>
                        <div className="bg-white/5 p-6 rounded-2xl border border-white/5">
                            <span className="text-[10px] text-gray-500 font-bold uppercase block mb-1">Confidence Score</span>
                            <span className="text-2xl font-black text-blue-400">{((result.confidence_score ?? 0) * 100).toFixed(1)}%</span>
                        </div>
                    </div>
                </div>
              </div>

              {/* ACTION AREA */}
              <div className="space-y-6">
                 <button 
                   onClick={() => setShowSGP(true)}
                   className="w-full bg-[#fbef5a] text-[#002f6c] p-10 rounded-[2.5rem] font-black text-2xl tracking-tighter uppercase italic flex flex-col items-center justify-center gap-4 transition-all hover:scale-105 shadow-[0_20px_60px_rgba(251,239,90,0.1)] relative overflow-hidden"
                 >
                    <div className="absolute top-0 left-0 w-full h-full bg-gradient-to-br from-white/20 to-transparent" />
                    <Zap size={40} strokeWidth={3} className="fill-[#002f6c]" />
                    <span>Generate SGP Blueprint</span>
                 </button>

                 <div className="bg-white/5 border border-white/10 rounded-[2.5rem] p-8 flex flex-col items-center gap-3">
                    <ShieldCheck size={24} className="text-emerald-500" />
                    <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Institutional Verification</span>
                    <span className="text-xs font-mono text-gray-400">{result.hash}</span>
                 </div>
              </div>
            </motion.div>
          )}
        </AnimatePresence>

        {/* FOOTER STATS (REPLACING BORING CARDS) */}
        {!isAnalyzing && !result && (
            <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-6 mt-12 opacity-50">
                 {[
                   { label: "Alpha Capture", value: "24.8%", icon: TrendingUp },
                   { label: "Execution Speed", value: "142ms", icon: Activity },
                   { label: "Model Complexity", value: "v13.7", icon: Cpu },
                   { label: "Verification", value: "Locked", icon: ShieldCheck }
                 ].map((stat, i) => (
                    <div key={i} className="bg-white/5 border border-white/10 p-6 rounded-3xl flex items-center justify-between">
                        <div>
                            <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest">{stat.label}</p>
                            <p className="text-xl font-black">{stat.value}</p>
                        </div>
                        <stat.icon size={20} className="text-blue-500" />
                    </div>
                 ))}
            </div>
        )}
      </div>

      {/* SGP MODAL */}
      <AnimatePresence>
        {showSGP && result && (
            <GodEngineSGP data={result} onClose={() => setShowSGP(false)} />
        )}
      </AnimatePresence>
    </div>
  );
}
