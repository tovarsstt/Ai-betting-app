import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import { v4 as uuidv4 } from 'uuid';

interface LedgerEntry {
    id: string;
    date: string;
    amount: number;
    type: 'deposit' | 'withdrawal' | 'bet_placed' | 'bet_won' | 'bet_lost';
    status?: 'pending' | 'won' | 'lost';
    description: string;
    eventId?: string;
    odds?: number;
    confidenceScore?: number;
}

interface BankrollConfig {
    totalBankroll: number;
    kellyFraction: number;
}

interface OracleDB extends DBSchema {
    ledger: {
        key: string;
        value: LedgerEntry;
    };
    config: {
        key: string;
        value: BankrollConfig;
    };
}

const DB_NAME = 'oracle-audit-db';
const DB_VERSION = 1;

export class BankrollService {
    private dbPromise: Promise<IDBPDatabase<OracleDB>>;

    constructor() {
        this.dbPromise = openDB<OracleDB>(DB_NAME, DB_VERSION, {
            upgrade(db) {
                if (!db.objectStoreNames.contains('ledger')) {
                    db.createObjectStore('ledger', { keyPath: 'id' });
                }
                if (!db.objectStoreNames.contains('config')) {
                    db.createObjectStore('config');
                }
            },
        });
    }

    async setConfig(config: BankrollConfig): Promise<void> {
        const db = await this.dbPromise;
        await db.put('config', config, 'main');
    }

    async getBankroll(): Promise<number> {
        const db = await this.dbPromise;
        const config = await db.get('config', 'main');
        return config?.totalBankroll || 0;
    }

    async getKellyFraction(): Promise<number> {
        const db = await this.dbPromise;
        const config = await db.get('config', 'main');
        return config?.kellyFraction || 0.25;
    }

    calculateKellyBet(bankroll: number, winProb: number, decimalOdds: number, fraction: number = 1): number {
        if (decimalOdds <= 1) return 0;

        const b = decimalOdds - 1;
        const p = winProb;
        const q = 1 - p;
        const f = (b * p - q) / b;

        if (f <= 0) return 0;

        return bankroll * f * fraction;
    }

    calculateEV(winProb: number, decimalOdds: number): number {
        const profit = decimalOdds - 1;
        const ev = (winProb * profit) - (1 - winProb);
        return ev;
    }

    isValueBet(winProb: number, decimalOdds: number): boolean {
        return this.calculateEV(winProb, decimalOdds) > 0;
    }

    async addTransaction(amount: number, type: LedgerEntry['type'], description: string, opts?: { eventId?: string, odds?: number, status?: LedgerEntry['status'], confidenceScore?: number }): Promise<string> {
        const db = await this.dbPromise;
        const tx = db.transaction(['ledger', 'config'], 'readwrite');

        const id = uuidv4();

        const entry: LedgerEntry = {
            id,
            date: new Date().toISOString(),
            amount,
            type,
            description,
            eventId: opts?.eventId,
            odds: opts?.odds,
            confidenceScore: opts?.confidenceScore,
            status: opts?.status || (type === 'bet_placed' ? 'pending' : undefined)
        };
        await tx.objectStore('ledger').add(entry);

        const configStore = tx.objectStore('config');
        const existingConfig = await configStore.get('main') || { totalBankroll: 0, kellyFraction: 0.25 };

        switch (type) {
            case 'deposit':
            case 'bet_won':
                existingConfig.totalBankroll += amount;
                break;
            case 'withdrawal':
            case 'bet_placed':
                existingConfig.totalBankroll -= amount;
                break;
            case 'bet_lost':
                // No change, stake was already deducted on place
                break;
        }

        await configStore.put(existingConfig, 'main');
        await tx.done;

        return id;
    }

    async resolveBet(id: string, result: 'won' | 'lost'): Promise<void> {
        const db = await this.dbPromise;
        const tx = db.transaction(['ledger', 'config'], 'readwrite');
        const ledgerStore = tx.objectStore('ledger');
        const configStore = tx.objectStore('config');

        const entry = await ledgerStore.get(id);
        if (!entry || entry.type !== 'bet_placed' || entry.status !== 'pending') {
            await tx.done;
            return; // Can only resolve pending bets
        }

        // Update status
        entry.status = result;
        entry.type = result === 'won' ? 'bet_won' : 'bet_lost'; // Visually update type
        await ledgerStore.put(entry);

        // Update Bankroll
        const existingConfig = await configStore.get('main') || { totalBankroll: 0, kellyFraction: 0.25 };

        if (result === 'won') {
            const returnAmount = entry.amount * (entry.odds || 2.0); // Default to 2.0 if no odds
            existingConfig.totalBankroll += returnAmount;
        }

        await configStore.put(existingConfig, 'main');
        await tx.done;
    }

    async deleteTransaction(id: string): Promise<void> {
        const db = await this.dbPromise;
        const tx = db.transaction(['ledger', 'config'], 'readwrite');
        const ledgerStore = tx.objectStore('ledger');
        const configStore = tx.objectStore('config');

        const entry = await ledgerStore.get(id);
        if (!entry) {
            await tx.done;
            return;
        }

        // Revert Bankroll changes if needed
        const existingConfig = await configStore.get('main') || { totalBankroll: 0, kellyFraction: 0.25 };

        switch (entry.type) {
            case 'deposit':
                existingConfig.totalBankroll -= entry.amount;
                break;
            case 'withdrawal':
            case 'bet_placed':
                existingConfig.totalBankroll += entry.amount;
                break;
            case 'bet_lost':
                // Undo the stake deduction that happened at placement
                existingConfig.totalBankroll += entry.amount;
                break;
            case 'bet_won':
                // Undo: win payout (+returnAmount) and original stake deduction (-stake)
                // Net needed: -returnAmount + stake
                existingConfig.totalBankroll -= entry.amount * (entry.odds || 2.0); // undo payout
                existingConfig.totalBankroll += entry.amount; // undo stake deduction
                break;
        }

        await configStore.put(existingConfig, 'main');
        await ledgerStore.delete(id);
        await tx.done;
    }

    async getLedger(): Promise<LedgerEntry[]> {
        const db = await this.dbPromise;
        return db.getAll('ledger');
    }
}

export const bankrollService = new BankrollService();
