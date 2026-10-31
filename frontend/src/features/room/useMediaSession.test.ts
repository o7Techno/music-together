import { describe, expect, it } from 'vitest'

import { usesTrackButtonsOnly } from './useMediaSession'

const iphone = 'Mozilla/5.0 (iPhone; CPU iPhone OS 18_0 like Mac OS X) AppleWebKit/605.1.15'
const mac = 'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/605.1.15'
const android = 'Mozilla/5.0 (Linux; Android 14; Pixel 7) AppleWebKit/537.36 Chrome/120 Mobile'

describe('usesTrackButtonsOnly', () => {
  it('is true for iPhone and iPad, whose lock screen hides skip when seek steps exist', () => {
    expect(usesTrackButtonsOnly({ userAgent: iphone, maxTouchPoints: 5 })).toBe(true)
    expect(usesTrackButtonsOnly({ userAgent: mac, maxTouchPoints: 5 })).toBe(true)
  })

  it('is false for desktop Mac and Android', () => {
    expect(usesTrackButtonsOnly({ userAgent: mac, maxTouchPoints: 0 })).toBe(false)
    expect(usesTrackButtonsOnly({ userAgent: android, maxTouchPoints: 5 })).toBe(false)
  })
})
