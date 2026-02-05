import { useState, useEffect } from 'react'
import { Folder, File, ChevronRight, ArrowUp, RefreshCw } from 'lucide-react'
import { useStore } from '../store/useStore'

interface FsItem {
    name: string
    is_dir: boolean
    size: number | null
}

export function FilesView() {
    const { sessionId } = useStore()
    const [path, setPath] = useState('.')
    const [items, setItems] = useState<FsItem[]>([])
    const [content, setContent] = useState<string | null>(null)
    const [selectedFile, setSelectedFile] = useState<string | null>(null)
    const [loading, setLoading] = useState(false)

    const fetchDir = async (p: string) => {
        setLoading(true)
        try {
            const res = await fetch(`/api/fs/list?path=${encodeURIComponent(p)}&session_id=${sessionId}`)
            const data = await res.json()
            setItems(data.items || [])
            setPath(data.path || p)
            setContent(null)
            setSelectedFile(null)
        } catch {
            setItems([])
        } finally {
            setLoading(false)
        }
    }

    const readFile = async (name: string) => {
        const filePath = path === '.' ? name : `${path}/${name}`
        try {
            const res = await fetch(`/api/fs/read?path=${encodeURIComponent(filePath)}&session_id=${sessionId}`)
            const data = await res.json()
            setContent(data.content || null)
            setSelectedFile(name)
        } catch {
            setContent('Error reading file')
        }
    }

    const goUp = () => {
        const parts = path.split('/')
        parts.pop()
        fetchDir(parts.join('/') || '.')
    }

    useEffect(() => {
        fetchDir('.')
    }, [sessionId])

    return (
        <div className="space-y-4">
            {/* Path Bar */}
            <div className="flex items-center gap-2">
                <button
                    onClick={goUp}
                    disabled={path === '.'}
                    title="Go up one directory"
                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800 disabled:opacity-50"
                >
                    <ArrowUp size={18} />
                </button>
                <button
                    onClick={() => fetchDir(path)}
                    title="Refresh directory"
                    className="p-2 rounded-lg hover:bg-slate-100 dark:hover:bg-slate-800"
                >
                    <RefreshCw size={18} className={loading ? 'animate-spin' : ''} />
                </button>
                <div className="flex-1 px-3 py-2 bg-slate-100 dark:bg-slate-800 rounded-lg font-mono text-sm">
                    {path}
                </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
                {/* File List */}
                <div className="space-y-1 max-h-96 overflow-auto">
                    {items.map((item) => (
                        <button
                            key={item.name}
                            onClick={() => {
                                if (item.is_dir) {
                                    fetchDir(path === '.' ? item.name : `${path}/${item.name}`)
                                } else {
                                    readFile(item.name)
                                }
                            }}
                            className={`w-full flex items-center gap-2 p-2 rounded-lg text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-700 ${selectedFile === item.name ? 'bg-primary-100 dark:bg-primary-900' : ''
                                }`}
                        >
                            {item.is_dir ? (
                                <Folder size={16} className="text-yellow-500" />
                            ) : (
                                <File size={16} className="text-slate-400" />
                            )}
                            <span className="flex-1 truncate">{item.name}</span>
                            {item.is_dir && <ChevronRight size={14} className="text-slate-400" />}
                            {item.size !== null && (
                                <span className="text-xs text-slate-400">
                                    {item.size < 1024 ? `${item.size}B` : `${(item.size / 1024).toFixed(1)}KB`}
                                </span>
                            )}
                        </button>
                    ))}
                </div>

                {/* File Content */}
                <div>
                    {content !== null ? (
                        <div>
                            <div className="text-sm font-medium mb-2">{selectedFile}</div>
                            <pre className="p-3 bg-slate-900 text-slate-100 rounded-lg text-xs overflow-auto max-h-80 font-mono">
                                {content}
                            </pre>
                        </div>
                    ) : (
                        <div className="text-center text-slate-400 py-8">
                            Select a file to view
                        </div>
                    )}
                </div>
            </div>
        </div>
    )
}
