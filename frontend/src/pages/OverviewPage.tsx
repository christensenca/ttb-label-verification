import styles from './OverviewPage.module.css'

interface Step {
  name: string
  desc: string
}

const PIPELINE: Step[] = [
  { name: 'Upload', desc: 'Image plus expected values, single or CSV batch.' },
  { name: 'Extract', desc: 'Vision call with structured Pydantic output.' },
  { name: 'Normalize', desc: 'Case, units, abbreviations.' },
  { name: 'Compare', desc: 'Per-field rules: fuzzy, numeric, strict.' },
  { name: 'Review', desc: 'Diffs, image lightbox, override with comment.' },
  { name: 'Decide', desc: 'Approved or rejected with structured reasons.' },
]

interface Tradeoff {
  title: string
  body: string
}

const TRADEOFFS: Tradeoff[] = [
  {
    title: 'Fast model over pro model',
    body: 'Gemini 3.1 Flash Lite: 91% accuracy, 3.4s mean. Pro variant at 95% / 5.8s is one env var away.',
  },
  {
    title: 'Deterministic compare, not LLM-as-judge',
    body: 'Cheap, debuggable, stable across runs. Reviewer override covers edge cases.',
  },
  {
    title: 'No auth, no roles',
    body: 'Shared demo URL. Override is open to anyone with the link.',
  },
  {
    title: 'Image-only intake',
    body: 'JPEG, PNG, WebP. No PDF intake in this prototype.',
  },
  {
    title: 'In-process asyncio pool',
    body: 'One container, configurable concurrency semaphore. No Celery, no Redis.',
  },
  {
    title: 'Distilled-spirits test corpus',
    body: 'Seven fixtures cover spirits. Schema generalizes to beer and wine.',
  },
]

export default function OverviewPage() {
  return (
    <div className={styles.page}>
      <header className={styles.header}>
        <h1>Overview</h1>
        <p className={styles.tagline}>How LabelGuard works.</p>
      </header>

      <section className={styles.section}>
        <span className={styles.sectionLabel}>Why</span>
        <h2 className={styles.sectionTitle}>The pain in the existing process</h2>
        <div className={styles.stats}>
          <div className={styles.stat}>
            <span className={styles.statNumber}>150K</span>
            <span className={styles.statLabel}>label applications a year</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>47</span>
            <span className={styles.statLabel}>agents, down from 100+</span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>5s</span>
            <span className={styles.statLabel}>
              max per label or agents stop using
            </span>
          </div>
          <div className={styles.stat}>
            <span className={styles.statNumber}>200-300</span>
            <span className={styles.statLabel}>labels per importer batch</span>
          </div>
        </div>
        <ul className={styles.bullets}>
          <li>Most of the day is matching fields by eye.</li>
          <li>
            Prior scanning pilot died at 30 to 40 seconds per label. Agents
            stopped using it.
          </li>
          <li>
            Government warning is the most-gamed field. Vendors shrink it,
            retitle it, bury it.
          </li>
        </ul>
      </section>

      <section className={styles.section}>
        <span className={styles.sectionLabel}>Approach</span>
        <h2 className={styles.sectionTitle}>Model proposes, human decides</h2>
        <ul className={styles.bullets}>
          <li>Reviewer uploads label image plus expected values.</li>
          <li>
            One vision-LLM call per label, schema-enforced structured output.
          </li>
          <li>Deterministic normalize and compare per field.</li>
          <li>
            Government warning checked strict against canonical 27 CFR 16.21
            text.
          </li>
          <li>
            Human always reviews. Overrides persist alongside model output for
            audit.
          </li>
        </ul>
      </section>

      <section className={styles.section}>
        <span className={styles.sectionLabel}>Pipeline</span>
        <h2 className={styles.sectionTitle}>Six stages, one container</h2>
        <div className={styles.pipeline}>
          {PIPELINE.map((step, i) => (
            <div key={step.name} className={styles.step}>
              <span className={styles.stepNum}>Stage {i + 1}</span>
              <span className={styles.stepName}>{step.name}</span>
              <span className={styles.stepDesc}>{step.desc}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <span className={styles.sectionLabel}>Tradeoffs</span>
        <h2 className={styles.sectionTitle}>What we deliberately gave up</h2>
        <div className={styles.twoCol}>
          {TRADEOFFS.map((t) => (
            <div key={t.title} className={styles.card}>
              <span className={styles.cardTitle}>{t.title}</span>
              <span className={styles.cardBody}>{t.body}</span>
            </div>
          ))}
        </div>
      </section>

      <section className={styles.section}>
        <span className={styles.sectionLabel}>What's next</span>
        <h2 className={styles.sectionTitle}>If this graduated to production</h2>
        <ul className={styles.bullets}>
          <li>Azure OpenAI deployment for FedRAMP and IL5.</li>
          <li>Beer and wine corpus expansion.</li>
          <li>LLM as judge for low-confidence verdicts only (hybrid).</li>
          <li>More training and eval data per beverage type.</li>
          <li>Submitter and reviewer roles with SSO.</li>
        </ul>
      </section>

      <p className={styles.footerNote}>
        Full detail in the repo:{' '}
        <a
          href="https://github.com/christensenca/ttb-label-verification/blob/main/docs/APPROACH.md"
          target="_blank"
          rel="noreferrer"
        >
          APPROACH
        </a>
        ,{' '}
        <a
          href="https://github.com/christensenca/ttb-label-verification/blob/main/docs/TRADEOFFS.md"
          target="_blank"
          rel="noreferrer"
        >
          TRADEOFFS
        </a>
        , and{' '}
        <a
          href="https://github.com/christensenca/ttb-label-verification/blob/main/docs/architecture-decisions.md"
          target="_blank"
          rel="noreferrer"
        >
          architecture decisions
        </a>
        .
      </p>
    </div>
  )
}
