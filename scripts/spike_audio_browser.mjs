// Спайк: играются ли ссылки Яндекса напрямую в <audio> в браузере (SPEC §6.1).
//
// Запуск после `spike_yandex.py run` (ссылки живут недолго — запускать сразу):
//   node scripts/spike_audio_browser.mjs
//
// Страница отдаётся с http://localhost:5199 — так браузер шлёт Origin/Referer как у нашего фронта.
// Для каждой ссылки и браузера проверяем: загрузку метаданных, canplaythrough, воспроизведение,
// перемотку на 60 с (Range), а также вариант с crossOrigin="anonymous" (нужен только для Web Audio).
import { createServer } from 'node:http'
import { readFileSync, writeFileSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, resolve } from 'node:path'
import { fileURLToPath } from 'node:url'

const here = dirname(fileURLToPath(import.meta.url))
const require = createRequire(resolve(here, '../frontend/package.json'))
const { chromium, firefox } = require('@playwright/test')

const out = resolve(here, '.spike-out')
const { urls } = JSON.parse(readFileSync(resolve(out, 'urls.json'), 'utf8'))

const page = `<!doctype html><meta charset="utf-8"><title>spike</title><body><script>
window.testAudio = (src, cors) => new Promise((done) => {
  const a = new Audio()
  if (cors) a.crossOrigin = 'anonymous'
  const r = { events: [], cors }
  const t0 = performance.now()
  const mark = (e) => r.events.push(e + '@' + Math.round(performance.now() - t0))
  ;['loadedmetadata', 'canplay', 'canplaythrough', 'playing', 'seeked', 'stalled', 'waiting'].forEach((e) =>
    a.addEventListener(e, () => mark(e)))
  const finish = () => { r.currentTime = a.currentTime; r.duration = a.duration; r.readyState = a.readyState; done(r) }
  a.addEventListener('error', () => { r.error = a.error && (a.error.code + ' ' + a.error.message); finish() })
  a.addEventListener('canplaythrough', async () => {
    try {
      await a.play()
      await new Promise((s) => setTimeout(s, 1500))
      r.playedFor1500 = a.currentTime
      a.currentTime = 60
      await new Promise((s) => a.addEventListener('seeked', s, { once: true }))
      await new Promise((s) => setTimeout(s, 1000))
      r.afterSeek = a.currentTime
      a.pause()
    } catch (e) { r.error = String(e) }
    finish()
  }, { once: true })
  setTimeout(() => { r.timeout = true; finish() }, 20000)
  a.src = src
  a.load()
})
</script>`

const server = createServer((_req, res) => {
  res.writeHead(200, { 'content-type': 'text/html; charset=utf-8' })
  res.end(page)
}).listen(5199)

const browsers = [
  ['chromium (playwright)', () => chromium.launch({ args: ['--autoplay-policy=no-user-gesture-required'] })],
  ['chrome', () => chromium.launch({ channel: 'chrome', args: ['--autoplay-policy=no-user-gesture-required'] })],
  ['msedge', () => chromium.launch({ channel: 'msedge', args: ['--autoplay-policy=no-user-gesture-required'] })],
  ['firefox', () => firefox.launch({ firefoxUserPrefs: { 'media.autoplay.default': 0 } })],
]

const results = []
for (const [name, launch] of browsers) {
  let browser
  try {
    browser = await launch()
  } catch (e) {
    results.push({ browser: name, skipped: String(e).split('\n')[0] })
    continue
  }
  const p = await (await browser.newContext()).newPage()
  await p.goto('http://localhost:5199/')
  for (const item of urls) {
    for (const cors of [false, true]) {
      const r = await p.evaluate(([src, c]) => window.testAudio(src, c), [item.url, cors])
      const row = { browser: name, kind: item.kind, ...r }
      results.push(row)
      console.log(JSON.stringify(row))
    }
  }
  await browser.close()
}
server.close()
writeFileSync(resolve(out, 'browser.json'), JSON.stringify(results, null, 2))
console.log(`\nСохранено: ${resolve(out, 'browser.json')}`)
