import { Activity, CheckCircle, XCircle, AlertCircle, Zap } from 'lucide-react'
import type { SystemEvent } from '../store/useStore'

interface SystemPanelProps {
    events: SystemEvent[]
}

function EventIcon({ type }: { type: string }) {
    switch (type) {
        case 'agent_message':
            return <CheckCircle size={14} className="text-green-500" />
        case 'error':
            return <XCircle size={14} className="text-red-500" />
        case 'tool_call':
        case 'manual_tool_call':
            return <Zap size={14} className="text-blue-500" />
        case 'permission_granted':
        case 'permission_revoked':
            return <AlertCircle size={14} className="text-yellow-500" />
        default:
            return <Activity size={14} className="text-slate-400" />
    }
}

export function SystemPanel({ events }: SystemPanelProps) {
    const recentEvents = events.slice(-20).reverse()

    return (
        <aside className="w-72 bg-slate-50 dark:bg-slate-800 flex flex-col">
            {/* Header */}
            <div className="h-14 flex items-center px-4 border-b border-slate-200 dark:border-slate-700">
                <Activity size={18} className="mr-2 text-green-500" />
                <span className="font-semibold">Live System</span>
            </div>

            {/* Events List */}
            <div className="flex-1 overflow-auto p-3">
                {recentEvents.length === 0 ? (
                    <div className="text-center text-slate-400 text-sm py-8">
                        No events yet
                    </div>
                ) : (
                    <div className="space-y-2">
                        {recentEvents.map((event) => (
                            <div
                                key={event.id}
                                className="bg-white dark:bg-slate-700 rounded-lg p-2.5 text-xs animate-fade-in"
                            >
                                <div className="flex items-center gap-2 mb-1">
                                    <EventIcon type={event.type} />
                                    <span className="font-medium capitalize">
                                        {event.type.replace(/_/g, ' ')}
                                    </span>
                                    <span className="ml-auto text-slate-400">
                                        {new Date(event.ts).toLocaleTimeString()}
                                    </span>
                                </div>
                                {event.content && (
                                    <p className="text-slate-500 dark:text-slate-400 truncate">
                                        {event.content.slice(0, 80)}
                                    </p>
                                )}
                                {event.tool && (
                                    <div className="mt-1">
                                        <code className="bg-slate-100 dark:bg-slate-600 px-1.5 py-0.5 rounded text-xs">
                                            {event.tool}
                                        </code>
                                        {event.success !== undefined && (
                                            <span className={`ml-2 ${event.success ? 'text-green-500' : 'text-red-500'}`}>
                                                {event.success ? '✓' : '✗'}
                                            </span>
                                        )}
                                    </div>
                                )}
                                {event.error && (
                                    <p className="text-red-500 mt-1">{event.error}</p>
                                )}
                            </div>
                        ))}
                    </div>
                )}
            </div>
        </aside>
    )
}
