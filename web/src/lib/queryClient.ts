// The dashboard's one data cache. Server data (workspace, timelines, team)
// lives here, keyed by the signed-in user's email, never in module variables
// or localStorage. Login, logout and an expired session call resetSession(),
// which cancels in-flight requests and drops every cached row, so nothing
// from the previous session can show up or be written into the next one.
import { QueryClient } from '@tanstack/react-query';

import { ApiError } from './api';

export const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      staleTime: 30_000,
      // Screens refresh after their own writes; a refetch on focus would
      // reorder work queues under the user's cursor.
      refetchOnWindowFocus: false,
      // 4xx answers (401, 403, 404, 409) do not get better by retrying.
      retry: (failureCount, error) => !(error instanceof ApiError && error.status < 500) && failureCount < 1,
    },
    mutations: { retry: false },
  },
});

export function resetSession(): void {
  void queryClient.cancelQueries();
  queryClient.clear();
}
