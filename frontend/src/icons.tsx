// Small, consistent inline icons for the player (replace mismatched unicode glyphs).
const S = { width: 18, height: 18, viewBox: '0 0 24 24', fill: 'none', stroke: 'currentColor', strokeWidth: 2, strokeLinecap: 'round' as const, strokeLinejoin: 'round' as const, 'aria-hidden': true }

export const IconPlay = () => <svg {...S} width={20} height={20}><path d="M8 5.5v13l10.5-6.5z" fill="currentColor" stroke="none" /></svg>
export const IconPause = () => <svg {...S} width={20} height={20}><rect x="6.5" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none" /><rect x="13.9" y="5" width="3.6" height="14" rx="1" fill="currentColor" stroke="none" /></svg>
export const IconPrev = () => <svg {...S}><path d="M6 5v14" /><path d="M18 6l-8 6 8 6z" fill="currentColor" stroke="none" /></svg>
export const IconNext = () => <svg {...S}><path d="M18 5v14" /><path d="M6 6l8 6-8 6z" fill="currentColor" stroke="none" /></svg>
export const IconBack15 = () => (
  <svg {...S} width={22} height={22}><path d="M4.5 12a7.5 7.5 0 1 0 2.2-5.3" /><path d="M4 4.5v3.6h3.6" />
    <text x="12" y="15.2" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="currentColor" stroke="none" fontFamily="Inter, sans-serif">15</text></svg>)
export const IconFwd15 = () => (
  <svg {...S} width={22} height={22}><path d="M19.5 12a7.5 7.5 0 1 1-2.2-5.3" /><path d="M20 4.5v3.6h-3.6" />
    <text x="12" y="15.2" textAnchor="middle" fontSize="7.5" fontWeight="700" fill="currentColor" stroke="none" fontFamily="Inter, sans-serif">15</text></svg>)
export const IconChevronLeft = () => <svg {...S} width={16} height={16}><path d="M15 5l-7 7 7 7" /></svg>
export const IconSpeaker = () => <svg {...S} width={16} height={16}><path d="M4 9.5h3.5L12 5.5v13l-4.5-4H4z" fill="currentColor" stroke="none" /><path d="M15.5 9a4 4 0 0 1 0 6" /><path d="M18 6.5a7.5 7.5 0 0 1 0 11" /></svg>
export const IconGear = () => (
  <svg {...S} width={22} height={22}><circle cx="12" cy="12" r="3.2" />
    <path d="M19.4 15a1.7 1.7 0 0 0 .3 1.8l.1.1a2 2 0 1 1-2.8 2.8l-.1-.1a1.7 1.7 0 0 0-1.8-.3 1.7 1.7 0 0 0-1 1.5V21a2 2 0 1 1-4 0v-.1a1.7 1.7 0 0 0-1.1-1.5 1.7 1.7 0 0 0-1.8.3l-.1.1a2 2 0 1 1-2.8-2.8l.1-.1a1.7 1.7 0 0 0 .3-1.8 1.7 1.7 0 0 0-1.5-1H3a2 2 0 1 1 0-4h.1a1.7 1.7 0 0 0 1.5-1.1 1.7 1.7 0 0 0-.3-1.8l-.1-.1a2 2 0 1 1 2.8-2.8l.1.1a1.7 1.7 0 0 0 1.8.3H9a1.7 1.7 0 0 0 1-1.5V3a2 2 0 1 1 4 0v.1a1.7 1.7 0 0 0 1 1.5 1.7 1.7 0 0 0 1.8-.3l.1-.1a2 2 0 1 1 2.8 2.8l-.1.1a1.7 1.7 0 0 0-.3 1.8V9a1.7 1.7 0 0 0 1.5 1H21a2 2 0 1 1 0 4h-.1a1.7 1.7 0 0 0-1.5 1z" /></svg>)
export const IconSearch = () => <svg {...S}><circle cx="11" cy="11" r="6.5" /><path d="M20 20l-4.2-4.2" /></svg>
