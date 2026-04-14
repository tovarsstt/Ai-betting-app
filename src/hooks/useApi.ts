import { useQuery, useMutation, useQueryClient } from '@tanstack/react-query';

const API_BASE = '/api/v12';

// --- PREDICTIONS ---

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

// --- EV SIGNALS ---

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

// --- LINE MOVEMENTS ---

export function useListLineMovements() {
    return useQuery<any[]>({
        queryKey: ['line-movements'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/line-movements`);
            if (!res.ok) throw new Error('Failed to fetch line movements');
            const result = await res.json();
            return result.data || [];
        }
    });
}

// --- TEAMS ---

export function useListTeams(sport?: string) {
    return useQuery<any[]>({
        queryKey: ['teams', sport],
        queryFn: async () => {
            const params = sport && sport !== 'ALL' ? `?sport=${sport}` : '';
            const res = await fetch(`${API_BASE}/teams${params}`);
            if (!res.ok) throw new Error('Failed to fetch teams');
            const result = await res.json();
            return result.data || [];
        }
    });
}

export function useGetTeamPerformance(teamId: string) {
    return useQuery<any>({
        queryKey: ['team-performance', teamId],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/teams/${teamId}`);
            if (!res.ok) throw new Error('Failed to fetch team performance');
            const result = await res.json();
            return result.data || null;
        },
        enabled: !!teamId
    });
}

// --- MATCHUPS ---

export function useListMatchups() {
    return useQuery<any[]>({
        queryKey: ['matchups'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/matchups`);
            if (!res.ok) throw new Error('Failed to fetch matchups');
            const result = await res.json();
            return result.data || [];
        }
    });
}

// --- INGEST ---

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

// --- PLAYS (Stake tracker) ---

export function useListPlays() {
    return useQuery<any[]>({
        queryKey: ['plays'],
        queryFn: async () => {
            const res = await fetch(`${API_BASE}/plays`);
            if (!res.ok) throw new Error('Failed to fetch plays');
            const result = await res.json();
            return result.data || [];
        }
    });
}

export function useCreatePlay() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async (payload: {
            matchup: string;
            selection: string;
            alphaEdge?: string;
            kellySizing?: string;
            mathEv?: number;
            actualOutcome?: string;
            prospectTheoryRead?: string;
        }) => {
            const res = await fetch(`${API_BASE}/plays`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (!res.ok) throw new Error('Failed to create play');
            return res.json();
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plays'] })
    });
}

export function useUpdatePlay() {
    const queryClient = useQueryClient();
    return useMutation({
        mutationFn: async ({ id, outcome }: { id: string; outcome: string }) => {
            const res = await fetch(`${API_BASE}/plays/${id}`, {
                method: 'PATCH',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ actualOutcome: outcome })
            });
            if (!res.ok) throw new Error('Failed to update play');
            return res.json();
        },
        onSuccess: () => queryClient.invalidateQueries({ queryKey: ['plays'] })
    });
}
