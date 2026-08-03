import { useEffect, useRef, useState } from 'react'
import { useStore } from '../store'
import { relativeTime, thumbnailPath, type Project } from '../lib/projects'
import { formatArea } from '../lib/format'
import { useEscape } from '../lib/useEscape'
import BrandMark from './BrandMark'

/**
 * The home screen — Procreate's gallery, for sites.
 *
 * The idea worth stealing is not the grid, it is that the gallery is the
 * *front door*: you land on your work, not on an empty canvas with a file
 * menu. Opening a card puts you back exactly where you left off, so a project
 * is a place you return to rather than a file you reconstruct.
 *
 * Each card's thumbnail is the site's own outline, drawn from the geometry we
 * already store. No tiles, no screenshots — a list of forty projects renders
 * instantly and offline, and two sites are told apart the way a map reader
 * tells them apart anyway: by shape.
 */

const THUMB = { width: 260, height: 150, pad: 18 }

export default function Gallery() {
  const open = useStore((s) => s.galleryOpen)
  const projects = useStore((s) => s.projects)
  const currentId = useStore((s) => s.currentProjectId)
  const aoi = useStore((s) => s.aoi)
  const openProject = useStore((s) => s.openProject)
  const newProject = useStore((s) => s.newProject)
  const renameProject = useStore((s) => s.renameProject)
  const duplicateProject = useStore((s) => s.duplicateProject)
  const deleteProject = useStore((s) => s.deleteProject)
  const setGalleryOpen = useStore((s) => s.setGalleryOpen)
  const setTemplatesOpen = useStore((s) => s.setTemplatesOpen)

  const [menuFor, setMenuFor] = useState<string | null>(null)
  const [renaming, setRenaming] = useState<string | null>(null)
  const [confirming, setConfirming] = useState<string | null>(null)
  const renameRef = useRef<HTMLInputElement>(null)

  // Escape backs out to the canvas — but only when there is a canvas worth
  // going back to. With nothing drawn there is nothing behind the gallery, so
  // the key would look broken.
  useEscape(open && !!aoi, () => setGalleryOpen(false))

  useEffect(() => {
    if (renaming) renameRef.current?.select()
  }, [renaming])

  // Any click that is not on a card menu closes the open one.
  useEffect(() => {
    if (!menuFor) return
    const close = () => setMenuFor(null)
    window.addEventListener('click', close)
    return () => window.removeEventListener('click', close)
  }, [menuFor])

  if (!open) return null

  const commitRename = (id: string, value: string) => {
    renameProject(id, value)
    setRenaming(null)
  }

  return (
    <div className="gallery" role="dialog" aria-modal="true" aria-label="Your sites">
      <header className="gallery-head">
        <div className="brand gallery-brand">
          <span className="brand-mark"><BrandMark size={30} /></span>
          <span className="brand-text">
            <span className="brand-name">Site Scanner</span>
            <span className="brand-sub">GIS for land management</span>
          </span>
        </div>

        <div className="gallery-actions">
          <button className="g-btn" onClick={() => setTemplatesOpen(true)}>
            Start from a question
          </button>
          <button className="g-btn g-btn-primary" onClick={newProject}>
            <svg viewBox="0 0 20 20" width="15" height="15" fill="none" stroke="currentColor"
                 strokeWidth="1.8" strokeLinecap="round" aria-hidden="true">
              <path d="M10 4v12M4 10h12" />
            </svg>
            New site
          </button>
          {/* Only offered when there is something to go back to. */}
          {aoi && (
            <button className="g-btn" onClick={() => setGalleryOpen(false)}>
              Back to map
            </button>
          )}
        </div>
      </header>

      <div className="gallery-bar">
        <span className="eyebrow">
          {projects.length} {projects.length === 1 ? 'site' : 'sites'}
        </span>
      </div>

      {projects.length === 0 ? (
        <div className="gallery-empty">
          <div className="placeholder-frame">
            <p>No sites yet.</p>
            <p className="placeholder-sub">
              Draw a shape on the map and save it, and it will be waiting here next time.
            </p>
          </div>
          <button className="g-btn g-btn-primary" onClick={newProject}>Draw the first one</button>
        </div>
      ) : (
        <ul className="gallery-grid">
          {projects.map((p) => (
            <li key={p.id}>
              <Card
                project={p}
                isCurrent={p.id === currentId}
                isRenaming={renaming === p.id}
                isConfirming={confirming === p.id}
                menuOpen={menuFor === p.id}
                renameRef={renameRef}
                onOpen={() => openProject(p.id)}
                onMenu={(e) => {
                  e.stopPropagation()
                  setMenuFor(menuFor === p.id ? null : p.id)
                  setConfirming(null)
                }}
                onRenameStart={() => { setRenaming(p.id); setMenuFor(null) }}
                onRenameCommit={(v) => commitRename(p.id, v)}
                onRenameCancel={() => setRenaming(null)}
                onDuplicate={() => { duplicateProject(p.id); setMenuFor(null) }}
                onDeleteAsk={() => setConfirming(p.id)}
                onDeleteConfirm={() => {
                  deleteProject(p.id)
                  setConfirming(null)
                  setMenuFor(null)
                }}
              />
            </li>
          ))}
        </ul>
      )}
    </div>
  )
}

function Card({
  project: p, isCurrent, isRenaming, isConfirming, menuOpen, renameRef,
  onOpen, onMenu, onRenameStart, onRenameCommit, onRenameCancel,
  onDuplicate, onDeleteAsk, onDeleteConfirm,
}: {
  project: Project
  isCurrent: boolean
  isRenaming: boolean
  isConfirming: boolean
  menuOpen: boolean
  renameRef: React.RefObject<HTMLInputElement | null>
  onOpen: () => void
  onMenu: (e: React.MouseEvent) => void
  onRenameStart: () => void
  onRenameCommit: (value: string) => void
  onRenameCancel: () => void
  onDuplicate: () => void
  onDeleteAsk: () => void
  onDeleteConfirm: () => void
}) {
  const d = thumbnailPath(p.geometry, THUMB)

  return (
    <div className={`g-card${isCurrent ? ' is-current' : ''}`}>
      {/* The whole thumbnail is the open affordance, as in any gallery. The
          menu sits outside it so a click on ⋯ never also opens the project. */}
      <button className="g-thumb" onClick={onOpen} aria-label={`Open ${p.name}`}>
        <svg viewBox={`0 0 ${THUMB.width} ${THUMB.height}`} preserveAspectRatio="xMidYMid meet"
             aria-hidden="true">
          {/* A graticule behind the outline. Without it a boundary floats in
              an empty field and reads as a rectangle rather than as an extent;
              the grid costs nothing and makes the card say "map" at a glance.
              The id is per-project because two <defs> sharing one id in the
              same document collapse to whichever rendered first. */}
          <defs>
            <pattern id={`grid-${p.id}`} width="26" height="26" patternUnits="userSpaceOnUse">
              <path d="M18 0H0V18" fill="none" stroke="currentColor" strokeWidth="1" />
            </pattern>
          </defs>
          <rect width="100%" height="100%" fill={`url(#grid-${p.id})`} className="g-thumb-grid" />
          <path d={d} className="g-thumb-shape" />
        </svg>
        {isCurrent && <span className="g-open-tag">Open</span>}
      </button>

      <div className="g-meta">
        <div className="g-meta-text">
          {isRenaming ? (
            <input
              ref={renameRef}
              className="g-rename"
              defaultValue={p.name}
              onClick={(e) => e.stopPropagation()}
              onBlur={(e) => onRenameCommit(e.target.value)}
              onKeyDown={(e) => {
                if (e.key === 'Enter') onRenameCommit((e.target as HTMLInputElement).value)
                if (e.key === 'Escape') { e.stopPropagation(); onRenameCancel() }
              }}
            />
          ) : (
            <button className="g-name" onClick={onOpen} title={p.name}>{p.name}</button>
          )}
          <div className="g-sub">
            {formatArea(p.area_ha)} · {p.factors.length} factors · {relativeTime(p.updatedAt)}
          </div>
        </div>

        <div className="g-menu-wrap">
          <button className={`g-more${menuOpen ? ' is-open' : ''}`} onClick={onMenu}
                  aria-label={`Actions for ${p.name}`} aria-expanded={menuOpen}>
            <svg viewBox="0 0 20 20" width="16" height="16" fill="currentColor" aria-hidden="true">
              <circle cx="4" cy="10" r="1.5" /><circle cx="10" cy="10" r="1.5" />
              <circle cx="16" cy="10" r="1.5" />
            </svg>
          </button>

          {menuOpen && (
            <div className="tb-menu g-menu" onClick={(e) => e.stopPropagation()}>
              <button onClick={onRenameStart}>Rename</button>
              <button onClick={onDuplicate}>Duplicate</button>
              {isConfirming ? (
                // Deletion is the one thing here that undo cannot reach, so it
                // asks — inline, rather than in a dialog that steals focus.
                <button className="g-danger" onClick={onDeleteConfirm}>
                  Delete permanently?
                </button>
              ) : (
                <button className="g-danger" onClick={onDeleteAsk}>Delete</button>
              )}
            </div>
          )}
        </div>
      </div>
    </div>
  )
}
