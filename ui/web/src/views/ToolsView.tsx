import { useState, useEffect } from 'react'
import { Play, AlertTriangle, Shield, ChevronDown, ChevronUp } from 'lucide-react'
import { useStore } from '../store/useStore'

interface Tool {
    name: string
    risk: string
    description: string
    require_grant: boolean
    deny_in_replay: boolean
    budget: { calls_per_turn: number; bytes_per_turn: number }
    schema: Record<string, unknown>
}

export function ToolsView() {
    const { sessionId } = useStore()
    const [tools, setTools] = useState<Tool[]>([])
    const [expanded, setExpanded] = useState<string | null>(null)
    const [runForm, setRunForm] = useState<{ tool: string; args: string } | null>(null)
    const [result, setResult] = useState<Record<string, unknown> | null>(null)

    useEffect(() => {
        fetch('/api/tools')
            .then((r) => r.json())
            .then((d) => setTools(d.tools || []))
    }, [])

    const runTool = async () => {
        if (!runForm) return
        try {
            const args = JSON.parse(runForm.args || '{}')
            const res = await fetch('/api/tools/run', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    tool: runForm.tool,
                    arguments: args,
                    session_id: sessionId,
                }),
            })
            setResult(await res.json())
        } catch (e) {
            setResult({ error: String(e) })
        }
    }

    const riskColor = (risk: string) => {
        switch (risk) {
            case 'low': return 'text-green-500 bg-green-50 dark:bg-green-900/20'
            case 'medium': return 'text-yellow-500 bg-yellow-50 dark:bg-yellow-900/20'
            case 'high': return 'text-red-500 bg-red-50 dark:bg-red-900/20'
            default: return 'text-slate-500 bg-slate-50'
        }
    }

    return (
        <div className="space-y-4">
            <h2 className="text-lg font-semibold">Tool Registry ({tools.length})</h2>

            <div className="grid gap-2">
                {tools.map((tool) => (
                    <div
                        key={tool.name}
                        className="bg-slate-50 dark:bg-slate-800 rounded-lg overflow-hidden"
                    >
                        {/* Header */}
                        <button
                            onClick={() => setExpanded(expanded === tool.name ? null : tool.name)}
                            className="w-full p-4 flex items-center justify-between text-left"
                        >
                            <div className="flex items-center gap-3">
                                <code className="font-medium">{tool.name}</code>
                                <span className={`px-2 py-0.5 rounded text-xs ${riskColor(tool.risk)}`}>
                                    {tool.risk}
                                </span>
                                {tool.require_grant && (
                                    <Shield size={14} className="text-yellow-500" />
                                )}
                                {tool.deny_in_replay && (
                                    <AlertTriangle size={14} className="text-red-400" />
                                )}
                            </div>
                            {expanded === tool.name ? <ChevronUp size={18} /> : <ChevronDown size={18} />}
                        </button>

                        {/* Expanded */}
                        {expanded === tool.name && (
                            <div className="px-4 pb-4 space-y-3 border-t border-slate-200 dark:border-slate-700 pt-3">
                                <p className="text-sm text-slate-600 dark:text-slate-400">
                                    {tool.description}
                                </p>

                                <div className="text-xs space-y-1">
                                    <div>Budget: {tool.budget.calls_per_turn} calls/turn</div>
                                    {tool.budget.bytes_per_turn > 0 && (
                                        <div>Bytes: {(tool.budget.bytes_per_turn / 1024).toFixed(0)}KB/turn</div>
                                    )}
                                </div>

                                {/* Run Form */}
                                <div className="mt-4 space-y-2">
                                    <textarea
                                        placeholder='{"arg": "value"}'
                                        className="w-full p-2 text-xs font-mono bg-white dark:bg-slate-900 border border-slate-200 dark:border-slate-700 rounded"
                                        rows={3}
                                        value={runForm?.tool === tool.name ? runForm.args : ''}
                                        onChange={(e) => setRunForm({ tool: tool.name, args: e.target.value })}
                                    />
                                    <button
                                        onClick={() => {
                                            setRunForm({ tool: tool.name, args: runForm?.args || '{}' })
                                            runTool()
                                        }}
                                        className="flex items-center gap-2 px-3 py-1.5 bg-primary-500 text-white rounded text-sm"
                                    >
                                        <Play size={14} /> Run
                                    </button>
                                </div>

                                {result && runForm?.tool === tool.name && (
                                    <pre className="mt-2 p-2 bg-slate-900 text-green-400 rounded text-xs overflow-auto max-h-40">
                                        {JSON.stringify(result, null, 2)}
                                    </pre>
                                )}
                            </div>
                        )}
                    </div>
                ))}
            </div>
        </div>
    )
}
