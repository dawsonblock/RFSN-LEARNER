import { useState, useRef, useEffect } from 'react'
import { Send, Loader2, Bot, User } from 'lucide-react'
import { useStore } from '../store/useStore'

export function ChatView() {
    const [input, setInput] = useState('')
    const [loading, setLoading] = useState(false)
    const { sessionId, messages, addMessage } = useStore()
    const messagesEndRef = useRef<HTMLDivElement>(null)

    useEffect(() => {
        messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
    }, [messages])

    const handleSend = async () => {
        if (!input.trim() || loading) return

        const userMessage = input.trim()
        setInput('')
        setLoading(true)
        addMessage('user', userMessage)

        try {
            const response = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: userMessage,
                    session_id: sessionId,
                }),
            })

            const data = await response.json()
            if (data.reply) {
                addMessage('assistant', data.reply)
            } else if (data.detail) {
                addMessage('assistant', `Error: ${data.detail}`)
            }
        } catch (error) {
            addMessage('assistant', `Error: ${error}`)
        } finally {
            setLoading(false)
        }
    }

    return (
        <div className="h-full flex flex-col">
            {/* Messages */}
            <div className="flex-1 overflow-auto space-y-4 pb-4">
                {messages.length === 0 ? (
                    <div className="text-center text-slate-400 py-12">
                        <Bot size={48} className="mx-auto mb-4 opacity-50" />
                        <p>Start a conversation with the agent</p>
                    </div>
                ) : (
                    messages.map((msg, i) => (
                        <div
                            key={i}
                            className={`flex gap-3 ${msg.role === 'user' ? 'justify-end' : ''}`}
                        >
                            {msg.role === 'assistant' && (
                                <div className="w-8 h-8 rounded-full bg-primary-100 dark:bg-primary-900 flex items-center justify-center">
                                    <Bot size={16} className="text-primary-600 dark:text-primary-400" />
                                </div>
                            )}
                            <div
                                className={`
                  max-w-[70%] rounded-2xl px-4 py-3 text-sm
                  ${msg.role === 'user'
                                        ? 'message-user text-white'
                                        : 'message-assistant'
                                    }
                `}
                            >
                                <pre className="whitespace-pre-wrap font-sans">{msg.content}</pre>
                            </div>
                            {msg.role === 'user' && (
                                <div className="w-8 h-8 rounded-full bg-primary-500 flex items-center justify-center">
                                    <User size={16} className="text-white" />
                                </div>
                            )}
                        </div>
                    ))
                )}
                <div ref={messagesEndRef} />
            </div>

            {/* Input */}
            <div className="border-t border-slate-200 dark:border-slate-700 pt-4">
                <div className="flex gap-3">
                    <input
                        type="text"
                        value={input}
                        onChange={(e) => setInput(e.target.value)}
                        onKeyDown={(e) => e.key === 'Enter' && !e.shiftKey && handleSend()}
                        placeholder="Type a message..."
                        className="flex-1 px-4 py-3 rounded-xl bg-slate-100 dark:bg-slate-800 border-0 focus:ring-2 focus:ring-primary-500 outline-none"
                        disabled={loading}
                    />
                    <button
                        onClick={handleSend}
                        disabled={loading || !input.trim()}
                        className="px-5 py-3 bg-primary-500 hover:bg-primary-600 disabled:opacity-50 text-white rounded-xl transition flex items-center gap-2"
                    >
                        {loading ? (
                            <Loader2 size={18} className="animate-spin" />
                        ) : (
                            <Send size={18} />
                        )}
                    </button>
                </div>
            </div>
        </div>
    )
}
