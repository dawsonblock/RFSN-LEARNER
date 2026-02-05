import { useState, useEffect } from 'react'
import { Gauge, RefreshCw } from 'lucide-react'
import { useStore } from '../store/useStore'

interface Budgets {
    tool_calls: Record<string, number>
    bytes_used: Record<string, number>
    turn_number: number
}

export function BudgetsView() {
    const { sessionId } = useStore()
    const [budgets, setBudgets] = useState<Budgets | null>(null)

    const fetchBudgets = async () => {
        if (!sessionId) return
        const res = await fetch(`/api/budgets?session_id=${sessionId}`)
        setBudgets(await res.json())
    }

    useEffect(() => {
        fetchBudgets()
        const interval = setInterval(fetchBudgets, 2000)
        return () => clearInterval(interval)
    }, [sessionId])

    const entries = budgets
        ? Object.entries(budgets.tool_calls).map(([tool, calls]) => ({
            tool,
            calls,
            bytes: budgets.bytes_used[tool] || 0,
        }))
        : []

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Gauge size={20} /> Budget Usage
                </h2>
                <button
                    onClick={fetchBudgets}
                    title="Refresh budgets"
                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                    <RefreshCw size={18} />
                </button>
            </div>

            <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <div className="text-sm text-slate-500 mb-2">Turn Number</div>
                <div className="text-3xl font-bold">{budgets?.turn_number || 0}</div>
            </div>

            <div>
                <h3 className="font-medium mb-3">Per-Tool Usage This Turn</h3>
                {entries.length === 0 ? (
                    <div className="text-slate-400 text-center py-8">
                        No tool calls this turn
                    </div>
                ) : (
                    <div className="space-y-2">
                        {entries.map(({ tool, calls, bytes }) => (
                            <div
                                key={tool}
                                className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800 rounded-lg"
                            >
                                <code className="text-sm">{tool}</code>
                                <div className="flex items-center gap-4 text-sm">
                                    <span className="text-primary-500 font-medium">{calls} calls</span>
                                    {bytes > 0 && (
                                        <span className="text-slate-500">
                                            {bytes < 1024 ? `${bytes}B` : `${(bytes / 1024).toFixed(1)}KB`}
                                        </span>
                                    )}
                                </div>
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </div>
    )
}
