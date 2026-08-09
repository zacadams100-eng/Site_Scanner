import { describe, expect, it } from 'vitest'
import { openOnGallery } from './home'
import { encodeState } from './permalink'

const SQUARE: GeoJSON.Polygon = {
  type: 'Polygon',
  coordinates: [[[-0.5, 51.2], [-0.4, 51.2], [-0.4, 51.3], [-0.5, 51.3], [-0.5, 51.2]]],
}

const shared = '#' + encodeState({
  aoi: SQUARE, factors: ['ndvi'], t: 3, compare: null, markers: [], name: 'Manor Farm',
})

describe('openOnGallery', () => {
  it('sends a returning user to their sites', () => {
    expect(openOnGallery(4, '')).toBe(true)
  })

  it('sends a first-time user to the map', () => {
    // The one that decides the product. A newcomer with no saved sites must
    // land on the map, because until there is a shape on it nothing else in
    // the app is reachable — and a full window of "empty" is a wall.
    expect(openOnGallery(0, '')).toBe(false)
  })

  it('opens a shared link on its site, not on your gallery', () => {
    expect(openOnGallery(9, shared)).toBe(false)
  })

  it('still opens the gallery for a hash with no shape in it', () => {
    // A link that carries only a time position or a factor list is not a
    // shared site, so it does not override the home screen.
    expect(openOnGallery(2, '#t=7&f=ndvi.lst_day')).toBe(true)
  })

  it('is not confused by a malformed hash', () => {
    // A hand-edited or truncated link decodes to no geometry. Treating that
    // as "a site was shared" would strand a returning user on a blank map.
    expect(openOnGallery(3, '#g=nonsense')).toBe(true)
    expect(openOnGallery(3, '#')).toBe(true)
  })

  it('treats a negative or absurd count as none', () => {
    expect(openOnGallery(-1, '')).toBe(false)
  })
})
