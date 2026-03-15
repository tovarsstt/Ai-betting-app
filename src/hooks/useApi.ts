import { useQuery, useMutation } from '@tanstack/react-query';

const API_BASE = '/api/v12';

export function useListPredictions() {
    return useQuery<any[]>({
        queryKey: ['predictions'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/predictions`);
            if (!res.ok) throw new Error('Failed to fetch predictions');
            const result = await res.json();
            return result.data || []; 
        }
    });
}

export function useListEvSignals() {
    return useQuery<any[]>({
        queryKey: ['ev-signals'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/ev-signals`);
            if (!res.ok) throw new Error('Failed to fetch EV signals');
            const result = await res.json();
            return result.data || [];
        }
    });
}

export function useListLineMovements() {
    return useQuery<any[]>({
        queryKey: ['line-movements'],
        queryFn: async () => []
    });
}

export function useListTeams() {
    return useQuery<any[]>({
        queryKey: ['teams'],
        queryFn: async () => []
    });
}

export function useGetTeamPerformance(teamId: string) {
    return useQuery<any>({
        queryKey: ['team-performance', teamId],
        queryFn: async () => null,
        enabled: !!teamId
    });
}

export function useListMatchups() {
    return useQuery<any[]>({
        queryKey: ['matchups'],
        queryFn: async () => []
    });
}

export function useIngestMatchup() {
    return useMutation({
        mutationFn: async (payload: { sport: string; matchup: string; trueProbability: number; marketDecimalOdds: number }) => {
            const res = await fetch(`${API_BASE}/ingest`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error('Failed to ingest matchup');
            return res.json();
        }
    });
}
