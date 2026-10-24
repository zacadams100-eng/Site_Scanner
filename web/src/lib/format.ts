export function formatArea(ha: number): string {
  if (ha < 1) return `${(ha * 10_000).toLocaleString('en-GB', { maximumFractionDigits: 0 })} m²`
  return `${ha.toLocaleString('en-GB', { maximumFractionDigits: ha < 100 ? 2 : 0 })} ha`
}

/** "2 km", "250 m", or "red line" for layers checked against the red line only. */
export function formatRadius(m: number): string {
  if (m === 0) return 'red line'
  return m < 1000 ? `${m} m` : `${m / 1000} km`
}
