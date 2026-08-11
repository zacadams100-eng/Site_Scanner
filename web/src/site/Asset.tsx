import { ASSETS, assetUrl, type AssetId, type AssetSlot } from './assets'
import { SUPPLIED } from './assets.generated'

/**
 * One picture on the public site.
 *
 * Renders the file you supplied. If you have not supplied it yet, renders a
 * frame the same size stating which file goes there and what it should show —
 * so an unfinished site reads as a shot list rather than as a broken one, and
 * dropping the file in never moves the layout.
 *
 * **It will never invent an image.** No gradient stand-ins, no stock, no
 * generated texture pretending to be a photograph. The empty state is the
 * honest state, and it is designed to be looked at.
 *
 * ## Collage
 *
 * `tilt`, `tape`, `torn` and `overlap` are the messy vocabulary — plates set
 * at an angle, taped down, torn along an edge, overlapping their neighbour.
 * They are props rather than a fixed style so the composition is yours to
 * dial: none of them, or all of them, per plate.
 */

export interface AssetProps {
  id: AssetId
  /** Degrees of rotation. Small numbers. Beyond about 4 it stops reading as a
   *  pinned photograph and starts reading as a mistake. */
  tilt?: number
  /** A strip of masking tape. 'tl' | 'tr' | 'both' — which corners. */
  tape?: 'tl' | 'tr' | 'both'
  /** Torn paper edge along the bottom. */
  torn?: boolean
  /** Pull the plate up into the one above it. */
  overlap?: boolean
  /** Print halftone, for the archival plates. */
  halftone?: boolean
  /** Caption printed beneath, in the field-note face. */
  caption?: string
  /** Load eagerly. Use for anything above the fold; everything else waits. */
  priority?: boolean
  className?: string
}

export default function Asset({
  id, tilt = 0, tape, torn, overlap, halftone, caption, priority, className = '',
}: AssetProps) {
  const slot = ASSETS[id]
  const supplied = SUPPLIED[id] ?? { file: false, poster: false }

  const classes = [
    'plate',
    tilt ? 'plate-tilt' : '',
    tape ? `plate-tape plate-tape-${tape}` : '',
    torn ? 'plate-torn' : '',
    overlap ? 'plate-overlap' : '',
    halftone ? 'plate-halftone' : '',
    supplied.file ? 'is-supplied' : 'is-awaiting',
    className,
  ].filter(Boolean).join(' ')

  return (
    <figure
      className={classes}
      style={{
        aspectRatio: slot.ratio,
        ...(tilt ? { ['--tilt' as string]: `${tilt}deg` } : {}),
        // Read by the reduced-motion rule, which hides the clip and shows this
        // frame instead. Set here because only this component knows the path.
        ...(slot.kind === 'video' && supplied.poster
          ? { ['--poster' as string]: `url(${assetUrl(slot, 'poster')})` }
          : {}),
      }}
    >
      {supplied.file ? (
        slot.kind === 'video' ? (
          /*
           * Muted, inline and looping, with the poster doing the work until it
           * plays. `playsInline` is not optional: without it iOS takes the
           * video fullscreen on play, which turns a background into a takeover.
           */
          <video
            className="plate-media"
            src={assetUrl(slot)}
            poster={supplied.poster ? assetUrl(slot, 'poster') : undefined}
            autoPlay loop muted playsInline
            preload={priority ? 'auto' : 'metadata'}
            aria-label={slot.alt}
          />
        ) : (
          <img
            className="plate-media"
            src={assetUrl(slot)}
            alt={slot.alt}
            loading={priority ? 'eager' : 'lazy'}
            decoding="async"
          />
        )
      ) : (
        <Awaiting id={id} />
      )}

      {caption && <figcaption className="plate-cap">{caption}</figcaption>}
    </figure>
  )
}

/**
 * The empty frame.
 *
 * Deliberately a working document rather than a grey box: the exact path, the
 * brief, and the export size. Someone art-directing the site can read the shot
 * list off the page itself.
 */
function Awaiting({ id }: { id: AssetId }) {
  const slot = ASSETS[id]
  return (
    <div className="plate-awaiting">
      <span className="plate-corner plate-corner-tl" aria-hidden />
      <span className="plate-corner plate-corner-tr" aria-hidden />
      <span className="plate-corner plate-corner-bl" aria-hidden />
      <span className="plate-corner plate-corner-br" aria-hidden />
      <p className="plate-slot mono">{slot.kind === 'video' ? 'VIDEO' : 'PLATE'} · {slot.id}</p>
      <p className="plate-path mono">public/assets/{slot.section}/{slot.file}</p>
      <p className="plate-brief">{slot.brief}</p>
      <p className="plate-spec mono">{slot.ratio.replace(' / ', ':')} · ≥{slot.maxWidth}px wide</p>
    </div>
  )
}

/**
 * Credits for everything actually on the page.
 *
 * Only lists slots that are both supplied and carry a credit — an empty
 * credits block on a site with no photographs is furniture, and crediting a
 * picture that is not there is worse.
 */
export function AssetCredits() {
  // Widened to the interface: no slot carries a credit yet, so the literal
  // type has no such key and narrowing on it would never compile. The field is
  // part of the contract regardless — the first supplied photograph will need
  // one, and it should not require a type change to add.
  const slots: AssetSlot[] = Object.values(ASSETS)
  const credits = slots
    .filter((a) => SUPPLIED[a.id]?.file && a.credit)
    .map((a) => a.credit as string)
  if (!credits.length) return null
  return <p className="mk-credits mono">Imagery: {credits.join(' · ')}</p>
}
