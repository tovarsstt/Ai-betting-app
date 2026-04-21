import { useQuery, useMutation } from '@tanstack/react-query';
import type { SwarmFinalPayload, AlphaSheetContainer } from '../types/swarm';

const API_BASE = 'http://localhost:3001/api';

export function useAlphaSheets(sport: string = 'NBA') {
    return useQuery<AlphaSheetContainer>({
        queryKey: ['alpha-sheets', sport],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/alpha-sheets`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ sport })
            });
            if (!res.ok) throw new Error('Failed to fetch Alpha Sheets');
            return res.json();
        }
    });
}

export function useAnalyzeUnified() {
    return useMutation<SwarmFinalPayload, Error, { matchup: string; sport: string }>({
        mutationFn: async ({ matchup, sport }) => {
            const res = await fetch(`${API_BASE}/analyze-unified`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ matchup, sport })
            });
            if (!res.ok) throw new Error('Failed to analyze matchup');
            return res.json();
        }
    });
}

// Legacy Mappings (Hardened)
export function useListPredictions() {
    return useQuery<unknown[]>({
        queryKey: ['predictions'],
        queryFn: async () => []
    });
}

export function useListEvSignals() {
    return useQuery<unknown[]>({
        queryKey: ['ev-signals'],
        queryFn: async () => []
    });
}

export function useListMatchups() {
    return useQuery<unknown[]>({
        queryKey: ['matchups'],
        queryFn: async () => []
    });
}

export function useListLineMovements() {
    return useQuery<unknown[]>({
        queryKey: ['line-movements'],
        queryFn: async () => []
    });
}

export function useListTeams() {
    return useQuery<unknown[]>({
        queryKey: ['teams'],
        queryFn: async () => []
    });
}

export function useGetTeamPerformance(_teamId: string) {
    return useQuery<unknown>({
        queryKey: ['team-performance', _teamId],
        queryFn: async () => undefined
    });
}

