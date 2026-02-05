import { useState, useEffect } from 'react'
import { CheckCircle, XCircle, RefreshCw, Shield } from 'lucide-react'
import { useStore } from '../store/useStore'

interface LedgerEntry {
    idx: number
    ts_utc: string
    decision: string
    entry_hash: string
    prev_entry_hash: string
    payload: {
        action: { kind: string; tool: string }
        decision: string
    }
}

export function LedgerView() {
    const { sessionId } = useStore()
    const [entries, setEntries] = useState<LedgerEntry[]>([])
    const [loading, setLoading] = useState(false)
    const [verified, setVerified] = useState<boolean | null>(null)
    const [filter, setFilter] = useState<'all' | 'allow' | 'deny'>('all')

    const fetchLedger = async () => {
        if (!sessionId) return
        setLoading(true)
        try {
            const res = await fetch(`/api/ledger/${sessionId}`)
            const data = await res.json()
            setEntries(data.entries || [])
        } catch {
            setEntries([])
        } finally {
            setLoading(false)
        }
    }

    const verifyChain = async () => {
        if (!sessionId) return
        try {
            const res = await fetch(`/api/ledger/${sessionId}/verify`)
            const data = await res.json()
            setVerified(data.valid)
        } catch {
            setVerified(false)
        }
    }

    useEffect(() => {
        fetchLedger()
    }, [sessionId])

    const filteredEntries = entries.filter((e) => {
        if (filter === 'all') return true
        return e.decision === filter
    })

    return (
        <div className="space-y-4">
            {/* Header */}
            <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                    <button
                        onClick={fetchLedger}
                        title="Refresh ledger"
                        className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                    >
                        <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                    </button>
                    <button
                        onClick={verifyChain}
                        className="flex items-center gap-2 px-3 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg text-sm"
                    >
                        <Shield size={16} />
                        Verify Chain
                    </button>
                    {verified !== null && (
                        <span className={`flex items-center gap-1 text-sm ${verified ? 'text-green-500' : 'text-red-500'}`}>
                            {verified ? <CheckCircle size={16} /> : <XCircle size={16} />}
                            {verified ? 'Valid' : 'Broken'}
                        </span>
                    )}
                </div>

                {/* Filter */}
                <div className="flex gap-2">
                    {(['all', 'allow', 'deny'] as const).map((f) => (
                        <button
                            key={f}
                            onClick={() => setFilter(f)}
                            className={`px-3 py-1.5 rounded-lg text-sm capitalize ${filter === f
                                ? 'bg-primary-500 text-white'
                                : 'bg-slate-100 dark:bg-slate-800'
                                }`}
                        >
                            {f}
                        </button>
                    ))}
                </div>
            </div>

            {/* Entries */}
            <div className="space-y-2">
                {filteredEntries.length === 0 ? (
                    <div className="text-center text-slate-400 py-8">
                        No ledger entries
                    </div>
                ) : (
                    filteredEntries.map((entry) => (
                        <div
                            key={entry.idx}
                            className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4"
                        >
                            <div className="flex items-center justify-between mb-2">
                                <div className="flex items-center gap-3">
                                    <span className="text-xs text-slate-400">#{entry.idx}</span>
                                    <code className="text-xs bg-slate-200 dark:bg-slate-700 px-2 py-0.5 rounded">
                                        {entry.payload?.action?.tool || 'unknown'}
                                    </code>
                                    <span
                                        className={`px-2 py-0.5 rounded-full text-xs font-medium ${entry.decision === 'allow'
                                            ? 'bg-green-100 text-green-700 dark:bg-green-900 dark:text-green-300'
                                            : 'bg-red-100 text-red-700 dark:bg-red-900 dark:text-red-300'
                                            }`}
                                    >
                                        {entry.decision}
                                    </span>
                                </div>
                                <span className="text-xs text-slate-400">{entry.ts_utc}</span>
                            </div>
                            <div className="text-xs text-slate-500 font-mono truncate">
                                hash: {entry.entry_hash.slice(0, 16)}...
                            </div>
                        </div>
                    ))
                )}
            </div>
        </div>
    )
}
