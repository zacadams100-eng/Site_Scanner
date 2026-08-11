/**
 * How each scanner presents itself.
 *
 * Three instruments from one expedition company: the same case, the same
 * engineering, different dials. This module is the whole of the difference —
 * a lookup table of vocabulary and identity, read by generic components.
 *
 * ## Why this is configuration and not three components
 *
 * There is not one scanner id anywhere else in `web/src`, and that is the
 * property worth keeping: the workspace, the radar, the evidence drawer and
 * the report all render whatever the API describes. A fourth scanner needs an
 * entry here and nothing else. The moment a component asks
 * `if (scanner === 'habitat')` that property is gone and the next scanner is a
 * refactor rather than a row.
 *
 * ## What is not here
 *
 * Nothing that could be mistaken for a finding. No thresholds, no
 * interpretations, no domain rules — those come from the backend and only from
 * the backend. This file names things and picks colours.
 *
 * ## The unknown scanner
 *
 * `voiceFor` always returns something. A scanner registered but not described
 * here gets the neutral instrument rather than a blank screen, because the
 * registry is allowed to move faster than the art direction.
 */

export type SignatureMark = 'contour' | 'spectral' | 'waterline' | 'blank'

export interface ScannerVoice {
  /** Position in the instrument case. Printed as `01`, `02`, `03`. */
  instrument: string
  /** The instrument's name, above the product name. Not the scanner's `name`
   *  from the API — that is "Land"; this is what Land *does*. */
  title: string
  /** The question this instrument is pointed at, in the user's words. */
  question: string
  /** One line under the question. Plain, declarative, no adjectives that
   *  cannot be defended. */
  strapline: string
  /** What this instrument calls one of its checks. A land surveyor runs a
   *  field check; an ecologist makes an observation; a coastal survey takes a
   *  sounding. */
  checkLabel: string
  /** Plural of the above, for headings. */
  checkLabelPlural: string
  /** What it calls a flagged finding. */
  findingLabel: string
  /** The graphic drawn behind its identity block. */
  signature: SignatureMark
  /** Short line printed in the instrument's own margin — the eccentric
   *  technical annotation. Always a true statement about the instrument. */
  margin: string
}

const LAND: ScannerVoice = {
  instrument: '01',
  title: 'Site reconnaissance',
  question: 'What is this place telling us?',
  strapline: 'Know the ground before you build on it.',
  checkLabel: 'Field check',
  checkLabelPlural: 'Field checks',
  findingLabel: 'Field note',
  signature: 'contour',
  margin: 'Terrestrial survey · England',
}

const HABITAT: ScannerVoice = {
  instrument: '02',
  title: 'Habitat intelligence',
  question: 'What is alive here, and how is it changing?',
  strapline: 'Fifteen years of observation, read for one parcel.',
  checkLabel: 'Observation',
  checkLabelPlural: 'Observations',
  findingLabel: 'Field note',
  signature: 'spectral',
  margin: 'Spectral record · Sentinel-2',
}

const COASTAL: ScannerVoice = {
  instrument: '03',
  title: 'Coastal intelligence',
  question: 'How is this site interacting with water?',
  strapline: 'Read the relationship between land and water.',
  checkLabel: 'Sounding',
  checkLabelPlural: 'Soundings',
  findingLabel: 'Chart note',
  signature: 'waterline',
  margin: 'Site assessment · not a corridor',
}

/** The neutral instrument. Deliberately dull: a scanner that reaches this has
 *  no art direction yet, and dressing it in another scanner's clothes would
 *  say something untrue about what it does. */
const UNSPECIFIED: ScannerVoice = {
  instrument: '—',
  title: 'Assessment',
  question: 'What does the evidence show?',
  strapline: '',
  checkLabel: 'Check',
  checkLabelPlural: 'Checks',
  findingLabel: 'Finding',
  signature: 'blank',
  margin: '',
}

const VOICES: Record<string, ScannerVoice> = {
  land: LAND,
  habitat: HABITAT,
  coastal: COASTAL,
}

export function voiceFor(scannerId: string | undefined): ScannerVoice {
  return VOICES[(scannerId ?? '').toLowerCase()] ?? UNSPECIFIED
}

/** Whether this scanner has a described identity. Used to decide between the
 *  instrument treatment and the plain one, rather than testing for an id. */
export function hasVoice(scannerId: string | undefined): boolean {
  return (scannerId ?? '').toLowerCase() in VOICES
}

/**
 * The four states, in the words each instrument uses for them.
 *
 * `not_assessed` deliberately reads as a property of the instrument rather
 * than of the site: "no signal" is a fact about what could be measured here,
 * and the alternative wording — "unknown", "missing" — sounds like a defect in
 * the place rather than a limit of the reading.
 */
export const STATE_LABEL: Record<string, string> = {
  flagged: 'Investigate',
  clear: 'Checked · clear',
  partial: 'Partly read',
  not_assessed: 'No signal',
}

/** The symbol printed beside a state. Filled, half, hollow, absent — a
 *  four-step scale a reader learns once and can then read at a glance, and
 *  which survives greyscale and colour-blindness because the shape carries it
 *  rather than the colour. */
export const STATE_GLYPH: Record<string, string> = {
  flagged: '◉',
  clear: '●',
  partial: '◐',
  not_assessed: '○',
}
