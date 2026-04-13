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

        {/* Opportunities table */}
        {filtered.length > 0 ? (
          <div style={{ overflowX: 'auto' }}>
            <table style={styles.table}>
              <thead>
                <tr>
                  <th style={styles.th}>Sport</th>
                  <th style={styles.th}>Event</th>
                  <th style={styles.th}>Prediction Mkt</th>
                  <th style={styles.th}>Sportsbook</th>
                  <th style={styles.th}>Edge</th>
                  <th style={styles.th}>EV / $1</th>
                  <th style={{ ...styles.th, minWidth: '300px' }}>Recommendation</th>
                </tr>
              </thead>
              <tbody>
                {filtered.map((opp, idx) => {
                  const sc = SPORT_COLORS[opp.sport] || SPORT_COLORS.nfl
                  const ec = EDGE_COLORS[opp.category] || EDGE_COLORS.minimal
                  return (
                    <tr
                      key={opp.id + idx}
                      style={{
                        background: idx % 2 === 0 ? 'transparent' : '#0d132108',
                      }}
                      onMouseEnter={e => e.currentTarget.style.background = '#1e293b40'}
                      onMouseLeave={e => e.currentTarget.style.background = idx % 2 === 0 ? 'transparent' : '#0d132108'}
                    >
                      <td style={styles.td}>
                        <span style={{
                          ...styles.sportBadge,
                          background: sc.bg,
                          color: sc.color,
                        }}>
                          {opp.sport.toUpperCase()}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <div style={{ fontWeight: 600, marginBottom: '2px' }}>
                          {opp.event}
                        </div>
                        {opp.event_date && (
                          <div style={{ color: '#64748b', fontSize: '12px' }}>
                            {new Date(opp.event_date).toLocaleDateString()}
                          </div>
                        )}
                      </td>
                      <td style={styles.td}>
                        <div style={{ fontWeight: 600 }}>
                          {opp.prediction_market?.platform?.toUpperCase()}
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '13px' }}>
                          {opp.prediction_market?.price_cents?.toFixed(0)}¢
                          ({(opp.prediction_market?.probability * 100)?.toFixed(1)}%)
                        </div>
                        {opp.prediction_market?.url && (
                          <a href={opp.prediction_market.url} target="_blank" rel="noopener" style={styles.platformLink}>
                            View →
                          </a>
                        )}
                      </td>
                      <td style={styles.td}>
                        <div style={{ fontWeight: 600 }}>
                          {opp.sportsbook?.platform?.toUpperCase()}
                        </div>
                        <div style={{ color: '#94a3b8', fontSize: '13px' }}>
                          {opp.sportsbook?.american_odds > 0 ? '+' : ''}
                          {opp.sportsbook?.american_odds}
                          ({(opp.sportsbook?.probability * 100)?.toFixed(1)}%)
                        </div>
                        {opp.sportsbook?.url && (
                          <a href={opp.sportsbook.url} target="_blank" rel="noopener" style={styles.platformLink}>
                            View →
                          </a>
                        )}
                      </td>
                      <td style={styles.td}>
                        <span style={{
                          ...styles.edgeBadge,
                          background: ec.bg,
                          color: ec.color,
                        }}>
                          {opp.edge_percent > 0 ? '+' : ''}{opp.edge_percent.toFixed(1)}%
                        </span>
                      </td>
                      <td style={styles.td}>
                        <span style={{
                          color: opp.expected_value > 0 ? '#4ade80' : '#f87171',
                          fontWeight: 600,
                        }}>
                          {opp.expected_value > 0 ? '+' : ''}
                          ${opp.expected_value.toFixed(3)}
                        </span>
                      </td>
                      <td style={styles.td}>
                        <div style={styles.recommendation}>
                          {opp.recommendation}
                        </div>
                        <div style={styles.confidence}>
                          Match confidence: {(opp.match_confidence * 100).toFixed(0)}%
                        </div>
                      </td>
                    </tr>
                  )
                })}
              </tbody>
            </table>
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
