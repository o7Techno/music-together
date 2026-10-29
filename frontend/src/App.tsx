import { QueryClient, QueryClientProvider } from '@tanstack/react-query'
import { Suspense, lazy } from 'react'
import { BrowserRouter, Route, Routes } from 'react-router-dom'

import { HomePage } from '@/features/auth/HomePage'
import { FullScreenSpinner } from '@/shared/ui/Spinner'
import { Toaster } from '@/shared/ui/Toaster'

const RoomPage = lazy(() => import('@/features/room/RoomPage'))

const queryClient = new QueryClient({
  defaultOptions: {
    queries: { retry: 1, refetchOnWindowFocus: false, staleTime: 30_000 },
  },
})

export function App() {
  return (
    <QueryClientProvider client={queryClient}>
      <BrowserRouter>
        <Suspense fallback={<FullScreenSpinner />}>
          <Routes>
            <Route path="/" element={<HomePage />} />
            <Route path="/r/:slug" element={<RoomPage />} />
            <Route path="*" element={<NotFound />} />
          </Routes>
        </Suspense>
        <Toaster />
      </BrowserRouter>
    </QueryClientProvider>
  )
}

function NotFound() {
  return (
    <main className="flex min-h-dvh flex-col items-center justify-center gap-4 p-6 text-center">
      <h1 className="text-2xl font-semibold">Страница не найдена</h1>
      <a href="/" className="text-accent hover:underline">
        На главную
      </a>
    </main>
  )
}
