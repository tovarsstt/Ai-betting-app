import { useState, useEffect, useCallback } from "react";
import { motion, AnimatePresence } from "framer-motion";
import { DollarSign, TrendingUp, TrendingDown, Plus, Minus, Settings, ChevronDown, ChevronUp } from "lucide-react";
import { bankrollService } from "@/services/BankrollService";
import { cn } from "@/lib/utils";

interface LedgerEntry {
  id: string;
  date: string;
  amount: number;
  type: string;
  status?: string;
  description: string;
  odds?: number;
  confidenceScore?: number;
}

const KELLY_CONFIDENCE_LEVELS = [0.55, 0.60, 0.65, 0.70, 0.75, 0.80];
const DEFAULT_ODDS = 1.91; // -110 equivalent

function formatUSD(n: number) {
  return new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: 0 }).format(n);
}

export function BankrollWidget() {
  const [bankroll, setBankroll] = useState(0);
  const [kellyFraction, setKellyFraction] = useState(0.25);
  const [ledger, setLedger] = useState<LedgerEntry[]>([]);
  const [showConfig, setShowConfig] = useState(false);
  const [showLedger, setShowLedger] = useState(false);
  const [inputAmount, setInputAmount] = useState("");
  const [loading, setLoading] = useState(true);

  const reload = useCallback(async () => {
    const [br, kf, entries] = await Promise.all([
      bankrollService.getBankroll(),
      bankrollService.getKellyFraction(),
      bankrollService.getLedger(),
    ]);
    setBankroll(br);
    setKellyFraction(kf);
    const sorted = [...entries].sort((a, b) => new Date(b.date).getTime() - new Date(a.date).getTime());
    setLedger(sorted.slice(0, 6));
    setLoading(false);
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  const handleDeposit = async () => {
    const amt = parseFloat(inputAmount);
    if (!amt || amt <= 0) return;
    if (bankroll === 0) {
      await bankrollService.setConfig({ totalBankroll: amt, kellyFraction });
    } else {
      await bankrollService.addTransaction(amt, "deposit", `Deposit: ${formatUSD(amt)}`);
    }
    setInputAmount("");
    await reload();
  };

  const handleWithdraw = async () => {
    const amt = parseFloat(inputAmount);
    if (!amt || amt <= 0 || amt > bankroll) return;
    await bankrollService.addTransaction(amt, "withdrawal", `Withdrawal: ${formatUSD(amt)}`);
    setInputAmount("");
    await reload();
  };

  const typeColor = (type: string) => {
    if (type === "deposit" || type === "bet_won") return "text-emerald-400";
    if (type === "withdrawal" || type === "bet_placed" || type === "bet_lost") return "text-red-400";
    return "text-gray-400";
  };

  const typeIcon = (type: string) => {
    if (type === "deposit" || type === "bet_won") return <TrendingUp className="w-3 h-3" />;
    return <TrendingDown className="w-3 h-3" />;
  };

  if (loading) {
    return (
      <div className="bg-white/5 border border-white/10 rounded-3xl p-6 flex items-center justify-center h-28">
        <div className="w-5 h-5 rounded-full border-2 border-t-transparent border-emerald-400 animate-spin" />
      </div>
    );
  }

  return (
    <div className="bg-white/5 border border-white/10 rounded-3xl overflow-hidden">
      {/* Header */}
      <div className="flex items-center justify-between p-6 pb-4">
        <div className="flex items-center gap-3">
          <div className="w-8 h-8 rounded-xl bg-emerald-500/10 border border-emerald-500/20 flex items-center justify-center">
            <DollarSign className="w-4 h-4 text-emerald-400" />
          </div>
          <div>
            <p className="text-[10px] font-black text-gray-500 uppercase tracking-widest">Bankroll Manager</p>
            <p className="text-2xl font-black text-emerald-400 leading-tight">{formatUSD(bankroll)}</p>
          </div>
        </div>
        <button
          onClick={() => setShowConfig(!showConfig)}
          className="p-2 rounded-xl bg-white/5 hover:bg-white/10 transition-colors"
        >
          <Settings className="w-4 h-4 text-gray-500" />
        </button>
      </div>

      {/* Config Panel */}
      <AnimatePresence>
        {showConfig && (
          <motion.div
            initial={{ height: 0, opacity: 0 }}
            animate={{ height: "auto", opacity: 1 }}
            exit={{ height: 0, opacity: 0 }}
            className="overflow-hidden border-t border-white/5"
          >
            <div className="p-4 space-y-3">
              <div className="flex gap-2">
                <input
                  type="number"
                  value={inputAmount}
                  onChange={(e) => setInputAmount(e.target.value)}
                  placeholder={bankroll === 0 ? "Set bankroll ($)" : "Amount ($)"}
                  className="flex-1 bg-white/5 border border-white/10 rounded-xl px-3 py-2 text-sm font-mono outline-none focus:border-emerald-500/50"
                />
                <button
                  onClick={handleDeposit}
                  className="flex items-center gap-1.5 bg-emerald-600 hover:bg-emerald-500 text-white px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-colors"
                >
                  <Plus className="w-3 h-3" />
                  {bankroll === 0 ? "Set" : "Deposit"}
                </button>
                {bankroll > 0 && (
                  <button
                    onClick={handleWithdraw}
                    className="flex items-center gap-1.5 bg-white/5 hover:bg-white/10 border border-white/10 text-gray-400 px-4 py-2 rounded-xl text-xs font-black uppercase tracking-wider transition-colors"
                  >
                    <Minus className="w-3 h-3" />
                    Withdraw
                  </button>
                )}
              </div>
              <div className="flex items-center gap-3">
                <p className="text-[10px] text-gray-500 font-bold uppercase tracking-wider whitespace-nowrap">
                  Kelly Fraction: <span className="text-white">{(kellyFraction * 100).toFixed(0)}%</span>
                </p>
                <input
                  type="range"
                  min={5}
                  max={100}
                  step={5}
                  value={kellyFraction * 100}
                  onChange={async (e) => {
                    const frac = Number(e.target.value) / 100;
                    setKellyFraction(frac);
                    await bankrollService.setConfig({ totalBankroll: bankroll, kellyFraction: frac });
                  }}
                  className="flex-1 accent-emerald-400 h-1.5"
                />
              </div>
            </div>
          </motion.div>
        )}
      </AnimatePresence>

      {/* Kelly Sizing Grid */}
      {bankroll > 0 && (
        <div className="px-6 pb-4">
          <p className="text-[9px] font-black text-gray-600 uppercase tracking-[0.2em] mb-2">
            Kelly Stakes @ {(kellyFraction * 100).toFixed(0)}% Fraction
          </p>
          <div className="grid grid-cols-3 sm:grid-cols-6 gap-1.5">
            {KELLY_CONFIDENCE_LEVELS.map((conf) => {
              const stake = bankrollService.calculateKellyBet(bankroll, conf, DEFAULT_ODDS, kellyFraction);
              const isZero = stake <= 0;
              return (
                <div
                  key={conf}
                  className={cn(
                    "rounded-xl p-2 text-center border",
                    isZero
                      ? "bg-white/3 border-white/5 opacity-40"
                      : "bg-emerald-500/5 border-emerald-500/15"
                  )}
                >
                  <p className="text-[9px] text-gray-500 font-bold">{(conf * 100).toFixed(0)}%</p>
                  <p className={cn("text-xs font-black font-mono", isZero ? "text-gray-600" : "text-emerald-400")}>
                    {isZero ? "—" : `$${stake.toFixed(0)}`}
                  </p>
                </div>
              );
            })}
          </div>
          <p className="text-[9px] text-gray-600 mt-1.5">Confidence → Kelly Stake at -110 odds</p>
        </div>
      )}

      {/* Ledger Toggle */}
      {ledger.length > 0 && (
        <div className="border-t border-white/5">
          <button
            onClick={() => setShowLedger(!showLedger)}
            className="w-full flex items-center justify-between px-6 py-3 text-[10px] font-black text-gray-500 uppercase tracking-widest hover:text-gray-300 transition-colors"
          >
            Recent Transactions ({ledger.length})
            {showLedger ? <ChevronUp className="w-3 h-3" /> : <ChevronDown className="w-3 h-3" />}
          </button>
          <AnimatePresence>
            {showLedger && (
              <motion.div
                initial={{ height: 0, opacity: 0 }}
                animate={{ height: "auto", opacity: 1 }}
                exit={{ height: 0, opacity: 0 }}
                className="overflow-hidden"
              >
                <div className="px-4 pb-4 space-y-1">
                  {ledger.map((entry) => (
                    <div
                      key={entry.id}
                      className="flex items-center justify-between py-1.5 px-3 rounded-xl hover:bg-white/3 transition-colors"
                    >
                      <div className="flex items-center gap-2">
                        <span className={typeColor(entry.type)}>{typeIcon(entry.type)}</span>
                        <span className="text-xs text-gray-400 truncate max-w-[180px]">{entry.description}</span>
                      </div>
                      <span className={cn("text-xs font-black font-mono", typeColor(entry.type))}>
                        {entry.type === "deposit" || entry.type === "bet_won" ? "+" : "-"}
                        {formatUSD(entry.amount)}
                      </span>
                    </div>
                  ))}
                </div>
              </motion.div>
            )}
          </AnimatePresence>
        </div>
      )}

      {/* Empty state */}
      {bankroll === 0 && !showConfig && (
        <div className="px-6 pb-6 text-center">
          <p className="text-xs text-gray-600 mb-3">No bankroll set. Click the gear to initialize.</p>
          <button
            onClick={() => setShowConfig(true)}
            className="text-[10px] font-black text-emerald-500 uppercase tracking-widest hover:text-emerald-400 transition-colors"
          >
            + Set Bankroll
          </button>
        </div>
      )}
    </div>
  );
}
