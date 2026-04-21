import { motion } from 'framer-motion';
import { Cpu, MessageSquare, ShieldAlert, Zap } from 'lucide-react';

const nodes = [
  { id: 'quant', label: 'QUANT ASSASSIN', icon: Zap, color: '#3b82f6' },
  { id: 'sim', label: 'SCENARIO SCOUT', icon: MessageSquare, color: '#a855f7' },
  { id: 'omqx', label: 'OMQX CONVERGENCE', icon: Cpu, color: '#22c55e' },
  { id: 'audit', label: 'MARKET AUDITOR', icon: ShieldAlert, color: '#ef4444' },
];

export const DeerTaskGraph = ({ activeNode }: { activeNode: number }) => {
  return (
    <div className="relative w-full h-48 bg-white/5 border border-white/10 rounded-3xl overflow-hidden p-6 flex items-center justify-between">
      {/* BACKGROUND GRID */}
      <div className="absolute inset-0 opacity-10 pointer-events-none" 
           style={{ backgroundImage: 'linear-gradient(#fff 1px, transparent 1px), linear-gradient(90deg, #fff 1px, transparent 1px)', backgroundSize: '20px 20px' }} />
      
      {/* CONNECTOR LINES */}
      <div className="absolute inset-x-20 top-1/2 h-[2px] bg-white/10 -translate-y-1/2 z-0">
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: activeNode >= 1 ? '33.33%' : '0%' }}
            className="h-full bg-blue-500 shadow-[0_0_15px_rgba(59,130,246,0.5)] absolute left-0"
          />
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: activeNode >= 2 ? '33.33%' : '0%' }}
            className="h-full bg-purple-500 shadow-[0_0_15px_rgba(168,85,247,0.5)] absolute left-[33.33%]"
          />
          <motion.div 
            initial={{ width: 0 }}
            animate={{ width: activeNode >= 3 ? '33.33%' : '0%' }}
            className="h-full bg-emerald-500 shadow-[0_0_15px_rgba(34,197,94,0.5)] absolute left-[66.66%]"
          />
      </div>

      {nodes.map((node, i) => (
        <div key={node.id} className="relative z-10 flex flex-col items-center gap-3">
          <motion.div
            animate={{ 
              scale: activeNode === i ? 1.2 : 1,
              borderColor: activeNode === i ? node.color : 'rgba(255,255,255,0.1)',
              backgroundColor: activeNode === i ? `${node.color}20` : 'transparent'
            }}
            className="w-16 h-16 rounded-2xl border-2 flex items-center justify-center transition-colors shadow-2xl backdrop-blur-md"
          >
            <node.icon size={28} className={activeNode === i ? 'text-white' : 'text-gray-600'} />
            
            {activeNode === i && (
                <motion.div 
                  layoutId="glow"
                  className="absolute inset-0 rounded-2xl blur-xl opacity-50"
                  style={{ backgroundColor: node.color }}
                />
            )}
            
            {activeNode > i && (
                <motion.div 
                  initial={{ scale: 0 }}
                  animate={{ scale: 1 }}
                  className="absolute -top-1 -right-1 w-5 h-5 bg-green-500 rounded-full border-2 border-[#070b0d] flex items-center justify-center"
                >
                    <div className="w-2 h-2 bg-white rounded-full animate-pulse" />
                </motion.div>
            )}
          </motion.div>
          <span className={`text-[9px] font-black uppercase tracking-[0.2em] ${activeNode === i ? 'text-white' : 'text-gray-600'}`}>
            {node.label}
          </span>
        </div>
      ))}
    </div>
  );
};
