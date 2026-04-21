import { useState, useEffect, useRef } from "react";
import { motion } from 'framer-motion';
import html2canvas from 'html2canvas';

const getAggressionStyles = (edge: number) => {
  if (edge > 12) return "border-red-600 shadow-[0_0_20px_rgba(220,38,38,0.3)]"; // HIGH AGGRESSION
  if (edge > 8) return "border-yellow-500 shadow-[0_0_15px_rgba(234,179,8,0.2)]"; // MID AGGRESSION
  return "border-[#3b82f6] shadow-[0_0_10px_rgba(59,130,246,0.1)]"; // STANDARD STAKE BLUE
};

const ExecutionLog = () => {
  const logs = [
    "> INITIALIZING MARKET_SCAN...",
    "> BYPASSING RETAIL_SENTIMENT...",
    "> CALCULATING SIGMA_DEVIATION...",
    "> STAKE_LIQUIDITY_GAP_FOUND...",
    "> ALPHA_EXTRACTION_READY."
  ];

  return (
    <div className="bg-black/60 p-3 rounded font-mono text-[10px] text-green-500/70 space-y-1 mb-6 border border-green-500/20">
      {logs.map((log, i) => (
        <motion.p 
          initial={{ opacity: 0 }}
          animate={{ opacity: 1 }}
          transition={{ delay: i * 0.4 }}
          key={i}
        >
          {log}
        </motion.p>
      ))}
    </div>
  );
};

export interface ProphetData {
  error?: string;
  message?: string;
  hash?: string;
  selection?: string;
  odds?: number | string;
  game_name?: string;
  value_gap?: string;
  recommended_unit?: string;
  logic_bullets?: string[];
  correlated_insight?: string;
  loading?: boolean;
}

const ProphetTerminal = ({ data }: { data: ProphetData }) => {
  const [isSettled, setIsSettled] = useState(false);
  const printRef = useRef<HTMLDivElement>(null);

  const handleAudit = async () => {
    setIsSettled(true);
    // Give react time to render the settled overlay
    setTimeout(async () => {
      if (!printRef.current) return;
      const canvas = await html2canvas(printRef.current, { 
        backgroundColor: '#070b0d', 
        scale: 2,
        useCORS: true
      });
      const imgData = canvas.toDataURL('image/png');
      const link = document.createElement('a');
      link.href = imgData;
      link.download = `STAKE_AUDIT_${data.hash}.png`;
      link.click();
      setIsSettled(false);
    }, 150);
  };

  // If data is loading or errored
  if (!data || data.error) return <div className="p-10 text-red-500 font-mono italic">SYSTEM_OFFLINE: {data?.message || "MARKET_DATA_SYNC_ERROR"}</div>;

  return (
    <div className="min-h-screen w-full bg-[#070b0d] text-[#b1bad3] p-6 font-mono -mt-16 sm:-mt-24 selection:bg-blue-500/30 flex justify-center">
      <div className="w-full max-w-4xl relative" ref={printRef}>
        
        {/* POST-TRADE AUDIT OVERLAY (Only visible during html2canvas render) */}
        {isSettled && (
          <div className="absolute inset-0 z-50 bg-black/60 flex items-center justify-center backdrop-blur-[2px]">
             <div className="border-4 border-[#00ffc3] text-[#00ffc3] font-black text-5xl sm:text-7xl tracking-[0.4em] rotate-[-12deg] uppercase px-12 py-8 bg-[#00ffc3]/10 shadow-[0_0_50px_rgba(0,255,195,0.2)] text-center mix-blend-screen">
                STATUS: SETTLED <br/>
                <span className="text-3xl sm:text-5xl text-white tracking-[0.2em] mt-2 block">PROFIT LOCKED</span>
             </div>
          </div>
        )}

        {/* HEADER SECTION */}
        <div className="flex justify-between items-center mb-12 border-b border-[#2f4553] pb-4 pt-16">
          <div className="flex items-center gap-3">
            <div className="w-3 h-3 bg-[#3b82f6] rounded-full animate-pulse shadow-[0_0_10px_#3b82f6]" />
            <span className="text-white font-bold text-xs sm:text-base tracking-[0.3em] uppercase">V13_Prophet_Engine</span>
          </div>
          <div className="text-[10px] sm:text-xs text-[#557086] text-right">
            TIMESTAMP: {new Date().toLocaleTimeString()} <br className="sm:hidden" /> <span className="hidden sm:inline">//</span> VERIFY: {data.hash} <span className="ml-2 bg-red-600/20 text-red-500 font-bold border border-red-500 px-1 shadow-[0_0_10px_rgba(220,38,38,0.3)]">STAKE_EXPLOIT_CONFIRMED</span>
          </div>
        </div>

        {/* MAIN SIGNAL - THE HERO */}
        <div className={`relative overflow-hidden bg-[#0f212e] border-l-4 p-6 sm:p-10 mb-8 rounded-r-lg transition-all duration-500 ${getAggressionStyles(parseFloat(data.value_gap || "0"))}`}>
          {/* Decorative Grid Background */}
          <div className="absolute inset-0 opacity-5 pointer-events-none" 
              style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '20px 20px' }} />

          <div className="relative z-10">
            <h2 className="text-[#3b82f6] text-xs font-bold uppercase tracking-widest mb-2">Target_Acquired</h2>
            <h1 className="text-4xl sm:text-6xl md:text-7xl font-black text-white italic tracking-tighter mb-4 break-words leading-none">
              {data.selection?.toUpperCase()} <br className="sm:hidden" /> <span className="text-[#3b82f6]">@{data.odds}</span>
            </h1>
            <p className="text-lg sm:text-2xl text-[#b1bad3] font-medium tracking-tight mb-8">
              {data.game_name}
            </p>

            <div className="flex flex-col sm:flex-row gap-4 sm:gap-6">
              <div className="bg-black/20 px-4 py-2 border border-[#2f4553]">
                <p className="text-[9px] uppercase text-[#557086]">Edge_Value</p>
                <p className="text-xl sm:text-2xl font-bold text-[#00ffc3]">{data.value_gap}</p>
              </div>
              <div className="bg-black/20 px-4 py-2 border border-[#2f4553]">
                <p className="text-[9px] uppercase text-[#557086]">Execution_Risk</p>
                <p className="text-xl sm:text-2xl font-bold text-white">{data.recommended_unit}</p>
              </div>
            </div>
          </div>
        </div>

        <ExecutionLog />

        {/* NEURAL REASONING BOX */}
        <div className="bg-[#1a2c38] border border-[#2f4553] p-6 rounded-lg mb-8">
          <div className="text-[10px] text-[#3b82f6] font-bold uppercase mb-4 tracking-widest flex items-center gap-2">
            <span className="w-1 h-4 bg-[#3b82f6]" /> Neural_Logic_Stream
          </div>
          <div className="space-y-3">
            {data.logic_bullets?.map((bullet: string, i: number) => (
              <motion.div 
                initial={{ opacity: 0, x: -10 }}
                animate={{ opacity: 1, x: 0 }}
                transition={{ delay: i * 0.2 }}
                key={i} className="flex gap-3 text-sm sm:text-base leading-relaxed"
              >
                <span className="text-[#3b82f6] font-bold">[{i+1}]</span>
                <span className="text-white/90">{bullet}</span>
              </motion.div>
            ))}
          </div>
        </div>

        {/* NEURAL CORRELATOR WIDGET (Multi-Leg Delta) */}
        {data.correlated_insight && (
          <div className="bg-[#0f212e]/50 border border-[#3b82f6]/30 p-6 rounded-lg mb-8 relative overflow-hidden">
            <div className="absolute right-0 top-0 opacity-10 font-black text-8xl md:text-9xl rotate-[15deg] text-[#3b82f6] -mr-6 -mt-8 select-none">Δ</div>
            <div className="text-[10px] text-[#00ffc3] font-bold uppercase mb-4 tracking-widest flex items-center gap-2 relative z-10">
              <span className="text-lg font-black text-[#00ffc3] leading-none">+</span> MULTI-LEG DELTA (CORRELATION)
            </div>
            <p className="text-[#b1bad3] font-medium leading-relaxed relative z-10 text-sm sm:text-base">
              {data.correlated_insight}
            </p>
          </div>
        )}

        {/* STAKE CTA & AUDIT GEN */}
        <div className={`flex flex-col sm:flex-row gap-4 mb-10 ${isSettled ? "invisible" : ""}`}>
          <button 
            onClick={() => window.open('https://stake.com/?c=YOUR_CODE', '_blank')}
            className="group relative w-full bg-[#3b82f6] hover:bg-[#4d91ff] p-6 text-white font-black italic text-xl sm:text-2xl tracking-[0.2em] transition-all overflow-hidden shadow-[0_0_20px_rgba(37,99,235,0.4)]"
          >
            <div className="absolute inset-0 bg-white/10 translate-x-[-100%] group-hover:translate-x-[100%] transition-transform duration-700 skew-x-12" />
            PLACE BET ON STAKE.COM
          </button>
          
          <button 
            onClick={handleAudit}
            className="w-full sm:w-auto bg-transparent border-2 border-[#2f4553] hover:border-[#00ffc3] hover:text-[#00ffc3] hover:shadow-[0_0_15px_rgba(0,255,195,0.2)] p-6 text-[#557086] font-bold text-sm tracking-[0.2em] transition-all whitespace-nowrap uppercase"
          >
            Generate Audit
          </button>
        </div>

      </div>
    </div>
  );
};

export default function Predictions() {
  const [data, setData] = useState<ProphetData>({ loading: true });

  useEffect(() => {
    fetch('/api/prophet')
      .then(res => res.json())
      .then(d => {
        setData(d);
      })
      .catch(err => {
        setData({ error: "SYSTEM_OFFLINE", message: err.message });
      });
  }, []);

  if (data.loading) {
    return (
      <div className="min-h-screen w-full flex flex-col items-center justify-center bg-[#070b0d] font-mono text-[#3b82f6] -mt-16 sm:-mt-24">
        <div className="w-12 h-12 rounded-full border-2 border-t-transparent border-[#3b82f6] animate-spin mb-6" />
        <p className="animate-pulse tracking-[0.3em] font-bold">SCANNING GLOBAL LIQUIDITY</p>
        <p className="text-xs text-[#557086] mt-4 uppercase tracking-widest text-center animate-pulse">
          Engine Active: Scraping 14+ Matchups... <br/> Isolating Maximum Alpha Edge
        </p>
      </div>
    );
  }

  return <ProphetTerminal data={data} />;
}
