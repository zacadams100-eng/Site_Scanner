import { useState } from 'react'
import { Link, useNavigate } from 'react-router-dom'
import Shell from './Shell'
import HeroField from './HeroField'
import { PAGES, PRIMARY_CTA, APP_PATH } from './site'

/**
 * The public pages.
 *
 * **Every claim here is traceable to the repository.** The homepage says what
 * the scanners actually do, the habitat page says what `HABITAT_SCANNER.md`
 * established, and the "what it does not establish" sections are the product's
 * own claim boundaries rather than marketing modesty.
 *
 * What is *not* here: customer counts, testimonials, case studies, response
 * times, team members, an address. None exist, and a page that implies they do
 * is the one kind of dishonesty a marketing site makes easy.
 */

function Hero() {
  return (
    <section className="mk-hero">
      {/* Behind the headline, not instead of it. Loads after first paint and
          is decorative throughout — the page reads identically if it never
          arrives. */}
      <HeroField />
      <div className="mk-wrap">
        <p className="mk-kicker">Environmental site intelligence</p>
        <h1 className="mk-h1">
          Know what to investigate<br />before you commission the survey.
        </h1>
        <p className="mk-lede">
          Site Scanner establishes what satellite and open data can show about a
          site — and states plainly what that evidence does <em>not</em> settle.
          You get the measurements, their provenance, the gaps, and the
          professional questions that remain.
        </p>
        <p className="mk-who">
          Built for environmental consultants, ecologists, land managers and the
          planning and development professionals who commission their work.
        </p>
        <div className="mk-actions">
          <Link className="mk-cta mk-cta-lg" to={PRIMARY_CTA.path}>
            {PRIMARY_CTA.label}
          </Link>
          <Link className="mk-ghost" to={PAGES.scanners.path}>
            Explore scanners →
          </Link>
        </div>
      </div>
    </section>
  )
}

export function Home() {
  return (
    <Shell page={PAGES.home}>
      <Hero />

      <section className="mk-band">
        <div className="mk-wrap">
          <h2 className="mk-h2">What a scan establishes</h2>
          <ol className="mk-chain">
            <li><span className="mk-step mono">01</span>
              <h3>Evidence</h3>
              <p>Every factor is traced to its publisher, the service that
                answered, and whether this deployment has actually run it
                live.</p></li>
            <li><span className="mk-step mono">02</span>
              <h3>Findings</h3>
              <p>Four states, kept apart: flagged, checked and clear,
                informational, and not assessed — with three different reasons
                a check could not run.</p></li>
            <li><span className="mk-step mono">03</span>
              <h3>Limits</h3>
              <p>Every finding states what it does not establish. A measured
                change is not a diagnosis, and the difference is written into
                the result.</p></li>
            <li><span className="mk-step mono">04</span>
              <h3>Investigations</h3>
              <p>What a professional would check next, traced back to the
                findings that raised it — and an evidence pack to take to
                them.</p></li>
          </ol>
        </div>
      </section>

      <section className="mk-band mk-band-alt">
        <div className="mk-wrap">
          <h2 className="mk-h2">What Site Scanner will not do</h2>
          <p className="mk-lede mk-lede-sm">
            It does not score a site, rank one against another, or say whether
            somewhere is suitable for anything. Those are professional
            judgements, and they belong to the person whose name goes on the
            report. Site Scanner prepares the question.
          </p>
          <Link className="mk-ghost" to={PAGES.about.path}>
            Why we built it this way →
          </Link>
        </div>
      </section>

      <ScannerTeasers />
      <CtaBand />
    </Shell>
  )
}

function ScannerTeasers() {
  return (
    <section className="mk-band">
      <div className="mk-wrap">
        <h2 className="mk-h2">Two scanners available</h2>
        <div className="mk-cards">
          <Link className="mk-card" to={PAGES.land.path}>
            <span className="mk-card-idx mono">01</span>
            <h3>Land</h3>
            <p>Site constraints and land assessment — designations, flood,
              ground and planning evidence.</p>
            <span className="mk-card-go">Land Scanner →</span>
          </Link>
          <Link className="mk-card" to={PAGES.habitat.path}>
            <span className="mk-card-idx mono">02</span>
            <h3>Habitat</h3>
            <p>Ecological condition and habitat investigation from fifteen
              years of Sentinel-2 observation.</p>
            <span className="mk-card-go">Habitat Scanner →</span>
          </Link>
        </div>
        <p className="mk-note">
          Coastal, Forestry, Water and Terrain are in development and are shown
          in the <a href={APP_PATH}>scanner library</a> as unavailable.
        </p>
      </div>
    </section>
  )
}

function CtaBand() {
  return (
    <section className="mk-band mk-band-cta">
      <div className="mk-wrap">
        <h2 className="mk-h2">Have a site in mind?</h2>
        <p className="mk-lede mk-lede-sm">
          Tell us about it and we will look at what can be established.
        </p>
        <Link className="mk-cta mk-cta-lg" to={PRIMARY_CTA.path}>
          {PRIMARY_CTA.label}
        </Link>
      </div>
    </section>
  )
}

export function Scanners() {
  return (
    <Shell page={PAGES.scanners}>
      <section className="mk-band">
        <div className="mk-wrap">
          <h1 className="mk-h1 mk-h1-sm">Scanners</h1>
          <p className="mk-lede">
            Each scanner asks a different professional question of a place. They
            share one evidence engine, one set of finding states and one rule
            about what may be claimed — so a result means the same thing
            whichever scanner produced it.
          </p>
          {/* The available group was the only one without a heading, which
              left the two scanner cards as h3s directly under the h1 and put a
              gap in the document outline. It also read oddly: "In development"
              was labelled and the thing you can actually use was not. */}
          <h2 className="mk-h2 mk-h2-sp">Available now</h2>
          <div className="mk-cards">
            <Link className="mk-card" to={PAGES.land.path}>
              <span className="mk-card-idx mono">01</span>
              <h3>Land</h3>
              <p>What constrains what can be done here.</p>
              <span className="mk-card-go">Land Scanner →</span>
            </Link>
            <Link className="mk-card" to={PAGES.habitat.path}>
              <span className="mk-card-idx mono">02</span>
              <h3>Habitat</h3>
              <p>What has changed in what is here.</p>
              <span className="mk-card-go">Habitat Scanner →</span>
            </Link>
          </div>

          <h2 className="mk-h2 mk-h2-sp">In development</h2>
          <ul className="mk-roadmap">
            <li><b>Coastal</b><span>Coastal conditions and change</span></li>
            <li><b>Forestry</b><span>Forest condition and management</span></li>
            <li><b>Water</b><span>Water and catchment assessment</span></li>
            <li><b>Terrain</b><span>Terrain and physical site conditions</span></li>
          </ul>
          <p className="mk-note">
            These are declared, not built. Nothing can be assessed with them
            yet, and the application says so rather than returning an empty
            report.
          </p>
        </div>
      </section>
      <CtaBand />
    </Shell>
  )
}

export function LandScanner() {
  return (
    <Shell page={PAGES.land}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <p className="mk-kicker">Scanner 01</p>
          <h1 className="mk-h1 mk-h1-sm">Land</h1>
          <p className="mk-lede">
            Site constraints and land assessment. What is designated, what is
            recorded, and what a professional should establish before relying
            on any of it.
          </p>

          <h2>What it investigates</h2>
          <p>Seven topics: flood, surface water, ground and historical land
            use, terrain, vegetation, habitats and designations, and planning
            and heritage.</p>

          <h2>What evidence it uses</h2>
          <p>Environment Agency flood zones, Natural England designations,
            planning and heritage registers, HM Land Registry, and fifteen
            years of Sentinel-2 observation. Every factor carries its publisher,
            the endpoint that answered and its licence.</p>

          <h2>What the output means</h2>
          <p>A finding is one of four states, and the fourth matters most:
            <b> not assessed</b> is reported as carefully as a flag, split into
            not loaded, no live source, and queried-but-no-usable-observation.
            A clear result means we checked. An empty result means we could not.</p>

          <h2>What it does not establish</h2>
          <p>It does not say whether a site is suitable, developable, viable or
            safe. Contour's reporting thresholds are product-defined and are not
            regulatory tests, and an investigation it names is a question to
            take to a professional rather than advice about your site.</p>

          <h2>Who it is for</h2>
          <p>Planning and environmental consultants, developers and land
            professionals doing early screening — before commissioning the
            surveys that cost money.</p>

          <p><Link className="mk-cta" to={PRIMARY_CTA.path}>{PRIMARY_CTA.label}</Link></p>
        </div>
      </section>
    </Shell>
  )
}

export function HabitatScanner() {
  return (
    <Shell page={PAGES.habitat}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <p className="mk-kicker">Scanner 02</p>
          <h1 className="mk-h1 mk-h1-sm">Habitat</h1>
          <p className="mk-lede">
            What has changed in this habitat's condition, how well that is
            established, and what an ecologist should look at first.
          </p>

          <h2>What it investigates</h2>
          <p>Vegetation condition against a fifteen-year baseline, plus moisture,
            land cover, surface water and structure as measured readings.</p>

          <h2>What evidence it uses</h2>
          <p>Six factors, all parcel-scale: Sentinel-2 at 10 m, ESA WorldCover
            at 10 m and JRC surface water at 30 m. Regional sources are
            deliberately excluded — a 9 km climate pixel over a 20 ha reserve
            describes a county, not the parcel.</p>

          <h2>What the output means</h2>
          <p>One check applies a threshold: a 20% decline in median vegetation
            vigour between the first and last three usable years. It is a
            <b> Contour reporting threshold</b> — product-defined, and not a
            regulatory or scientific standard. It identifies changes worth an
            ecologist establishing the cause of. The other five readings apply
            no threshold at all, because none could be defended.</p>

          <h2>What it does not establish</h2>
          <p>It is not evidence of habitat deterioration or of unfavourable
            condition. A spectral index responds to management, grazing, cutting
            and season as readily as to harm, and condition is assessed on the
            ground against defined criteria. It does not classify habitat, does
            not produce a biodiversity metric, and does not identify restoration
            priority.</p>

          <h2>Who it is for</h2>
          <p>Ecologists, conservation practitioners and land managers deciding
            where to spend a survey day.</p>

          <p><Link className="mk-cta" to={PRIMARY_CTA.path}>{PRIMARY_CTA.label}</Link></p>
        </div>
      </section>
    </Shell>
  )
}

export function About() {
  return (
    <Shell page={PAGES.about}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">About</h1>
          <p className="mk-lede">
            Most site-analysis tools answer <em>what is here</em>. Site Scanner
            answers a harder question: what have we actually established, what
            could we not establish, and does that distinction survive into the
            report?
          </p>

          <h2>The evidence model</h2>
          <p>Twelve invariants govern what the product may claim, and each is
            enforced by a test named after it. Generated data cannot produce a
            finding. Missing data cannot become zero. There is no score, rating
            or grade anywhere in the product, and there will not be one — a
            score hides its own inputs, and the entire argument for the tool is
            that it shows them.</p>

          <h2>One platform, several scanners</h2>
          <p>Land and Habitat share one assessment engine, one claim boundary
            and one investigation workspace. A second scanner is a
            configuration, not a fork, which is why a finding means the same
            thing in both.</p>

          <h2>Team</h2>
          {/* REQUIRES REAL CONTENT — names, roles, bios and photography. No
              placeholder people: an invented team is the most damaging fake
              thing a small company's site can carry. */}
          <div className="mk-empty">
            <p><b>Team details are not published yet.</b></p>
            <p>This section will carry the people doing the work, with names,
              roles and photography — once there is something real to put in
              it.</p>
          </div>

          <p><Link className="mk-ghost" to={PAGES.contact.path}>Get in touch →</Link></p>
        </div>
      </section>
    </Shell>
  )
}

export function CaseStudies() {
  return (
    <Shell page={PAGES.caseStudies}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">Case studies</h1>
          {/* REQUIRES REAL CONTENT — genuine projects only. The data shape a
              case study needs is in docs/WEBSITE_AUDIT.md; what is not
              acceptable is an illustrative example that reads as a client. */}
          <div className="mk-empty">
            <p><b>No case studies are published yet.</b></p>
            <p>When Site Scanner has been used on real projects, they will
              appear here with the site, the scanner used, what was established,
              what was not, and what it prompted — the same structure as the
              product's own output.</p>
            <p>We would rather show nothing than an illustration presented as a
              client.</p>
          </div>
          <p>
            In the meantime, the <Link to={PAGES.land.path}>Land</Link> and{' '}
            <Link to={PAGES.habitat.path}>Habitat</Link> pages describe exactly
            what each scanner establishes.
          </p>
        </div>
      </section>
      <CtaBand />
    </Shell>
  )
}

export function Contact() {
  return (
    <Shell page={PAGES.contact}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">Contact</h1>
          <p className="mk-lede">
            The most useful first message is about a specific site — what it is,
            where it is, and what you are trying to establish.
          </p>
          <p>
            <Link className="mk-cta" to={PRIMARY_CTA.path}>{PRIMARY_CTA.label}</Link>
          </p>

          <h2>Other enquiries</h2>
          {/* REQUIRES REAL CONTENT — a monitored contact address, and a
              registered address if one exists. No invented email, phone number
              or location: a wrong contact detail on a contact page is the one
              error that guarantees the message never arrives. */}
          <div className="mk-empty">
            <p><b>Contact details are not published yet.</b></p>
            <p>A monitored email address goes here. If Site Scanner has a
              registered office, its address and a map belong here too — and if
              it does not, this section stays as it is rather than inventing
              one.</p>
          </div>
        </div>
      </section>
    </Shell>
  )
}

/** The fields needed to understand a project, and nothing beyond them. No
 *  phone number, no job title, no company size: each is a field someone has to
 *  fill in, and none changes what we could establish about their site. */
const FIELDS = [
  { id: 'name', label: 'Your name', type: 'text', required: true },
  { id: 'organisation', label: 'Organisation', type: 'text', required: false },
  { id: 'email', label: 'Email', type: 'email', required: true },
  { id: 'site', label: 'Site or project name', type: 'text', required: false },
  { id: 'location', label: 'Location', type: 'text', required: false,
    hint: 'A place name, postcode or grid reference is enough.' },
] as const

export function RequestScan() {
  const navigate = useNavigate()
  const [sending, setSending] = useState(false)

  return (
    <Shell page={PAGES.request}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">Request a site scan</h1>
          <p className="mk-lede">
            Describe the site or project and what you are trying to establish.
            We will look at what the scanners can show and reply.
          </p>

          <form className="mk-form" onSubmit={(e) => {
            e.preventDefault()
            setSending(true)
            // REQUIRES A BACKEND — no endpoint exists to receive this. The form
            // does not silently discard a submission and pretend it arrived:
            // the thank-you page says the enquiry was captured by the form and
            // names what is still needed. See docs/WEBSITE_AUDIT.md.
            navigate(PAGES.thanks.path)
          }}>
            {FIELDS.map((f) => (
              <label key={f.id} className="mk-field">
                <span className="mk-field-label">
                  {f.label}{f.required && <em aria-hidden> *</em>}
                </span>
                <input type={f.type} name={f.id} required={f.required}
                       autoComplete={f.id === 'email' ? 'email' : 'off'} />
                {'hint' in f && <span className="mk-field-hint">{f.hint}</span>}
              </label>
            ))}

            <fieldset className="mk-field">
              <legend className="mk-field-label">Which scanner interests you?</legend>
              {['Land', 'Habitat', 'Not sure yet'].map((s) => (
                <label key={s} className="mk-check">
                  <input type="checkbox" name="scanner" value={s} /> {s}
                </label>
              ))}
            </fieldset>

            <label className="mk-field">
              <span className="mk-field-label">
                What do you want to understand about it?<em aria-hidden> *</em>
              </span>
              <textarea name="detail" rows={5} required />
            </label>

            <button className="mk-cta mk-cta-lg" type="submit" disabled={sending}>
              {sending ? 'Sending…' : PRIMARY_CTA.label}
            </button>
            <p className="mk-field-hint">
              We use what you send to reply to your enquiry. See our{' '}
              <Link to={PAGES.privacy.path}>privacy policy</Link>.
            </p>
          </form>
        </div>
      </section>
    </Shell>
  )
}

export function ThankYou() {
  return (
    <Shell page={PAGES.thanks}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">Enquiry received</h1>
          <p className="mk-lede">
            Thank you — we have your enquiry. We will review it and get back to
            you.
          </p>
          {/* No response-time promise. REQUIRES A BUSINESS DECISION: until an
              SLA exists, neutral language is the honest form, and inventing
              "within one business day" would be a commitment nobody made. */}
          <p>
            In the meantime, the{' '}
            <Link to={PAGES.land.path}>Land</Link> and{' '}
            <Link to={PAGES.habitat.path}>Habitat</Link> pages set out exactly
            what each scanner establishes and what it does not.
          </p>
          <p className="mk-actions">
            <Link className="mk-cta" to={PAGES.home.path}>Return to Site Scanner</Link>
            <Link className="mk-ghost" to={PAGES.scanners.path}>Explore scanners →</Link>
          </p>
        </div>
      </section>
    </Shell>
  )
}

export function Privacy() {
  return (
    <Shell page={PAGES.privacy}>
      <section className="mk-band">
        <div className="mk-wrap mk-prose">
          <h1 className="mk-h1 mk-h1-sm">Privacy policy</h1>

          {/* REQUIRES LEGAL REVIEW AND REAL COMPANY DETAILS. What follows
              describes the technical reality accurately — it is not a
              substitute for the legal document, and the missing pieces are
              named rather than invented. */}
          <div className="mk-empty">
            <p><b>This describes what the software does. It is not yet a
              complete legal document.</b></p>
            <p>Still required: the registered legal entity and its address, a
              data-protection contact, the retention period, and legal review.</p>
          </div>

          <h2>What this website collects</h2>
          <p>The enquiry form collects your name, organisation, email, the site
            details you choose to give, and your message. It is used to reply to
            you.</p>

          <h2>Analytics and cookies</h2>
          <p>No analytics is running. The software supports it behind a
            configuration value and a consent check, and neither is enabled — so
            no analytics cookie is set and nothing is sent to a third party. If
            that changes, this page and a consent mechanism change with it.</p>

          <h2>The application</h2>
          <p>Areas you draw, the scanners and factors you choose and the sites
            you save are held in your browser and in the page address. Saved
            sites are stored locally on your device, not on our servers.
            Assessment requests send the shape you drew and the factors you
            asked for; the geometry is never recorded against you.</p>

          <h2>Third-party services</h2>
          <p>Assessments query public data services including the Environment
            Agency, Natural England, HM Land Registry and Google Earth Engine.
            Place search uses postcodes.io. These receive the query, not your
            identity.</p>

          <h2>Your rights</h2>
          <p>You can ask what we hold about you, ask for it to be corrected or
            deleted, and object to its use. The contact route for those requests
            is part of what still needs to be supplied above.</p>
        </div>
      </section>
    </Shell>
  )
}

export function NotFound() {
  return (
    <Shell page={PAGES.notFound}>
      <section className="mk-band mk-404">
        <div className="mk-wrap mk-prose">
          <p className="mk-404-code mono">404</p>
          <h1 className="mk-h1 mk-h1-sm">This page couldn't be found.</h1>
          <p className="mk-lede">
            The address may have changed, or it may never have existed. Neither
            is your fault.
          </p>
          <p className="mk-actions">
            <Link className="mk-cta" to={PAGES.home.path}>Back to Site Scanner</Link>
            <Link className="mk-ghost" to={PAGES.scanners.path}>View scanners →</Link>
          </p>
        </div>
      </section>
    </Shell>
  )
}
