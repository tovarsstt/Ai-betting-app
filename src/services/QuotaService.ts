import { openDB, type DBSchema, type IDBPDatabase } from 'idb';
import { v4 as uuidv4 } from 'uuid';

interface QuotaLog {
    id: string;
    timestamp: string;
    action: string;
    inputTokens: number;
    outputTokens: number;
    cost: number;
}

interface QuotaConfig {
    totalBudget: number; // Hard cap $300
    totalBurned: number;
}

interface QuotaDB extends DBSchema {
    logs: {
        key: string;
        value: QuotaLog;
    };
    config: {
        key: string;
        value: QuotaConfig;
    };
}

const DB_NAME = 'oracle-quota-db';
const DB_VERSION = 1;

// Pricing: $0.10/1M input, $0.40/1M output
const PRICE_PER_MILLION_INPUT = 0.10;
const PRICE_PER_MILLION_OUTPUT = 0.40;

export class QuotaService {
    private dbPromise: Promise<IDBPDatabase<QuotaDB>>;

    constructor() {
        if (typeof indexedDB === 'undefined') {
            // Node.js / Server-side fallback (or just mock for CLI scripts)
            console.warn("QuotaService: IndexedDB not available, using in-memory mock.");
            this.dbPromise = Promise.resolve({
                get: async () => ({ totalBudget: 300, totalBurned: 0 }),
                put: async () => null,
                add: async () => null,
                transaction: (_storeNames: any, _mode: any) => ({
                    objectStore: (_name: string) => ({
                        get: async (_key: string) => ({ totalBudget: 300, totalBurned: 0 }),
                        put: async (_val: any, _key: any) => null,
                        add: async (_val: any) => null
                    }),
                    done: Promise.resolve()
                }),
                objectStoreNames: { contains: () => true },
                createObjectStore: () => { }
            } as any);
        } else {
            this.dbPromise = openDB<QuotaDB>(DB_NAME, DB_VERSION, {
                upgrade(db) {
                    if (!db.objectStoreNames.contains('logs')) {
                        db.createObjectStore('logs', { keyPath: 'id' });
                    }
                    if (!db.objectStoreNames.contains('config')) {
                        db.createObjectStore('config');
                    }
                },
            });
        }
    }

    async initializeBudget(amount: number = 300): Promise<void> {
        const db = await this.dbPromise;
        const existing = await db.get('config', 'main');
        if (!existing) {
            await db.put('config', { totalBudget: amount, totalBurned: 0 }, 'main');
        }
    }

    async getStatus(): Promise<QuotaConfig> {
        const db = await this.dbPromise;
        const config = await db.get('config', 'main');
        return config || { totalBudget: 300, totalBurned: 0 };
    }

    calculateCost(inputTokens: number, outputTokens: number): number {
        const inputCost = (inputTokens / 1_000_000) * PRICE_PER_MILLION_INPUT;
        const outputCost = (outputTokens / 1_000_000) * PRICE_PER_MILLION_OUTPUT;
        return inputCost + outputCost;
    }

    async logUsage(action: string, inputTokens: number, outputTokens: number): Promise<boolean> {
        const cost = this.calculateCost(inputTokens, outputTokens);
        const db = await this.dbPromise;

        const tx = db.transaction(['logs', 'config'], 'readwrite');
        const configStore = tx.objectStore('config');
        const logStore = tx.objectStore('logs');

        const config = await configStore.get('main');
        if (!config) throw new Error("Quota not initialized");

        if (config.totalBurned + cost > config.totalBudget) {
            // Reject if over budget? Or allow and warn?
            // Requirement: "Safety: MANUAL TRIGGERS ONLY. No background API calls."
            // Assuming strict cost control means we should stop.
            // But maybe we return false to indicate budget exceeded.
            return false;
        }

        config.totalBurned += cost;
        await configStore.put(config, 'main');

        await logStore.add({
            id: uuidv4(),
            timestamp: new Date().toISOString(),
            action,
            inputTokens,
            outputTokens,
            cost
        });

        await tx.done;
        return true;
    }

    async getRemainingBudget(): Promise<number> {
        const status = await this.getStatus();
        return status.totalBudget - status.totalBurned;
    }
}

export const quotaService = new QuotaService();
