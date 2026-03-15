import { useQuery } from '@tanstack/react-query';

const API_BASE = '/api/v12';

export function useListPredictions() {
    return useQuery({
        queryKey: ['predictions'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/predictions`);
            if (!res.ok) throw new Error('Failed to fetch predictions');
            const data = await res.json();
            return { data: data.data || [] }; // Adjust based on our route response
        }
    });
}

export function useListEvSignals() {
    return useQuery({
        queryKey: ['ev-signals'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/ev-signals`);
            if (!res.ok) throw new Error('Failed to fetch EV signals');
            const data = await res.json();
            return { data: data.data || [] };
        }
    });
}

// Stubs for other endpoints that were mocked
export function useListLineMovements() {
    return useQuery({
        queryKey: ['line-movements'],
        queryFn: async () => ({ data: [] })
    });
}

export function useListTeams() {
    return useQuery({
        queryKey: ['teams'],
        queryFn: async () => ({ data: [] })
    });
}

export function useGetTeamPerformance(teamId: string) {
    return useQuery({
        queryKey: ['team-performance', teamId],
        queryFn: async () => ({ data: null }),
        enabled: !!teamId
    });
}

export function useListMatchups() {
    return useQuery({
        queryKey: ['matchups'],
        queryFn: async () => ({ data: [] })
    });
}
