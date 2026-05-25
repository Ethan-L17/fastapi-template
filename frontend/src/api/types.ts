export interface Item {
  id: number
  name: string
  description: string | null
  price: number
}

export interface ItemCreate {
  name: string
  description?: string | null
  price: number
}

export interface ChatMessage {
  role: string
  content: string
}

export interface ChatResponse {
  thread_id: string
  workflow: string
  messages: ChatMessage[]
}

export interface HistoryItem {
  checkpoint_id: string
  step: number | null
  messages: ChatMessage[]
}

export interface McpServer {
  transport: string
  enabled: boolean
}

export interface McpTool {
  name: string
  description?: string
  inputSchema?: Record<string, unknown>
}

export interface McpResource {
  uri: string
  name?: string
  description?: string
  mimeType?: string
}