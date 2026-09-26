import { readFileSync, writeFileSync, existsSync } from 'fs';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname = path.dirname(__filename);
const MEMORY_PATH = path.resolve(__dirname, '../../data/persistent_memory.json');

export class PersistentMemory {
  private data: Record<string, any> = {};

  constructor() {
    this.load();
  }

  private load() {
    try {
      if (existsSync(MEMORY_PATH)) {
        const raw = readFileSync(MEMORY_PATH, 'utf8');
        this.data = JSON.parse(raw);
      }
    } catch (err) {
      console.error("[PersistentMemory] Failed to load memory:", err);
      this.data = {};
    }
  }

  public save() {
    try {
      writeFileSync(MEMORY_PATH, JSON.stringify(this.data, null, 2));
    } catch (err) {
      console.error("[PersistentMemory] Failed to save memory:", err);
    }
  }

  public get(key: string): any {
    return this.data[key];
  }

  public set(key: string, value: any) {
    this.data[key] = value;
    this.save();
  }

  public has(key: string): boolean {
    return key in this.data;
  }

  public delete(key: string) {
    delete this.data[key];
    this.save();
  }

  public clearExpired(now: number) {
    let changed = false;
    for (const key in this.data) {
      if (this.data[key].expires && this.data[key].expires < now) {
        delete this.data[key];
        changed = true;
      }
    }
    if (changed) this.save();
  }
}

export const memory = new PersistentMemory();
