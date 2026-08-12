import { useState } from 'react'
import { useStore } from '../store'

/**
 * Who reviewed this report, if anyone has.
 *
 * **Scaffolding, absent by default, never populated by the product.** This is
 * the field a co-signed brief would eventually hang off — an ecologist or a
 * coastal engineer putting their name to an assessment. It is empty on every
 * report today and that is the accurate state.
 *
 * ## Why the empty state says what it says
 *
 * "Not reviewed" is a true and useful statement about every report this
 * product has ever produced. The temptation is to hide the section until
 * someone fills it in, which would leave a reader with no signal either way —
 * and a reader who assumes a professional has been over the numbers because
 * nothing said otherwise is exactly the misreading this product exists to
 * prevent.
 *
 * ## Why there is no approved flag
 *
 * A named person and a date is the whole statement. A boolean would need a
 * default, and the default would itself be a claim.
 */
export default function SiteReview() {
  const saved = useStore((s) => s.saved)
  const projectName = useStore((s) => s.projectName)
  const setReview = useStore((s) => s.setReview)

  const site = saved.find((s) => s.name === projectName)
  const review = site?.review
  const [editing, setEditing] = useState(false)
  const [name, setName] = useState('')
  const [role, setRole] = useState('')
  const [on, setOn] = useState('')

  if (!site) return null

  if (review && !editing) {
    return (
      <section className="ovw-section">
        <h2 className="ovw-h">Professional review</h2>
        <div className="rev-card">
          <p className="rev-name">{review.name}</p>
          <p className="rev-role">{review.role}</p>
          <p className="rev-date mono">Reviewed {review.reviewedOn}</p>
        </div>
        <p className="rev-note">
          A named review records that a professional read this assessment. It
          does not change any finding, and it is not an approval of the site.
        </p>
        <button className="linklike" type="button"
                onClick={() => setReview(site.id, null)}>
          Remove review
        </button>
      </section>
    )
  }

  return (
    <section className="ovw-section">
      <h2 className="ovw-h">Professional review</h2>
      {!editing ? (
        <>
          {/* Stated rather than hidden. A reader who assumes a professional
              has been over the numbers because nothing said otherwise is the
              misreading this whole product is built to prevent. */}
          <p className="rev-empty mono">Not reviewed</p>
          <p className="rev-note">
            No one has put their name to this assessment. Every report is
            machine-produced from the evidence listed above.
          </p>
          <button className="btn btn-secondary btn-sm" type="button"
                  onClick={() => setEditing(true)}>
            Record a review
          </button>
        </>
      ) : (
        <form className="out-form" onSubmit={(e) => {
          e.preventDefault()
          setReview(site.id, { name: name.trim(), role: role.trim(), reviewedOn: on })
          setEditing(false)
        }}>
          <label className="out-field">
            <span className="out-label">Name</span>
            <input value={name} maxLength={120}
                   onChange={(e) => setName(e.target.value)} />
          </label>
          <label className="out-field">
            <span className="out-label">Role or qualification</span>
            <input value={role} maxLength={120}
                   onChange={(e) => setRole(e.target.value)} />
          </label>
          <label className="out-field">
            <span className="out-label">Date reviewed</span>
            <input type="date" value={on} onChange={(e) => setOn(e.target.value)} />
          </label>
          <div className="out-actions">
            {/* All three required. A review with no name is not a review, and
                a half-filled one would be a claim with nobody behind it. */}
            <button className="btn btn-sm" type="submit"
                    disabled={!name.trim() || !role.trim() || !on}>
              Record
            </button>
            <button className="btn btn-secondary btn-sm" type="button"
                    onClick={() => setEditing(false)}>Cancel</button>
          </div>
        </form>
      )}
    </section>
  )
}
