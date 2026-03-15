import React, { useState } from 'react';
import { Home, Settings, Menu, X, Zap } from 'lucide-react';
import { clsx } from 'clsx';
import { twMerge } from 'tailwind-merge';

interface SidebarProps {
    activeTab: string;
    onTabChange: (tab: string) => void;
    onOpenSettings: () => void;
}

export const Sidebar: React.FC<SidebarProps> = ({ activeTab, onTabChange, onOpenSettings }) => {
    const [isOpen, setIsOpen] = useState(false);

    const navItems = [
        { id: 'dashboard', label: 'OMNI-CORE', icon: Home },
        { id: 'omniscience', label: 'V12 REBIRTH', icon: Zap },
    ];

    return (
        <>
            {/* Mobile Hamburger */}
            <button
                className="lg:hidden fixed top-3 left-4 z-[60] text-gray-400 hover:text-white"
                onClick={() => setIsOpen(!isOpen)}
            >
                {isOpen ? <X size={24} /> : <Menu size={24} />}
            </button>

            {/* Sidebar Container */}
            <aside className={twMerge(
                "fixed top-0 left-0 h-full bg-black/95 backdrop-blur-xl border-r border-yellow-900/30 shadow-[4px_0_24px_rgba(0,0,0,0.8)] shadow-yellow-900/10 transition-transform duration-300 z-50 w-64 lg:w-20 lg:translate-x-0 pt-16 flex flex-col items-center",
                isOpen ? "translate-x-0" : "-translate-x-full"
            )}>
                <div className="absolute inset-0 bg-[url('https://www.transparenttextures.com/patterns/carbon-fibre.png')] opacity-10 mix-blend-overlay pointer-events-none"></div>
                <nav className="flex-1 w-full flex flex-col gap-4 py-6 relative z-10">
                    {navItems.map((item) => (
                        <button
                            key={item.id}
                            onClick={() => {
                                onTabChange(item.id);
                                setIsOpen(false);
                            }}
                            className={clsx(
                                "flex items-center gap-4 px-6 lg:px-0 lg:justify-center py-3 w-full transition-all duration-300 relative group",
                                activeTab === item.id ? "text-yellow-400 drop-shadow-[0_0_8px_rgba(250,204,21,0.5)]" : "text-gray-500 hover:text-yellow-100"
                            )}
                        >
                            <item.icon size={24} />
                            <span className="lg:hidden font-mono text-sm tracking-wider">{item.label}</span>

                            {/* Desktop Tooltip */}
                            <div className="hidden lg:block absolute left-full ml-4 px-3 py-1.5 bg-black border border-yellow-900/50 shadow-[0_0_15px_rgba(250,204,21,0.2)] text-xs font-black font-mono tracking-widest text-yellow-500 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none z-50">
                                {item.label}
                            </div>

                            {/* Active Indicator */}
                            {activeTab === item.id && (
                                <div className="absolute left-0 top-0 bottom-0 w-1 bg-gradient-to-b from-yellow-300 to-yellow-600 shadow-[2px_0_10px_rgba(250,204,21,0.8)]" />
                            )}
                        </button>
                    ))}
                </nav>

                {/* Settings Button (Bottom) */}
                <button
                    onClick={() => {
                        onOpenSettings();
                        setIsOpen(false);
                    }}
                    className="mb-8 p-3 text-gray-500 hover:text-yellow-400 hover:drop-shadow-[0_0_8px_rgba(250,204,21,0.5)] transition-all duration-300 relative group z-10"
                >
                    <Settings size={24} className="group-hover:rotate-90 transition-transform duration-500" />
                    <div className="hidden lg:block absolute left-full ml-4 px-3 py-1.5 bg-black border border-yellow-900/50 shadow-[0_0_15px_rgba(250,204,21,0.2)] text-[10px] font-black font-mono tracking-widest text-yellow-500 rounded opacity-0 group-hover:opacity-100 transition-opacity whitespace-nowrap pointer-events-none">
                        SYSTEM CONFIG
                    </div>
                </button>
            </aside>

            {/* Overlay for mobile */}
            {isOpen && (
                <div
                    className="fixed inset-0 bg-black/50 z-40 lg:hidden"
                    onClick={() => setIsOpen(false)}
                />
            )}
        </>
    );
};
