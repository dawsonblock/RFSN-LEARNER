import { useState, useEffect } from 'react'
import { Play, Square, Circle, Radio } from 'lucide-react'
import { useStore } from '../store/useStore'

type ReplayMode = 'off' | 'record' | 'replay'

export function ReplayView() {
    const { sessionId } = useStore()
    const [mode, setMode] = useState<ReplayMode>('off')
    const [loading, setLoading] = useState(false)

    const fetchMode = async () => {
        if (!sessionId) return
        const res = await fetch(`/api/replay/mode?session_id=${sessionId}`)
        const data = await res.json()
        setMode(data.mode || 'off')
    }

    useEffect(() => {
        fetchMode()
    }, [sessionId])

    const changeMode = async (newMode: ReplayMode) => {
        setLoading(true)
        await fetch(`/api/replay/mode?session_id=${sessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ mode: newMode }),
        })
        setMode(newMode)
        setLoading(false)
    }

    const modes: Array<{ id: ReplayMode; label: string; icon: typeof Play; color: string }> = [
        { id: 'off', label: 'Off', icon: Square, color: 'slate' },
        { id: 'record', label: 'Record', icon: Circle, color: 'red' },
        { id: 'replay', label: 'Replay', icon: Play, color: 'green' },
    ]

    return (
        <div className="space-y-6">
            <h2 className="text-lg font-semibold flex items-center gap-2">
                <Radio size={20} /> Replay Mode
            </h2>

            <div className="grid grid-cols-3 gap-4">
                {modes.map(({ id, label, icon: Icon, color }) => (
                    <button
                        key={id}
                        onClick={() => changeMode(id)}
                        disabled={loading}
                        className={`
              p-6 rounded-xl flex flex-col items-center gap-3 transition
              ${mode === id
                                ? `bg-${color}-100 dark:bg-${color}-900/30 ring-2 ring-${color}-500`
                                : 'bg-slate-50 dark:bg-slate-800 hover:bg-slate-100 dark:hover:bg-slate-700'
                            }
            `}
                    >
                        <Icon
                            size={32}
                            className={mode === id ? `text-${color}-500` : 'text-slate-400'}
                        />
                        <span className={`font-medium ${mode === id ? `text-${color}-700 dark:text-${color}-300` : ''}`}>
                            {label}
                        </span>
                    </button>
                ))}
            </div>

            <div className="bg-slate-50 dark:bg-slate-800 rounded-lg p-4">
                <h3 className="font-medium mb-2">Current Mode</h3>
                <p className="text-slate-600 dark:text-slate-400 text-sm">
                    {mode === 'off' && 'Normal execution mode. Actions are executed live.'}
                    {mode === 'record' && 'Recording mode. Actions are executed and recorded for replay.'}
                    {mode === 'replay' && 'Replay mode. Actions return cached results. Destructive tools are blocked.'}
                </p>
            </div>
        </div>
    )
}
