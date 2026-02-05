import { useState, useEffect } from 'react'
import { Globe, RefreshCw } from 'lucide-react'
import { useStore } from '../store/useStore'

interface WorldState {
    session_id: string
    cwd: string
    memory_db_path: string
    replay_mode: string
    enabled_tools: string[]
    granted_permissions: string[]
    created_at: string
}

export function WorldView() {
    const { sessionId } = useStore()
    const [world, setWorld] = useState<WorldState | null>(null)

    const fetchWorld = async () => {
        if (!sessionId) return
        const res = await fetch(`/api/world?session_id=${sessionId}`)
        setWorld(await res.json())
    }

    useEffect(() => {
        fetchWorld()
    }, [sessionId])

    if (!world) {
        return (
            <div className="text-center text-slate-400 py-8">
                Loading world state...
            </div>
        )
    }

    const items = [
        { label: 'Session ID', value: world.session_id },
        { label: 'Working Directory', value: world.cwd },
        { label: 'Memory DB', value: world.memory_db_path },
        { label: 'Replay Mode', value: world.replay_mode },
        { label: 'Created At', value: world.created_at },
        { label: 'Enabled Tools', value: `${world.enabled_tools?.length || 0} tools` },
        { label: 'Granted Permissions', value: `${world.granted_permissions?.length || 0} tools` },
    ]

    return (
        <div className="space-y-6">
            <div className="flex items-center justify-between">
                <h2 className="text-lg font-semibold flex items-center gap-2">
                    <Globe size={20} /> World State
                </h2>
                <button
                    onClick={fetchWorld}
                    title="Refresh world state"
                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                    <RefreshCw size={18} />
                </button>
            </div>

            <div className="grid gap-3">
                {items.map(({ label, value }) => (
                    <div
                        key={label}
                        className="flex items-center justify-between p-4 bg-slate-50 dark:bg-slate-800 rounded-lg"
                    >
                        <span className="text-slate-500">{label}</span>
                        <code className="text-sm bg-slate-100 dark:bg-slate-700 px-2 py-1 rounded">
                            {value}
                        </code>
                    </div>
                ))}
            </div>

            {/* Enabled Tools */}
            <div>
                <h3 className="font-medium mb-3">Enabled Tools</h3>
                <div className="flex flex-wrap gap-2">
                    {world.enabled_tools?.map((tool) => (
                        <code
                            key={tool}
                            className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-1 rounded"
                        >
                            {tool}
                        </code>
                    ))}
                </div>
            </div>
        </div>
    )
}
