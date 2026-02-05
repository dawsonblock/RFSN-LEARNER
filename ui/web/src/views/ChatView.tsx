import React, { useMemo, useState } from "react";
import { useStore } from "../store/useStore";

type AnyEvent = { type: string; ts?: string;[k: string]: any };

type Turn = {
    idx: number;
    startTs?: string;
    endTs?: string;
    events: AnyEvent[];
    userText?: string;
    finalMessage?: string;
};

function buildTurns(events: AnyEvent[]): Turn[] {
    const turns: Turn[] = [];
    let cur: Turn | null = null;

    for (const ev of events) {
        if (!ev || typeof ev.type !== "string") continue;

        if (ev.type === "turn_start") {
            if (cur) turns.push(cur);
            cur = {
                idx: turns.length,
                startTs: ev.ts,
                events: [ev],
                userText: ev.user_text ?? ev.userText,
            };
            continue;
        }

        if (!cur) continue;

        cur.events.push(ev);

        if (ev.type === "turn_end") {
            cur.endTs = ev.ts;
            cur.finalMessage = ev.final_message ?? ev.finalMessage;
            turns.push(cur);
            cur = null;
        }
    }

    if (cur) turns.push(cur);
    return turns;
}

function formatEvent(ev: AnyEvent): { label: string; detail?: string } {
    const t = ev.type;

    if (t === "gate_decision") {
        const decision = String(ev.decision ?? "");
        const allowed = ev.allowed === true ? "allowed" : "denied";
        const reason = ev.reason ? String(ev.reason) : "";
        return { label: `gate: ${decision} (${allowed})`, detail: reason };
    }

    if (t === "tool_call") {
        const tool = String(ev.tool ?? ev?.action?.payload?.tool ?? "");
        return { label: `tool_call: ${tool}` };
    }

    if (t === "tool_result") {
        const ok = ev.ok === true ? "ok" : "fail";
        const summary = ev.summary ? String(ev.summary) : "";
        return { label: `tool_result: ${ok}`, detail: summary };
    }

    if (t === "deny") {
        const reason = ev.reason ? String(ev.reason) : "deny";
        const err = ev.error ? String(ev.error) : "";
        return { label: `deny: ${reason}`, detail: err };
    }

    if (t === "replay_hit") {
        const tool = ev.tool ? String(ev.tool) : "";
        return { label: `replay_hit: ${tool}`, detail: ev.summary ? String(ev.summary) : "" };
    }

    if (t === "replay_miss") {
        return { label: `replay_miss`, detail: ev.action_id ? String(ev.action_id) : "" };
    }

    if (t === "replay_record") {
        const tool = ev.tool ? String(ev.tool) : "";
        return { label: `replay_record: ${tool}`, detail: ev.action_id ? String(ev.action_id) : "" };
    }

    if (t === "ledger_append") {
        const decision = ev.decision ? String(ev.decision) : "";
        return { label: `ledger_append`, detail: decision };
    }

    if (t === "permission_request") {
        const req = ev.request ? String(ev.request) : "";
        const why = ev.why ? String(ev.why) : "";
        return { label: `permission_request: ${req}`, detail: why };
    }

    if (t === "error") {
        const kind = ev.kind ? String(ev.kind) : "error";
        const e = ev.error ? String(ev.error) : "";
        return { label: `error: ${kind}`, detail: e };
    }

    return { label: t };
}

function TurnTimeline({ turn }: { turn: Turn }) {
    const [open, setOpen] = useState(false);

    const useful = useMemo(() => {
        return turn.events.filter((e) => {
            const t = e.type;
            return (
                t === "gate_decision" ||
                t === "tool_call" ||
                t === "tool_result" ||
                t === "ledger_append" ||
                t === "deny" ||
                t === "replay_hit" ||
                t === "replay_miss" ||
                t === "replay_record" ||
                t === "permission_request" ||
                t === "error"
            );
        });
    }, [turn.events]);

    return (
        <div className="mt-2 rounded border border-slate-700/60 bg-slate-900/30">
            <div className="flex items-center justify-between px-3 py-2">
                <div className="text-sm text-slate-200">
                    Execution timeline{" "}
                    <span className="text-slate-400">
                        (events: {useful.length}
                        {turn.startTs ? ` • start ${turn.startTs}` : ""}
                        {turn.endTs ? ` • end ${turn.endTs}` : ""})
                    </span>
                </div>
                <button
                    className="text-sm px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-slate-100"
                    onClick={() => setOpen((v) => !v)}
                >
                    {open ? "Collapse" : "Expand"}
                </button>
            </div>

            {open && (
                <div className="px-3 pb-3">
                    {useful.length === 0 ? (
                        <div className="text-sm text-slate-400">No internal events captured for this turn.</div>
                    ) : (
                        <ul className="space-y-2">
                            {useful.map((ev, i) => {
                                const f = formatEvent(ev);
                                return (
                                    <li key={i} className="text-sm">
                                        <div className="text-slate-200">{f.label}</div>
                                        {f.detail ? <div className="text-slate-400 whitespace-pre-wrap">{f.detail}</div> : null}
                                    </li>
                                );
                            })}
                        </ul>
                    )}
                </div>
            )}
        </div>
    );
}

export default function ChatView() {
    const messages = useStore((s) => s.messages);
    const events = useStore((s) => s.events);
    const sessionId = useStore((s) => s.sessionId);
    const sendChat = useStore((s) => s.sendChat);
    const [text, setText] = useState("");

    const turns = useMemo(() => buildTurns(events as AnyEvent[]), [events]);

    let turnPtr = 0;

    const onSend = async () => {
        const t = text.trim();
        if (!t) return;
        setText("");
        await sendChat(t);
    };

    return (
        <div className="flex flex-col h-full">
            <div className="flex-1 overflow-auto p-4 space-y-4">
                <div className="text-xs text-slate-500">session: {sessionId || "(none)"}</div>

                {messages.map((m: any, idx: number) => {
                    const role = m.role || m[0];
                    const content = m.content || m[1] || "";
                    const isUser = role === "user";

                    let timeline: React.ReactNode = null;

                    if (!isUser) {
                        const t = turns[turnPtr];
                        if (t) {
                            timeline = <TurnTimeline turn={t} />;
                            turnPtr += 1;
                        }
                    }

                    return (
                        <div key={idx} className="max-w-4xl">
                            <div
                                className={[
                                    "rounded px-3 py-2 whitespace-pre-wrap",
                                    isUser ? "bg-slate-800 text-slate-100" : "bg-slate-900/50 text-slate-100 border border-slate-700/60",
                                ].join(" ")}
                            >
                                <div className="text-xs text-slate-400 mb-1">{isUser ? "user" : "assistant"}</div>
                                <div>{content}</div>
                            </div>
                            {timeline}
                        </div>
                    );
                })}
            </div>

            <div className="border-t border-slate-800 p-3">
                <div className="flex gap-2">
                    <input
                        className="flex-1 rounded bg-slate-900 border border-slate-700 px-3 py-2 text-slate-100"
                        value={text}
                        onChange={(e) => setText(e.target.value)}
                        onKeyDown={(e) => {
                            if (e.key === "Enter" && !e.shiftKey) {
                                e.preventDefault();
                                onSend();
                            }
                        }}
                        placeholder="Message the agent…"
                    />
                    <button className="px-4 py-2 rounded bg-slate-700 hover:bg-slate-600 text-slate-100" onClick={onSend}>
                        Send
                    </button>
                </div>
            </div>
        </div>
    );
}
