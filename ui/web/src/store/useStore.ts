import { useState, useEffect } from 'react'

export interface SystemEvent {
    id: string
    type: string
    ts: string
    content?: string
    tool?: string
    success?: boolean
    error?: string
    [key: string]: unknown
}

interface Store {
    sessionId: string | null
    setSessionId: (id: string) => void
    ws: WebSocket | null
    connected: boolean
    connectWebSocket: (sessionId: string) => void
    events: SystemEvent[]
    addEvent: (event: SystemEvent) => void
    clearEvents: () => void
    messages: Array<{ role: 'user' | 'assistant'; content: string }>
    addMessage: (role: 'user' | 'assistant', content: string) => void
    clearMessages: () => void
}

type SetState = (partial: Partial<Store> | ((state: Store) => Partial<Store>)) => void

// Simple state management (no external dependencies)
function createStore(createState: (set: SetState, get: () => Store) => Store): () => Store {
    let state: Store
    const listeners = new Set<() => void>()

    const set: SetState = (partial) => {
        const nextPartial = typeof partial === 'function' ? partial(state) : partial
        state = { ...state, ...nextPartial }
        listeners.forEach((l) => l())
    }

    const get = () => state

    state = createState(set, get)

    return () => {
        const [, forceUpdate] = useState({})
        useEffect(() => {
            const listener = () => forceUpdate({})
            listeners.add(listener)
            return () => { listeners.delete(listener) }
        }, [])
        return state
    }
}

export const useStore = createStore((set, get) => ({
    sessionId: null,
    setSessionId: (id) => set({ sessionId: id }),

    ws: null,
    connected: false,
    connectWebSocket: (sessionId: string) => {
        const existing = get().ws
        if (existing) {
            existing.close()
        }

        const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
        const wsUrl = `${protocol}//${window.location.host}/ws/session/${sessionId}`
        const ws = new WebSocket(wsUrl)

        ws.onopen = () => {
            set({ connected: true })
            get().addEvent({
                id: crypto.randomUUID(),
                type: 'connected',
                ts: new Date().toISOString(),
                content: `Connected to session ${sessionId}`,
            })
        }

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data)
                if (data.type !== 'ping' && data.type !== 'pong') {
                    get().addEvent({
                        id: crypto.randomUUID(),
                        ...data,
                    })
                }
            } catch {
                // Ignore parse errors
            }
        }

        ws.onclose = () => {
            set({ connected: false })
        }

        ws.onerror = () => {
            set({ connected: false })
        }

        set({ ws })
    },

    events: [],
    addEvent: (event) => set((state) => ({
        events: [...state.events.slice(-99), event],
    })),
    clearEvents: () => set({ events: [] }),

    messages: [],
    addMessage: (role, content) => set((state) => ({
        messages: [...state.messages, { role, content }],
    })),
    clearMessages: () => set({ messages: [] }),
}))
