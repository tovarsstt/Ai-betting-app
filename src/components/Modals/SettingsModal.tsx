import React, { useEffect, useState } from 'react';
import { X, Save, DollarSign, Settings } from 'lucide-react';
import { bankrollService } from '../../services/BankrollService';

interface SettingsModalProps {
    isOpen: boolean;
    onClose: () => void;
}

export const SettingsModal: React.FC<SettingsModalProps> = ({ isOpen, onClose }) => {
    const [bankroll, setBankroll] = useState<string>('');
    const [kellyFraction, setKellyFraction] = useState<number>(0.25);
    const [loading, setLoading] = useState(false);

    useEffect(() => {
        if (isOpen) {
            loadSettings();
        }
    }, [isOpen]);

    const loadSettings = async () => {
        try {
            const b = await bankrollService.getBankroll();
            const k = await bankrollService.getKellyFraction();
            setBankroll(b.toString());
            setKellyFraction(k);
        } catch (error) {
            console.error("Failed to load settings", error);
        }
    };

    const handleSave = async () => {
        setLoading(true);
        try {
            await bankrollService.setConfig({
                totalBankroll: parseFloat(bankroll) || 0,
                kellyFraction
            });
            // Optionally trigger a refresh or toast
            onClose();
        } catch (error) {
            console.error("Failed to save settings", error);
        } finally {
            setLoading(false);
        }
    };

    if (!isOpen) return null;

    return (
        <div className="fixed inset-0 z-[100] flex items-center justify-center p-4">
            {/* Backdrop */}
            <div
                className="absolute inset-0 bg-black/80 backdrop-blur-sm"
                onClick={onClose}
            />

            {/* Modal Content */}
            <div className="relative bg-[#18181b] border border-gray-700 rounded-xl w-full max-w-md shadow-2xl p-6">
                <div className="flex justify-between items-center mb-6">
                    <h2 className="text-xl font-bold font-mono text-white flex items-center gap-2">
                        <Settings size={20} className="text-emerald-400" />
                        FUND_MANAGEMENT
                    </h2>
                    <button onClick={onClose} className="text-gray-500 hover:text-white transition-colors">
                        <X size={24} />
                    </button>
                </div>

                <div className="space-y-6">
                    {/* Initial Capital */}
                    <div className="space-y-2">
                        <label className="text-xs font-mono text-gray-400">TOTAL BANKROLL ($)</label>
                        <div className="relative">
                            <DollarSign size={16} className="absolute left-3 top-1/2 -translate-y-1/2 text-gray-500" />
                            <input
                                type="number"
                                value={bankroll}
                                onChange={(e) => setBankroll(e.target.value)}
                                className="w-full bg-black/30 border border-gray-700 rounded-lg py-2 pl-9 pr-4 text-white focus:outline-none focus:border-emerald-500 font-mono transition-colors"
                                placeholder="1000.00"
                            />
                        </div>
                    </div>

                    {/* Kelly Criterion */}
                    <div className="space-y-2">
                        <label className="text-xs font-mono text-gray-400 flex justify-between">
                            <span>KELLY MULTIPLIER</span>
                            <span className="text-emerald-400">{kellyFraction === 1 ? 'FULL KELLY (AGGRESSIVE)' : kellyFraction === 0.5 ? 'HALF KELLY' : 'QUARTER KELLY (CONSERVATIVE)'}</span>
                        </label>
                        <div className="grid grid-cols-3 gap-2">
                            {[0.25, 0.5, 1].map((fraction) => (
                                <button
                                    key={fraction}
                                    onClick={() => setKellyFraction(fraction)}
                                    className={`py-2 px-3 rounded-lg border text-sm font-mono transition-colors ${kellyFraction === fraction
                                        ? 'bg-emerald-500/10 border-emerald-500 text-emerald-400'
                                        : 'bg-black/30 border-gray-700 text-gray-500 hover:border-gray-500'
                                        }`}
                                >
                                    {fraction}x
                                </button>
                            ))}
                        </div>
                    </div>

                    {/* Action Buttons */}
                    <button
                        onClick={handleSave}
                        disabled={loading}
                        className="w-full bg-emerald-600 hover:bg-emerald-500 text-white font-bold py-3 rounded-lg transition-colors flex items-center justify-center gap-2 mt-4"
                    >
                        {loading ? (
                            <span className="animate-spin h-4 w-4 border-2 border-white/20 border-t-white rounded-full" />
                        ) : (
                            <>
                                <Save size={18} />
                                UPDATE_LEDGER
                            </>
                        )}
                    </button>
                </div>
            </div>
        </div>
    );
};
