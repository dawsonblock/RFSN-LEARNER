import {
    MessageSquare,
    FileText,
    Wrench,
    Database,
    Folder,
    Terminal,
    Shield,
    Gauge,
    Play,
    Globe,
} from 'lucide-react'

type ViewType = 'chat' | 'ledger' | 'tools' | 'memory' | 'files' | 'shell' | 'permissions' | 'budgets' | 'replay' | 'world'

interface SidebarProps {
    activeView: ViewType
    onViewChange: (view: ViewType) => void
}

const navItems: Array<{ id: ViewType; icon: typeof MessageSquare; label: string }> = [
    { id: 'chat', icon: MessageSquare, label: 'Chat' },
    { id: 'ledger', icon: FileText, label: 'Ledger' },
    { id: 'tools', icon: Wrench, label: 'Tools' },
    { id: 'memory', icon: Database, label: 'Memory' },
    { id: 'files', icon: Folder, label: 'Files' },
    { id: 'shell', icon: Terminal, label: 'Shell' },
    { id: 'permissions', icon: Shield, label: 'Permissions' },
    { id: 'budgets', icon: Gauge, label: 'Budgets' },
    { id: 'replay', icon: Play, label: 'Replay' },
    { id: 'world', icon: Globe, label: 'World' },
]

export function Sidebar({ activeView, onViewChange }: SidebarProps) {
    return (
        <aside className="w-56 bg-slate-50 dark:bg-slate-800 p-4 flex flex-col">
            {/* Logo */}
            <div className="flex items-center gap-2 mb-8 px-2">
                <span className="text-2xl">🧠</span>
                <span className="font-bold text-lg">RFSN Agent</span>
            </div>

            {/* Navigation */}
            <nav className="flex-1 space-y-1">
                {navItems.map(({ id, icon: Icon, label }) => (
                    <button
                        key={id}
                        onClick={() => onViewChange(id)}
                        className={`
              w-full flex items-center gap-3 px-3 py-2.5 rounded-lg text-sm font-medium transition
              ${activeView === id
                                ? 'bg-primary-500 text-white shadow-md'
                                : 'text-slate-600 dark:text-slate-300 hover:bg-slate-100 dark:hover:bg-slate-700'
                            }
            `}
                    >
                        <Icon size={18} />
                        {label}
                    </button>
                ))}
            </nav>

            {/* Footer */}
            <div className="pt-4 border-t border-slate-200 dark:border-slate-700">
                <div className="text-xs text-slate-400 text-center">
                    RFSN Agent UI v1.0
                </div>
            </div>
        </aside>
    )
}
