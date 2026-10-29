import { useMutation, useQuery, useQueryClient } from '@tanstack/react-query'

import { api } from '@/shared/api'

export function useMe() {
  return useQuery({
    queryKey: ['me'],
    queryFn: async () => (await api.session()).me,
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
