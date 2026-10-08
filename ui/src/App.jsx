import React, { useState, useEffect, useMemo, useRef } from 'react'

const CLINICAL_PRESETS = [
  {
    label: 'GLP-1 RA in Type 2 Diabetes (MACE)',
    question:
      'In adult patients with type 2 diabetes and high cardiovascular risk, do GLP-1 receptor agonists (semaglutide, liraglutide, or dulaglutide) compared to placebo reduce major adverse cardiovascular events (MACE)?',
  },
  {
    label: 'DOACs vs Warfarin in Atrial Fibrillation',
    question:
      'In adult patients with non-valvular atrial fibrillation, do direct oral anticoagulants (apixaban, rivaroxaban, dabigatran, or edoxaban) compared to warfarin reduce stroke or systemic embolism?',
  },
  {
    label: 'SGLT2i in Chronic Kidney Disease (CKD)',
    question:
      'In adults with chronic kidney disease with or without type 2 diabetes, do SGLT2 inhibitors (dapagliflozin or empagliflozin) compared to placebo reduce kidney disease progression or cardiovascular death?',
  },
  {
    label: 'Short DAPT (1-3m) vs 12-Month DAPT Post-PCI',
    question:
      'In patients undergoing percutaneous coronary intervention with drug-eluting stents, does short-course DAPT (1 to 3 months) followed by P2Y12 monotherapy compared to standard 12-month DAPT reduce major bleeding?',
  },
  {
    label: 'CAR-T vs Bispecifics (MM / Lymphoma CRS)',
    question:
      'In adult patients with relapsed or refractory multiple myeloma or B-cell lymphoma, what is the incidence and relative risk of Cytokine Release Syndrome (CRS) in CAR-T cell therapy compared to bispecific antibodies or standard regimens?',
  },
  {
    label: 'Aspirin Primary CV Prevention',
    question:
      'Does low-dose aspirin compared to placebo or no aspirin reduce major adverse cardiovascular events (myocardial infarction, stroke, or cardiovascular death) in adults without established cardiovascular disease?',
  },
  {
    label: 'Corticosteroids in Severe COVID-19',
    question:
      'Do systemic corticosteroids (dexamethasone, hydrocortisone, or methylprednisolone) compared to usual care or placebo reduce 28-day all-cause mortality in hospitalized patients with severe or critical COVID-19?',
  },
  {
    label: 'SGLT2i in Heart Failure (HFrEF/HFpEF)',
    question:
      'Do SGLT2 inhibitors (dapagliflozin or empagliflozin) compared to placebo reduce composite cardiovascular death or hospitalization for heart failure in adults with chronic heart failure?',
  },
]

function formatNum(val, digits = 2) {
  if (val === null || val === undefined || Number.isNaN(Number(val))) return '—'
  return Number(val).toFixed(digits)
}

function formatPValue(p) {
  if (p === null || p === undefined || Number.isNaN(Number(p))) return '—'
  const num = Number(p)
  if (num < 0.0001) return '< 0.0001'
  return num.toFixed(4)
}

function getRobBadge(judgment) {
  const j = String(judgment || '').toLowerCase()
  if (j.includes('low')) {
    return <span className="badge badge-low">Low Risk</span>
  }
  if (j.includes('high')) {
    return <span className="badge badge-high">High Risk</span>
  }
  if (j.includes('concern') || j.includes('moderate') || j.includes('unclear')) {
    return <span className="badge badge-warn">Some Concerns</span>
  }
  return <span className="badge badge-neutral">{judgment || 'N/A'}</span>
}

function getGradeBadge(certainty) {
  const c = String(certainty || '').toUpperCase()
  if (c === 'HIGH') return <span className="badge badge-low">⊕⊕⊕⊕ HIGH</span>
  if (c === 'MODERATE') return <span className="badge badge-warn">⊕⊕⊕◯ MODERATE</span>
  if (c === 'LOW') return <span className="badge badge-warn">⊕⊕◯◯ LOW</span>
  if (c === 'VERY LOW') return <span className="badge badge-high">⊕◯◯◯ VERY LOW</span>
  return <span className="badge badge-neutral">{certainty || 'N/A'}</span>
}

function resolveStudyUrl(item) {
  if (!item) return null
  if (item.url) return item.url
  const pmid = item.pmid
  const doi = item.doi
  const nct = item.nct_id
  const rawId = String(item.raw_id || item.id || item.study_id || '').trim()
  const title = String(item.title || item.removed_title || '').trim()

  if (pmid) return `https://pubmed.ncbi.nlm.nih.gov/${pmid}/`
  if (doi) return doi.startsWith('http') ? doi : `https://doi.org/${doi}`
  if (nct) return `https://clinicaltrials.gov/study/${nct}`

  const nctMatch = (rawId + ' ' + title).match(/(NCT\d{8})/i)
  if (nctMatch) return `https://clinicaltrials.gov/study/${nctMatch[1].toUpperCase()}`

  const doiMatch = rawId.match(/(10\.\d{4,9}\/[-._;()/:A-Za-z0-9]+)/)
  if (doiMatch) return `https://doi.org/${doiMatch[1]}`

  const pmidMatch = (rawId + ' ' + title).match(/PMID:\s*(\d+)/i)
  if (pmidMatch) return `https://pubmed.ncbi.nlm.nih.gov/${pmidMatch[1]}/`
  if (/^\d{6,10}$/.test(rawId)) return `https://pubmed.ncbi.nlm.nih.gov/${rawId}/`

  if (title || rawId) {
    return `https://scholar.google.com/scholar?q=${encodeURIComponent(title || rawId)}`
  }
  return null
}

function VerificationBadges({ item }) {
  if (!item) return null
  const pmid = item.pmid
  const doi = item.doi
  const nct = item.nct_id
  const fallbackUrl = resolveStudyUrl(item)

  return (
    <div style={{ display: 'flex', flexWrap: 'wrap', gap: '4px', marginTop: '4px' }}>
      {pmid && (
        <a
          href={`https://pubmed.ncbi.nlm.nih.gov/${pmid}/`}
          target="_blank"
          rel="noreferrer"
          className="ext-link-badge"
        >
          PMID: {pmid} ↗
        </a>
      )}
      {doi && (
        <a
          href={doi.startsWith('http') ? doi : `https://doi.org/${doi}`}
          target="_blank"
          rel="noreferrer"
          className="ext-link-badge"
        >
          DOI: {doi.replace(/^https?:\/\/doi\.org\//i, '')} ↗
        </a>
      )}
      {nct && (
        <a
          href={`https://clinicaltrials.gov/study/${nct}`}
          target="_blank"
          rel="noreferrer"
          className="ext-link-badge"
        >
          {nct} ↗
        </a>
      )}
      {!pmid && !doi && !nct && fallbackUrl && (
        <a href={fallbackUrl} target="_blank" rel="noreferrer" className="ext-link-badge">
          Verify Article ↗
        </a>
      )}
      {item.source && (
        <span className="badge badge-neutral" style={{ fontSize: '10px' }}>
          {item.source}
        </span>
      )}
    </div>
  )
}

export default function App() {
  const [runs, setRuns] = useState([])
  const [selectedRunId, setSelectedRunId] = useState(null)
  const [isNewChatMode, setIsNewChatMode] = useState(false)
  const [runData, setRunData] = useState(null)

  // View Mode: 'chat' (default simple Chatbot view) or 'analysis' (Full Analysis Page)
  const [viewMode, setViewMode] = useState('chat')
  const [activeTab, setActiveTab] = useState('overview')

  // Chat Input State
  const [composerText, setComposerText] = useState('')
  const [submitting, setSubmitting] = useState(false)
  const [activeJobs, setActiveJobs] = useState([])
  // Inline replies for greetings / off-topic messages (no review started)
  const [chatReplies, setChatReplies] = useState([])

  // Filter / Modal State
  const [auditSubTab, setAuditSubTab] = useState('excluded')
  const [auditSearch, setAuditSearch] = useState('')
  const [lightboxImage, setLightboxImage] = useState(null)

  const chatEndRef = useRef(null)

  const fetchRunsList = async (autoSelectFirst = false) => {
    try {
      const runsRes = await fetch('/api/runs')
      if (runsRes.ok) {
        const list = await runsRes.json()
        setRuns(list)
        if (autoSelectFirst && list.length > 0 && !selectedRunId) {
          setSelectedRunId(list[0].run_id)
        }
      }
    } catch (err) {
      console.error('Failed to load runs:', err)
    }
  }

  useEffect(() => {
    fetchRunsList(true)
  }, [])

  // Poll active background reviews
  useEffect(() => {
    const timer = setInterval(async () => {
      try {
        const res = await fetch('/api/reviews/active')
        if (!res.ok) return
        const jobs = await res.json()
        const running = jobs.filter((j) => j.status === 'running')
        setActiveJobs(running)

        const completed = jobs.filter(
          (j) => j.status === 'completed' && j.run_id && !runs.some((r) => r.run_id === j.run_id)
        )
        if (completed.length > 0) {
          await fetchRunsList(false)
          setIsNewChatMode(false)
          setSelectedRunId(completed[0].run_id)
        }
      } catch (e) {
        // ignore transient poll errors
      }
    }, 2500)
    return () => clearInterval(timer)
  }, [runs])

  // Load selected run details
  useEffect(() => {
    if (!selectedRunId) return
    let cancelled = false
    const loadRun = async () => {
      try {
        const resDetail = await fetch(`/api/runs/${selectedRunId}`)
        if (!cancelled && resDetail.ok) {
          const data = await resDetail.json()
          setRunData(data)
        }
      } catch (err) {
        console.error('Error loading run detail:', err)
      }
    }
    loadRun()
    return () => {
      cancelled = true
    }
  }, [selectedRunId])

  // Derived data from runData
  const pico = runData?.pico || {}
  const prisma = runData?.prisma_counts || {}
  const screeningStats = runData?.screening_stats || {}
  const includedStudies = runData?.included_studies || []
  const meta = runData?.meta_analysis || {}
  const grade = runData?.grade || {}
  const robList = runData?.rob2_assessments || []
  const excludedRecords = runData?.excluded_records || []
  const unpooledRecords = runData?.approved_but_unpooled_records || []
  const duplicateRecords = runData?.duplicate_records || []

  const studyStatMap = useMemo(() => {
    const m = {}
    ;(meta.studies || []).forEach((st) => {
      if (st.study_id) m[st.study_id] = st
    })
    return m
  }, [meta])

  const pooledStudies = useMemo(
    () => includedStudies.filter((s) => Boolean(studyStatMap[s.study_id])),
    [includedStudies, studyStatMap]
  )
  const unpooledIncludedStudies = useMemo(
    () => includedStudies.filter((s) => !studyStatMap[s.study_id]),
    [includedStudies, studyStatMap]
  )

  // Build Approved Unpooled directly from the Table 1 studies not pooled in 2x2 meta-analysis
  // so Included (k) = Pooled + Approved Unpooled is 100% exact and every row has full links & reasons
  const enrichedUnpooledRecords = useMemo(() => {
    return unpooledIncludedStudies.map((matched, uIdx) => {
      const table1Idx = includedStudies.indexOf(matched) + 1
      const rawUnp =
        unpooledRecords.find(
          (r) =>
            (r.table1_index && r.table1_index === table1Idx) ||
            (r.id && (r.id === matched.raw_id || r.id === matched.study_id)) ||
            (r.study_id && r.study_id === matched.study_id)
        ) ||
        unpooledRecords[uIdx] ||
        {}

      const hasArms =
        matched.events_treatment !== null &&
        matched.events_treatment !== undefined &&
        matched.n_treatment !== null &&
        matched.n_treatment !== undefined
      const armSummary =
        rawUnp.extracted_arms ||
        (hasArms
          ? `Intervention: ${matched.events_treatment} / ${matched.n_treatment} vs Control: ${matched.events_control} / ${matched.n_control}`
          : 'Single-Arm / Qualitative (No 2×2 event/total counts in abstract)')

      const computedReason =
        matched.unpooled_reason ||
        rawUnp.unpooled_reason ||
        (hasArms &&
        (Number(matched.events_treatment) > Number(matched.n_treatment) ||
          Number(matched.events_control) > Number(matched.n_control))
          ? `Events exceed arm total (${matched.events_treatment}/${matched.n_treatment}, ${matched.events_control}/${matched.n_control}).`
          : 'Requires n_events and n_total in both arms; one or more were missing.')

      const computedCode =
        matched.unpooled_reason_code ||
        rawUnp.reason_code ||
        (hasArms &&
        (Number(matched.events_treatment) > Number(matched.n_treatment) ||
          Number(matched.events_control) > Number(matched.n_control))
          ? 'EVENTS_EXCEED_TOTAL'
          : 'MISSING_BINARY_DATA')

      return {
        table1_index: table1Idx,
        id: matched.raw_id || matched.study_id,
        study_id: matched.study_id,
        title: matched.title || rawUnp.title || matched.study_id,
        pmid: matched.pmid || rawUnp.pmid,
        doi: matched.doi || rawUnp.doi,
        nct_id: matched.nct_id || rawUnp.nct_id,
        url: matched.url || rawUnp.url,
        source: matched.source || rawUnp.source,
        extracted_arms: armSummary,
        reviewer_a_reason: matched.reviewer_a_reason || rawUnp.reviewer_a_reason,
        reason_code: computedCode,
        unpooled_reason: computedReason,
      }
    })
  }, [unpooledIncludedStudies, includedStudies, unpooledRecords])

  // Map study_id -> unpooled reason so Table 1 can also display the exact unpooled reason inline
  const unpooledReasonMap = useMemo(() => {
    const m = {}
    enrichedUnpooledRecords.forEach((u) => {
      if (u.study_id) m[u.study_id] = u
      if (u.id) m[u.id] = u
    })
    return m
  }, [enrichedUnpooledRecords])

  const primaryPool = meta.pooled_reml_hksj || meta.pooled_dl || {}
  const het = meta.heterogeneity || {}
  const measureLabel = meta.measure || pico.effect_measure || 'OR'

  // Launch a new review using default backend config
  const handleSendQuery = async (e) => {
    if (e) e.preventDefault()
    const q = composerText.trim()
    if (!q || submitting) return
    setSubmitting(true)
    try {
      const res = await fetch('/api/reviews', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ question: q }),
      })
      if (res.ok) {
        const data = await res.json()
        if (data.kind && data.kind !== 'review') {
          // Greeting / off-topic: the server replied inline, no review started.
          setChatReplies((prev) => [...prev, { question: q, kind: data.kind, reply: data.reply }])
        } else {
          setActiveJobs((prev) => [data, ...prev])
        }
        setComposerText('')
        setViewMode('chat')
      }
    } catch (err) {
      console.error('Failed to launch review:', err)
    } finally {
      setSubmitting(false)
    }
  }

  return (
    <div className="app-shell">
      {/* LEFT SIDEBAR: NEW CHAT + PAST STUDIES */}
      <aside className="sidebar">
        <div className="sidebar-brand">
          <div className="brand-eyebrow">Clinical AI Assistant</div>
          <div className="brand-title">SRMA Research Agent</div>
          <div className="brand-subtitle">Systematic Review & Meta-Analysis</div>
        </div>

        <div className="sidebar-new-chat">
          <button
            type="button"
            className="btn-new-chat"
            onClick={() => {
              setIsNewChatMode(true)
              setViewMode('chat')
              setComposerText('')
              setChatReplies([])
            }}
          >
            ＋ New Clinical Query
          </button>
        </div>

        <div className="sidebar-history">
          <div className="sidebar-section-title">
            <span>Completed Studies ({runs.length})</span>
          </div>

          <div className="run-list">
            {runs.map((r) => {
              const isSelected = !isNewChatMode && r.run_id === selectedRunId
              return (
                <div
                  key={r.run_id}
                  className={`run-item ${isSelected ? 'active' : ''}`}
                  onClick={() => {
                    setIsNewChatMode(false)
                    setSelectedRunId(r.run_id)
                    setViewMode('chat')
                  }}
                >
                  <div className="run-item-header">
                    <span>{r.run_id}</span>
                    <span>k = {r.included_count}</span>
                  </div>
                  <div className="run-item-title">{r.title || r.question}</div>
                </div>
              )
            })}
          </div>
        </div>
      </aside>

      {/* MAIN WORKSPACE */}
      <main className="main-workspace">
        {/* TOP HEADER */}
        <header className="top-navbar">
          <div className="top-navbar-left">
            {viewMode === 'analysis' && (
              <button
                type="button"
                className="btn-export-secondary"
                onClick={() => setViewMode('chat')}
              >
                ← Back to Chat
              </button>
            )}
            <div className="top-navbar-title">
              {isNewChatMode
                ? 'New Systematic Review Query'
                : runData?.question || 'SRMA Clinical Assistant'}
            </div>
          </div>

          <div className="top-navbar-right">
            {!isNewChatMode && runData && (
              <>
                {viewMode === 'chat' ? (
                  <button
                    type="button"
                    className="btn-export-secondary"
                    onClick={() => setViewMode('analysis')}
                  >
                    View Full Analysis →
                  </button>
                ) : null}
                <a
                  href={`/api/runs/${runData.run_id}/pdf`}
                  target="_blank"
                  rel="noreferrer"
                  className="btn-pdf-primary"
                >
                  ⬇ Download PDF Report
                </a>
              </>
            )}
          </div>
        </header>

        {/* ===================================================================
            VIEW 1: SIMPLE CHATBOT INTERFACE (DEFAULT)
           =================================================================== */}
        {viewMode === 'chat' && (
          <div className="chat-viewport">
            <div className="chat-messages-scroll">
              <div className="chat-container">
                {/* Inline replies (greeting / off-topic) - no review was started */}
                {chatReplies.map((m, idx) => (
                  <div key={`reply-${idx}`}>
                    <div className="msg-row-user">
                      <div className="msg-bubble-user">
                        <div className="msg-user-text">{m.question}</div>
                      </div>
                    </div>
                    <div className="msg-card-agent">
                      <div className="msg-agent-header">
                        <div className="msg-agent-identity">
                          <div className="agent-avatar">AI</div>
                          <div>
                            <strong style={{ fontSize: '13.5px', color: '#0f2537' }}>
                              SRMA Research Agent
                            </strong>
                          </div>
                        </div>
                        {m.kind === 'off_topic' && (
                          <span className="badge badge-warn">OUT OF SCOPE</span>
                        )}
                        {(m.kind === 'offline' || m.kind === 'unavailable') && (
                          <span className="badge badge-warn">SERVICE OFFLINE</span>
                        )}
                      </div>
                      <div className="msg-agent-body">
                        <div style={{ fontSize: '13.5px', whiteSpace: 'pre-wrap' }}>{m.reply}</div>
                      </div>
                    </div>
                  </div>
                ))}

                {/* Live Running Job Progress */}
                {activeJobs.map((job) => (
                  <div key={job.job_id} className="msg-card-agent">
                    <div className="msg-agent-header">
                      <div className="msg-agent-identity">
                        <div className="agent-avatar">AI</div>
                        <div>
                          <strong style={{ fontSize: '13.5px', color: '#0f2537' }}>
                            Running Systematic Review — {job.phase}
                          </strong>
                        </div>
                      </div>
                      <span className="badge badge-warn">IN PROGRESS</span>
                    </div>
                    <div className="msg-agent-body">
                      <div style={{ fontSize: '13.5px', marginBottom: '10px' }}>
                        <strong>Question:</strong> {job.question}
                      </div>
                      {job.logs && job.logs.length > 0 && (
                        <div className="code-pre" style={{ fontSize: '11.5px', padding: '12px' }}>
                          {job.logs.slice(-5).map((l, idx) => (
                            <div key={idx}>
                              [{new Date(l.time).toLocaleTimeString()}] {l.detail}
                            </div>
                          ))}
                        </div>
                      )}
                    </div>
                  </div>
                ))}

                {/* New Chat Welcome Screen */}
                {(isNewChatMode || !runData) && (
                  <div className="chat-welcome-card">
                    <div className="welcome-eyebrow">PRISMA 2020 · Cochrane · GRADE</div>
                    <h2 className="welcome-title">
                      Ask a Clinical Research Question
                    </h2>
                    <p className="welcome-desc">
                      Enter your clinical question below or select an example. The agent will
                      automatically search medical databases, remove duplicates, screen abstracts,
                      extract study data, run meta-analysis, and generate your report and PDF.
                    </p>

                    <div className="preset-cards-grid">
                      {CLINICAL_PRESETS.map((p, idx) => (
                        <div
                          key={idx}
                          className="preset-card"
                          onClick={() => setComposerText(p.question)}
                        >
                          <div className="preset-card-title">
                            <span>{p.label}</span>
                            <span style={{ color: '#0284c7', fontSize: '11px' }}>Select →</span>
                          </div>
                          <div className="preset-card-text">{p.question}</div>
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {/* Chat Conversation for Selected Study */}
                {!isNewChatMode && runData && (
                  <>
                    {/* User Question Bubble */}
                    <div className="msg-row-user">
                      <div className="msg-bubble-user">
                        <div className="msg-user-label">Clinical Question</div>
                        <div className="msg-user-text">{runData.question}</div>
                      </div>
                    </div>

                    {/* Agent Response Bubble */}
                    <div className="msg-row-agent">
                      <div className="msg-card-agent">
                        <div className="msg-agent-header">
                          <div className="msg-agent-identity">
                            <div className="agent-avatar">AI</div>
                            <div>
                              <div style={{ fontWeight: 700, fontSize: '14px', color: '#0f2537' }}>
                                SRMA Clinical Synthesis
                              </div>
                              <div style={{ fontSize: '11.5px', color: '#64748b' }}>
                                Run ID: {runData.run_id} · {runData.created_at}
                              </div>
                            </div>
                          </div>
                          <div>{getGradeBadge(grade.certainty)}</div>
                        </div>

                        <div className="msg-agent-body">
                          {/* Direct Clinical Answer */}
                          <div className="chat-takeaway-banner">
                            <div
                              style={{
                                fontSize: '11px',
                                fontWeight: 700,
                                textTransform: 'uppercase',
                                letterSpacing: '0.06em',
                                color: '#1e3a8a',
                                marginBottom: '4px',
                              }}
                            >
                              Clinical Conclusion
                            </div>
                            <div
                              style={{
                                fontSize: '14.5px',
                                fontWeight: 600,
                                color: '#0f172a',
                                lineHeight: '1.55',
                              }}
                            >
                              {grade.summary_statement ||
                                (meta.k >= 1 && primaryPool.effect !== undefined
                                  ? `Across k = ${meta.k} quantitative comparative study/studies (${includedStudies.length} total included studies: ${pooledStudies.length} pooled + ${unpooledIncludedStudies.length} unpooled), the ${measureLabel} was ${formatNum(
                                      primaryPool.effect,
                                      2
                                    )} (95% CI [${formatNum(primaryPool.ci_low, 2)}, ${formatNum(
                                      primaryPool.ci_high,
                                      2
                                    )}], p = ${formatPValue(
                                      primaryPool.p_value
                                    )}), with heterogeneity I² = ${formatNum(
                                      het.I2,
                                      1
                                    )}% and ${grade.certainty} GRADE certainty.`
                                  : `A total of ${includedStudies.length} studies met inclusion criteria (${pooledStudies.length} pooled in meta-analysis, ${unpooledIncludedStudies.length} qualitative/unpooled). Click "View Full Analysis" below to inspect all study details and audit logs.`)}
                            </div>
                          </div>

                          {/* 4 Simple Key Numbers (Clickable to jump straight to that report table) */}
                          <div className="chat-kpi-grid">
                            <div
                              className="chat-kpi-box"
                              style={{ cursor: 'pointer' }}
                              title="Click to inspect removed duplicates"
                              onClick={() => {
                                setViewMode('analysis')
                                setActiveTab('audit')
                                setAuditSubTab('duplicates')
                              }}
                            >
                              <div className="chat-kpi-label">Articles Found</div>
                              <div className="chat-kpi-val">{prisma.identified_total ?? 0}</div>
                              <div className="chat-kpi-sub" style={{ color: '#0284c7' }}>
                                {prisma.duplicates_removed ?? duplicateRecords.length} duplicates
                                removed →
                              </div>
                            </div>

                            <div
                              className="chat-kpi-box"
                              style={{ cursor: 'pointer' }}
                              title="Click to inspect excluded articles"
                              onClick={() => {
                                setViewMode('analysis')
                                setActiveTab('audit')
                                setAuditSubTab('excluded')
                              }}
                            >
                              <div className="chat-kpi-label">Abstracts Screened</div>
                              <div className="chat-kpi-val">{prisma.records_screened ?? 0}</div>
                              <div className="chat-kpi-sub" style={{ color: '#0284c7' }}>
                                {excludedRecords.length} excluded · {includedStudies.length} included →
                              </div>
                            </div>

                            <div
                              className="chat-kpi-box"
                              style={{ cursor: 'pointer' }}
                              title="Click to inspect included studies"
                              onClick={() => {
                                setViewMode('analysis')
                                setActiveTab('studies')
                              }}
                            >
                              <div className="chat-kpi-label">Included Studies</div>
                              <div className="chat-kpi-val">k = {includedStudies.length}</div>
                              <div className="chat-kpi-sub" style={{ color: '#0284c7' }}>
                                {pooledStudies.length} pooled · {unpooledIncludedStudies.length}{' '}
                                unpooled →
                              </div>
                            </div>

                            <div
                              className="chat-kpi-box"
                              style={{ cursor: 'pointer' }}
                              title="Click to inspect meta-analysis & GRADE"
                              onClick={() => {
                                setViewMode('analysis')
                                setActiveTab('meta')
                              }}
                            >
                              <div className="chat-kpi-label">Pooled {measureLabel}</div>
                              <div className="chat-kpi-val">
                                {meta.k >= 1 && primaryPool.effect !== undefined
                                  ? `${formatNum(primaryPool.effect, 2)}`
                                  : 'Qualitative'}
                              </div>
                              <div className="chat-kpi-sub" style={{ color: '#0284c7' }}>
                                {meta.k >= 1 && primaryPool.ci_low !== undefined
                                  ? `95% CI [${formatNum(primaryPool.ci_low, 2)}, ${formatNum(
                                      primaryPool.ci_high,
                                      2
                                    )}] →`
                                  : 'See Table 1 in Full Analysis →'}
                              </div>
                            </div>
                          </div>

                          {/* Quick Included Study Links in Chat View */}
                          {includedStudies.length > 0 && (
                            <div
                              style={{
                                marginBottom: '16px',
                                padding: '12px 14px',
                                background: '#f8fafc',
                                border: '1px solid #e2e8f0',
                                borderRadius: '8px',
                              }}
                            >
                              <div
                                style={{
                                  fontSize: '11.5px',
                                  fontWeight: 700,
                                  textTransform: 'uppercase',
                                  letterSpacing: '0.05em',
                                  color: '#475569',
                                  marginBottom: '8px',
                                }}
                              >
                                Included Study Reports (k = {includedStudies.length}:{' '}
                                {pooledStudies.length} Pooled + {unpooledIncludedStudies.length}{' '}
                                Unpooled) — Click Any Study to Verify Source
                              </div>
                              <div style={{ display: 'flex', flexWrap: 'wrap', gap: '6px' }}>
                                {includedStudies.map((st, idx) => {
                                  const studyHref = resolveStudyUrl(st)
                                  const isPooled = Boolean(studyStatMap[st.study_id])
                                  return (
                                    <a
                                      key={st.study_id || idx}
                                      href={studyHref || '#'}
                                      target="_blank"
                                      rel="noreferrer"
                                      className="ext-link-badge"
                                      title={`${st.title} (${isPooled ? 'Pooled in Meta-Analysis' : 'Approved Unpooled'})`}
                                      style={{ padding: '4px 8px', fontSize: '11.5px' }}
                                    >
                                      [{idx + 1}] {st.study_id}{' '}
                                      {isPooled ? '✓' : '(Unpooled)'} ↗
                                    </a>
                                  )
                                })}
                              </div>
                            </div>
                          )}

                          {/* Forest & Funnel Plots Preview if available */}
                          {meta.k >= 1 && (
                            <div className="plots-grid">
                              <div className="plot-card">
                                <div
                                  style={{
                                    fontWeight: 700,
                                    fontSize: '12.5px',
                                    marginBottom: '6px',
                                    color: '#0f2537',
                                  }}
                                >
                                  Forest Plot ({measureLabel})
                                </div>
                                <div
                                  className="plot-img-wrapper"
                                  onClick={() =>
                                    setLightboxImage({
                                      url: `/api/runs/${runData.run_id}/plot/forest`,
                                      title: `Forest Plot (${runData.run_id})`,
                                    })
                                  }
                                >
                                  <img
                                    src={`/api/runs/${runData.run_id}/plot/forest`}
                                    alt="Forest Plot"
                                  />
                                </div>
                              </div>

                              <div className="plot-card">
                                <div
                                  style={{
                                    fontWeight: 700,
                                    fontSize: '12.5px',
                                    marginBottom: '6px',
                                    color: '#0f2537',
                                  }}
                                >
                                  Funnel Plot (Publication Bias)
                                </div>
                                <div
                                  className="plot-img-wrapper"
                                  onClick={() =>
                                    setLightboxImage({
                                      url: `/api/runs/${runData.run_id}/plot/funnel`,
                                      title: `Funnel Plot (${runData.run_id})`,
                                    })
                                  }
                                >
                                  <img
                                    src={`/api/runs/${runData.run_id}/plot/funnel`}
                                    alt="Funnel Plot"
                                  />
                                </div>
                              </div>
                            </div>
                          )}
                        </div>

                        {/* Clean Action Bar: View Full Analysis + Download PDF + Markdown Report */}
                        <div className="msg-agent-footer">
                          <button
                            type="button"
                            className="btn-full-analysis-cta"
                            onClick={() => {
                              setActiveTab('overview')
                              setViewMode('analysis')
                            }}
                          >
                            📊 View Full Analysis & Study Details →
                          </button>

                          <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                            <a
                              href={`/api/runs/${runData.run_id}/markdown`}
                              target="_blank"
                              rel="noreferrer"
                              className="btn-export-secondary"
                            >
                              📄 Full Text Report (.md) ↗
                            </a>
                            <a
                              href={`/api/runs/${runData.run_id}/pdf`}
                              target="_blank"
                              rel="noreferrer"
                              className="btn-pdf-primary"
                            >
                              ⬇ Download PDF Report
                            </a>
                          </div>
                        </div>
                      </div>
                    </div>
                  </>
                )}

                <div ref={chatEndRef} />
              </div>
            </div>

            {/* SIMPLE, CLEAN CHAT INPUT BAR (NO TECHNICAL OPTIONS) */}
            <footer className="chat-composer-bar">
              <div className="chat-composer-inner">
                <form onSubmit={handleSendQuery}>
                  <div className="composer-box">
                    <textarea
                      className="composer-textarea"
                      rows={2}
                      value={composerText}
                      onChange={(e) => setComposerText(e.target.value)}
                      onKeyDown={(e) => {
                        if (e.key === 'Enter' && !e.shiftKey) {
                          e.preventDefault()
                          handleSendQuery(e)
                        }
                      }}
                      placeholder="Ask a clinical question to run a Systematic Review & Meta-Analysis..."
                    />
                    <button
                      type="submit"
                      className="btn-send-chat"
                      disabled={!composerText.trim() || submitting}
                    >
                      {submitting ? 'Starting...' : 'Send →'}
                    </button>
                  </div>
                </form>
              </div>
            </footer>
          </div>
        )}

        {/* ===================================================================
            VIEW 2: FULL ANALYSIS PAGE (OPENED WHEN CLICKING "VIEW FULL ANALYSIS")
           =================================================================== */}
        {viewMode === 'analysis' && runData && (
          <div className="full-analysis-scroll">
            <header className="manuscript-header">
              <div className="journal-eyebrow-row">
                <div className="journal-classification">
                  <span>SYSTEMATIC REVIEW & META-ANALYSIS</span>
                  <span>•</span>
                  <span>PRISMA 2020</span>
                  <span>•</span>
                  <span style={{ fontFamily: 'var(--font-mono)', color: '#475569' }}>
                    {runData.run_id}
                  </span>
                </div>
                <div style={{ display: 'flex', gap: '8px', alignItems: 'center' }}>
                  <a
                    href={`/api/runs/${runData.run_id}/markdown`}
                    target="_blank"
                    rel="noreferrer"
                    className="ext-link-badge"
                  >
                    📄 Full Markdown Report ↗
                  </a>
                  <a
                    href={`/api/runs/${runData.run_id}/pdf`}
                    target="_blank"
                    rel="noreferrer"
                    className="ext-link-badge"
                  >
                    📕 Full PDF Manuscript ↗
                  </a>
                  <span style={{ fontSize: '12px', color: '#64748b' }}>
                    Generated: {runData.created_at || '2026'}
                  </span>
                </div>
              </div>

              <div className="manuscript-title-row">
                <div>
                  <h1 className="manuscript-title">{pico.title || runData.question}</h1>
                </div>
              </div>
            </header>

            {/* 4 CLEAN CLINICAL SECTIONS */}
            <nav className="tabs-bar">
              <button
                className={`tab-btn ${activeTab === 'overview' ? 'active' : ''}`}
                onClick={() => setActiveTab('overview')}
              >
                1. Abstract, PICO & PRISMA Flow
              </button>
              <button
                className={`tab-btn ${activeTab === 'studies' ? 'active' : ''}`}
                onClick={() => setActiveTab('studies')}
              >
                2. Included Studies & Risk of Bias ({includedStudies.length})
              </button>
              <button
                className={`tab-btn ${activeTab === 'meta' ? 'active' : ''}`}
                onClick={() => setActiveTab('meta')}
              >
                3. Meta-Analysis ({pooledStudies.length} Pooled), Plots & GRADE
              </button>
              <button
                className={`tab-btn ${activeTab === 'audit' ? 'active' : ''}`}
                onClick={() => setActiveTab('audit')}
              >
                4. Excluded ({excludedRecords.length}), Unpooled ({enrichedUnpooledRecords.length}) &
                Duplicates ({prisma.duplicates_removed ?? duplicateRecords.length})
              </button>
            </nav>

            <div className="workspace-body">
              {/* SECTION 1: OVERVIEW, PICO & PRISMA FLOW */}
              {activeTab === 'overview' && (
                <>
                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div className="panel-title">Structured Abstract</div>
                    </div>
                    <div className="panel-body">
                      <div className="abstract-box">
                        <div className="abstract-section">
                          <span className="abstract-label">Background & Objective:</span>
                          Evaluates: <em>&ldquo;{runData.question}&rdquo;</em> in{' '}
                          <strong>{pico.population || 'target patients'}</strong> comparing{' '}
                          <strong>{pico.intervention || 'intervention'}</strong> against{' '}
                          <strong>{pico.comparator || 'comparator'}</strong> for{' '}
                          <strong>{pico.primary_outcome || 'primary outcome'}</strong>.
                        </div>
                        <div className="abstract-section">
                          <span className="abstract-label">Methods:</span>
                          Searched PubMed, Europe PMC, ClinicalTrials.gov, and OpenAlex (
                          <strong>{prisma.identified_total ?? 0}</strong> records identified,{' '}
                          <strong>{prisma.duplicates_removed ?? duplicateRecords.length}</strong>{' '}
                          duplicates removed →{' '}
                          <strong>
                            {(prisma.identified_total ?? 0) -
                              (prisma.duplicates_removed ?? duplicateRecords.length)}
                          </strong>{' '}
                          unique records). Dual-model screening by MedGemma and Gemini evaluated{' '}
                          <strong>{prisma.records_screened ?? 0}</strong> abstracts (agreement{' '}
                          {formatNum((screeningStats.raw_agreement || 0) * 100, 1)}%).
                        </div>
                        <div className="abstract-section">
                          <span className="abstract-label">Results & Conclusion:</span>
                          Included <strong>k = {includedStudies.length} studies</strong> (
                          <strong>{pooledStudies.length} pooled</strong> in quantitative 2×2
                          meta-analysis, <strong>{unpooledIncludedStudies.length} unpooled</strong>{' '}
                          in qualitative synthesis).{' '}
                          {meta.k >= 1 && primaryPool.effect !== undefined
                            ? `Pooled ${measureLabel} = ${formatNum(
                                primaryPool.effect,
                                2
                              )} (95% CI [${formatNum(primaryPool.ci_low, 2)}, ${formatNum(
                                primaryPool.ci_high,
                                2
                              )}], p = ${formatPValue(primaryPool.p_value)}, I² = ${formatNum(
                                het.I2,
                                1
                              )}%). `
                            : ''}
                          GRADE Certainty: <strong>{grade.certainty || 'N/A'}</strong>.{' '}
                          {grade.summary_statement || ''}
                        </div>
                      </div>
                    </div>
                  </section>

                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div className="panel-title">PICOS Protocol & Eligibility Criteria</div>
                    </div>
                    <div className="panel-body">
                      <div className="table-container">
                        <table className="clinical-table">
                          <tbody>
                            <tr>
                              <td style={{ width: '200px' }}>
                                <strong>Population (P)</strong>
                              </td>
                              <td>{pico.population || '—'}</td>
                            </tr>
                            <tr>
                              <td>
                                <strong>Intervention (I)</strong>
                              </td>
                              <td>{pico.intervention || '—'}</td>
                            </tr>
                            <tr>
                              <td>
                                <strong>Comparator (C)</strong>
                              </td>
                              <td>{pico.comparator || '—'}</td>
                            </tr>
                            <tr>
                              <td>
                                <strong>Primary Outcome (O)</strong>
                              </td>
                              <td>{pico.primary_outcome || '—'}</td>
                            </tr>
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </section>

                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div className="panel-title">
                        PRISMA 2020 Study Selection Flow & Exact Mathematical Accounting
                      </div>
                    </div>
                    <div className="panel-body">
                      <div className="prisma-grid">
                        <div className="prisma-row">
                          <div className="prisma-stage-tag">1. Identified</div>
                          <div className="prisma-box-main">
                            <div className="prisma-count">
                              {prisma.identified_total ?? 0} Total Records Retrieved
                            </div>
                            <div style={{ fontSize: '12px', color: '#334155', marginTop: '4px' }}>
                              {Object.entries(prisma.identified_per_source || {})
                                .map(
                                  ([src, cnt]) =>
                                    `${src}: ${typeof cnt === 'object' ? cnt.count ?? 0 : cnt}`
                                )
                                .join(' + ')}{' '}
                              = <strong>{prisma.identified_total ?? 0}</strong>
                            </div>
                            <div style={{ fontSize: '12px', color: '#0f2537', marginTop: '4px' }}>
                              Math: <strong>{prisma.identified_total ?? 0}</strong> Identified −{' '}
                              <strong>
                                {prisma.duplicates_removed ?? duplicateRecords.length}
                              </strong>{' '}
                              Duplicates Removed ={' '}
                              <strong>
                                {(prisma.identified_total ?? 0) -
                                  (prisma.duplicates_removed ?? duplicateRecords.length)}
                              </strong>{' '}
                              Unique Records
                            </div>
                          </div>
                          <div
                            className="prisma-box-side"
                            style={{ cursor: 'pointer' }}
                            onClick={() => {
                              setActiveTab('audit')
                              setAuditSubTab('duplicates')
                            }}
                          >
                            <strong>Duplicates Removed:</strong>{' '}
                            {prisma.duplicates_removed ?? duplicateRecords.length}{' '}
                            <span style={{ color: '#0284c7', fontWeight: 600 }}>
                              (View All {duplicateRecords.length} →)
                            </span>
                          </div>
                        </div>

                        <div className="prisma-row">
                          <div className="prisma-stage-tag">2. Screened</div>
                          <div className="prisma-box-main">
                            <div className="prisma-count">
                              {prisma.records_screened ?? 0} Top-Ranked Abstracts Screened
                            </div>
                            <div style={{ fontSize: '12px', color: '#0f2537', marginTop: '4px' }}>
                              Math: <strong>{prisma.records_screened ?? 0}</strong> Screened −{' '}
                              <strong>{excludedRecords.length}</strong> Excluded at Screening ={' '}
                              <strong>{includedStudies.length}</strong> Included Studies
                            </div>
                          </div>
                          <div
                            className="prisma-box-side"
                            style={{ cursor: 'pointer' }}
                            onClick={() => {
                              setActiveTab('audit')
                              setAuditSubTab('excluded')
                            }}
                          >
                            <strong>Excluded at Screening:</strong> {excludedRecords.length}{' '}
                            <span style={{ color: '#0284c7', fontWeight: 600 }}>
                              (View All {excludedRecords.length} →)
                            </span>
                          </div>
                        </div>

                        <div className="prisma-row">
                          <div className="prisma-stage-tag">3. Included</div>
                          <div
                            className="prisma-box-main"
                            style={{
                              borderColor: '#166534',
                              background: '#f0fdf4',
                              cursor: 'pointer',
                            }}
                            onClick={() => setActiveTab('studies')}
                          >
                            <div className="prisma-count" style={{ color: '#166534' }}>
                              k = {includedStudies.length} Included Studies — Inspect Table 1 →
                            </div>
                            <div style={{ fontSize: '12px', color: '#14532d', marginTop: '4px' }}>
                              Math: <strong>{includedStudies.length}</strong> Included ={' '}
                              <strong>{pooledStudies.length}</strong> Pooled in 2×2 Meta-Analysis +{' '}
                              <strong>{unpooledIncludedStudies.length}</strong> Approved Unpooled
                              (Qualitative)
                            </div>
                          </div>
                          <div
                            className="prisma-box-side"
                            style={{ cursor: 'pointer' }}
                            onClick={() => {
                              setActiveTab('audit')
                              setAuditSubTab('unpooled')
                            }}
                          >
                            <strong>Approved Unpooled:</strong> {enrichedUnpooledRecords.length}{' '}
                            <span style={{ color: '#0284c7', fontWeight: 600 }}>
                              (Why Not Pooled →)
                            </span>
                          </div>
                        </div>
                      </div>
                    </div>
                  </section>
                </>
              )}

              {/* SECTION 2: INCLUDED STUDIES (TABLE 1) & COCHRANE ROB 2.0 */}
              {activeTab === 'studies' && (
                <>
                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div>
                        <div className="panel-title">
                          Table 1. Included Studies & Extracted Clinical Evidence (Total k ={' '}
                          {includedStudies.length}: {pooledStudies.length} Pooled in Meta-Analysis +{' '}
                          {unpooledIncludedStudies.length} Unpooled)
                        </div>
                      </div>
                    </div>
                    <div className="panel-body">
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th style={{ width: '45px' }}>#</th>
                              <th style={{ width: '300px' }}>Study & Verification Links</th>
                              <th>Intervention (Events / Total)</th>
                              <th>Control (Events / Total)</th>
                              <th style={{ width: '250px' }}>
                                {measureLabel} [95% CI] / Pooling Status
                              </th>
                              <th>RoB 2.0</th>
                              <th>Inclusion Reason & Proof</th>
                            </tr>
                          </thead>
                          <tbody>
                            {includedStudies.map((st, idx) => {
                              const hasArmNumbers =
                                st.events_treatment !== null &&
                                st.events_treatment !== undefined &&
                                st.n_treatment !== null &&
                                st.n_treatment !== undefined
                              const stat = studyStatMap[st.study_id] || {}
                              const isPooled = stat.effect !== undefined
                              const studyHref = resolveStudyUrl(st)
                              const unpObj =
                                unpooledReasonMap[st.study_id] || unpooledReasonMap[st.raw_id] || {}
                              const unpooledWhy =
                                st.unpooled_reason ||
                                unpObj.unpooled_reason ||
                                (hasArmNumbers &&
                                (Number(st.events_treatment) > Number(st.n_treatment) ||
                                  Number(st.events_control) > Number(st.n_control))
                                  ? `Events exceed arm total (${st.events_treatment}/${st.n_treatment}, ${st.events_control}/${st.n_control}).`
                                  : 'Requires n_events and n_total in both arms; one or more were missing.')
                              return (
                                <tr key={st.study_id || idx}>
                                  <td style={{ fontFamily: 'var(--font-mono)', fontWeight: 700 }}>
                                    [{idx + 1}]
                                  </td>
                                  <td>
                                    <div style={{ fontWeight: 700 }}>
                                      {studyHref ? (
                                        <a
                                          href={studyHref}
                                          target="_blank"
                                          rel="noreferrer"
                                          style={{ color: '#0f2537', textDecoration: 'underline' }}
                                        >
                                          {st.study_id} ↗
                                        </a>
                                      ) : (
                                        st.study_id
                                      )}
                                    </div>
                                    <div style={{ fontSize: '12px', color: '#334155' }}>
                                      {studyHref ? (
                                        <a
                                          href={studyHref}
                                          target="_blank"
                                          rel="noreferrer"
                                          style={{ color: '#334155', textDecoration: 'none' }}
                                        >
                                          {st.title}
                                        </a>
                                      ) : (
                                        st.title
                                      )}
                                    </div>
                                    <VerificationBadges item={st} />
                                  </td>
                                  <td style={{ fontFamily: 'var(--font-mono)' }}>
                                    {hasArmNumbers
                                      ? `${st.events_treatment} / ${st.n_treatment}`
                                      : st.effect_Point_estimate || 'Single-Arm / Qualitative'}
                                  </td>
                                  <td style={{ fontFamily: 'var(--font-mono)' }}>
                                    {hasArmNumbers &&
                                    st.events_control !== null &&
                                    st.events_control !== undefined
                                      ? `${st.events_control} / ${st.n_control}`
                                      : '—'}
                                  </td>
                                  <td>
                                    {isPooled ? (
                                      <div>
                                        <div
                                          style={{
                                            fontFamily: 'var(--font-mono)',
                                            fontWeight: 700,
                                            color: '#0f2537',
                                          }}
                                        >
                                          {formatNum(stat.effect, 2)} [{formatNum(stat.ci_low, 2)},{' '}
                                          {formatNum(stat.ci_high, 2)}]
                                        </div>
                                        <div style={{ marginTop: '4px' }}>
                                          <span className="badge badge-low">
                                            ✓ Pooled
                                            {stat.weight_random_pct
                                              ? ` (${formatNum(stat.weight_random_pct, 1)}% wt)`
                                              : ''}
                                          </span>
                                        </div>
                                      </div>
                                    ) : (
                                      <div>
                                        <span className="badge badge-warn">
                                          Not Pooled (Qualitative)
                                        </span>
                                        <div
                                          style={{
                                            fontSize: '11.5px',
                                            color: '#9a3412',
                                            marginTop: '5px',
                                            lineHeight: '1.4',
                                          }}
                                        >
                                          <strong>Why not pooled:</strong> {unpooledWhy}
                                        </div>
                                        <button
                                          type="button"
                                          onClick={() => {
                                            setActiveTab('audit')
                                            setAuditSubTab('unpooled')
                                          }}
                                          style={{
                                            marginTop: '4px',
                                            background: 'none',
                                            border: 'none',
                                            padding: 0,
                                            color: '#0284c7',
                                            fontSize: '11px',
                                            fontWeight: 600,
                                            cursor: 'pointer',
                                            textDecoration: 'underline',
                                          }}
                                        >
                                          View Unpooled Audit Log →
                                        </button>
                                      </div>
                                    )}
                                  </td>
                                  <td>{getRobBadge(st.rob_overall)}</td>
                                  <td style={{ fontSize: '12px' }}>
                                    <div>{st.reviewer_a_reason}</div>
                                    {st.verbatim_quote && (
                                      <div className="verbatim-quote">
                                        &ldquo;{st.verbatim_quote}&rdquo;
                                      </div>
                                    )}
                                  </td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </section>

                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div className="panel-title">
                        Cochrane Risk of Bias 2.0 (RoB 2) Domain Matrix
                      </div>
                    </div>
                    <div className="panel-body">
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th>Study</th>
                              <th className="rob-cell">D1: Randomization</th>
                              <th className="rob-cell">D2: Deviations</th>
                              <th className="rob-cell">D3: Missing Data</th>
                              <th className="rob-cell">D4: Measurement</th>
                              <th className="rob-cell">D5: Selection</th>
                              <th className="rob-cell">Overall</th>
                            </tr>
                          </thead>
                          <tbody>
                            {robList.map((r, i) => {
                              const doms = r.domains || []
                              const getDom = (idx) =>
                                doms[idx]?.judgment || doms[idx]?.rating || 'Some concerns'
                              const robHref = resolveStudyUrl(r)
                              return (
                                <tr key={i}>
                                  <td>
                                    <strong>
                                      {robHref ? (
                                        <a
                                          href={robHref}
                                          target="_blank"
                                          rel="noreferrer"
                                          style={{ color: '#0f2537', textDecoration: 'underline' }}
                                        >
                                          {r.study_id} ↗
                                        </a>
                                      ) : (
                                        r.study_id
                                      )}
                                    </strong>
                                    <VerificationBadges item={r} />
                                  </td>
                                  <td className="rob-cell">{getRobBadge(getDom(0))}</td>
                                  <td className="rob-cell">{getRobBadge(getDom(1))}</td>
                                  <td className="rob-cell">{getRobBadge(getDom(2))}</td>
                                  <td className="rob-cell">{getRobBadge(getDom(3))}</td>
                                  <td className="rob-cell">{getRobBadge(getDom(4))}</td>
                                  <td className="rob-cell">{getRobBadge(r.overall_judgment)}</td>
                                </tr>
                              )
                            })}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </section>
                </>
              )}

              {/* SECTION 3: META-ANALYSIS, PLOTS & GRADE */}
              {activeTab === 'meta' && (
                <>
                  {meta.k >= 1 ? (
                    <section className="clinical-panel">
                      <div className="panel-header">
                        <div className="panel-title">
                          Forest Plot & Funnel Plot (Pooled Studies: {pooledStudies.length} of{' '}
                          {includedStudies.length} Included)
                        </div>
                        <span className="badge badge-info">
                          {measureLabel}: {formatNum(primaryPool.effect, 2)} (95% CI [
                          {formatNum(primaryPool.ci_low, 2)}, {formatNum(primaryPool.ci_high, 2)}], p ={' '}
                          {formatPValue(primaryPool.p_value)})
                        </span>
                      </div>
                      <div className="panel-body">
                        {unpooledIncludedStudies.length > 0 && (
                          <div
                            style={{
                              padding: '10px 14px',
                              marginBottom: '14px',
                              background: '#fffbeb',
                              border: '1px solid #fde68a',
                              borderRadius: '8px',
                              fontSize: '12.5px',
                              color: '#92400e',
                              display: 'flex',
                              justifyContent: 'space-between',
                              alignItems: 'center',
                              flexWrap: 'wrap',
                              gap: '8px',
                            }}
                          >
                            <span>
                              <strong>Statistical Pooling Note:</strong>{' '}
                              <strong>{pooledStudies.length}</strong> of{' '}
                              <strong>{includedStudies.length}</strong> included studies reported
                              valid two-arm binary event counts (<code>n_events / n_total</code>)
                              and are plotted below. The remaining{' '}
                              <strong>{unpooledIncludedStudies.length}</strong> included studies did
                              not report two-arm binary event data and are synthesized qualitatively.
                            </span>
                            <button
                              className="audit-subtab-btn"
                              style={{ padding: '4px 10px', fontSize: '11.5px' }}
                              onClick={() => {
                                setActiveTab('audit')
                                setAuditSubTab('unpooled')
                              }}
                            >
                              Inspect {unpooledIncludedStudies.length} Unpooled Studies →
                            </button>
                          </div>
                        )}
                        <div className="plots-grid">
                          <div className="plot-card">
                            <strong style={{ marginBottom: '8px', fontSize: '13px' }}>
                              Figure 1. Forest Plot ({measureLabel}, k = {meta.k})
                            </strong>
                            <div
                              className="plot-img-wrapper"
                              onClick={() =>
                                setLightboxImage({
                                  url: `/api/runs/${runData.run_id}/plot/forest`,
                                  title: `Forest Plot (${runData.run_id})`,
                                })
                              }
                            >
                              <img
                                src={`/api/runs/${runData.run_id}/plot/forest`}
                                alt="Forest Plot"
                              />
                            </div>
                          </div>

                          <div className="plot-card">
                            <strong style={{ marginBottom: '8px', fontSize: '13px' }}>
                              Figure 2. Funnel Plot (k = {meta.k})
                            </strong>
                            <div
                              className="plot-img-wrapper"
                              onClick={() =>
                                setLightboxImage({
                                  url: `/api/runs/${runData.run_id}/plot/funnel`,
                                  title: `Funnel Plot (${runData.run_id})`,
                                })
                              }
                            >
                              <img
                                src={`/api/runs/${runData.run_id}/plot/funnel`}
                                alt="Funnel Plot"
                              />
                            </div>
                          </div>
                        </div>
                      </div>
                    </section>
                  ) : (
                    <section className="clinical-panel">
                      <div className="panel-header">
                        <div className="panel-title">Forest Plot & Funnel Plot</div>
                        <span className="badge badge-amber">
                          Quantitative Pooling Skipped (k = 0 with 2×2 Binary Data)
                        </span>
                      </div>
                      <div className="panel-body">
                        <div
                          style={{
                            padding: '16px',
                            background: '#fffbeb',
                            border: '1px solid #fde68a',
                            borderRadius: '8px',
                            color: '#92400e',
                            fontSize: '13px',
                            lineHeight: '1.6',
                          }}
                        >
                          <strong>Why No Forest or Funnel Plot Was Generated:</strong> None of the{' '}
                          <strong>{includedStudies.length}</strong> included studies reported
                          complete two-arm binary event counts (<code>n_events / n_total</code> in
                          both Intervention and Control arms) in their abstracts. In accordance with
                          Cochrane methodology, the agent never fabricates or imputes missing arm
                          counts; all {includedStudies.length} studies are retained in the
                          qualitative synthesis.
                          <div style={{ marginTop: '10px' }}>
                            <button
                              className="audit-subtab-btn active"
                              onClick={() => {
                                setActiveTab('audit')
                                setAuditSubTab('unpooled')
                              }}
                            >
                              View Exact Unpooling Reasons for All {unpooledIncludedStudies.length}{' '}
                              Studies →
                            </button>
                          </div>
                        </div>
                      </div>
                    </section>
                  )}

                  <section className="clinical-panel">
                    <div className="panel-header">
                      <div className="panel-title">GRADE Summary of Findings</div>
                      <div>{getGradeBadge(grade.certainty)}</div>
                    </div>
                    <div className="panel-body">
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th>GRADE Domain</th>
                              <th>Status</th>
                              <th>Downgrade</th>
                              <th>Justification</th>
                            </tr>
                          </thead>
                          <tbody>
                            {(grade.domains || []).map((d, i) => (
                              <tr key={i}>
                                <td>
                                  <strong>{d.domain}</strong>
                                </td>
                                <td>{d.status}</td>
                                <td style={{ fontFamily: 'var(--font-mono)' }}>{d.downgrade}</td>
                                <td>{d.rationale}</td>
                              </tr>
                            ))}
                          </tbody>
                        </table>
                      </div>
                    </div>
                  </section>
                </>
              )}

              {/* SECTION 4: EXCLUDED & DUPLICATE ARTICLES LOG */}
              {activeTab === 'audit' && (
                <section className="clinical-panel">
                  <div className="panel-header">
                    <div>
                      <div className="panel-title">
                        Complete Transparency Log: Excluded, Unpooled & Duplicate Articles
                      </div>
                      <div style={{ fontSize: '12px', color: '#475569', marginTop: '4px' }}>
                        <strong>Exact PRISMA Math:</strong>{' '}
                        {prisma.records_screened ?? 0} Screened ={' '}
                        <strong>{excludedRecords.length} Excluded at Screening</strong> +{' '}
                        <strong>{includedStudies.length} Included Studies</strong> (
                        {pooledStudies.length} Pooled in Meta-Analysis +{' '}
                        {unpooledIncludedStudies.length} Unpooled in Table 1) ·{' '}
                        <strong>
                          {prisma.duplicates_removed ?? duplicateRecords.length} Duplicates Removed
                        </strong>{' '}
                        before screening
                      </div>
                    </div>
                    <div style={{ display: 'flex', gap: '8px', flexWrap: 'wrap' }}>
                      <button
                        type="button"
                        className={`btn-export-secondary ${
                          auditSubTab === 'excluded' ? 'btn-pdf-primary' : ''
                        }`}
                        onClick={() => setAuditSubTab('excluded')}
                      >
                        Excluded Articles ({excludedRecords.length})
                      </button>
                      <button
                        type="button"
                        className={`btn-export-secondary ${
                          auditSubTab === 'unpooled' ? 'btn-pdf-primary' : ''
                        }`}
                        onClick={() => setAuditSubTab('unpooled')}
                      >
                        Approved Unpooled ({enrichedUnpooledRecords.length})
                      </button>
                      <button
                        type="button"
                        className={`btn-export-secondary ${
                          auditSubTab === 'duplicates' ? 'btn-pdf-primary' : ''
                        }`}
                        onClick={() => setAuditSubTab('duplicates')}
                      >
                        Removed Duplicates ({duplicateRecords.length})
                      </button>
                    </div>
                  </div>

                  <div className="panel-body">
                    <div className="filter-bar">
                      <input
                        type="text"
                        className="search-input"
                        placeholder="Search by article title, ID, or reason..."
                        value={auditSearch}
                        onChange={(e) => setAuditSearch(e.target.value)}
                      />
                    </div>

                    {auditSubTab === 'excluded' && (
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th style={{ width: '50px' }}>#</th>
                              <th style={{ width: '340px' }}>Article & Verification Link</th>
                              <th style={{ width: '180px' }}>Reason Category</th>
                              <th>Exact Exclusion Rationale</th>
                            </tr>
                          </thead>
                          <tbody>
                            {excludedRecords
                              .filter((r) => {
                                if (!auditSearch.trim()) return true
                                const q = auditSearch.toLowerCase()
                                return (
                                  (r.title || '').toLowerCase().includes(q) ||
                                  (r.final_reason || '').toLowerCase().includes(q) ||
                                  (r.id || '').toLowerCase().includes(q)
                                )
                              })
                              .map((r, idx) => {
                                const exHref = resolveStudyUrl(r)
                                return (
                                  <tr key={idx}>
                                    <td>{idx + 1}</td>
                                    <td>
                                      <div style={{ fontWeight: 600 }}>
                                        {exHref ? (
                                          <a
                                            href={exHref}
                                            target="_blank"
                                            rel="noreferrer"
                                            style={{ color: '#0f2537', textDecoration: 'underline' }}
                                          >
                                            {r.title} ↗
                                          </a>
                                        ) : (
                                          r.title
                                        )}
                                      </div>
                                      <VerificationBadges item={r} />
                                    </td>
                                    <td>
                                      <span className="badge badge-high">{r.final_reason}</span>
                                    </td>
                                    <td>{r.reviewer_a_reason}</td>
                                  </tr>
                                )
                              })}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {auditSubTab === 'unpooled' && (
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th style={{ width: '80px' }}># / Ref</th>
                              <th style={{ width: '320px' }}>
                                Approved Study & Verification Links
                              </th>
                              <th style={{ width: '220px' }}>Extracted Arm Counts</th>
                              <th>Why Included in Review</th>
                              <th>Why Not Pooled in 2×2 Meta-Analysis</th>
                            </tr>
                          </thead>
                          <tbody>
                            {enrichedUnpooledRecords
                              .filter((r) => {
                                if (!auditSearch.trim()) return true
                                const q = auditSearch.toLowerCase()
                                return (
                                  (r.title || '').toLowerCase().includes(q) ||
                                  (r.study_id || '').toLowerCase().includes(q) ||
                                  (r.unpooled_reason || '').toLowerCase().includes(q)
                                )
                              })
                              .map((r, idx) => {
                                const unpHref = resolveStudyUrl(r)
                                return (
                                  <tr key={idx}>
                                    <td style={{ fontFamily: 'var(--font-mono)' }}>
                                      <div>
                                        <strong>#{idx + 1}</strong>
                                      </div>
                                      {r.table1_index && (
                                        <span
                                          className="badge badge-neutral"
                                          style={{ fontSize: '10px', marginTop: '3px' }}
                                        >
                                          Table 1: [{r.table1_index}]
                                        </span>
                                      )}
                                    </td>
                                    <td>
                                      {r.study_id && (
                                        <div style={{ fontWeight: 700, fontSize: '12.5px' }}>
                                          {unpHref ? (
                                            <a
                                              href={unpHref}
                                              target="_blank"
                                              rel="noreferrer"
                                              style={{
                                                color: '#0f2537',
                                                textDecoration: 'underline',
                                              }}
                                            >
                                              {r.study_id} ↗
                                            </a>
                                          ) : (
                                            r.study_id
                                          )}
                                        </div>
                                      )}
                                      <div style={{ fontSize: '12px', color: '#334155' }}>
                                        {unpHref ? (
                                          <a
                                            href={unpHref}
                                            target="_blank"
                                            rel="noreferrer"
                                            style={{ color: '#334155', textDecoration: 'none' }}
                                          >
                                            {r.title}
                                          </a>
                                        ) : (
                                          r.title
                                        )}
                                      </div>
                                      <VerificationBadges item={r} />
                                    </td>
                                    <td
                                      style={{
                                        fontFamily: 'var(--font-mono)',
                                        fontSize: '11.5px',
                                        color: '#334155',
                                      }}
                                    >
                                      {r.extracted_arms || 'Single-Arm / Qualitative'}
                                    </td>
                                    <td style={{ fontSize: '12px' }}>
                                      {r.reviewer_a_reason ||
                                        'Met PICO inclusion criteria during dual-reviewer screening'}
                                    </td>
                                    <td style={{ fontSize: '12px' }}>
                                      {r.reason_code && (
                                        <div style={{ marginBottom: '4px' }}>
                                          <span className="badge badge-warn">{r.reason_code}</span>
                                        </div>
                                      )}
                                      <div style={{ fontWeight: 600, color: '#9a3412' }}>
                                        {r.unpooled_reason}
                                      </div>
                                    </td>
                                  </tr>
                                )
                              })}
                          </tbody>
                        </table>
                      </div>
                    )}

                    {auditSubTab === 'duplicates' && (
                      <div className="table-container">
                        <table className="clinical-table">
                          <thead>
                            <tr>
                              <th style={{ width: '50px' }}>#</th>
                              <th>Removed Duplicate Citation</th>
                              <th>Match Method</th>
                              <th>Merged Into Canonical Record</th>
                            </tr>
                          </thead>
                          <tbody>
                            {duplicateRecords
                              .filter((d) => {
                                if (!auditSearch.trim()) return true
                                const q = auditSearch.toLowerCase()
                                return (
                                  (d.removed_title || '').toLowerCase().includes(q) ||
                                  (d.kept_title || '').toLowerCase().includes(q) ||
                                  (d.match_type || '').toLowerCase().includes(q)
                                )
                              })
                              .map((d, idx) => {
                                const remItem = {
                                  id: d.kept_id,
                                  title: d.removed_title,
                                  pmid: d.removed_pmid,
                                  doi: d.removed_doi,
                                  nct_id: d.removed_nct_id,
                                  source: d.removed_source,
                                  url: d.removed_url,
                                }
                                const keptItem = {
                                  id: d.kept_id,
                                  title: d.removed_title,
                                  pmid: d.kept_pmid,
                                  doi: d.kept_doi,
                                  nct_id: d.kept_nct_id,
                                  source: d.kept_source,
                                  url: d.kept_url,
                                }
                                const remHref = resolveStudyUrl(remItem)
                                const keptHref = resolveStudyUrl(keptItem)
                                return (
                                  <tr key={idx}>
                                    <td>{idx + 1}</td>
                                    <td>
                                      <div style={{ fontWeight: 600 }}>
                                        {remHref ? (
                                          <a
                                            href={remHref}
                                            target="_blank"
                                            rel="noreferrer"
                                            style={{ color: '#0f2537', textDecoration: 'underline' }}
                                          >
                                            {d.removed_title} ↗
                                          </a>
                                        ) : (
                                          d.removed_title
                                        )}
                                      </div>
                                      <VerificationBadges item={remItem} />
                                    </td>
                                    <td>
                                      <span className="badge badge-neutral">{d.match_type}</span>
                                    </td>
                                    <td>
                                      <div style={{ fontWeight: 600 }}>
                                        {keptHref ? (
                                          <a
                                            href={keptHref}
                                            target="_blank"
                                            rel="noreferrer"
                                            style={{ color: '#0f2537', textDecoration: 'underline' }}
                                          >
                                            {d.kept_title} ↗
                                          </a>
                                        ) : (
                                          d.kept_title
                                        )}
                                      </div>
                                      <VerificationBadges item={keptItem} />
                                    </td>
                                  </tr>
                                )
                              })}
                          </tbody>
                        </table>
                      </div>
                    )}
                  </div>
                </section>
              )}
            </div>
          </div>
        )}
      </main>

      {/* IMAGE ZOOM MODAL */}
      {lightboxImage && (
        <div className="lightbox-backdrop" onClick={() => setLightboxImage(null)}>
          <div className="lightbox-content" onClick={(e) => e.stopPropagation()}>
            <div
              style={{
                display: 'flex',
                justifyContent: 'space-between',
                alignItems: 'center',
                marginBottom: '12px',
              }}
            >
              <strong>{lightboxImage.title}</strong>
              <button
                type="button"
                className="btn-export-secondary"
                onClick={() => setLightboxImage(null)}
              >
                Close ✕
              </button>
            </div>
            <img
              src={lightboxImage.url}
              alt={lightboxImage.title}
              style={{ maxWidth: '88vw', maxHeight: '80vh', display: 'block' }}
            />
          </div>
        </div>
      )}
    </div>
  )
}
