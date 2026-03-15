import React, { useState } from 'react';
import { motion } from 'framer-motion';
import { Brain, Activity, Target, Shield, Zap } from 'lucide-react';

interface Prediction {
  matchup: string;
  composite_probability: number;
  neuro_link_score: number;
  mc_details: {
    avg_score_a: number;
    avg_score_b: number;
    win_prob_a: number;
  };
  primary_lock?: {
    player_name: string;
    prop_line: string;
    display_label: string;
  };
}

const OmniscienceV12: React.FC = () => {
  const [predictions] = useState<Prediction[]>([]);
  // Use status for visual indicators
  const engineStatus = "Active (Local Ensemble)";

  const aestheticClasses = {
    card: "bg-slate-900/80 backdrop-blur-xl border border-slate-700/50 rounded-2xl p-6 shadow-2xl relative overflow-hidden",
    glow: "absolute -inset-1 bg-gradient-to-r from-purple-600 to-cyan-500 rounded-2xl blur opacity-25 group-hover:opacity-50 transition duration-1000 group-hover:duration-200",
    textGradient: "bg-clip-text text-transparent bg-gradient-to-r from-teal-400 to-blue-500",
    metricLabel: "text-slate-500 text-xs font-mono uppercase tracking-widest"
  };

  return (
    <div className="min-h-screen bg-[#050505] text-slate-100 p-8 font-sans">
      <header className="mb-12 flex justify-between items-end">
        <div>
          <h1 className="text-5xl font-black tracking-tighter mb-2 italic">
            PROJECT <span className={aestheticClasses.textGradient}>OMNISCIENCE</span>
          </h1>
          <p className="text-slate-400 font-mono text-sm max-w-md uppercase">
            V12 Rebirth: Self-Correcting Non-Linear Prediction Ecosystem
          </p>
        </div>
        <div className="text-right">
          <div className="flex items-center gap-2 text-cyan-400 mb-1">
            <Shield size={16} />
            <span className="text-xs font-mono uppercase tracking-tighter">Status: {engineStatus}</span>
          </div>
          <div className="text-slate-600 text-[10px] font-mono uppercase">ENGINE_VERSION: 12.1.0-ALPHA-BUILD</div>
        </div>
      </header>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-8">
        {/* Main Intelligence Grid */}
        <div className="lg:col-span-2 space-y-8">
          <div className={aestheticClasses.card}>
            <div className="flex items-center gap-3 mb-6">
              <Brain className="text-purple-500" />
              <h2 className="text-xl font-bold tracking-tight">Active Neural Inference</h2>
            </div>
            
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {predictions.length > 0 ? (
                predictions.map((pred, i) => (
                  <div key={i} className="p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 group relative">
                    <div className="flex justify-between items-start mb-4">
                      <div>
                        <span className={aestheticClasses.metricLabel}>{pred.matchup}</span>
                        <div className="text-lg font-bold">{pred.primary_lock?.display_label || 'MATCHUP_LOADED'}</div>
                      </div>
                      <div className="text-xs px-2 py-1 bg-green-500/10 text-green-400 rounded-full border border-green-500/20 font-mono">
                        EDGE: +5.2%
                      </div>
                    </div>
                    
                    <div className="space-y-4">
                      <div>
                        <div className="flex justify-between text-xs mb-1">
                          <span className="text-slate-500 uppercase">Composite Probability</span>
                          <span className="font-bold text-teal-400 italic">{(pred.composite_probability * 100).toFixed(1)}%</span>
                        </div>
                        <div className="w-full h-1.5 bg-slate-700 rounded-full overflow-hidden">
                          <motion.div 
                            initial={{ width: 0 }}
                            animate={{ width: `${pred.composite_probability * 100}%` }}
                            className="h-full bg-gradient-to-r from-teal-500 to-blue-500 shadow-[0_0_10px_rgba(20,184,166,0.5)]"
                          />
                        </div>
                      </div>
                    </div>

                    <div className="mt-4 pt-4 border-t border-slate-700/30 grid grid-cols-5 gap-1">
                      {[1, 2, 3, 4, 5].map((_, i) => (
                        <div key={i} className={`h-1.5 rounded-full ${i < 3 ? 'bg-cyan-500/50' : 'bg-slate-700'}`} />
                      ))}
                    </div>
                  </div>
                ))
              ) : (
                <div className="p-4 bg-slate-800/40 rounded-xl border border-slate-700/50 group relative opacity-50">
                  <div className="flex justify-between items-start mb-4">
                    <div>
                      <span className={aestheticClasses.metricLabel}>LAKERS @ KNICKS</span>
                      <div className="text-lg font-bold">MATCHUP_LOADED</div>
                    </div>
                    <div className="text-xs px-2 py-1 bg-green-500/10 text-green-400 rounded-full border border-green-500/20 font-mono">
                      EDGE: +5.2%
                    </div>
                  </div>
                  <div className="text-xs text-slate-500 italic mt-8 text-center uppercase tracking-widest">Awaiting Neural Link Data...</div>
                </div>
              )}
            </div>
          </div>

          {/* Performance Heatmap Placeholder */}
          <div className={aestheticClasses.card}>
            <div className="flex items-center gap-3 mb-6">
              <Activity className="text-teal-400" />
              <h2 className="text-xl font-bold tracking-tight">System Velocity (PnL Heatmap)</h2>
            </div>
            <div className="h-48 w-full bg-slate-800/20 rounded-xl flex items-center justify-center border border-dashed border-slate-700/50">
               <span className="text-slate-600 font-mono text-xs uppercase tracking-widest italic">Visualizing Neural Convergence...</span>
            </div>
          </div>
        </div>

        {/* Accountability Sidebar */}
        <div className="space-y-8">
          <div className={aestheticClasses.card}>
            <div className="flex items-center gap-3 mb-6">
              <Zap className="text-yellow-400" size={20} />
              <h2 className="text-lg font-bold tracking-tight uppercase tracking-wider">Accountability Ledger</h2>
            </div>
            
            <div className="space-y-4">
              {[1, 2, 3].map((bet) => (
                <div key={bet} className="flex items-center justify-between p-3 bg-white/5 rounded-lg border border-white/5">
                  <div className="flex flex-col">
                    <span className="text-[10px] text-slate-500 uppercase font-mono">03/08/26 . 15.2% KELLY</span>
                    <span className="text-sm font-semibold">Game ID: #V12_9821</span>
                  </div>
                  <div className="text-sm font-mono text-green-400">+$245.00</div>
                </div>
              ))}
            </div>
            
            <button className="w-full mt-6 py-3 bg-slate-100 text-slate-900 rounded-xl font-black uppercase text-xs tracking-widest hover:bg-white transition-all transform hover:scale-[1.02] active:scale-[0.98]">
              Generate TikTok Share Card
            </button>
          </div>

          <div className={aestheticClasses.card}>
            <div className="flex items-center gap-3 mb-6">
              <Target className="text-red-500" size={20} />
              <h2 className="text-lg font-bold tracking-tight uppercase tracking-wider italic">Neuro-Quant Meta</h2>
            </div>
            <div className="space-y-3">
              <div className="flex justify-between text-xs">
                 <span className="text-slate-500">Circadian Friction Bias</span>
                 <span className="text-purple-400">+1.25</span>
              </div>
              <div className="flex justify-between text-xs">
                 <span className="text-slate-500">Tilt Tensor Impact</span>
                 <span className="text-red-400">-0.45</span>
              </div>
              <div className="flex justify-between text-xs">
                 <span className="text-slate-500">Fatigue Decay Index</span>
                 <span className="text-yellow-400">0.82</span>
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
};

export default OmniscienceV12;
