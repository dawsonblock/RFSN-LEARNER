import { useState, useEffect, useCallback } from 'react'
import { Sidebar } from './components/Sidebar'
import { SystemPanel } from './components/SystemPanel'
import { ChatView } from './views/ChatView'
import { LedgerView } from './views/LedgerView'
import { ToolsView } from './views/ToolsView'
import { MemoryView } from './views/MemoryView'
import { FilesView } from './views/FilesView'
import { PermissionsView } from './views/PermissionsView'
import { BudgetsView } from './views/BudgetsView'
import { ReplayView } from './views/ReplayView'
import { WorldView } from './views/WorldView'
import { useStore } from './store/useStore'
import { Sun, Moon } from 'lucide-react'

type ViewType = 'chat' | 'ledger' | 'tools' | 'memory' | 'files' | 'shell' | 'permissions' | 'budgets' | 'replay' | 'world'

export default function App() {
    const [activeView, setActiveView] = useState<ViewType>('chat')
    const [darkMode, setDarkMode] = useState(false)
    const { sessionId, setSessionId, events, connectWebSocket } = useStore()

    // Initialize session and WebSocket
    useEffect(() => {
        if (!sessionId) {
            const newId = crypto.randomUUID().slice(0, 8)
            setSessionId(newId)
        }
    }, [sessionId, setSessionId])

    useEffect(() => {
        if (sessionId) {
            connectWebSocket(sessionId)
        }
    }, [sessionId, connectWebSocket])

    // Toggle dark mode
    useEffect(() => {
        document.documentElement.classList.toggle('dark', darkMode)
    }, [darkMode])

    const renderView = useCallback(() => {
        switch (activeView) {
            case 'chat': return <ChatView />
            case 'ledger': return <LedgerView />
            case 'tools': return <ToolsView />
            case 'memory': return <MemoryView />
            case 'files': return <FilesView />
            case 'permissions': return <PermissionsView />
            case 'budgets': return <BudgetsView />
            case 'replay': return <ReplayView />
            case 'world': return <WorldView />
            default: return <ChatView />
        }
    }, [activeView])

    return (
        <div className="h-screen flex bg-white dark:bg-slate-900 text-slate-800 dark:text-slate-100">
            {/* Left Sidebar - Navigation */}
            <Sidebar activeView={activeView} onViewChange={setActiveView} />

            {/* Center - Main Content */}
            <main className="flex-1 flex flex-col min-w-0 border-x border-slate-200 dark:border-slate-700">
                {/* Header */}
                <header className="h-14 flex items-center justify-between px-6 border-b border-slate-200 dark:border-slate-700 bg-white dark:bg-slate-900">
                    <h1 className="text-lg font-semibold capitalize">{activeView}</h1>
                    <div className="flex items-center gap-4">
                        <span className="text-sm text-slate-500">
                            Session: <code className="text-xs bg-slate-100 dark:bg-slate-800 px-2 py-0.5 rounded">{sessionId || '...'}</code>
                        </span>
                        <button
                            onClick={() => setDarkMode(!darkMode)}
                            className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 transition"
                        >
                            {darkMode ? <Sun size={18} /> : <Moon size={18} />}
                        </button>
                    </div>
                </header>

                {/* Content */}
                <div className="flex-1 overflow-auto p-6">
                    {renderView()}
                </div>
            </main>

            {/* Right Panel - Live System */}
            <SystemPanel events={events} />
        </div>
    )
}
