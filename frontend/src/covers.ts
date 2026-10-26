// Card pictures: public-domain / CC images from Wikimedia Commons, fetched once by scripts/fetch_covers.py.
import { useEffect, useState } from 'react'

export interface Credit { file: string; page: string; artist: string; license: string }
let credits: Record<string, Credit> | null = null
let loading: Promise<Record<string, Credit>> | null = null

export function useCovers(): Record<string, Credit> {
  const [c, setC] = useState<Record<string, Credit>>(credits ?? {})
  useEffect(() => {
    if (credits) return
    loading ??= fetch('/covers/credits.json').then(r => (r.ok ? r.json() : {})).catch(() => ({}))
    loading.then(x => { credits = x; setC(x) })
  }, [])
  return c
}

export const coverUrl = (id: string) => `/covers/${id}.jpg`
export const creditText = (c?: Credit) =>
  c ? `Picture: ${c.artist || c.file.replace(/^File:/, '').replace(/\.\w+$/, '')} · ${c.license} · Wikimedia Commons` : ''
