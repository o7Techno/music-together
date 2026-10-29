import { create } from 'zustand'

/** Сигнал «Яндекс отклонил токен» из любого места (например, при получении ссылки на аудио). */
export const useAuthIssue = create<{ relogin: boolean }>(() => ({ relogin: false }))
