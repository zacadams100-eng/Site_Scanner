import { describe, it, expect } from 'vitest'
import {
  coverageGrade, coverageMark, coverageCaveat, missingMonths,
  seasonalBias, yearToYearNoise,
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
    expect(b?.direction).toBe('high')
    expect(b?.missing).toEqual(['Jan', 'Feb'])
    expect(b!.magnitude).toBeGreaterThan(0)
  })

  it('reads a missing summer as a year biased low', () => {
    const s = seasonalSeries([2017, 2018, 2019, 2020], (y, m) => y === 2019 && (m === 7 || m === 8))
    expect(seasonalBias(s, 2019)?.direction).toBe('low')
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
    expect(b.direction).toBe('low')
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

  it('says the years still compare with each other when the hole is dataset-wide', () => {
    // The caveat a reader most needs before quoting an "annual" NDVI figure
    // that has never once included a January.
    const s = seasonalSeries([2017, 2018, 2019, 2020], (_y, m) => m === 1 || m === 2 || m === 12)
    const text = coverageCaveat(s, s.annual[1])!
    expect(text).toContain('never observed in Jan, Feb and Dec in any year')
    expect(text).toContain('no year here is a true 12-month average')
    expect(text).toContain('comparable with each other')
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
