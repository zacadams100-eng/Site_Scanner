import { useStore } from '../store'
import { voiceFor, type SignatureMark } from '../lib/scannerVoice'

/**
 * The instrument's nameplate, at the head of every report.
 *
 * Three scanners, one component. Everything that differs — the title, the
 * question, the margin note, the graphic behind it — is read from
 * `scannerVoice.ts`, and the palette comes from a `data-scanner` attribute on
 * the application root. There is no scanner id in this file.
 *
 * It states what the instrument is pointed at *before* any number, which is
 * the hierarchy the product argues for everywhere else: what are we looking
 * at, then what did we find.
 */
export default function ScannerIdentity() {
  const catalog = useStore((s) => s.catalog)
  const scannerId = useStore((s) => s.scannerId)
  const scanner = catalog?.scanner
  const voice = voiceFor(scannerId)

  return (
    <header className="ident">
      <Signature mark={voice.signature} />
      <div className="ident-body">
        <p className="ident-inst mono">
          Field instrument <span className="ident-num">{voice.instrument}</span>
        </p>
        <h2 className="ident-title">{voice.title}</h2>
        <p className="ident-question">{voice.question}</p>
        {voice.strapline && <p className="ident-strap">{voice.strapline}</p>}
        {/* The registry's own words for what this scanner covers — not a
            restatement, the same string the API serves the library. */}
        {scanner?.subject && (
          <p className="ident-subject mono">{scanner.subject}</p>
        )}
      </div>
      {voice.margin && <p className="ident-margin mono">{voice.margin}</p>}
    </header>
  )
}

/**
 * The instrument's signature graphic.
 *
 * Drawn rather than photographed, in one colour, at low contrast: this sits
 * behind type and its job is to make the scanner recognisable at a glance from
 * across a desk, not to be looked at directly.
 *
 * Each is a real diagram of what the instrument reads — contour rings for
 * terrain, a spectral stack for a vegetation index, a waterline section for
 * elevation against water — rather than an abstract pattern chosen to look
 * scientific.
 */
function Signature({ mark }: { mark: SignatureMark }) {
  if (mark === 'blank') return null
  return (
    <svg className={`ident-sig ident-sig-${mark}`} viewBox="0 0 220 120"
         aria-hidden focusable="false">
      {mark === 'contour' && <ContourMark />}
      {mark === 'spectral' && <SpectralMark />}
      {mark === 'waterline' && <WaterlineMark />}
    </svg>
  )
}

/** Land: nested contour rings around a high point, the way a hill is drawn on
 *  a survey sheet. Every fourth ring heavier, as an index contour. */
function ContourMark() {
  const rings = [8, 17, 27, 38, 50, 63, 77, 92]
  return (
    <g fill="none" strokeLinejoin="round">
      {rings.map((r, i) => (
        <ellipse key={r} cx="112" cy="62" rx={r * 1.5} ry={r}
                 strokeWidth={i % 4 === 0 ? 1.6 : 0.9}
                 opacity={i % 4 === 0 ? 0.85 : 0.5} />
      ))}
      {/* Survey mark at the summit — the triangle a trig point is drawn as. */}
      <path d="M112 50 l7 12 h-14 z" strokeWidth="1.4" opacity=".9" />
    </g>
  )
}

/** Habitat: a spectral stack — bands of a vegetation index through a season,
 *  with the sampling ticks a transect is recorded along. */
function SpectralMark() {
  const bands = [0, 1, 2, 3, 4, 5, 6, 7]
  return (
    <g>
      {bands.map((i) => (
        <rect key={i} x={18 + i * 24} y={22 + (i % 3) * 6} width="15"
              height={76 - (i % 3) * 12}
              opacity={0.14 + (i % 4) * 0.13} stroke="none" />
      ))}
      <g fill="none" strokeWidth="1.1" opacity=".7">
        {/* The growth curve read off those bands. */}
        <path d="M18 88 C 60 84, 78 40, 112 36 S 172 58, 206 30" />
        {bands.map((i) => (
          <line key={i} x1={25 + i * 24} y1="104" x2={25 + i * 24} y2="110" />
        ))}
      </g>
    </g>
  )
}

/** Coastal: a section through the shore — ground falling to a waterline, with
 *  the datum ticks a level is read against. */
function WaterlineMark() {
  return (
    <g fill="none" strokeLinecap="round">
      {/* Ground profile. */}
      <path d="M6 34 C 44 32, 72 44, 96 58 S 140 86, 214 90" strokeWidth="1.7" />
      {/* Datum line, dashed the way a chart datum is drawn. */}
      <line x1="6" y1="72" x2="214" y2="72" strokeWidth="1"
            strokeDasharray="5 4" opacity=".75" />
      {/* Water, as two low swells rather than a cartoon wave. */}
      <path d="M6 84 q 26 -7 52 0 t 52 0 t 52 0 t 52 0" strokeWidth="1.2" opacity=".65" />
      <path d="M6 95 q 26 -7 52 0 t 52 0 t 52 0 t 52 0" strokeWidth="1" opacity=".4" />
      {/* Level ticks against the datum. */}
      <g strokeWidth=".9" opacity=".6">
        {[30, 58, 86, 114, 142, 170].map((x) => (
          <line key={x} x1={x} y1="68" x2={x} y2="76" />
        ))}
      </g>
    </g>
  )
}
