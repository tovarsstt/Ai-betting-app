import { useState, useEffect } from 'react';
import {
    Cpu, Activity, Zap, Terminal, ShieldAlert,
    Share2, Key, Target, AlertTriangle, Crosshair
} from 'lucide-react';
import ReactMarkdown from 'react-markdown';
import { SocialShareCard } from './SocialShareCard';
import { ParlayShareCard } from './ParlayShareCard'; // Assume Parlay template lives here.

const S0XVisualizer = ({ rawText, onShare }: { rawText: string, onShare: (pick: any) => void }) => {
    try {
        const parsed = JSON.parse(rawText);

        // For array-based returns (Alpha Scan / Ranked Mode)
        if (parsed.status === "ALPHA_ACTIVE" && parsed.picks) {
            return (
                <div className="mt-4 animate-in fade-in duration-500">
                    <div className="bg-gradient-to-br from-gray-900 to-black border border-blue-900/50 rounded-xl p-6 shadow-2xl relative overflow-hidden">
                        <div className="absolute top-0 right-0 w-32 h-32 bg-blue-600/10 blur-3xl rounded-full"></div>
                        <h3 className="text-sm font-black text-blue-400 tracking-widest uppercase mb-4 flex items-center gap-2">
                            <Zap size={16} />
                            Omni-Vector Alpha Detected
                        </h3>

                        <div className="space-y-4 relative z-10">
                            {parsed.picks.map((pick: any, idx: number) => (
                                <div key={idx} className="bg-black/60 border border-gray-800 rounded-lg p-4 flex flex-col md:flex-row md:items-center justify-between gap-4 hover:border-blue-500/30 transition-colors">
                                    <div className="flex-1">
                                        <div className="flex items-center gap-3 mb-2">
                                            <span className="bg-blue-600 text-white text-[10px] font-black px-2 py-0.5 rounded uppercase tracking-wider">
                                                Tier {idx + 1}
                                            </span>
                                            <span className="text-white font-bold text-sm tracking-wide">{pick.label}</span>
                                        </div>
                                        <div className="grid grid-cols-3 gap-2 text-[10px] font-mono mt-3">
                                            <div className="bg-gray-900/80 p-2 rounded border border-gray-800">
                                                <span className="text-gray-500 block mb-1">True Prob</span>
                                                <span className="text-emerald-400 font-bold">{pick.true_probability_percent.toFixed(1)}%</span>
                                            </div>
                                            <div className="bg-gray-900/80 p-2 rounded border border-gray-800">
                                                <span className="text-gray-500 block mb-1">Expected Val</span>
                                                <span className="text-green-400 font-bold">+${pick.expected_value_usd.toFixed(2)}</span>
                                            </div>
                                            <div className="bg-gray-900/80 p-2 rounded border border-gray-800">
                                                <span className="text-gray-500 block mb-1">Kelly Sizing</span>
                                                <span className="text-yellow-400 font-bold">${pick.kelly_sizing_usd.toFixed(2)} Risk</span>
                                            </div>
                                        </div>
                                    </div>
                                    <button
                                        onClick={() => onShare({
                                            lock_type: "QUANT_ALPHA",
                                            tier: `TIER ${idx + 1}`,
                                            lock_text: pick.label,
                                            lock_data: `EV: +$${pick.expected_value_usd.toFixed(2)} | PROB: ${pick.true_probability_percent.toFixed(1)}%`,
                                            headshot_url: pick.headshot_url
                                        })}
                                        className="h-10 px-4 bg-white/5 hover:bg-white/10 text-white rounded font-bold text-[10px] tracking-widest uppercase flex items-center gap-2 border border-white/10 transition-colors shrink-0 whitespace-nowrap"
                                    >
                                        <Share2 size={12} /> Format Social
                                    </button>
                                </div>
                            ))}
                        </div>
                    </div>
                </div>
            );
        }

        // ─────────────────────────────────────────────────────────────
        // ASA v5.0 OMNI-ORACLE VISUALIZER
        // ─────────────────────────────────────────────────────────────
        if (parsed.status === "ASA_V5_OMNISCIENCE_ACTIVE" && parsed.analysis) {
            const a = parsed.analysis;
            const intel = a.LIVE_INTEL || {};
            const sent = a.SENTIMENT_GAP || {};
            const rf = a.RANDOM_FOREST || {};
            const tac = a.TACTICAL_BLUEPRINT || {};
            const ev = a.EV_DISCREPANCY || {};
            const lo = a.LIMIT_ORDER || {};

            const isSharp = ev.IS_SHARP;
            const isTrap = sent.IS_PUBLIC_TRAP;

            return (
                <div className="mt-4 animate-in fade-in zoom-in-95 duration-700">
                    {/* Outer card */}
                    <div className="bg-gradient-to-br from-[#04050a] to-black border border-emerald-500/30 rounded-3xl p-8 shadow-[0_0_80px_rgba(16,185,129,0.08)] relative overflow-hidden">
                        {/* Ambient glow */}
                        <div className="absolute -top-32 -right-32 w-[500px] h-[500px] bg-emerald-600/5 blur-[150px] rounded-full pointer-events-none" />
                        <div className="absolute -bottom-24 -left-24 w-96 h-96 bg-blue-600/5 blur-[120px] rounded-full pointer-events-none" />

                        {/* ── STATUS BAR ── */}
                        <div className="flex items-center justify-between mb-10 relative z-10">
                            <div className="flex items-center gap-4 flex-wrap">
                                <div className="px-3 py-1.5 bg-emerald-500/10 border border-emerald-500/30 rounded-full flex items-center gap-2">
                                    <div className="h-1.5 w-1.5 rounded-full bg-emerald-400 animate-ping" />
                                    <span className="text-[10px] font-black text-emerald-400 tracking-widest uppercase">ASA_V5_OMNISCIENCE</span>
                                </div>
                                <span className="text-[9px] text-gray-600 font-mono">{a.ENGINE} // {a.EXEC_MS}ms</span>
                                {isTrap && (
                                    <span className="px-2 py-1 bg-red-500/10 border border-red-500/30 rounded text-[9px] font-black text-red-400 uppercase tracking-widest animate-pulse">
                                        ⚠️ PUBLIC TRAP DETECTED
                                    </span>
                                )}
                            </div>
                            <button
                                onClick={() => onShare({
                                    lock_type: "ASA_V5_ALPHA",
                                    tier: "OMNISCIENCE",
                                    lock_text: a.ALPHA_PICK,
                                    lock_data: `EDGE: ${ev.EDGE} | EV: ${ev.EXPECTED_VALUE} | SIGNAL: ${ev.SIGNAL}`,
                                    headshot_url: null
                                })}
                                className="px-5 py-2.5 bg-emerald-600 hover:bg-emerald-500 text-black rounded-xl font-black text-[10px] tracking-widest uppercase flex items-center gap-2 transition-all active:scale-95 shadow-lg"
                            >
                                <Share2 size={13} /> EXPORT ALPHA
                            </button>
                        </div>

                        {/* ── TITLE ── */}
                        <div className="mb-10 relative z-10">
                            <h2 className="text-4xl font-black text-white tracking-tighter uppercase italic leading-none mb-3">
                                {a.EVENT_NAME}
                            </h2>
                            <div className="flex items-center gap-3 flex-wrap">
                                <span className="px-3 py-1 bg-emerald-500/10 border border-emerald-500/20 rounded-lg text-[10px] font-black text-emerald-400 uppercase tracking-widest">
                                    🎯 {a.ALPHA_PICK}
                                </span>
                                <div className={`px-3 py-1 rounded-lg border text-[9px] font-black uppercase tracking-widest ${isSharp ? 'bg-emerald-500/10 border-emerald-500/20 text-emerald-400' : 'bg-gray-800/50 border-gray-700 text-gray-500'}`}>
                                    {ev.SIGNAL}
                                </div>
                            </div>
                        </div>

                        {/* ── 5-COLUMN OMNI-ORACLE GRID ── */}
                        <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-5 gap-4 relative z-10">

                            {/* 01 — LIVE INTEL */}
                            <div className="bg-white/[0.02] border border-white/10 p-5 rounded-2xl">
                                <div className="text-[8px] text-blue-400 font-black tracking-widest uppercase mb-4 flex items-center gap-1.5">
                                    <span className="opacity-50">01</span> ⚡ LIVE_INTEL
                                </div>
                                <div className="space-y-3">
                                    <div>
                                        <div className="text-[7px] text-gray-600 uppercase mb-0.5">Injury Impact</div>
                                        <div className="text-xs font-bold text-white">{typeof intel.IMPACT_DELTA === 'number' ? `${(intel.IMPACT_DELTA * 100).toFixed(0)}%` : "N/A"}</div>
                                    </div>
                                    <div>
                                        <div className="text-[7px] text-gray-600 uppercase mb-0.5">Stadium</div>
                                        <div className="text-xs font-bold text-white">{intel.STADIUM}</div>
                                    </div>
                                    <div className="pt-2 border-t border-white/5 text-[9px] text-gray-500">{intel.INJURY_IMPACT}</div>
                                </div>
                            </div>

                            {/* 02 — SENTIMENT GAP */}
                            <div className={`border p-5 rounded-2xl relative overflow-hidden ${isTrap ? 'bg-red-500/5 border-red-500/20' : 'bg-white/[0.02] border-white/10'}`}>
                                <div className="text-[8px] text-rose-400 font-black tracking-widest uppercase mb-4 flex items-center gap-1.5">
                                    <span className="opacity-50">02</span> 📉 SENTIMENT_GAP
                                </div>
                                <div className="space-y-2">
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">Public %</span>
                                        <span className="font-bold text-white">{sent.PUBLIC_SENTIMENT}</span>
                                    </div>
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">True Prob</span>
                                        <span className="font-bold text-emerald-400">{sent.SIM_TRUE_PROB}</span>
                                    </div>
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">Gap</span>
                                        <span className={`font-black ${parseFloat(sent.SENTIMENT_GAP) > 10 ? 'text-red-400' : 'text-yellow-400'}`}>{sent.SENTIMENT_GAP}</span>
                                    </div>
                                    <div className="pt-2 border-t border-white/5">
                                        <div className="text-[8px] font-black text-rose-400 uppercase">{sent.MARKET_SIGNAL}</div>
                                        {sent.IS_REVENGE_ARC && <div className="mt-1 text-[8px] text-yellow-400">⚡ Revenge Arc: {sent.ADRENALINE_DELTA}</div>}
                                    </div>
                                </div>
                            </div>

                            {/* 03 — RANDOM FOREST */}
                            <div className="bg-white/[0.02] border border-white/10 p-5 rounded-2xl">
                                <div className="text-[8px] text-purple-400 font-black tracking-widest uppercase mb-4 flex items-center gap-1.5">
                                    <span className="opacity-50">03</span> 🌲 RANDOM_FOREST
                                </div>
                                <div className="space-y-2">
                                    <div className="text-2xl font-black text-white">{rf.RF_TRUE_PROB}</div>
                                    <div className="text-[8px] text-gray-500 font-mono">{rf.FOREST_VOTES}</div>
                                    <div className="pt-2 border-t border-white/5">
                                        <div className="text-[7px] text-gray-600 uppercase mb-1">Key Factor</div>
                                        <div className="text-[9px] font-bold text-purple-300">{rf.TOP_FACTOR}</div>
                                    </div>
                                    <div className={`px-2 py-1 rounded text-[8px] font-black uppercase ${rf.CONFIDENCE === 'HIGH' ? 'bg-emerald-500/10 text-emerald-400' : 'bg-yellow-500/10 text-yellow-400'}`}>
                                        {rf.CONFIDENCE} CONFIDENCE
                                    </div>
                                </div>
                            </div>

                            {/* 04 — TACTICAL BLUEPRINT */}
                            <div className="bg-purple-500/[0.03] border border-purple-500/20 p-5 rounded-2xl relative overflow-hidden">
                                <div className="absolute -bottom-6 -right-6 text-purple-500/5"><Zap size={80} strokeWidth={3} /></div>
                                <div className="text-[8px] text-purple-400 font-black tracking-widest uppercase mb-4 flex items-center gap-1.5">
                                    <span className="opacity-50">04</span> 🧠 TACTICAL_BLUEPRINT
                                </div>
                                <div className="space-y-2">
                                    <div>
                                        <div className="text-[7px] text-gray-600 uppercase mb-0.5">Blended Prob</div>
                                        <div className="text-2xl font-black text-white">{tac.BLENDED_PROB}</div>
                                    </div>
                                    <div className="text-[9px] font-bold text-purple-400">{tac.PIVOT_POINT}</div>
                                    <div className="pt-2 border-t border-white/5 text-[9px] text-gray-400 leading-relaxed">{tac.MATCH_SCRIPT}</div>
                                </div>
                            </div>

                            {/* 05 — +EV DISCREPANCY */}
                            <div className={`border p-5 rounded-2xl ${isSharp ? 'bg-emerald-500/5 border-emerald-500/30' : 'bg-white/[0.02] border-white/10'}`}>
                                <div className="text-[8px] text-emerald-400 font-black tracking-widest uppercase mb-4 flex items-center gap-1.5">
                                    <span className="opacity-50">05</span> ⚖️ +EV_FILTER
                                </div>
                                <div className="space-y-3">
                                    <div>
                                        <div className="text-[7px] text-gray-600 uppercase mb-0.5">Value Edge</div>
                                        <div className={`text-2xl font-black ${isSharp ? 'text-emerald-400' : 'text-yellow-400'}`}>{ev.EDGE}</div>
                                    </div>
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">EV</span>
                                        <span className="font-bold text-white">{ev.EXPECTED_VALUE}</span>
                                    </div>
                                    <div className="flex justify-between text-xs">
                                        <span className="text-gray-500">Kelly Stake</span>
                                        <span className="font-bold text-blue-400">{ev.KELLY_STAKE}</span>
                                    </div>
                                    {/* Limit Order */}
                                    {lo.MAKER_AMERICAN && (
                                        <div className="pt-2 border-t border-white/5">
                                            <div className="text-[7px] text-yellow-500 uppercase font-black mb-1">🏦 LIMIT ORDER</div>
                                            <div className="text-lg font-black text-yellow-400">{lo.MAKER_AMERICAN}</div>
                                            <div className="text-[8px] text-gray-500 mt-1">{lo.STRATEGY}</div>
                                        </div>
                                    )}
                                </div>
                            </div>
                        </div>

                        {/* ── ENGINE FOOTER ── */}
                        <div className="mt-8 pt-6 border-t border-white/5 flex justify-between items-center relative z-10 flex-wrap gap-4">
                            <div className="flex items-center gap-6 flex-wrap text-[8px]">
                                <span className="text-gray-600 uppercase font-bold">Random Forest: <span className="text-white">100 Trees</span></span>
                                <span className="text-gray-600 uppercase font-bold">Monte Carlo: <span className="text-white">10,000 Sims</span></span>
                                <span className="text-gray-600 uppercase font-bold">Sharp Edge: <span className="text-emerald-400">&gt;4%</span></span>
                            </div>
                            <div className="text-[8px] text-gray-600 font-mono uppercase tracking-widest">
                                Antigravity Sharp Architect // v5.0
                            </div>
                        </div>
                    </div>
                </div>
            );
        }

        // --- QSA v4.0 VISUALIZER (Legacy) ---
        if (parsed.status === "QSA_V4_EVOLUTION_ACTIVE" && parsed.analysis) {
            const qsa = parsed.analysis;
            const edge = qsa.EDGE_CALCULATION;

            return (
                <div className="mt-4 animate-in fade-in zoom-in-95 duration-700">
                    <div className="bg-gradient-to-br from-[#050608] to-black border border-purple-500/40 rounded-2xl p-8 shadow-[0_0_60px_rgba(168,85,247,0.15)] relative overflow-hidden group">
                        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10 pointer-events-none"></div>
                        <div className="absolute -top-24 -right-24 w-96 h-96 bg-purple-600/10 blur-[120px] rounded-full group-hover:bg-purple-600/20 transition-all duration-1000"></div>
                        
                        {/* Status Bar */}
                        <div className="flex items-center justify-between mb-10 relative z-10">
                            <div className="flex items-center gap-4">
                                <div className="px-3 py-1 bg-purple-500/10 border border-purple-500/30 rounded-full flex items-center gap-2">
                                    <div className="h-1.5 w-1.5 rounded-full bg-purple-400 animate-ping"></div>
                                    <span className="text-[10px] font-black text-purple-400 tracking-widest uppercase">QSA_V4_EVOLUTION_ACTIVE</span>
                                </div>
                                <span className="text-[10px] text-gray-500 font-mono tracking-tighter">{qsa.DIAGNOSTIC}</span>
                            </div>
                            <button
                                onClick={() => onShare({
                                    lock_type: "QSA_V4_ALPHA",
                                    tier: "OMNISCIENCE",
                                    lock_text: qsa.ALPHA_PICK,
                                    lock_data: `PROB: ${edge.SIM_WIN_PROB} | EDGE: ${edge.VALUE_EDGE}`,
                                    headshot_url: null
                                })}
                                className="px-5 py-2.5 bg-purple-600 hover:bg-purple-500 text-white rounded-lg font-black text-[10px] tracking-widest uppercase flex items-center gap-2 transition-all active:scale-95 shadow-lg shadow-purple-900/20"
                            >
                                <Share2 size={14} /> EXPORT ALPHA
                            </button>
                        </div>

                        {/* Title Section */}
                        <div className="mb-10 relative z-10">
                            <h2 className="text-4xl font-black text-white tracking-tighter uppercase italic leading-none mb-3">
                                {qsa.EVENT_NAME}
                            </h2>
                            <div className="flex items-center gap-3">
                                <span className="px-3 py-1 bg-white/5 border border-white/10 rounded-md text-[9px] font-bold text-gray-400 uppercase tracking-widest">
                                    SHARP_SELECTION
                                </span>
                                <div className="h-px w-12 bg-purple-500/30"></div>
                                <span className="text-xl font-black text-purple-400 uppercase tracking-tighter">
                                    {qsa.ALPHA_PICK}
                                </span>
                            </div>
                        </div>

                        {/* QSA Subroutine Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-4 gap-4 relative z-10">
                            {/* DATA HARVEST */}
                            <div className="bg-white/[0.03] border border-white/10 p-5 rounded-2xl group/card hover:bg-white/[0.05] transition-colors">
                                <div className="text-[9px] text-purple-400 font-black tracking-widest uppercase mb-4 opacity-50">01. DATA_HARVEST</div>
                                <div className="text-xs text-white/80 font-medium leading-relaxed">
                                    {qsa.LIVE_INTEL}
                                </div>
                            </div>

                            {/* TACTICAL GEOMETRY */}
                            <div className="bg-white/[0.03] border border-white/10 p-5 rounded-2xl hover:bg-white/[0.05] transition-colors">
                                <div className="text-[9px] text-purple-400 font-black tracking-widest uppercase mb-4 opacity-50">02. TACTICAL_BLUEPRINT</div>
                                <div className="text-xs text-white/80 font-medium leading-relaxed">
                                    {qsa.TACTICAL_BLUEPRINT}
                                </div>
                            </div>

                            {/* PIVOT POINT */}
                            <div className="bg-purple-500/5 border border-purple-500/20 p-5 rounded-2xl relative overflow-hidden group/pivot">
                                <div className="absolute -bottom-4 -right-4 text-purple-500/10 rotate-12">
                                    <Zap size={80} strokeWidth={3} />
                                </div>
                                <div className="text-[9px] text-purple-400 font-black tracking-widest uppercase mb-4">03. THE_PIVOT_POINT</div>
                                <div className="text-2xl font-black text-white mb-1">{qsa.PIVOT_POINT}</div>
                                <div className="text-[8px] text-purple-400/60 font-mono uppercase">Critical Probability Shift Detected</div>
                            </div>

                            {/* EDGE CALC */}
                            <div className="bg-emerald-500/5 border border-emerald-500/20 p-5 rounded-2xl">
                                <div className="text-[9px] text-emerald-400 font-black tracking-widest uppercase mb-4">04. EDGE_CALCULATION</div>
                                <div className="flex justify-between items-end">
                                    <div>
                                        <div className="text-[8px] text-gray-500 font-bold uppercase mb-1">Sim Win %</div>
                                        <div className="text-2xl font-black text-white">{edge.SIM_WIN_PROB}</div>
                                    </div>
                                    <div className="text-right">
                                        <div className="text-[8px] text-emerald-500 font-bold uppercase mb-1">Alpha Edge</div>
                                        <div className="text-xl font-black text-emerald-400">{edge.VALUE_EDGE}</div>
                                    </div>
                                </div>
                                <div className="mt-4 pt-4 border-t border-white/5 flex items-center justify-between">
                                    <span className="text-[8px] text-gray-600 font-bold uppercase">Market Implied: {edge.MARKET_IMPLIED}</span>
                                    <div className="flex gap-1">
                                        {[1,2,3,4,5].map(i => (
                                            <div key={i} className={`h-1 w-2 rounded-full ${i <= 4 ? 'bg-emerald-500' : 'bg-gray-800'}`}></div>
                                        ))}
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Self-Evolution Footer */}
                        <div className="mt-8 pt-6 border-t border-white/5 flex justify-between items-center relative z-10">
                            <div className="flex items-center gap-6">
                                <div className="flex items-center gap-2">
                                    <span className="text-[8px] text-gray-500 font-bold uppercase">Model Status:</span>
                                    <span className="text-[9px] text-blue-400 font-black uppercase">Self-Correcting</span>
                                </div>
                                <div className="flex items-center gap-2">
                                    <span className="text-[8px] text-gray-500 font-bold uppercase">Iterations:</span>
                                    <span className="text-[9px] text-white font-black">10,000 Atomic Sims</span>
                                </div>
                            </div>
                            <div className="text-[8px] text-gray-600 font-mono uppercase tracking-widest">
                                Quantum Sports Architect // V4.0.0
                            </div>
                        </div>
                    </div>
                </div>
            );
        }

        // --- V12 SHARP SYNDICATION RESOLUTION ---
        if (parsed.status === "V12_SHARP_ACTIVE" && parsed.analysis?.SYNDICATION_BLOCK) {
            const block = parsed.analysis.SYNDICATION_BLOCK;
            const metrics = block.METRICS;
            const risk = block.RISK_MGMT;

            return (
                <div className="mt-4 animate-in fade-in zoom-in-95 duration-500">
                    <div className="bg-gradient-to-br from-[#0c0d10] to-black border border-blue-500/30 rounded-2xl p-8 shadow-[0_0_50px_rgba(37,99,235,0.15)] relative overflow-hidden group">
                        {/* Background Patterns */}
                        <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10 pointer-events-none"></div>
                        <div className="absolute top-0 right-0 w-96 h-96 bg-blue-600/5 blur-[120px] rounded-full -translate-y-1/2 translate-x-1/2 group-hover:bg-blue-600/10 transition-colors"></div>
                        
                        {/* Header Area */}
                        <div className="flex flex-col md:flex-row justify-between items-start md:items-center gap-4 mb-8 relative z-10">
                            <div>
                                <div className="flex items-center gap-2 mb-2">
                                    <div className="h-2 w-2 rounded-full bg-blue-500 animate-pulse"></div>
                                    <span className="text-[10px] font-black text-blue-500 tracking-[0.4em] uppercase">{block.HEADER}</span>
                                </div>
                                <h2 className="text-3xl font-black text-white tracking-tighter uppercase italic">{block.PRIMARY_PICK}</h2>
                                <span className="inline-block mt-2 px-3 py-1 bg-blue-600/10 border border-blue-500/20 rounded text-[9px] font-mono text-blue-400 font-bold uppercase tracking-widest">
                                    {block.SPORT_CORE}
                                </span>
                            </div>
                            
                            <button
                                onClick={() => onShare({
                                    lock_type: "V12_SHARP_BLOCK",
                                    tier: "ALPHA_LOCK",
                                    lock_text: block.PRIMARY_PICK,
                                    lock_data: `PROB: ${metrics.MODEL_PROB} | EDGE: ${metrics.MARKET_EDGE} | EV: ${metrics.ADJ_EV}`,
                                    headshot_url: null
                                })}
                                className="px-6 py-3 bg-white text-black rounded-lg font-black text-[11px] tracking-widest uppercase flex items-center gap-3 hover:bg-blue-500 hover:text-white transition-all shadow-xl active:scale-95"
                            >
                                <Share2 size={14} /> Syndication Export
                            </button>
                        </div>

                        {/* Content Grid */}
                        <div className="grid grid-cols-1 md:grid-cols-3 gap-4 relative z-10">
                            {/* Projections */}
                            <div className="bg-white/5 border border-white/10 p-5 rounded-xl backdrop-blur-sm">
                                <span className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-4 block">OMNI_PROJECTIONS</span>
                                <div className="space-y-4">
                                    <div>
                                        <div className="text-[9px] text-gray-500 font-bold uppercase mb-1">Model Confidence</div>
                                        <div className="text-2xl font-black text-white">{metrics.MODEL_PROB}</div>
                                    </div>
                                    <div className="h-1.5 w-full bg-gray-800 rounded-full overflow-hidden">
                                        <div 
                                            className="h-full bg-blue-500 rounded-full" 
                                            style={{ width: metrics.MODEL_PROB }}
                                        ></div>
                                    </div>
                                </div>
                            </div>

                            {/* Market Edge */}
                                    <div className="bg-white/5 border border-white/10 p-5 rounded-xl backdrop-blur-sm">
                                        <span className="text-[10px] text-gray-500 font-mono uppercase tracking-widest mb-4 block">EFFICIENCY_DELTA</span>
                                        <div className="space-y-4">
                                            <div>
                                                <div className="text-[9px] text-gray-500 font-bold uppercase mb-1">Market Edge</div>
                                                <div className="text-2xl font-black text-emerald-400">{metrics.MARKET_EDGE}</div>
                                            </div>
                                            {parsed.analysis?.sharp_variables?.under_3_5_prob && (
                                                <div className="pt-2 border-t border-white/5">
                                                    <div className="text-[8px] text-emerald-500/80 font-mono uppercase tracking-[0.2em] mb-1">Under 3.5 Prob</div>
                                                    <div className="text-sm font-bold text-white">{parsed.analysis.sharp_variables.under_3_5_prob}</div>
                                                </div>
                                            )}
                                        </div>
                                    </div>

                                    {/* OMNISCIENCE DEPTH (HIDDEN VARIABLES) */}
                                    {metrics.DEEP_FEATURES && (
                                        <div className="bg-purple-600/5 border border-purple-500/20 p-5 rounded-xl backdrop-blur-sm relative overflow-hidden group">
                                            <div className="absolute top-0 right-0 p-2 opacity-20">
                                                <div className="w-12 h-12 border-2 border-purple-500 rounded-full animate-ping"></div>
                                            </div>
                                            <span className="text-[10px] text-purple-400 font-black uppercase tracking-widest mb-4 block">OMNISCIENCE_DEPTH</span>
                                            <div className="grid grid-cols-2 gap-4">
                                                <div className="space-y-1">
                                                    <div className="text-[8px] text-gray-500 font-mono uppercase">Jet Lag Tax</div>
                                                    <div className="text-sm font-black text-purple-300">x{metrics.DEEP_FEATURES.JET_LAG_TAX?.toFixed(3)}</div>
                                                </div>
                                                <div className="space-y-1">
                                                    <div className="text-[8px] text-gray-500 font-mono uppercase">Narrative Stress</div>
                                                    <div className="text-sm font-black text-rose-300">x{metrics.DEEP_FEATURES.NARRATIVE_STRESS?.toFixed(2)}</div>
                                                </div>
                                                <div className="col-span-2 pt-2 border-t border-purple-500/10">
                                                    <div className="flex justify-between items-center">
                                                        <span className="text-[9px] text-purple-400 font-bold uppercase">Quantum CFI Index</span>
                                                        <span className={`text-[10px] font-black ${metrics.DEEP_FEATURES.CFI > 1.0 ? 'text-rose-400' : 'text-emerald-400'}`}>
                                                            {metrics.DEEP_FEATURES.CFI?.toFixed(4)}
                                                        </span>
                                                    </div>
                                                    <div className="w-full bg-gray-800 h-1 mt-1 rounded-full overflow-hidden">
                                                        <div 
                                                            className={`h-full transition-all duration-1000 ${metrics.DEEP_FEATURES.CFI > 1.0 ? 'bg-rose-500' : 'bg-emerald-500'}`} 
                                                            style={{ width: `${Math.min(100, (metrics.DEEP_FEATURES.CFI / 2) * 100)}%` }}
                                                        ></div>
                                                    </div>
                                                </div>
                                            </div>
                                        </div>
                                    )}

                            {/* Risk Management */}
                            <div className="bg-blue-600/10 border border-blue-500/30 p-5 rounded-xl backdrop-blur-sm relative">
                                <div className="absolute top-4 right-4 text-blue-500/20">
                                    <ShieldAlert size={40} />
                                </div>
                                <span className="text-[10px] text-blue-400 font-mono uppercase tracking-widest mb-4 block">RISK_ALLOCATION</span>
                                <div className="space-y-4">
                                    <div>
                                        <div className="text-[9px] text-gray-400 font-bold uppercase mb-1">Suggested Stake</div>
                                        <div className="text-2xl font-black text-white">{risk.SUGGESTED_STAKE}</div>
                                    </div>
                                    <div className="flex items-center gap-2">
                                        <div className={`h-2 w-2 rounded-full ${risk.CONFIDENCE === 'ALPHA_LOCK' ? 'bg-emerald-500' : 'bg-yellow-500'}`}></div>
                                        <span className={`text-[11px] font-black tracking-widest ${risk.CONFIDENCE === 'ALPHA_LOCK' ? 'text-emerald-400' : 'text-yellow-400'}`}>
                                            {risk.CONFIDENCE}
                                        </span>
                                    </div>
                                </div>
                            </div>
                        </div>

                        {/* Footer Diagnostic */}
                        <div className="mt-8 flex items-center justify-between border-t border-white/5 pt-4 text-[9px] font-mono text-gray-600 tracking-wider">
                            <div className="flex items-center gap-4">
                                <span>{block.V12_DIAGNOSTIC}</span>
                                <span className="h-3 w-px bg-gray-800"></span>
                                <span>ENCRYPTION: SHARP_V4</span>
                            </div>
                            <span className="text-blue-900/40 font-black">PROPRIETARY_OMNI_CORE</span>
                        </div>
                    </div>
                </div>
            );
        }

        // --- SINGLE MATCHUP V11 RESOLUTION [WITH SGP SUPPORT] ---
        const {
            matchup, date_context, target_odds, vig_adjusted_ev, alpha_edge,
            primary_lock, derivative_alpha, correlation_play, sgp_builder, synthetic_edge, teaser_builder, exact_score_builder
        } = parsed;

        // Ensure we handle missing components securely depending on Python state
        const picksArray = [primary_lock, derivative_alpha, correlation_play, sgp_builder, synthetic_edge, teaser_builder, exact_score_builder].filter(Boolean);

        return (
            <div className="mt-4 animate-in fade-in duration-500 space-y-4">

                {/* Hero Genesis Block */}
                <div className="bg-[#0f1115] border border-gray-800 rounded-xl p-6 relative overflow-hidden">
                    <div className="absolute top-0 right-0 w-64 h-64 bg-yellow-600/5 blur-[100px] rounded-full pointer-events-none"></div>

                    <div className="flex flex-col md:flex-row justify-between md:items-end mb-6 border-b border-gray-800/50 pb-4">
                        <div>
                            <div className="text-yellow-500/80 font-mono text-[10px] uppercase tracking-[0.3em] mb-2 flex items-center gap-2">
                                <Key size={12} /> God-Engine V11 Resolution
                            </div>
                            <h2 className="text-2xl font-black text-white uppercase tracking-tight">{matchup}</h2>
                            <div className="text-gray-500 text-xs font-mono mt-1">{date_context}</div>
                        </div>
                        <div className="mt-4 md:mt-0 flex gap-2">
                            <div className="bg-black/60 border border-gray-800 px-3 py-1.5 rounded flex flex-col items-center">
                                <span className="text-[9px] text-gray-500 uppercase tracking-widest font-mono">Target Odds</span>
                                <span className="text-sm font-black text-white">{target_odds}</span>
                            </div>
                            <div className="bg-black/60 border border-gray-800 px-3 py-1.5 rounded flex flex-col items-center">
                                <span className="text-[9px] text-gray-500 uppercase tracking-widest font-mono">Adj. EV</span>
                                <span className="text-sm font-black text-green-400">{vig_adjusted_ev}</span>
                            </div>
                        </div>
                    </div>

                    <div className="space-y-3 relative z-10">
                        {picksArray.map((pick: any, idx: number) => {
                            let accentColor = "yellow";
                            let TitleIcon = Target;
                            let titleName = "Primary Alpha Lock";

                            if (idx === 1) {
                                accentColor = "blue";
                                TitleIcon = Activity;
                                titleName = "Derivative Prop Target";
                            } else if (idx === 2) {
                                accentColor = "purple";
                                TitleIcon = Cpu;
                                titleName = "Macro Correlation Hedge";
                            } else if (idx === 3) {
                                accentColor = "emerald";
                                TitleIcon = Zap;
                                titleName = "SGP Architecture";
                            } else if (idx === 4) {
                                accentColor = "rose";
                                TitleIcon = Activity;
                                titleName = "Synthetic Cross-Prop";
                            } else if (idx === 5) {
                                accentColor = "orange";
                                TitleIcon = Target;
                                titleName = "Stanford Wong Teaser";
                            } else if (idx === 6) {
                                accentColor = "cyan";
                                TitleIcon = Crosshair;
                                titleName = "Poisson Exact Score";
                            }

                            return (
                                <div key={idx} className={`bg-black/40 border border-${accentColor}-900/30 rounded-lg p-4 hover:bg-black/60 transition-colors`}>
                                    <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 mb-3">
                                        <div className="flex items-center gap-2">
                                            <TitleIcon size={14} className={`text-${accentColor}-500`} />
                                            <span className={`text-[10px] font-bold text-${accentColor}-500 uppercase tracking-widest`}>
                                                {titleName}
                                            </span>
                                        </div>
                                        <button
                                            onClick={() => onShare({
                                                lock_type: titleName,
                                                tier: `TIER ${idx + 1}`,
                                                lock_text: pick.label,
                                                lock_data: `AI PROB: ${pick.true_probability_percent}%`,
                                                headshot_url: pick.headshot_url // Passing native ESPN URL down
                                            })}
                                            className="h-8 px-3 bg-white/5 hover:bg-white/10 text-white rounded font-bold text-[9px] tracking-widest uppercase flex items-center gap-2 border border-white/10 transition-colors shrink-0"
                                        >
                                            <Share2 size={10} /> Social View
                                        </button>
                                    </div>

                                    <div className="mb-3">
                                        <span className="text-white font-black text-lg tracking-tight px-3 py-1 bg-white/5 rounded block w-max">{pick.label}</span>
                                    </div>

                                    <p className="text-xs text-gray-400 leading-relaxed font-mono border-l-2 border-gray-700 pl-3">
                                        {pick.analysis_rationale}
                                    </p>

                                    <div className="grid grid-cols-3 gap-2 mt-4 border-t border-gray-800/50 pt-3">
                                        <div>
                                            <div className="text-[9px] text-gray-500 uppercase tracking-widest font-mono">Edge Factor</div>
                                            <div className={`text-sm font-bold text-${accentColor}-400`}>{pick.edge.toFixed(2)}x</div>
                                        </div>
                                        <div>
                                            <div className="text-[9px] text-gray-500 uppercase tracking-widest font-mono">Engine Prob</div>
                                            <div className="text-sm font-bold text-white">{pick.true_probability_percent}%</div>
                                        </div>
                                        <div>
                                            <div className="text-[9px] text-gray-500 uppercase tracking-widest font-mono">Suggested Risk</div>
                                            <div className="text-sm font-bold text-yellow-500">${pick.kelly_sizing_usd.toFixed(2)}</div>
                                        </div>
                                    </div>
                                </div>
                            );
                        })}
                    </div>

                    <div className="mt-4 flex items-center justify-between bg-yellow-900/10 border border-yellow-900/20 p-3 rounded text-[10px] font-mono text-yellow-500">
                        <div className="flex items-center gap-2">
                            <AlertTriangle size={12} />
                            <span>V11 ALPHA EDGE DIAGNOSTIC</span>
                        </div>
                        <span className="font-black text-xs">{alpha_edge} vs Public Market</span>
                    </div>
                </div>
            </div>
        );
    } catch (e) {
        return (
            <div className="mt-4 p-4 bg-black/20 rounded-lg border border-gray-800/50 overflow-y-auto max-h-[500px] prose prose-invert prose-sm max-w-none">
                <ReactMarkdown>{rawText}</ReactMarkdown>
            </div>
        );
    }
};

const TerminalLoader = ({ text, mode }: { text: string, mode?: string }) => {
    const [streamIndex, setStreamIndex] = useState(0);

    // Singularity Pulse: Neuromorphic Data Streams
    const dataStreams = [
        "ACTIVATING NVIDIA NEUROCHIP CORE...",
        "SYNTAXING 10TB QUIBILLION QUANTUM TENSOR CLUSTER...",
        "ANALYZING REVERSE LINE MOVEMENT (SHARP TRAPS)...",
        "INTERCEPTING LOCAL POLICE SCANNERS (OSINT)...",
        "TRACING OFFSHORE WHALE CRYPTO-WALLETS...",
        "DECODING SUPER-AGENT FLIGHT PATHS...",
        "CALCULATING API LATENCY DELTAS...",
        "EXECUTING ZERO-RISK HEDGE MATRICES...",
        "SCRAPING COACH AUDIO FOR NLP HESITATIONS...",
        "CALCULATING LEAGUE GAME 7 REVENUE SCRIPTING..."
    ];

    useEffect(() => {
        const interval = setInterval(() => {
            setStreamIndex(prev => (prev + 1) % dataStreams.length);
        }, 1200); // Fast pulse
        return () => clearInterval(interval);
    }, []);

    let steps = [
        "> INITIATING OMNI-CONVERGENCE MATRIX...",
        "> SCRAPING DARK DATA & BIOMETRIC DISTRESS...",
        "> INTERCEPTING OFFSHORE CRYPTO WALLETS...",
        "> CALCULATING INSTITUTIONAL REVENUE SCRIPTING...",
        "> SYNTHESIZING 10-BILLION CAUSAL VECTORS..."
    ];

    if (mode === "NBA_PROPS") {
        steps = [
            "> INITIALIZING LIVE INJURY SYNAPSE...",
            "> CROSS-REFERENCING 2026 NBA ROSTERS...",
            "> CALCULATING ALGORITHMIC USAGE VACUUMS...",
            "> ISOLATING HIGH-EV PLAYER PROJECTIONS...",
            "> FINALIZING ALPHA EDGE DISCREPANCY..."
        ];
    } else if (mode === "ALPHA_SCAN") {
        steps = [
            "> INITIATING SLATE-WIDE ARBITRAGE SCAN...",
            "> ANALYZING GLOBAL LIQUIDITY POOLS...",
            "> HUNTING VEGAS MISPRICINGS...",
            "> ISOLATING HIGHEST MATHEMATICAL EDGE...",
            "> SECURING ALPHA POSITION..."
        ];
    }

    return (
        <div className="w-full bg-[#050505] rounded-lg border border-gray-800 p-4 font-mono text-xs overflow-hidden relative shadow-2xl mt-4">
            <div className="absolute top-0 left-0 w-full h-1 bg-gradient-to-r from-blue-900 via-blue-500 to-blue-900 opacity-50 animate-pulse"></div>

            <div className="flex items-center gap-2 text-gray-500 mb-4 pb-2 border-b border-gray-900">
                <Terminal size={12} className="text-blue-500" />
                <span className="tracking-[0.2em]">{text}</span>
            </div>

            <div className="space-y-2 opacity-80">
                {steps.map((step, i) => (
                    <div
                        key={i}
                        className="animate-in slide-in-from-left-2 fade-in"
                        style={{
                            animationDelay: `${i * 800}ms`,
                            animationFillMode: 'both',
                            color: i === steps.length - 1 ? '#3b82f6' : '#6b7280'
                        }}
                    >
                        {step}
                    </div>
                ))}
            </div>

            <div className="mt-6 pt-3 border-t border-gray-900 flex justify-between items-center text-[9px] text-gray-600">
                <div className="flex items-center gap-2">
                    <span className="w-2 h-2 rounded-full bg-blue-500 animate-pulse"></span>
                    <span className="text-blue-500 tracking-wider mix-blend-screen">{dataStreams[streamIndex]}</span>
                </div>
                <span>TENSOR_CORE_ACTIVE</span>
            </div>
        </div>
    );
};

export const IntelligenceEngine = () => {
    const [sport, setSport] = useState("NBA");
    const [context, setContext] = useState("");
    const [isAnalyzing, setIsAnalyzing] = useState(false);
    const [result, setResult] = useState<string | null>(null);
    const [error, setError] = useState("");

    // Sharp Variables
    const [homeFortress, setHomeFortress] = useState(1.0);
    const [tacticalBias, setTacticalBias] = useState(1.0);

    // Social Sharing Modals
    const [showShareCard, setShowShareCard] = useState(false);
    const [selectedPick, setSelectedPick] = useState<any>(null);
    const [socialTheme, setSocialTheme] = useState<'antigravity' | 'minimal' | 'default'>('antigravity');

    const handleAnalysis = async () => {
        if (!context.trim()) {
            setError("Neural matrix requires input vectors. Target Matchup must be defined.");
            return;
        }

        setIsAnalyzing(true);
        setError("");

        try {
            // Check if asking for parlay/multi-game scan
            if (context.toLowerCase().includes("find") || context.toLowerCase().includes("slate") || context.toLowerCase().includes("best picks")) {
                context.split(" ");
                const res = await fetch(`http://localhost:8001/simulate-ranked`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        matchup: context,
                        sport: sport,
                        sharp_odds: 1.90,
                        soft_odds: 2.00,
                        bankroll: 25.0
                    })
                });

                if (!res.ok) throw new Error("Ranked Engine Failed");
                const data = await res.json();
                setResult(JSON.stringify(data));
                setIsAnalyzing(false);
                return;
            }

            // Normal V11 single-game execution
            const res = await fetch(`http://localhost:8001/v11/analyze`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    matchup: context,
                    sport: sport,
                    sharp_odds: 1.90, // Defaults
                    soft_odds: 2.00,
                    bankroll: 25.0,
                    market_spread: 0.0,
                    injury_impact_score: 0.0,
                    time_remaining_mins: 0.0,
                    distraction_index: 0.0,
                    home_fortress: homeFortress,
                    tactical_bias: tacticalBias
                })
            });

            if (!res.ok) {
                const errData = await res.json();
                throw new Error(errData.detail || "V11 API Fault");
            }

            const data = await res.json();
            setResult(JSON.stringify(data));

        } catch (err: any) {
            console.error("V11 Fatal Error:", err);
            setError(`QUANT_CORE_FAULT: ${err.message}. Ensure node server and python engine are running (Ports 3001, 8001).`);
        } finally {
            setIsAnalyzing(false);
        }
    };

    return (
        <div className="p-4 md:p-8 max-w-[1400px] mx-auto min-h-screen bg-black text-gray-200">
            {/* Context/Input Area */}
            <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 relative z-10">
                <div className="lg:col-span-4 flex flex-col gap-6">
                    <div className="bg-[#0a0a0a] border border-gray-800 rounded-xl p-5 shadow-2xl relative overflow-hidden">
                        <div className="flex items-center gap-3 mb-6">
                            <Cpu className="text-blue-500" size={20} />
                            <h2 className="text-sm font-black tracking-widest uppercase">Target Acquisition</h2>
                        </div>

                        <div className="flex gap-2 mb-4 flex-wrap">
                            {["NBA", "NFL", "MLB", "SOCCER", "UFC", "TENNIS", "F1", "NCAAB", "NCAAW", "CFB", "WNBA"].map((s) => (
                                <button
                                    key={s}
                                    onClick={() => setSport(s)}
                                    className={`flex-1 py-1.5 text-[10px] font-bold rounded uppercase tracking-wider transition-colors ${sport === s
                                            ? 'bg-blue-600 text-white'
                                            : 'bg-gray-900 border border-gray-800 text-gray-400 hover:bg-gray-800'
                                        }`}
                                >
                                    {s}
                                </button>
                            ))}
                        </div>

                        <div className="space-y-4">
                            <div>
                                <label className="block text-[10px] text-gray-500 font-mono uppercase mb-2">Omni-Vector Input</label>
                                <textarea
                                    value={context}
                                    onChange={(e) => setContext(e.target.value)}
                                    className="w-full h-32 bg-black border border-gray-800 rounded-lg p-3 text-sm text-white placeholder-gray-700 focus:outline-none focus:border-blue-500 focus:ring-1 focus:ring-blue-500 transition-all resize-none shadow-inner"
                                    placeholder={`e.g., "Lakers vs Nuggets"\ne.g., "Find the 3 highest mathematical edges in the NBA tonight"`}
                                />
                            </div>

                            {/* SHARP CALIBRATION LAYER */}
                            <div className="bg-blue-600/5 border border-blue-500/10 rounded-lg p-4 space-y-4">
                                <div className="flex items-center justify-between">
                                    <span className="text-[10px] font-black text-blue-500 uppercase tracking-widest">Sharp Calibration</span>
                                    <div className="h-1.5 w-1.5 rounded-full bg-blue-500 animate-pulse"></div>
                                </div>
                                
                                <div className="space-y-3">
                                    <div>
                                        <div className="flex justify-between text-[9px] font-mono text-gray-500 uppercase mb-1">
                                            <span>Home Fortress</span>
                                            <span className="text-blue-400">x{homeFortress.toFixed(2)}</span>
                                        </div>
                                        <input 
                                            type="range" min="0.8" max="1.5" step="0.05"
                                            value={homeFortress} 
                                            onChange={(e) => setHomeFortress(parseFloat(e.target.value))}
                                            className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-blue-500"
                                        />
                                    </div>
                                    
                                    <div>
                                        <div className="flex justify-between text-[9px] font-mono text-gray-500 uppercase mb-1">
                                            <span>Tactical Bias (Under/Over)</span>
                                            <span className="text-emerald-400">x{tacticalBias.toFixed(2)}</span>
                                        </div>
                                        <input 
                                            type="range" min="0.5" max="1.5" step="0.05"
                                            value={tacticalBias} 
                                            onChange={(e) => setTacticalBias(parseFloat(e.target.value))}
                                            className="w-full h-1.5 bg-gray-800 rounded-lg appearance-none cursor-pointer accent-emerald-500"
                                        />
                                    </div>
                                </div>
                                <div className="text-[8px] text-gray-600 font-mono leading-tight">
                                    Injecting manual sharp variables to bypass market inefficiency. Use for "Hell" stadiums or defensive grinds.
                                </div>
                            </div>

                            <button
                                onClick={handleAnalysis}
                                disabled={isAnalyzing}
                                className={`w-full py-3 rounded-lg font-black text-xs tracking-[0.2em] uppercase transition-all flex items-center justify-center gap-2 ${isAnalyzing
                                        ? 'bg-gray-800 text-gray-500 cursor-not-allowed'
                                        : 'bg-blue-600 hover:bg-blue-500 text-white shadow-[0_0_20px_rgba(37,99,235,0.4)]'
                                    }`}
                            >
                                {isAnalyzing ? 'SYNTHESIZING VECTORS...' : 'INITIALIZE GOD-ENGINE'}
                            </button>
                            {error && (
                                <div className="text-red-400 text-[10px] font-mono mt-2 flex items-start gap-2 bg-red-900/10 p-2 rounded border border-red-900/30">
                                    <ShieldAlert size={12} className="shrink-0 mt-0.5" />
                                    <span>{error}</span>
                                </div>
                            )}
                        </div>
                    </div>

                    {/* Passive Status Node */}
                    <div className="bg-[#050505] border border-gray-900 rounded-xl p-4 font-mono text-[10px] text-gray-600 space-y-2">
                        <div className="flex justify-between items-center pb-2 border-b border-gray-900">
                            <span>SYSTEM STATUS</span>
                            <span className="text-blue-500">NOMINAL</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span>V11 LOGIC NODE</span>
                            <span className="text-emerald-500">ONLINE</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span>ACTION NETWORK API</span>
                            <span className="text-emerald-500">SYNCED</span>
                        </div>
                        <div className="flex justify-between items-center">
                            <span>BALLDONTLIE API</span>
                            <span className="text-emerald-500">SYNCED</span>
                        </div>
                    </div>
                </div>

                {/* Output/Visualization Area */}
                <div className="lg:col-span-8 flex flex-col">
                    <div className="bg-[#0a0a0a] border border-gray-800 rounded-xl p-1 flex-1 shadow-2xl relative overflow-hidden flex flex-col">
                        <div className="absolute inset-x-0 top-0 h-px bg-gradient-to-r from-transparent via-blue-900 to-transparent"></div>

                        <div className="p-4 border-b border-gray-900 flex items-center justify-between">
                            <div className="flex items-center gap-2">
                                <Terminal size={14} className="text-gray-500" />
                                <span className="font-mono text-[10px] text-gray-500 tracking-[0.2em] uppercase">Matrix Output Resolution</span>
                            </div>
                            {isAnalyzing && (
                                <div className="flex items-center gap-2">
                                    <div className="w-1.5 h-1.5 bg-red-500 rounded-full animate-pulse"></div>
                                    <span className="text-[9px] font-mono text-gray-500">PROCESSING</span>
                                </div>
                            )}
                        </div>

                        <div className="p-4 flex-1 overflow-y-auto">
                            {isAnalyzing ? (
                                <TerminalLoader text={`COMPILING ${sport} DATASOURCES`} mode={
                                    context.toLowerCase().includes("find") ? "ALPHA_SCAN" :
                                        (sport === "NBA" ? "NBA_PROPS" : "QUANTUM_ARBITRAGE")
                                } />
                            ) : result ? (
                                <div className="animate-in fade-in zoom-in-95 duration-300">

                                    {/* EXPORT CONTROL HEADER */}
                                    <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 bg-gray-900/40 border border-gray-800/60 p-4 rounded-xl mb-4">
                                        <div className="flex flex-col gap-1">
                                            <span className="text-white font-bold text-sm tracking-wide">Data Extraction Complete</span>
                                            <span className="text-gray-400 text-xs font-mono">Select a pick block to format for social syndication.</span>
                                        </div>

                                        <div className="flex items-center gap-4">
                                            <div className="flex flex-col">
                                                <label className="text-[10px] font-mono text-gray-400 uppercase tracking-widest mb-1">Export Theme:</label>
                                                <select
                                                    value={socialTheme}
                                                    onChange={(e) => setSocialTheme(e.target.value as any)}
                                                    className="bg-black border border-gray-700 text-white text-xs font-bold rounded-md px-3 py-1.5 focus:outline-none focus:border-blue-500 outline-none"
                                                >
                                                    <option value="antigravity">Antigravity (Dynamic)</option>
                                                    <option value="minimal">Minimal (Clean)</option>
                                                    <option value="default">Classic (Default)</option>
                                                </select>
                                            </div>
                                        </div>
                                    </div>

                                    <S0XVisualizer
                                        rawText={result}
                                        onShare={(pick) => {
                                            setSelectedPick(pick);
                                            setShowShareCard(true);
                                        }}
                                    />
                                </div>
                            ) : (
                                <div className="h-full flex flex-col items-center justify-center text-gray-700 opacity-50 relative min-h-[300px]">
                                    <Target size={48} className="mb-4 text-gray-800" strokeWidth={1} />
                                    <span className="font-mono text-xs tracking-widest">[ V11_AWAITING_INPUT ]</span>
                                    <div className="absolute inset-0 bg-[radial-gradient(circle_at_center,rgba(255,255,255,0.02)_0%,transparent_70%)] pointer-events-none"></div>
                                </div>
                            )}
                        </div>
                    </div>
                </div>
            </div>

            {/* Social Sharing Portal */}
            {showShareCard && result && (
                result.includes("ALPHA_ACTIVE") ? (
                    <ParlayShareCard
                        data={JSON.parse(result)}
                        onClose={() => setShowShareCard(false)}
                    />
                ) : (
                    <SocialShareCard
                        data={JSON.parse(result)}
                        specificPick={selectedPick}
                        theme={socialTheme}
                        onClose={() => {
                            setShowShareCard(false);
                            setSelectedPick(null);
                        }}
                    />
                )
            )}
        </div>
    );
};
