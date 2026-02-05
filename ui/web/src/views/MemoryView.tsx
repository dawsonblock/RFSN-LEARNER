import { useState, useEffect } from 'react'
import { Search, Key, Database } from 'lucide-react'
import { useStore } from '../store/useStore'

export function MemoryView() {
    const { sessionId } = useStore()
    const [query, setQuery] = useState('')
    const [results, setResults] = useState<Array<{ key: string; value: string }>>([])
    const [keys, setKeys] = useState<string[]>([])
    const [selectedKey, setSelectedKey] = useState<string | null>(null)
    const [keyValue, setKeyValue] = useState<unknown>(null)

    useEffect(() => {
        fetch(`/api/memory/keys?session_id=${sessionId}`)
            .then((r) => r.json())
            .then((d) => setKeys(d.keys || []))
    }, [sessionId])

    const search = async () => {
        if (!query.trim()) return
        const res = await fetch(`/api/memory/search?q=${encodeURIComponent(query)}&session_id=${sessionId}`)
        const data = await res.json()
        setResults(data.results || [])
    }

    const getKey = async (key: string) => {
        setSelectedKey(key)
        const res = await fetch(`/api/memory/key/${encodeURIComponent(key)}?session_id=${sessionId}`)
        const data = await res.json()
        setKeyValue(data.value)
    }

    return (
        <div className="space-y-6">
            {/* Search */}
            <div>
                <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                    <Search size={18} /> Search Memory
                </h2>
                <div className="flex gap-2">
                    <input
                        type="text"
                        value={query}
                        onChange={(e) => setQuery(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && search()}
                        placeholder="Search query..."
                        className="flex-1 px-3 py-2 rounded-lg bg-slate-100 dark:bg-slate-800"
                    />
                    <button
                        onClick={search}
                        className="px-4 py-2 bg-primary-500 text-white rounded-lg"
                    >
                        Search
                    </button>
                </div>
                {results.length > 0 && (
                    <div className="mt-3 space-y-2">
                        {results.map((r, i) => (
                            <div
                                key={i}
                                className="p-3 bg-slate-50 dark:bg-slate-800 rounded-lg cursor-pointer hover:bg-slate-100 dark:hover:bg-slate-700"
                                onClick={() => getKey(r.key)}
                            >
                                <code className="text-sm">{r.key}</code>
                            </div>
                        ))}
                    </div>
                )}
            </div>

            {/* Keys List */}
            <div>
                <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                    <Key size={18} /> All Keys ({keys.length})
                </h2>
                <div className="grid grid-cols-2 gap-2 max-h-64 overflow-auto">
                    {keys.map((key) => (
                        <button
                            key={key}
                            onClick={() => getKey(key)}
                            className={`p-2 text-left text-sm rounded-lg ${selectedKey === key
                                    ? 'bg-primary-500 text-white'
                                    : 'bg-slate-100 dark:bg-slate-800 hover:bg-slate-200 dark:hover:bg-slate-700'
                                }`}
                        >
                            {key}
                        </button>
                    ))}
                </div>
            </div>

            {/* Value Display */}
            {selectedKey && (
                <div>
                    <h2 className="text-lg font-semibold mb-3 flex items-center gap-2">
                        <Database size={18} /> {selectedKey}
                    </h2>
                    <pre className="p-4 bg-slate-900 text-green-400 rounded-lg text-sm overflow-auto max-h-80">
                        {JSON.stringify(keyValue, null, 2)}
                    </pre>
                </div>
            )}
        </div>
    )
}
