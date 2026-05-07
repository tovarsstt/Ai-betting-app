import React, { useMemo } from 'react';
import { motion } from 'framer-motion';
import { ShieldCheck, TrendingUp, Zap } from 'lucide-react';

interface AlphaSheetItem {
  rank: number;
  team_logo: string;
  player_name: string;
  metric_label: string;
  metric_value: string;
  season_stat: string;
  ai_score: number;
  status_color: string;
  espn_id: string;
}

export interface AlphaSheetData {
  title: string;
  subtitle: string;
  data: AlphaSheetItem[];
  timestamp: string;
}

interface AlphaSheetProps {
  data: AlphaSheetData;
}

export const AlphaSheet: React.FC<AlphaSheetProps> = ({ data }) => {
  const sessionId = useMemo(() => "Σ_" + Math.random().toString(36).substring(7).toUpperCase(), []);

  return (
    <div className="w-full bg-[#070b0d] border border-white/5 rounded-[2rem] overflow-hidden shadow-2xl">
      {/* HEADER */}
      <div className="p-8 border-b border-white/5 bg-gradient-to-r from-blue-500/10 to-transparent flex justify-between items-end">
        <div>
          <div className="flex items-center gap-2 mb-2">
            <Zap size={14} className="text-blue-400 fill-blue-400" />
            <span className="text-[10px] font-black text-blue-400 uppercase tracking-widest">{data.subtitle}</span>
          </div>
          <h2 className="text-4xl font-black tracking-tighter italic uppercase text-white shadow-blue-500/20 drop-shadow-xl">
            {data.title}<span className="text-blue-500">_</span>
          </h2>
        </div>
        <div className="text-right">
          <span className="text-[10px] font-black text-gray-500 uppercase tracking-widest block mb-1">Sigma-Deviation Hash</span>
          <span className="text-xs font-mono text-gray-400">{sessionId}</span>
        </div>
      </div>

      {/* TABLE HEADER */}
      <div className="grid grid-cols-12 px-8 py-4 bg-white/5 text-[10px] font-black text-gray-500 uppercase tracking-[0.2em] border-b border-white/5">
        <div className="col-span-1">RNK</div>
        <div className="col-span-1">TM</div>
        <div className="col-span-4">PLAYER // PROPHET_ID</div>
        <div className="col-span-2 text-center">{data.data[0]?.metric_label || 'METRIC'}</div>
        <div className="col-span-1 text-center">SEASON</div>
        <div className="col-span-3 text-right">KARPATHY CONFIDENCE Σ</div>
      </div>

      {/* ROWS */}
      <div className="divide-y divide-white/5">
        {data.data.map((row, i) => (
          <motion.div 
            key={i}
            initial={{ opacity: 0, x: -20 }}
            animate={{ opacity: 1, x: 0 }}
            transition={{ delay: i * 0.05 }}
            className="grid grid-cols-12 items-center px-8 py-5 hover:bg-white/[0.02] transition-colors group"
          >
            <div className="col-span-1 text-lg font-black italic text-gray-600 group-hover:text-blue-500">
              #{row.rank}
            </div>
            <div className="col-span-1">
               <div className="w-8 h-8 rounded-lg bg-white/5 flex items-center justify-center p-1.5 border border-white/5 group-hover:border-blue-500/30">
                  <span className="text-[10px] font-black text-white/50">{row.team_logo || 'NYY'}</span>
               </div>
            </div>
            <div className="col-span-4 flex items-center gap-4">
              <div className="w-10 h-10 rounded-full bg-white/5 overflow-hidden border border-white/10 group-hover:border-blue-500/50 flex items-center justify-center">
                <img
                   src={`/api/proxy-image?url=${encodeURIComponent(`https://a.espncdn.com/combiner/i?img=/i/headshots/nba/players/full/${row.espn_id}.png`)}`}
                   className="w-full h-full object-cover mt-1 scale-150"
                   alt={row.player_name}
                   onError={e => { (e.target as HTMLImageElement).style.display = 'none'; }}
                />
              </div>
              <div className="flex flex-col">
                <span className="text-sm font-black text-white tracking-tight uppercase">{row.player_name}</span>
                <span className="text-[9px] font-mono text-gray-600 uppercase tracking-widest">PROP_CORR_ACTIVE</span>
              </div>
            </div>
            <div className="col-span-2 text-center">
              <span className="px-3 py-1 rounded bg-blue-500/10 text-blue-400 font-black text-xs">
                {row.metric_value}
              </span>
            </div>
            <div className="col-span-1 text-center">
              <span className="text-[10px] font-bold text-gray-500">{row.season_stat}</span>
            </div>
            <div className="col-span-3">
              <div className="flex flex-col items-end gap-1.5">
                <div className="flex items-center gap-2">
                   <span className="text-xs font-black" style={{ color: row.status_color }}>{(row.ai_score ?? 0).toFixed(1)}</span>
                   <ShieldCheck size={14} style={{ color: row.status_color }} />
                </div>
                <div className="w-full h-2 bg-white/5 rounded-full overflow-hidden border border-white/5">
                   <motion.div 
                     initial={{ width: 0 }}
                     animate={{ width: `${(row.ai_score / 10) * 100}%` }}
                     transition={{ duration: 1, delay: 0.5 + (i * 0.1) }}
                     className="h-full rounded-full"
                     style={{ backgroundColor: row.status_color }}
                   />
                </div>
              </div>
            </div>
          </motion.div>
        ))}
      </div>

      {/* FOOTER */}
      <div className="p-6 bg-white/[0.01] border-t border-white/5 flex justify-between items-center italic">
        <p className="text-[9px] text-gray-600 uppercase font-black tracking-widest leading-none">
          Data synthesized by Gemini 2.5 Flash // Statistical significance σ=2.4 threshold pass
        </p>
        <TrendingUp size={16} className="text-gray-700" />
      </div>
    </div>
  );
};
