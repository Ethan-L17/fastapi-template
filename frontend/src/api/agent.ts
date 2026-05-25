import client from './client'
import type { ChatResponse, HistoryItem } from './types'

export const agentApi = {
  chat: (threadId: string, message: string) =>
    client.post<ChatResponse>('/agent/chat', { thread_id: threadId, message }),

  supervisorChat: (threadId: string, message: string) =>
    client.post<ChatResponse>('/agent/supervisor/chat', { thread_id: threadId, message }),

  supervisorChatStream: async function* (threadId: string, message: string) {
    const response = await fetch('/api/agent/supervisor/chat/stream', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ thread_id: threadId, message }),
    })

    const reader = response.body!.getReader()
    const decoder = new TextDecoder()
    let buffer = ''

    while (true) {
      const { done, value } = await reader.read()
      if (done) break

      buffer += decoder.decode(value, { stream: true })
      const lines = buffer.split('\n')
      buffer = lines.pop() ?? ''

      for (const line of lines) {
        if (line.startsWith('data: ')) {
          const data = line.slice(6).trim()
          if (data === '[DONE]') return
          try {
            yield JSON.parse(data)
          } catch {
            // skip malformed lines
          }
        }
      }
    }
  },

  getHistory: (threadId: string) =>
    client.get<HistoryItem[]>(`/agent/threads/${threadId}/history`),

  getState: (threadId: string) =>
    client.get<ChatResponse>(`/agent/threads/${threadId}/state`),

  deleteThread: (threadId: string) =>
    client.delete(`/agent/threads/${threadId}`),
}