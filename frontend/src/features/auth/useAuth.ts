import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { ApiError, api } from '@/shared/api'

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => {
      try {
        return await api.me()
      } catch (err) {
        if (err instanceof ApiError && err.status === 401) return null
        throw err
      }
    },
    staleTime: 60_000,
  })
}

export function useAuthConfig() {
  return useQuery({ queryKey: ['auth-config'], queryFn: api.authConfig, staleTime: Infinity })
}

export function useLogout() {
  const qc = useQueryClient()
  return useMutation({
    mutationFn: api.logout,
    onSuccess: () => {
      qc.setQueryData(['me'], null)
      qc.removeQueries({ queryKey: ['rooms'] })
    },
  })
}
