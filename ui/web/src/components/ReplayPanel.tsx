// ui/web/src/components/ReplayPanel.tsx
import { useState, useEffect } from 'react';
import {
    Download,
    Upload,
    Trash2,
    Play,
    Pause,
    Radio,
    CheckCircle,
    XCircle
} from 'lucide-react';

interface ReplayRecord {
    action_id: string;
    tool: string;
    args: Record<string, unknown>;
    ok: boolean;
    summary: string;
}

interface ReplayData {
    session_id: string;
    record_count: number;
    records: ReplayRecord[];
}

export function ReplayPanel({ sessionId }: { sessionId: string | null }) {
    const [replayData, setReplayData] = useState<ReplayData | null>(null);
    const [mode, setMode] = useState<string>('off');
    const [loading, setLoading] = useState(false);
    const [message, setMessage] = useState<string | null>(null);

    const API_BASE = 'http://localhost:8080';

    const fetchReplayData = async () => {
        if (!sessionId) return;
        try {
            const res = await fetch(`${API_BASE}/api/replay/data?session_id=${sessionId}`);
            const data = await res.json();
            setReplayData(data);
        } catch (err) {
            console.error('Failed to fetch replay data:', err);
        }
    };

    const fetchMode = async () => {
        if (!sessionId) return;
        try {
            const res = await fetch(`${API_BASE}/api/replay/mode?session_id=${sessionId}`);
            const data = await res.json();
            setMode(data.mode || 'off');
        } catch (err) {
            console.error('Failed to fetch replay mode:', err);
        }
    };

    useEffect(() => {
        fetchReplayData();
        fetchMode();
    }, [sessionId]);

    const setReplayMode = async (newMode: string) => {
        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/replay/mode?session_id=${sessionId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ mode: newMode }),
            });
            const data = await res.json();
            setMode(data.mode);
            setMessage(`Mode set to ${data.mode}`);
        } catch (err) {
            setMessage('Failed to set mode');
        } finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    const exportReplay = async () => {
        if (!sessionId) return;
        window.open(`${API_BASE}/api/replay/export?session_id=${sessionId}`, '_blank');
    };

    const importReplay = async (event: React.ChangeEvent<HTMLInputElement>) => {
        const file = event.target.files?.[0];
        if (!file) return;

        setLoading(true);
        try {
            const text = await file.text();
            const records = text
                .split('\n')
                .filter((line: string) => line.trim())
                .map((line: string) => JSON.parse(line));

            const res = await fetch(`${API_BASE}/api/replay/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ data: records, session_id: sessionId }),
            });
            const data = await res.json();
            setMessage(data.message);
            fetchReplayData();
        } catch (err) {
            setMessage('Failed to import replay data');
        } finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    const clearReplay = async () => {
        if (!confirm('Are you sure you want to clear all replay data?')) return;

        setLoading(true);
        try {
            const res = await fetch(`${API_BASE}/api/replay/clear?session_id=${sessionId}`, {
                method: 'DELETE',
            });
            const data = await res.json();
            setMessage(data.message);
            fetchReplayData();
        } catch (err) {
            setMessage('Failed to clear replay data');
        } finally {
            setLoading(false);
            setTimeout(() => setMessage(null), 3000);
        }
    };

    return (
        <div className="p-4 space-y-4">
            <h2 className="text-lg font-semibold flex items-center gap-2">
                <Radio className="w-5 h-5" />
                Replay Manager
            </h2>

            {/* Mode Controls */}
            <div className="flex gap-2">
                <button
                    onClick={() => setReplayMode('off')}
                    disabled={loading}
                    className={`px-3 py-2 rounded flex items-center gap-1 ${mode === 'off'
                        ? 'bg-gray-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600'
                        }`}
                >
                    <Pause className="w-4 h-4" /> Off
                </button>
                <button
                    onClick={() => setReplayMode('record')}
                    disabled={loading}
                    className={`px-3 py-2 rounded flex items-center gap-1 ${mode === 'record'
                        ? 'bg-red-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600'
                        }`}
                >
                    <Radio className="w-4 h-4" /> Record
                </button>
                <button
                    onClick={() => setReplayMode('replay')}
                    disabled={loading}
                    className={`px-3 py-2 rounded flex items-center gap-1 ${mode === 'replay'
                        ? 'bg-green-600 text-white'
                        : 'bg-gray-200 dark:bg-gray-700 hover:bg-gray-300 dark:hover:bg-gray-600'
                        }`}
                >
                    <Play className="w-4 h-4" /> Replay
                </button>
            </div>

            {/* Status Message */}
            {message && (
                <div className="px-3 py-2 bg-blue-100 dark:bg-blue-900 text-blue-800 dark:text-blue-200 rounded">
                    {message}
                </div>
            )}

            {/* Actions */}
            <div className="flex gap-2">
                <button
                    onClick={exportReplay}
                    disabled={!replayData?.record_count}
                    className="px-3 py-2 bg-blue-600 text-white rounded flex items-center gap-1 hover:bg-blue-700 disabled:opacity-50"
                >
                    <Download className="w-4 h-4" /> Export
                </button>
                <label className="px-3 py-2 bg-green-600 text-white rounded flex items-center gap-1 hover:bg-green-700 cursor-pointer">
                    <Upload className="w-4 h-4" /> Import
                    <input
                        type="file"
                        accept=".jsonl,.json"
                        onChange={importReplay}
                        className="hidden"
                    />
                </label>
                <button
                    onClick={clearReplay}
                    disabled={!replayData?.record_count}
                    className="px-3 py-2 bg-red-600 text-white rounded flex items-center gap-1 hover:bg-red-700 disabled:opacity-50"
                >
                    <Trash2 className="w-4 h-4" /> Clear
                </button>
            </div>

            {/* Record Count */}
            <div className="text-sm text-gray-600 dark:text-gray-400">
                {replayData?.record_count ?? 0} recorded actions
            </div>

            {/* Records List */}
            {replayData && replayData.records.length > 0 && (
                <div className="border dark:border-gray-700 rounded max-h-80 overflow-y-auto">
                    <table className="w-full text-sm">
                        <thead className="bg-gray-100 dark:bg-gray-800 sticky top-0">
                            <tr>
                                <th className="px-2 py-1 text-left">Tool</th>
                                <th className="px-2 py-1 text-left">Status</th>
                                <th className="px-2 py-1 text-left">Summary</th>
                            </tr>
                        </thead>
                        <tbody>
                            {replayData.records.map((record, idx) => (
                                <tr key={record.action_id || idx} className="border-t dark:border-gray-700">
                                    <td className="px-2 py-1 font-mono text-xs">{record.tool}</td>
                                    <td className="px-2 py-1">
                                        {record.ok ? (
                                            <CheckCircle className="w-4 h-4 text-green-500" />
                                        ) : (
                                            <XCircle className="w-4 h-4 text-red-500" />
                                        )}
                                    </td>
                                    <td className="px-2 py-1 truncate max-w-xs" title={record.summary}>
                                        {record.summary}
                                    </td>
                                </tr>
                            ))}
                        </tbody>
                    </table>
                </div>
            )}
        </div>
    );
}
