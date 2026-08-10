/**
 * What a new report opens with.
 *
 * A *preference*, not a fixture. The catalogue is scoped to the active
 * scanner, so a factor this list names may not exist for it: habitat exposes
 * six factors and none of them is `precip_total`. Hard-coded, the list
 * produced a 422 on every first load of scanner #2, and the app showed an
 * empty map with no stated reason — found by driving it, not by reading.
 *
 * Lives in `lib/` rather than the store so it can be tested without importing
 * the whole app, which is where every other pure function here lives.
 */

const PREFERRED_FACTORS = ['ndvi', 'lc_tree_pct', 'precip_total', 'lst_day']
const OPENING_FACTORS = 4

/** The preferred factors this scanner actually has, topped up from what it
 *  does offer so a scanner never opens with almost nothing. */
export function defaultFactors(available: string[]): string[] {
  const have = new Set(available)
  const picked = PREFERRED_FACTORS.filter((f) => have.has(f))
  for (const f of available) {
    if (picked.length >= OPENING_FACTORS) break
    if (!picked.includes(f)) picked.push(f)
  }
  return picked
}
