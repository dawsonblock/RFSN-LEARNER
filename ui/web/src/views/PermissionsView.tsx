import { useState, useEffect } from 'react'
import { Shield, Check, X, Plus, Minus } from 'lucide-react'
import { useStore } from '../store/useStore'

export function PermissionsView() {
    const { sessionId } = useStore()
    const [grantedTools, setGrantedTools] = useState<string[]>([])
    const [allTools, setAllTools] = useState<string[]>([])
    const [loading, setLoading] = useState(false)

    const fetchPerms = async () => {
        if (!sessionId) return
        const [permsRes, toolsRes] = await Promise.all([
            fetch(`/api/perms?session_id=${sessionId}`),
            fetch('/api/tools'),
        ])
        const perms = await permsRes.json()
        const tools = await toolsRes.json()
        setGrantedTools(perms.granted_tools || [])
        setAllTools((tools.tools || []).filter((t: { require_grant: boolean }) => t.require_grant).map((t: { name: string }) => t.name))
    }

    useEffect(() => {
        fetchPerms()
    }, [sessionId])

    const grant = async (tool: string) => {
        setLoading(true)
        await fetch(`/api/perms/grant?session_id=${sessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool }),
        })
        await fetchPerms()
        setLoading(false)
    }

    const revoke = async (tool: string) => {
        setLoading(true)
        await fetch(`/api/perms/revoke?session_id=${sessionId}`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ tool }),
        })
        await fetchPerms()
        setLoading(false)
    }

    return (
        <div className="space-y-6">
            <h2 className="text-lg font-semibold flex items-center gap-2">
                <Shield size={20} /> Permission Management
            </h2>

            {/* Granted */}
            <div>
                <h3 className="font-medium mb-3 flex items-center gap-2">
                    <Check size={16} className="text-green-500" /> Granted ({grantedTools.length})
                </h3>
                <div className="grid grid-cols-2 gap-2">
                    {grantedTools.map((tool) => (
                        <div
                            key={tool}
                            className="flex items-center justify-between p-3 bg-green-50 dark:bg-green-900/20 rounded-lg"
                        >
                            <code className="text-sm">{tool}</code>
                            <button
                                onClick={() => revoke(tool)}
                                disabled={loading}
                                title={`Revoke permission for ${tool}`}
                                className="p-1.5 hover:bg-red-100 dark:hover:bg-red-900/30 rounded text-red-500"
                            >
                                <Minus size={16} />
                            </button>
                        </div>
                    ))}
                    {grantedTools.length === 0 && (
                        <div className="col-span-2 text-slate-400 text-center py-4">
                            No permissions granted
                        </div>
                    )}
                </div>
            </div>

            {/* Available to Grant */}
            <div>
                <h3 className="font-medium mb-3 flex items-center gap-2">
                    <X size={16} className="text-slate-400" /> Available to Grant
                </h3>
                <div className="grid grid-cols-2 gap-2">
                    {allTools
                        .filter((t) => !grantedTools.includes(t))
                        .map((tool) => (
                            <div
                                key={tool}
                                className="flex items-center justify-between p-3 bg-slate-50 dark:bg-slate-800 rounded-lg"
                            >
                                <code className="text-sm">{tool}</code>
                                <button
                                    onClick={() => grant(tool)}
                                    disabled={loading}
                                    title={`Grant permission for ${tool}`}
                                    className="p-1.5 hover:bg-green-100 dark:hover:bg-green-900/30 rounded text-green-500"
                                >
                                    <Plus size={16} />
                                </button>
                            </div>
                        ))}
                </div>
            </div>
        </div>
    )
}
