/**
 * lineMovementService.ts
 * Calls the Python Kronos adapter to predict bet line movement direction.
 *
 * Line → OHLCVA mapping (Kronos financial model):
 *   open/high/low/close = line values, volume/amount = bet volume & handle
 */
import { spawn } from 'child_process';
import path from 'path';
import { fileURLToPath } from 'url';

const __filename = fileURLToPath(import.meta.url);
const __dirname  = path.dirname(__filename);

const ADAPTER_PATH = path.resolve(__dirname, '../../scripts/kronos_adapter.py');
const KRONOS_CWD   = path.resolve(__dirname, '../../scripts/kronos');

export interface LineRecord {
  open:   number;
  high:   number;
  low:    number;
  close:  number;
  volume: number;
  amount: number;
}

export interface LineMovementSignal {
  direction:  'up' | 'down';
  mean:       number[];
  std:        number[];
  confidence: number;
}

export interface LineMovementError {
  error: string;
  note?: string;
}

export type LineMovementResult = LineMovementSignal | LineMovementError;

export async function predictLineMovement(
  history: LineRecord[],
  steps    = 3,
  nSamples = 30,
): Promise<LineMovementResult> {
  if (history.length < 5) {
    return { error: 'Need at least 5 line records' };
  }

  return new Promise((resolve) => {
    const input = JSON.stringify({ history, steps, n_samples: nSamples });
    const py    = spawn('python3', [ADAPTER_PATH, '--json'], { cwd: KRONOS_CWD });

    let stdout = '';
    let stderr = '';
    py.stdout.on('data', (chunk: Buffer) => { stdout += chunk.toString(); });
    py.stderr.on('data', (chunk: Buffer) => { stderr += chunk.toString(); });
    py.stdin.write(input);
    py.stdin.end();

    const timer = setTimeout(() => {
      py.kill();
      resolve({ error: 'Kronos timeout after 90s' });
    }, 90_000);

    py.on('close', () => {
      clearTimeout(timer);
      try {
        const result = JSON.parse(stdout.trim()) as LineMovementResult;
        if ('error' in result) { resolve(result); return; }

        const sig      = result as LineMovementSignal;
        const avgMean  = sig.mean.reduce((a, b) => a + Math.abs(b), 0) / sig.mean.length;
        const avgStd   = sig.std.reduce((a, b) => a + b, 0) / sig.std.length;
        const confidence = avgMean > 0 ? Math.max(0, Math.min(1, 1 - avgStd / avgMean)) : 0;
        resolve({ ...sig, confidence });
      } catch {
        resolve({ error: 'Kronos parse failed', note: stderr.slice(0, 200) });
      }
    });
  });
}

/** Build LineRecord history from a flat array of closing lines (oldest first). */
export function buildHistoryFromClosingLines(closingLines: number[]): LineRecord[] {
  return closingLines.map((close, i) => {
    const prev = closingLines[i - 1] ?? close;
    return {
      open:   prev,
      high:   Math.max(prev, close),
      low:    Math.min(prev, close),
      close,
      volume: 0,
      amount: 0,
    };
  });
}
