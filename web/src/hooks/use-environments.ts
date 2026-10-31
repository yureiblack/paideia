// Every read and write of environments goes through these hooks. Each query
// is cached under a key, and each change updates or refreshes exactly the
// cached data it affects, so every screen stays in step without reloading.

import {
  useMutation,
  useQuery,
  useQueryClient,
} from "@tanstack/react-query";

import { api } from "@/lib/api";
import type { EnvironmentInput, EnvironmentPatch } from "@/lib/types";

// Cache keys: the list lives under ["environments"], one environment under
// ["environments", id].
const listKey = ["environments"] as const;
const detailKey = (id: string) => ["environments", id] as const;

export function useEnvironments() {
  return useQuery({ queryKey: listKey, queryFn: api.listEnvironments });
}

export function useEnvironment(id: string) {
  return useQuery({
    queryKey: detailKey(id),
    queryFn: () => api.getEnvironment(id),
  });
}

export function useCreateEnvironment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (input: EnvironmentInput) => api.createEnvironment(input),
    onSuccess: (environment) => {
      // Seed the detail cache so opening the new environment is instant.
      queryClient.setQueryData(detailKey(environment.id), environment);
      // exact: refresh only the list, not every cached environment under it.
      return queryClient.invalidateQueries({ queryKey: listKey, exact: true });
    },
  });
}

export function useUpdateEnvironment(id: string) {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (patch: EnvironmentPatch) => api.updateEnvironment(id, patch),
    onSuccess: (environment) => {
      queryClient.setQueryData(detailKey(id), environment);
      return queryClient.invalidateQueries({ queryKey: listKey, exact: true });
    },
  });
}

export function useDeleteEnvironment() {
  const queryClient = useQueryClient();
  return useMutation({
    mutationFn: (id: string) => api.deleteEnvironment(id),
    onSuccess: (_, id) => {
      // Forget the deleted environment instead of refetching it into a 404.
      queryClient.removeQueries({ queryKey: detailKey(id) });
      return queryClient.invalidateQueries({ queryKey: listKey, exact: true });
    },
  });
}
