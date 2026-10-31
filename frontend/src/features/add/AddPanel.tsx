// Панель «Добавить»: вкладки «Поиск» / «Волна» / «Мои плейлисты» / «По ссылке» + просмотр сущностей.

import { SearchPanel } from '@/features/search/SearchPanel'
import { WavePanel } from '@/features/wave/WavePanel'

import { type AddTab, useAddNav } from './addNav'
import { EntityView } from './EntityView'
import { LibraryTab } from './LibraryTab'
import { LinkTab } from './LinkTab'

const TABS: { id: AddTab; label: string }[] = [
  { id: 'search', label: 'Поиск' },
  { id: 'wave', label: 'Волна' },
  { id: 'library', label: 'Мои плейлисты' },
  { id: 'link', label: 'По ссылке' },
]

export function AddPanel() {
  const tab = useAddNav((s) => s.tab)
  const setTab = useAddNav((s) => s.setTab)
  const top = useAddNav((s) => s.stack.at(-1))
  return (
    <div className="flex min-h-0 flex-col gap-3">
      <div
        role="tablist"
        aria-label="Способ добавления"
        className="bg-surface-2 flex rounded-full p-1"
      >
        {TABS.map((t) => (
          <button
            key={t.id}
            type="button"
            role="tab"
            aria-selected={tab === t.id && !top}
            onClick={() => {
              setTab(t.id)
            }}
            className={`focus-ring flex-1 rounded-full px-3 py-1.5 text-sm transition-colors ${
              tab === t.id && !top
                ? 'bg-surface-4 text-fg font-medium'
                : 'text-fg-muted hover:text-fg'
            }`}
          >
            {t.label}
          </button>
        ))}
      </div>
      {/* Поиск остаётся смонтированным, чтобы не терять запрос при возврате из альбома. */}
      <div hidden={Boolean(top) || tab !== 'search'}>
        <SearchPanel />
      </div>
      {top && <EntityView key={`${top.type}:${top.id}`} entity={top} />}
      {!top && tab === 'wave' && <WavePanel />}
      {!top && tab === 'library' && <LibraryTab />}
      {!top && tab === 'link' && <LinkTab />}
    </div>
  )
}
