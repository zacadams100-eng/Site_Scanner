import { describe, it, expect } from 'vitest'
import {
  coverageGrade, coverageMark, coverageCaveat, missingMonths,
  seasonalBias, yearToYearNoise, seriesCoverageNote,
} from './coverage'
import type { AnnualRow, Point, Series } from '../types'

const row = (o: Partial<AnnualRow>): AnnualRow => ({
  year: 2017, value: 0.5, min: 0, max: 1,
  months_observed: 12, months_total: 12, confidence: 0.9, ...o,
})

/** A seasonal series: a clean sine with its minimum in January. */
function seasonalSeries(years: number[], skip: (y: number, m: number) => boolean = () => false): Series {
  const points: Point[] = []
  for (const y of years) {
    for (let m = 1; m <= 12; m++) {
      const seasonal = -Math.cos(((m - 1) / 12) * 2 * Math.PI)   // Jan low, Jul high
      points.push({
        t: `${y}-${String(m).padStart(2, '0')}`,
        value: skip(y, m) ? null : 0.5 + seasonal * 0.2,
        valid_fraction: skip(y, m) ? 0 : 0.9,
        interpolated: false,
      })
    }
  }
  const annual: AnnualRow[] = years.map((y) => {
    const pts = points.filter((p) => p.t.startsWith(String(y)) && p.value !== null)
    return row({
      year: y,
      value: pts.reduce((a, p) => a + (p.value as number), 0) / (pts.length || 1),
      months_observed: pts.length, months_total: 12,
    })
  })
  return {
    factor_id: 'ndvi', kind: 'continuous', cadence: 'monthly', unit: 'index',
    points, annual, meta: {} as Series['meta'],
  }
}

describe('coverageGrade', () => {
  it('calls a full year complete', () => {
    expect(coverageGrade(row({}))).toBe('complete')
  })

  it('calls one or two missing months slight', () => {
    expect(coverageGrade(row({ months_observed: 11 }))).toBe('slight')
    expect(coverageGrade(row({ months_observed: 10 }))).toBe('slight')
  })

  it('calls three or more missing months severe', () => {
    expect(coverageGrade(row({ months_observed: 9 }))).toBe('severe')
    expect(coverageGrade(row({ months_observed: 2 }))).toBe('severe')
  })

  it('calls a year with no value at all severe', () => {
    expect(coverageGrade(row({ value: null, months_observed: 0 }))).toBe('severe')
  })

  it('does not call a short stub at the edge of a range complete', () => {
    // 2 of 2 is 100% observed and still only two months of a year. Grading
    // against months_total gets this wrong; grading against twelve does not.
    expect(coverageGrade(row({ months_observed: 2, months_total: 2 }))).toBe('severe')
  })
})

describe('coverageCaveat, when the range is what truncated the year', () => {
  it('says the months were never asked for, not that they are missing', () => {
    // Sending someone to look for a data fault that is really just the range
    // they chose is the failure mode here.
    const s = seasonalSeries([2017, 2018])
    const text = coverageCaveat(s, row({ year: 2017, months_observed: 7, months_total: 7 }))!
    expect(text).toContain('inside the selected range')
    expect(text).not.toContain('observed)')
    expect(text).toContain('Not comparable with a full year')
  })

  it('reports both causes when a truncated year also has gaps', () => {
    const s = seasonalSeries([2017, 2018])
    const text = coverageCaveat(s, row({ year: 2017, months_observed: 5, months_total: 7 }))!
    expect(text).toContain('7 of this year')
    expect(text).toContain('5 of those 7 observed')
  })
})

describe('coverageMark', () => {
  it('marks nothing on a complete year', () => {
    expect(coverageMark(row({}))).toBeNull()
  })
  it('keeps the quiet dot for a slight gap', () => {
    expect(coverageMark(row({ months_observed: 11 }))).toBe('·')
  })
  it('states the month count when the gap is severe', () => {
    // The dot only hints that a problem exists; the row is the last place
    // anyone looks before quoting the number.
    expect(coverageMark(row({ months_observed: 8 }))).toBe('8 mo')
  })
})

describe('missingMonths', () => {
  it('names the months with no value', () => {
    const s = seasonalSeries([2017], (_y, m) => m <= 2)
    expect(missingMonths(s.points, 2017)).toEqual(['Jan', 'Feb'])
  })
  it('returns nothing for a complete year', () => {
    const s = seasonalSeries([2017])
    expect(missingMonths(s.points, 2017)).toEqual([])
  })
  it('treats a year absent from the record as fully missing', () => {
    const s = seasonalSeries([2017])
    expect(missingMonths(s.points, 1999)).toHaveLength(12)
  })
})

describe('seasonalBias', () => {
  it('reads a missing winter as a year biased high', () => {
    // The real case: Sentinel-2 starts in March, so NDVI's first year averages
    // ten months and drops the two lowest. It looks like a record high.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2017 && m <= 2)
    const b = seasonalBias(s, 2017)
    expect(b?.direction).toBe('above')
    expect(b?.missing).toEqual(['Jan', 'Feb'])
    expect(b!.magnitude).toBeGreaterThan(0)
  })

  it('reads a missing summer as a year biased low', () => {
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2019 && (m === 7 || m === 8))
    expect(seasonalBias(s, 2019)?.direction).toBe('below')
  })

  it('calls gaps spread across the year unbiased', () => {
    // April and October sit either side of the curve and cancel out.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2018 && (m === 4 || m === 10))
    expect(seasonalBias(s, 2018)?.direction).toBe('none')
  })

  it('stays silent when the bias is inside the year-to-year noise', () => {
    // A series that wanders more between years than the gap moves the mean has
    // nothing to report, and saying otherwise is the overclaiming this project
    // refuses everywhere else.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2018 && m === 4)
    s.annual = s.annual.map((a, i) => ({ ...a, value: i % 2 ? 900 : 0 }))
    expect(seasonalBias(s, 2018)?.direction).toBe('none')
  })

  it('refuses to guess for a categorical factor', () => {
    // Halfway between Grassland and Cropland is Built-up.
    const s = seasonalSeries([2017, 2018], (y, m) => y === 2017 && m <= 2)
    s.kind = 'categorical'
    expect(seasonalBias(s, 2017)).toBeNull()
  })

  it('separates a month nobody ever observes from one this year is missing', () => {
    // The standing real case: Sentinel-2 returns nothing for Jan, Feb or Dec
    // in ANY year. That is a property of the dataset, not of one row, and
    // listing it as this year's gap sends the reader hunting for a fault that
    // is not there. 2019 additionally loses July, and that one IS its own.
    const s = seasonalSeries([2017, 2018, 2019, 2020],
      (y, m) => m === 1 || m === 2 || m === 12 || (y === 2019 && m === 7))
    const b = seasonalBias(s, 2019)!
    expect(b.neverObserved).toEqual(['Jan', 'Feb', 'Dec'])
    expect(b.missing).toEqual(['Jul'])
    // July is the seasonal maximum, so losing it pulls 2019 down.
    expect(b.direction).toBe('below')
  })

  it('measures bias against a typical year of this factor, not a true twelve', () => {
    // Every year missing the same winter is not a biased year — it is a
    // biased dataset, and the years remain comparable with each other.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (_y, m) => m <= 2)
    const b = seasonalBias(s, 2018)
    expect(b).toBeNull()          // nothing distinguishes 2018 from its peers
  })

  it('is null when there is no seasonal shape to measure', () => {
    const s = seasonalSeries([2017], (_y, m) => m > 1)
    expect(seasonalBias(s, 2017)).toBeNull()
  })

  it('returns null for a year that is actually complete', () => {
    const s = seasonalSeries([2017, 2018])
    expect(seasonalBias(s, 2018)).toBeNull()
  })
})

describe('yearToYearNoise', () => {
  it('is the mean absolute step between consecutive years', () => {
    const annual = [row({ year: 1, value: 10 }), row({ year: 2, value: 14 }), row({ year: 3, value: 12 })]
    expect(yearToYearNoise(annual)).toBeCloseTo(3)     // |4| and |2|
  })
  it('is zero when there is nothing to compare', () => {
    expect(yearToYearNoise([row({ value: 5 })])).toBe(0)
    expect(yearToYearNoise([])).toBe(0)
  })
  it('skips null years rather than treating them as zero', () => {
    const annual = [row({ year: 1, value: 10 }), row({ year: 2, value: null }), row({ year: 3, value: 12 })]
    expect(yearToYearNoise(annual)).toBeCloseTo(2)
  })
})

describe('coverageCaveat', () => {
  it('says nothing about a complete year', () => {
    const s = seasonalSeries([2017, 2018])
    expect(coverageCaveat(s, s.annual[1])).toBeNull()
  })

  it('names the missing months and the direction they push the mean', () => {
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2017 && m <= 2)
    const text = coverageCaveat(s, s.annual[0])!
    expect(text).toContain('10 of 12 months observed')
    expect(text).toContain('Jan and Feb')
    expect(text).toContain('reads high')
    expect(text).toContain('Not comparable with the other years')
  })

  it('does not repeat the dataset-wide fact on every single row', () => {
    // It belongs beside the factor's name — see seriesCoverageNote. Fifteen
    // identical tooltips down a column stop being read by the third row and
    // crowd out the caveats that are about a specific year.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (_y, m) => m === 1 || m === 2 || m === 12)
    expect(coverageCaveat(s, s.annual[1])).toBeNull()
  })

  it('says so plainly when the gaps do not bias the mean', () => {
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2018 && (m === 4 || m === 10))
    expect(coverageCaveat(s, s.annual[1])).toContain('do not obviously bias the mean')
  })

  it('handles a year with no observation at all', () => {
    const s = seasonalSeries([2017, 2018])
    expect(coverageCaveat(s, { ...s.annual[0], value: null, months_observed: 0 }))
      .toBe('No usable observation this year.')
  })

  it('abbreviates a long list of missing months', () => {
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2017 && m <= 6)
    const text = coverageCaveat(s, s.annual[0])!
    expect(text).toContain('and 3 more')
    expect(text.length).toBeLessThan(240)
  })
})

describe('coverageGrade against a factor that can never see twelve months', () => {
  // Sentinel-2 returns nothing for Jan, Feb or Dec in ANY year, so NDVI's best
  // possible year is nine months. Grading those against a flat twelve marked
  // every NDVI year in the record "severe" and greyed out the whole column —
  // while the caveat text on the same cell said the years were comparable with
  // each other, which is the true statement. Two views of one number
  // disagreeing is the exact failure this module exists to prevent.
  const s2 = (extraSkip: (y: number, m: number) => boolean = () => false) =>
    seasonalSeries([2017, 2018, 2019, 2020],
      (y, m) => m === 1 || m === 2 || m === 12 || extraSkip(y, m))

  it('calls a nine-month year complete when nine is the maximum', () => {
    const s = s2()
    expect(coverageGrade(s.annual[1], s)).toBe('complete')
  })

  it('still grades a year short for that factor', () => {
    const s = s2((y, m) => y === 2019 && (m === 6 || m === 7 || m === 8))
    const row2019 = s.annual.find((a) => a.year === 2019)!
    expect(coverageGrade(row2019, s)).toBe('severe')
  })

  it('marks nothing on a year that is complete for its factor', () => {
    const s = s2()
    expect(coverageMark(s.annual[1], s)).toBeNull()
  })

  it('keeps grading against twelve when no series is given', () => {
    // The cheap call site still works; it is simply less informed.
    expect(coverageGrade(row({ months_observed: 9 }))).toBe('severe')
  })

  it('agrees with the caveat text on the same row', () => {
    // The specific contradiction: "severe" in the cell, "comparable with each
    // other" in its own tooltip.
    const s = s2()
    const r = s.annual[1]
    expect(coverageGrade(r, s)).toBe('complete')
    expect(coverageCaveat(s, r)).toBeNull()
  })
})

describe('seriesCoverageNote', () => {
  it('says nothing about a factor with no dataset-wide hole', () => {
    expect(seriesCoverageNote(seasonalSeries([2017, 2018]))).toBeNull()
  })

  it('names the months and draws the conclusion that actually follows', () => {
    // Both halves matter: no year is a real annual mean, AND the years are
    // still comparable with each other. Either one alone misleads.
    const s = seasonalSeries([2017, 2018, 2019], (_y, m) => m === 1 || m === 2 || m === 12)
    const note = seriesCoverageNote(s)!
    expect(note).toContain('Jan, Feb and Dec')
    expect(note).toContain('no annual figure here is a true 12-month average')
    expect(note).toContain('comparable with each other')
  })

  it('handles a factor with no observations at all', () => {
    const s = seasonalSeries([2017], () => true)
    expect(seriesCoverageNote(s)).toBe('This factor has no observations at all.')
  })
})
