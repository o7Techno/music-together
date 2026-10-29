import { findYandexLinks, looksLikeYandexLink } from './links'

describe('findYandexLinks', () => {
  it('finds share links from the mobile app', () => {
    const share =
      'https://music.yandex.ru/album/3135476/track/26360014?ref_id=1F79053F-0800-465D-96DC-B0B6F6706A3B&utm_medium=copy_link'
    expect(findYandexLinks(share)).toEqual([share])
  })

  it('finds several links, one per line or inside text, without duplicates', () => {
    const text = `Вот:
music.yandex.ru/album/1/track/2
https://music.yandex.com/artist/36825, и ещё https://music.yandex.ru/album/1/track/2
https://music.yandex.ru/playlists/ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce.`
    expect(findYandexLinks(text)).toEqual([
      'music.yandex.ru/album/1/track/2',
      'https://music.yandex.com/artist/36825',
      'https://music.yandex.ru/album/1/track/2',
      'https://music.yandex.ru/playlists/ar.273c2610-f97c-452c-9b76-6ffe77b2f5ce',
    ])
  })

  it.each([
    'радиохед',
    'https://music.yandex.ru/',
    'https://music.yandex.ru/home',
    'https://open.spotify.com/track/1',
    'music.yandex.de/track/1',
    '',
  ])('ignores non-links: %s', (text) => {
    expect(looksLikeYandexLink(text)).toBe(false)
  })

  it('respects the limit', () => {
    const text = Array.from(
      { length: 50 },
      (_, i) => `https://music.yandex.ru/track/${String(i)}`,
    ).join('\n')
    expect(findYandexLinks(text, 5)).toHaveLength(5)
  })
})
