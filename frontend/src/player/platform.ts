// Профили коррекции под платформы (SPEC §5.5). Значения для мобильных — исходная гипотеза:
// проверяются вручную по docs/manual-qa.md и могут быть переопределены `?syncProfile=` для экспериментов.

import { DESKTOP_PROFILE, type DriftProfile } from './driftController'

export const IOS_PROFILE: DriftProfile = {
  ...DESKTOP_PROFILE,
  name: 'ios',
  // На iPhone смена playbackRate сама даёт просадку около 200 мс: подстройка темпом догоняла и
  // снова проваливалась, без конца (D-048). Поэтому темп не трогаем, а редко и один раз перематываем.
  deadZoneMs: 40,
  exitZoneMs: 15,
  maxRateDelta: 0,
  hardSeekMs: 200,
  minSeekIntervalMs: 5000,
}

export const ANDROID_PROFILE: DriftProfile = {
  ...DESKTOP_PROFILE,
  name: 'android',
  deadZoneMs: 25,
  exitZoneMs: 10,
}

const PROFILES: Record<string, DriftProfile> = {
  desktop: DESKTOP_PROFILE,
  ios: IOS_PROFILE,
  android: ANDROID_PROFILE,
}

export interface PlatformInfo {
  userAgent: string
  maxTouchPoints: number
  override?: string | null
}

export function isIOS(info: PlatformInfo): boolean {
  return (
    /iPhone|iPad|iPod/.test(info.userAgent) ||
    // iPadOS притворяется macOS, но с сенсорным экраном.
    (/Macintosh/.test(info.userAgent) && info.maxTouchPoints > 1)
  )
}

export function detectProfile(info: PlatformInfo): DriftProfile {
  if (info.override && info.override in PROFILES) return PROFILES[info.override] ?? DESKTOP_PROFILE
  if (isIOS(info)) return IOS_PROFILE
  if (/Android/.test(info.userAgent)) return ANDROID_PROFILE
  return DESKTOP_PROFILE
}
