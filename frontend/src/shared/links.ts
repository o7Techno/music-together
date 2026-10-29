// Распознавание ссылок Яндекс Музыки во вставленном тексте (буфер, поле поиска, drag-and-drop).
// Точный разбор — на бэкенде (/api/resolve-link); здесь только «похоже ли это на ссылку».

const LINK = /(?:https?:\/\/)?(?:www\.)?music\.yandex\.(?:ru|com|by|kz|uz)\/[^\s<>"']+/gi

/** Все ссылки Яндекс Музыки из текста (без дубликатов, в исходном порядке). */
export function findYandexLinks(text: string, limit = 20): string[] {
  const found = new Set<string>()
  for (const m of text.slice(0, 20_000).matchAll(LINK)) {
    const url = m[0].replace(/[.,;:!?)]+$/, '')
    if (/\/(album|track|users|playlists?|artist)\//.test(url)) found.add(url)
    if (found.size >= limit) break
  }
  return [...found]
}

export function looksLikeYandexLink(text: string): boolean {
  return findYandexLinks(text, 1).length > 0
}
