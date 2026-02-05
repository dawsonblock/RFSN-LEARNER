import React, { useEffect, useMemo, useState } from "react";
import { useStore } from "../store/useStore";

type Tool = {
    name: string;
    risk: string;
    description?: string;
    require_grant?: boolean;
    deny_in_replay?: boolean;
    budget?: { calls_per_turn: number; max_bytes?: number | null; max_results?: number | null };
    schema?: { name: string; required: boolean; kind: string }[];
};

const MUTATING = new Set(["write_file", "apply_diff", "memory_delete"]);

export default function ToolsView() {
    const apiGet = useStore((s) => s.apiGet);
    const apiPost = useStore((s) => s.apiPost);
    const sessionId = useStore((s) => s.sessionId);

    const [tools, setTools] = useState<Tool[]>([]);
    const [granted, setGranted] = useState<Set<string>>(new Set());
    const [pythonEnabled, setPythonEnabled] = useState(false);

    const [selected, setSelected] = useState<Tool | null>(null);
    const [argsJson, setArgsJson] = useState<string>("{}");
    const [manualOut, setManualOut] = useState<any>(null);

    const refresh = async () => {
        const t = await apiGet("/api/tools");
        setTools((t?.tools || []) as Tool[]);

        if (sessionId) {
            const p = await apiGet(`/api/perms?session_id=${encodeURIComponent(sessionId)}`);
            setGranted(new Set((p?.granted_tools || []) as string[]));
            setPythonEnabled(Boolean(p?.python_execution_enabled));
        }
    };

    useEffect(() => {
        refresh();
        // eslint-disable-next-line react-hooks/exhaustive-deps
    }, [sessionId]);

    const sorted = useMemo(() => {
        return [...tools].sort((a, b) => a.name.localeCompare(b.name));
    }, [tools]);

    const grant = async (tool: string) => {
        if (!sessionId) return;
        await apiPost("/api/perms/grant", { session_id: sessionId, tool });
        await refresh();
    };

    const revoke = async (tool: string) => {
        if (!sessionId) return;
        await apiPost("/api/perms/revoke", { session_id: sessionId, tool });
        await refresh();
    };

    const togglePython = async (enabled: boolean) => {
        if (!sessionId) return;
        await apiPost("/api/perms/python", { session_id: sessionId, enabled });
        await refresh();
    };

    const runManual = async () => {
        if (!sessionId || !selected) return;
        let args: any = {};
        try {
            args = JSON.parse(argsJson || "{}");
        } catch {
            setManualOut({ error: "Invalid JSON args" });
            return;
        }
        const r = await apiPost("/api/tools/run", { session_id: sessionId, tool: selected.name, arguments: args });
        setManualOut(r);
    };

    return (
        <div className="flex h-full">
            <div className="w-80 border-r border-slate-800 overflow-auto">
                <div className="p-3 text-sm text-slate-200 border-b border-slate-800">Tools</div>
                <div className="p-3 space-y-2">
                    <div className="rounded border border-slate-700/60 bg-slate-900/30 p-3">
                        <div className="text-sm text-slate-200">Python execution</div>
                        <div className="text-xs text-slate-400 mt-1">
                            run_python is gated by both tool grant and a separate enable flag.
                        </div>
                        <div className="mt-2 flex gap-2">
                            <button
                                className={`px-2 py-1 rounded text-sm ${pythonEnabled ? "bg-slate-700 text-slate-100" : "bg-slate-900 text-slate-300 border border-slate-700"}`}
                                onClick={() => togglePython(true)}
                            >
                                Enable
                            </button>
                            <button
                                className={`px-2 py-1 rounded text-sm ${!pythonEnabled ? "bg-slate-700 text-slate-100" : "bg-slate-900 text-slate-300 border border-slate-700"}`}
                                onClick={() => togglePython(false)}
                            >
                                Disable
                            </button>
                        </div>
                    </div>

                    {sorted.map((t) => (
                        <button
                            key={t.name}
                            onClick={() => { setSelected(t); setArgsJson("{}"); setManualOut(null); }}
                            className={`w-full text-left px-3 py-2 rounded border ${selected?.name === t.name ? "border-slate-500 bg-slate-900/60" : "border-slate-800 bg-slate-900/20"
                                }`}
                        >
                            <div className="flex items-center justify-between">
                                <div className="text-sm text-slate-100">{t.name}</div>
                                <div className="text-xs text-slate-400">{t.risk}</div>
                            </div>

                            <div className="mt-1 flex flex-wrap gap-1">
                                {MUTATING.has(t.name) ? (
                                    <span className="text-[10px] px-2 py-0.5 rounded bg-amber-900/40 border border-amber-700/50 text-amber-200">
                                        MUTATES
                                    </span>
                                ) : null}
                                {t.require_grant ? (
                                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">
                                        GRANT REQUIRED
                                    </span>
                                ) : null}
                                {t.deny_in_replay ? (
                                    <span className="text-[10px] px-2 py-0.5 rounded bg-slate-800 border border-slate-700 text-slate-200">
                                        DENIED IN REPLAY
                                    </span>
                                ) : null}
                                {t.name === "run_python" && !pythonEnabled ? (
                                    <span className="text-[10px] px-2 py-0.5 rounded bg-red-900/30 border border-red-700/40 text-red-200">
                                        PYTHON DISABLED
                                    </span>
                                ) : null}
                                {granted.has(t.name) ? (
                                    <span className="text-[10px] px-2 py-0.5 rounded bg-emerald-900/30 border border-emerald-700/40 text-emerald-200">
                                        GRANTED
                                    </span>
                                ) : null}
                            </div>

                            {t.description ? <div className="text-xs text-slate-400 mt-1 line-clamp-2">{t.description}</div> : null}
                        </button>
                    ))}
                </div>
            </div>

            <div className="flex-1 overflow-auto p-4">
                {!selected ? (
                    <div className="text-slate-400">Select a tool.</div>
                ) : (
                    <div className="space-y-4 max-w-3xl">
                        <div className="flex items-start justify-between gap-3">
                            <div>
                                <div className="text-lg text-slate-100">{selected.name}</div>
                                <div className="text-sm text-slate-400">{selected.description}</div>
                            </div>
                            <div className="flex gap-2">
                                {granted.has(selected.name) ? (
                                    <button className="px-3 py-2 rounded bg-slate-800 hover:bg-slate-700 text-slate-100" onClick={() => revoke(selected.name)}>
                                        Revoke
                                    </button>
                                ) : (
                                    <button className="px-3 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-100" onClick={() => grant(selected.name)}>
                                        Grant
                                    </button>
                                )}
                            </div>
                        </div>

                        <div className="rounded border border-slate-800 bg-slate-900/30 p-3">
                            <div className="text-sm text-slate-200">Schema</div>
                            <pre className="text-xs text-slate-400 mt-2 whitespace-pre-wrap">
                                {JSON.stringify(selected.schema || [], null, 2)}
                            </pre>
                        </div>

                        <div className="rounded border border-slate-800 bg-slate-900/30 p-3">
                            <div className="text-sm text-slate-200">Manual run</div>
                            <div className="text-xs text-slate-400 mt-1">Arguments JSON</div>
                            <textarea
                                className="w-full mt-2 h-28 rounded bg-slate-950 border border-slate-700 p-2 text-slate-100 text-sm"
                                value={argsJson}
                                onChange={(e) => setArgsJson(e.target.value)}
                            />
                            <div className="mt-2 flex gap-2">
                                <button className="px-3 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-100" onClick={runManual}>
                                    Run
                                </button>
                                <button className="px-3 py-2 rounded bg-slate-900 border border-slate-700 text-slate-200" onClick={() => setManualOut(null)}>
                                    Clear
                                </button>
                            </div>
                            {manualOut ? (
                                <pre className="text-xs text-slate-300 mt-3 whitespace-pre-wrap">{JSON.stringify(manualOut, null, 2)}</pre>
                            ) : null}
                        </div>
                    </div>
                )}
            </div>
        </div>
    );
}
