import React, { useState, useEffect, useCallback } from 'react'

/* ─── Styles ────────────────────────────────────────────────────────────────── */
const styles = {
  app: {
    minHeight: '100vh',
    background: '#0a0f1a',
    color: '#e2e8f0',
    fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
    margin: 0,
    padding: 0,
  },
  header: {
    background: '#111827',
    borderBottom: '1px solid #1e293b',
    padding: '16px 24px',
    display: 'flex',
    alignItems: 'center',
    justifyContent: 'space-between',
    flexWrap: 'wrap',
    gap: '12px',
  },
  logo: {
    display: 'flex',
    alignItems: 'center',
    gap: '10px',
  },
  logoIcon: {
    fontSize: '24px',
  },
  logoText: {
    fontSize: '20px',
    fontWeight: 700,
    color: '#f8fafc',
    letterSpacing: '-0.5px',
  },
  headerRight: {
    display: 'flex',
    alignItems: 'center',
    gap: '16px',
    flexWrap: 'wrap',
  },
  scanBtn: {
    background: '#2563eb',
    color: '#fff',
    border: 'none',
    padding: '8px 20px',
    borderRadius: '6px',
    fontSize: '14px',
    fontWeight: 600,
    cursor: 'pointer',
    display: 'flex',
    alignItems: 'center',
    gap: '6px',
    transition: 'background 0.15s',
  },
  scanBtnDisabled: {
    background: '#1e3a5f',
    cursor: 'not-allowed',
    opacity: 0.7,
  },
  scanTime: {
    color: '#64748b',
    fontSize: '13px',
  },
  main: {
    maxWidth: '1400px',
    margin: '0 auto',
    padding: '20px 24px',
  },
  filterBar: {
    display: 'flex',
    gap: '8px',
    marginBottom: '20px',
    flexWrap: 'wrap',
    alignItems: 'center',
  },
  filterChip: {
    padding: '6px 14px',
    borderRadius: '20px',
    border: '1px solid #334155',
    background: 'transparent',
    color: '#94a3b8',
    fontSize: '13px',
    fontWeight: 500,
    cursor: 'pointer',
    transition: 'all 0.15s',
  },
  filterChipActive: {
    background: '#1e3a5f',
    borderColor: '#2563eb',
    color: '#60a5fa',
  },
  edgeFilter: {
    marginLeft: 'auto',
    display: 'flex',
    alignItems: 'center',
    gap: '8px',
    color: '#64748b',
    fontSize: '13px',
  },
  edgeInput: {
    width: '60px',
    padding: '4px 8px',
    borderRadius: '4px',
    border: '1px solid #334155',
    background: '#1e293b',
    color: '#e2e8f0',
    fontSize: '13px',
    textAlign: 'center',
  },
  statsRow: {
    display: 'flex',
    gap: '16px',
    marginBottom: '20px',
    flexWrap: 'wrap',
  },
  statCard: {
    background: '#111827',
    border: '1px solid #1e293b',
    borderRadius: '8px',
    padding: '14px 20px',
    minWidth: '140px',
    flex: 1,
  },
  statLabel: {
    color: '#64748b',
    fontSize: '12px',
    fontWeight: 500,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    marginBottom: '4px',
  },
  statValue: {
    fontSize: '24px',
    fontWeight: 700,
  },
  table: {
    width: '100%',
    borderCollapse: 'collapse',
    background: '#111827',
    borderRadius: '8px',
    overflow: 'hidden',
    border: '1px solid #1e293b',
  },
  th: {
    padding: '12px 16px',
    textAlign: 'left',
    color: '#64748b',
    fontSize: '12px',
    fontWeight: 600,
    textTransform: 'uppercase',
    letterSpacing: '0.5px',
    borderBottom: '1px solid #1e293b',
    background: '#0d1321',
    cursor: 'pointer',
    userSelect: 'none',
  },
  td: {
    padding: '14px 16px',
    borderBottom: '1px solid #1e293b',
    fontSize: '14px',
    verticalAlign: 'top',
  },
  sportBadge: {
    display: 'inline-block',
    padding: '2px 8px',
    borderRadius: '4px',
    fontSize: '11px',
    fontWeight: 700,
    letterSpacing: '0.5px',
  },
  edgeBadge: {
    display: 'inline-block',
    padding: '4px 10px',
    borderRadius: '4px',
    fontWeight: 700,
    fontSize: '14px',
  },
  recommendation: {
    fontSize: '13px',
    lineHeight: '1.4',
    maxWidth: '400px',
  },
  confidence: {
    fontSize: '12px',
    color: '#64748b',
    marginTop: '4px',
  },
  emptyState: {
    textAlign: 'center',
    padding: '60px 20px',
    color: '#475569',
  },
  emptyIcon: {
    fontSize: '48px',
    marginBottom: '16px',
  },
  emptyTitle: {
    fontSize: '18px',
    fontWeight: 600,
    color: '#94a3b8',
    marginBottom: '8px',
  },
  errorBanner: {
    background: '#7f1d1d20',
    border: '1px solid #7f1d1d',
    borderRadius: '8px',
    padding: '12px 16px',
    marginBottom: '16px',
    color: '#fca5a5',
    fontSize: '13px',
  },
  platformLink: {
    color: '#60a5fa',
    textDecoration: 'none',
    fontSize: '12px',
  },
  spinner: {
    display: 'inline-block',
    width: '14px',
    height: '14px',
    border: '2px solid #ffffff40',
    borderTopColor: '#fff',
    borderRadius: '50%',
    animation: 'spin 0.6s linear infinite',
  },
}

const SPORT_COLORS = {
  nfl: { bg: '#164e1e', color: '#4ade80' },
  nba: { bg: '#7c2d12', color: '#fb923c' },
  mlb: { bg: '#1e3a5f', color: '#60a5fa' },
  nhl: { bg: '#312e81', color: '#a78bfa' },
  epl: { bg: '#581c87', color: '#c084fc' },
}

const EDGE_COLORS = {
  strong: { bg: '#14532d', color: '#4ade80' },
  moderate: { bg: '#713f12', color: '#fbbf24' },
  slight: { bg: '#1e293b', color: '#94a3b8' },
  minimal: { bg: '#1e293b', color: '#64748b' },
}

function formatTime(iso) {
  if (!iso) return 'Never'
  const d = new Date(iso)
  return d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

function Spinner() {
  return (
    <>
      <style>{`@keyframes spin { to { transform: rotate(360deg); } }`}</style>
      <span style={styles.spinner} />
    </>
  )
}

export default function App() {
  const [opportunities, setOpportunities] = useState([])
  const [meta, setMeta] = useState(null)
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  const [sportFilter, setSportFilter] = useState('all')
  const [minEdge, setMinEdge] = useState(1)
  const [lastScan, setLastScan] = useState(null)

  const sports = ['all', 'nfl', 'nba', 'mlb', 'nhl', 'epl']

  const scan = useCallback(async () => {
    setLoading(true)
    setError(null)
    try {
      const params = new URLSearchParams()
      if (sportFilter !== 'all') params.set('sport', sportFilter)
      params.set('min_edge', minEdge.toString())

      const res = await fetch(`/api/scan?${params}`)
      const data = await res.json()

      if (data.error) {
        setError(data.error)
      } else {
        setOpportunities(data.opportunities || [])
        setMeta(data.meta || null)
        setLastScan(data.meta?.scan_time)
      }
    } catch (err) {
      setError(`Network error: ${err.message}`)
    } finally {
      setLoading(false)
    }
  }, [sportFilter, minEdge])

  // Filter locally
  const filtered = opportunities.filter(o => {
    if (sportFilter !== 'all' && o.sport !== sportFilter) return false
    if (Math.abs(o.edge_percent) < minEdge) return false
    return true
  })

  const strongCount = filtered.filter(o => o.category === 'strong').length
  const bestEdge = filtered.length > 0
    ? Math.max(...filtered.map(o => Math.abs(o.edge_percent)))
    : 0

  return (
    <div style={styles.app}>
      {/* Header */}
      <header style={styles.header}>
        <div style={styles.logo}>
          <span style={styles.logoIcon}>⚡</span>
          <span style={styles.logoText}>Sports Arb Finder</span>
        </div>
        <div style={styles.headerRight}>
          <span style={styles.scanTime}>
            Last scan: {lastScan ? formatTime(lastScan) : 'None'}
          </span>
          <button
            style={{
              ...styles.scanBtn,
              ...(loading ? styles.scanBtnDisabled : {}),
            }}
            onClick={scan}
            disabled={loading}
            onMouseEnter={e => !loading && (e.target.style.background = '#1d4ed8')}
            onMouseLeave={e => !loading && (e.target.style.background = '#2563eb')}
          >
            {loading ? <><Spinner /> Scanning...</> : 'Scan Now'}
          </button>
        </div>
      </header>

      <main style={styles.main}>
        {/* Error banner */}
        {error && (
          <div style={styles.errorBanner}>
            {error}
            {meta?.errors?.map((e, i) => <div key={i}>{e}</div>)}
          </div>
        )}

        {/* Filter bar */}
        <div style={styles.filterBar}>
          {sports.map(s => (
            <button
              key={s}
              style={{
                ...styles.filterChip,
                ...(sportFilter === s ? styles.filterChipActive : {}),
              }}
              onClick={() => setSportFilter(s)}
            >
              {s === 'all' ? 'All Sports' : s.toUpperCase()}
            </button>
          ))}
          <div style={styles.edgeFilter}>
            Min edge:
            <input
              type="number"
              style={styles.edgeInput}
              value={minEdge}
              onChange={e => setMinEdge(parseFloat(e.target.value) || 0)}
              min="0"
              step="0.5"
            />
            %
          </div>
        </div>

        {/* Stats row */}
        {meta && (
          <div style={styles.statsRow}>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Opportunities</div>
              <div style={{ ...styles.statValue, color: '#60a5fa' }}>
                {filtered.length}
              </div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Strong Edges</div>
              <div style={{ ...styles.statValue, color: '#4ade80' }}>
                {strongCount}
              </div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Best Edge</div>
              <div style={{ ...styles.statValue, color: '#fbbf24' }}>
                {bestEdge.toFixed(1)}%
              </div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Markets Scanned</div>
              <div style={{ ...styles.statValue, color: '#94a3b8' }}>
                {(meta.prediction_markets_fetched || 0) + (meta.sportsbooks_fetched || 0)}
              </div>
            </div>
            <div style={styles.statCard}>
              <div style={styles.statLabel}>Events Matched</div>
              <div style={{ ...styles.statValue, color: '#94a3b8' }}>
                {meta.events_matched || 0}
              </div>
            </div>
          </div>
        )}

        {/* Opportunities */}
        {filtered.length > 0 ? (
          <div style={{ display: 'flex', flexDirection: 'column', gap: '12px' }}>
            {filtered.map((opp, idx) => {
                  const sc = SPORT_COLORS[opp.sport] || SPORT_COLORS.nfl
                  const ec = EDGE_COLORS[opp.category] || EDGE_COLORS.minimal
                  const isPositive = opp.edge_percent > 0
                  return (
                    <div
                      key={opp.id + idx}
                      style={{
                        background: '#111827',
                        border: `1px solid ${isPositive ? '#16532940' : '#7f1d1d30'}`,
                        borderLeft: `4px solid ${ec.color}`,
                        borderRadius: '8px',
                        padding: '16px 20px',
                      }}
                    >
                      {/* Top row: sport badge, event name, edge */}
                      <div style={{ display: 'flex', alignItems: 'flex-start', justifyContent: 'space-between', marginBottom: '12px', gap: '12px', flexWrap: 'wrap' }}>
                        <div style={{ flex: 1 }}>
                          <div style={{ display: 'flex', alignItems: 'center', gap: '8px', marginBottom: '4px' }}>
                            <span style={{
                              ...styles.sportBadge,
                              background: sc.bg,
                              color: sc.color,
                            }}>
                              {opp.sport.toUpperCase()}
                            </span>
                            <span style={{ fontSize: '15px', fontWeight: 700, color: '#f1f5f9' }}>
                              {opp.event}
                            </span>
                          </div>
                          <div style={{ color: '#64748b', fontSize: '12px' }}>
                            {opp.prediction_market?.raw_name}
                          </div>
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', gap: '12px', flexShrink: 0 }}>
                          <span style={{
                            ...styles.edgeBadge,
                            background: ec.bg,
                            color: ec.color,
                            fontSize: '16px',
                          }}>
                            {opp.edge_percent > 0 ? '+' : ''}{opp.edge_percent.toFixed(1)}% edge
                          </span>
                          <span style={{
                            color: opp.expected_value > 0 ? '#4ade80' : '#f87171',
                            fontWeight: 700,
                            fontSize: '14px',
                          }}>
                            {opp.expected_value > 0 ? '+' : ''}${opp.expected_value.toFixed(2)} EV/$1
                          </span>
                        </div>
                      </div>

                      {/* Odds comparison row */}
                      <div style={{ display: 'flex', gap: '16px', marginBottom: '14px', flexWrap: 'wrap' }}>
                        <div style={{ background: '#0d1321', borderRadius: '6px', padding: '10px 14px', flex: 1, minWidth: '180px' }}>
                          <div style={{ color: '#64748b', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
                            {opp.prediction_market?.platform?.toUpperCase()}
                          </div>
                          <div style={{ fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
                            {opp.prediction_market?.price_cents?.toFixed(0)}¢
                            <span style={{ fontSize: '14px', fontWeight: 400, color: '#94a3b8', marginLeft: '6px' }}>
                              ({(opp.prediction_market?.probability * 100)?.toFixed(1)}% implied)
                            </span>
                          </div>
                          {opp.prediction_market?.url && (
                            <a href={opp.prediction_market.url} target="_blank" rel="noopener" style={{ ...styles.platformLink, marginTop: '4px', display: 'inline-block' }}>
                              Open on {opp.prediction_market?.platform?.charAt(0).toUpperCase() + opp.prediction_market?.platform?.slice(1)} →
                            </a>
                          )}
                        </div>
                        <div style={{ display: 'flex', alignItems: 'center', color: '#475569', fontSize: '18px', padding: '0 4px' }}>vs</div>
                        <div style={{ background: '#0d1321', borderRadius: '6px', padding: '10px 14px', flex: 1, minWidth: '180px' }}>
                          <div style={{ color: '#64748b', fontSize: '11px', fontWeight: 600, textTransform: 'uppercase', letterSpacing: '0.5px', marginBottom: '4px' }}>
                            {opp.sportsbook?.platform?.toUpperCase()} — {opp.sportsbook?.selection}
                          </div>
                          <div style={{ fontSize: '20px', fontWeight: 700, color: '#e2e8f0' }}>
                            {opp.sportsbook?.american_odds > 0 ? '+' : ''}{opp.sportsbook?.american_odds}
                            <span style={{ fontSize: '14px', fontWeight: 400, color: '#94a3b8', marginLeft: '6px' }}>
                              ({(opp.sportsbook?.probability * 100)?.toFixed(1)}% implied)
                            </span>
                          </div>
                          {opp.sportsbook?.url && (
                            <a href={opp.sportsbook.url} target="_blank" rel="noopener" style={{ ...styles.platformLink, marginTop: '4px', display: 'inline-block' }}>
                              Open on {opp.sportsbook?.platform?.charAt(0).toUpperCase() + opp.sportsbook?.platform?.slice(1)} →
                            </a>
                          )}
                        </div>
                      </div>

                      {/* Recommendation — the main action */}
                      <div style={{
                        background: isPositive ? '#052e1620' : '#2d0a0a20',
                        border: `1px solid ${isPositive ? '#16532930' : '#7f1d1d25'}`,
                        borderRadius: '6px',
                        padding: '12px 14px',
                        fontSize: '13px',
                        lineHeight: '1.5',
                        color: '#cbd5e1',
                      }}>
                        <span style={{ fontWeight: 700, color: isPositive ? '#4ade80' : '#fbbf24', marginRight: '6px' }}>
                          {isPositive ? 'ACTION — BUY YES:' : 'ACTION — BUY NO:'}
                        </span>
                        {opp.recommendation}
                      </div>
                    </div>
                  )
                })}
          </div>
        ) : (
          <div style={styles.emptyState}>
            <div style={styles.emptyIcon}>⚡</div>
            <div style={styles.emptyTitle}>
              {loading ? 'Scanning platforms...' : 'No opportunities yet'}
            </div>
            <div>
              {loading
                ? 'Fetching odds from Kalshi, Polymarket, DraftKings, and FanDuel...'
                : 'Hit "Scan Now" to fetch live odds and find arbitrage opportunities.'}
            </div>
          </div>
        )}

        {/* Footer */}
        <div style={{ textAlign: 'center', color: '#334155', fontSize: '12px', padding: '32px 0 16px' }}>
          Sports Arb Finder — Odds change rapidly. Always verify before placing bets.
          <br />
          Data from Kalshi, Polymarket, DraftKings, and FanDuel.
        </div>
      </main>
    </div>
  )
}
