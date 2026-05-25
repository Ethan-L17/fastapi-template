<script setup lang="ts">
import { ref, nextTick } from 'vue'
import { agentApi } from '../api/agent'
import type { ChatMessage } from '../api/types'

const threadId = ref('test-thread-1')
const message = ref('')
const messages = ref<ChatMessage[]>([])
const loading = ref(false)
const error = ref('')
const mode = ref<'react' | 'supervisor' | 'supervisor-stream'>('react')

// 流式进行中的临时内容
const streamingContent = ref('')
const streamingNode = ref('')

const chatBox = ref<HTMLElement>()

function scrollBottom() {
  nextTick(() => {
    if (chatBox.value) chatBox.value.scrollTop = chatBox.value.scrollHeight
  })
}

async function send() {
  if (!message.value.trim()) return
  const msg = message.value.trim()
  message.value = ''
  error.value = ''
  loading.value = true
  streamingContent.value = ''
  streamingNode.value = ''

  try {
    if (mode.value === 'react') {
      // 显示用户消息 + loading
      messages.value.push({ role: 'user', content: msg })
      streamingContent.value = 'Thinking...'
      streamingNode.value = 'react'
      scrollBottom()
      const { data } = await agentApi.chat(threadId.value, msg)
      messages.value = data.messages
      streamingContent.value = ''
      streamingNode.value = ''
    } else if (mode.value === 'supervisor') {
      messages.value.push({ role: 'user', content: msg })
      streamingContent.value = 'Thinking...'
      streamingNode.value = 'supervisor'
      scrollBottom()
      const { data } = await agentApi.supervisorChat(threadId.value, msg)
      messages.value = data.messages
      streamingContent.value = ''
      streamingNode.value = ''
    } else {
      // supervisor-stream: 手动构建消息列表
      messages.value.push({ role: 'user', content: msg })
      scrollBottom()

      let accumulated = ''
      for await (const event of agentApi.supervisorChatStream(threadId.value, msg)) {
        if (event.type === 'routing') {
          // routing 事件：切换节点名，重置累加内容
          streamingNode.value = event.node
          accumulated = `Routing to: ${event.content}`
          streamingContent.value = accumulated
        } else if (event.type === 'token') {
          // token 级别流式：逐字累加
          if (streamingNode.value !== event.node) {
            // 节点切换，重置累加内容
            accumulated = ''
            streamingNode.value = event.node
          }
          accumulated += event.content
          streamingContent.value = accumulated
        } else if (event.type === 'message') {
          // 完整消息（非流式节点的输出）
          streamingNode.value = event.node
          accumulated = event.content
          streamingContent.value = accumulated
        } else if (event.type === 'final') {
          messages.value.push({ role: 'assistant', content: event.content })
          streamingContent.value = ''
          streamingNode.value = ''
          accumulated = ''
        } else if (event.type === 'error') {
          error.value = event.content
          streamingContent.value = ''
          streamingNode.value = ''
        }
        scrollBottom()
      }
      // 流结束时，如果还有累积内容没转为消息，推入
      if (accumulated && !messages.value.some((m, i) => i === messages.value.length - 1 && m.role === 'assistant' && m.content === accumulated)) {
        messages.value.push({ role: 'assistant', content: accumulated })
        streamingContent.value = ''
        streamingNode.value = ''
      }
    }
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
    scrollBottom()
  }
}

async function loadHistory() {
  error.value = ''
  try {
    const { data } = await agentApi.getHistory(threadId.value)
    if (data.length) {
      const last = data[0]
      messages.value = last.messages
    } else {
      messages.value = []
    }
  } catch (e: any) {
    error.value = e.message
  }
}

async function deleteThread() {
  error.value = ''
  try {
    await agentApi.deleteThread(threadId.value)
    messages.value = []
  } catch (e: any) {
    error.value = e.message
  }
}
</script>

<template>
  <div class="max-w-3xl mx-auto p-6 flex flex-col h-[calc(100vh-56px)]">
    <h1 class="text-2xl font-bold mb-4">Agent Chat</h1>

    <!-- Config -->
    <div class="flex gap-3 mb-4 flex-wrap items-center">
      <input
        v-model="threadId"
        placeholder="Thread ID"
        class="border rounded px-3 py-2 w-60"
      />
      <select v-model="mode" class="border rounded px-3 py-2">
        <option value="react">ReAct</option>
        <option value="supervisor">Supervisor</option>
        <option value="supervisor-stream">Supervisor (SSE)</option>
      </select>
      <button @click="loadHistory" class="text-blue-600 hover:underline text-sm">Load History</button>
      <button @click="deleteThread" class="text-red-600 hover:underline text-sm">Delete Thread</button>
    </div>

    <p v-if="error" class="text-red-600 mb-2 text-sm">{{ error }}</p>

    <!-- Messages -->
    <div ref="chatBox" class="border rounded p-4 flex-1 overflow-y-auto bg-white mb-4">
      <div v-if="!messages.length && !streamingContent" class="text-gray-400 text-center py-10">
        No messages yet.
      </div>

      <div
        v-for="(msg, i) in messages"
        :key="i"
        class="mb-3 flex"
        :class="msg.role === 'user' ? 'justify-end' : 'justify-start'"
      >
        <div class="max-w-[80%]">
          <span
            class="inline-block rounded-lg px-3 py-2 text-sm whitespace-pre-wrap"
            :class="
              msg.role === 'user'
                ? 'bg-blue-600 text-white'
                : 'bg-gray-100 text-gray-800'
            "
          >
            {{ msg.content }}
          </span>
          <p class="text-xs text-gray-400 mt-1" :class="msg.role === 'user' ? 'text-right' : ''">
            {{ msg.role }}
          </p>
        </div>
      </div>

      <!-- Streaming indicator -->
      <div v-if="streamingContent" class="mb-3 flex justify-start">
        <div class="max-w-[80%]">
          <span class="inline-block rounded-lg px-3 py-2 text-sm bg-gray-100 text-gray-800 whitespace-pre-wrap">
            {{ streamingContent }}
            <span class="inline-block w-1.5 h-4 bg-gray-400 animate-pulse ml-0.5 align-middle"></span>
          </span>
          <p class="text-xs text-gray-400 mt-1">
            {{ streamingNode }} <span class="text-blue-500">streaming...</span>
          </p>
        </div>
      </div>
    </div>

    <!-- Input -->
    <form @submit.prevent="send" class="flex gap-3">
      <input
        v-model="message"
        placeholder="Type a message..."
        class="border rounded px-3 py-2 flex-1"
        :disabled="loading"
      />
      <button
        type="submit"
        class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700 disabled:opacity-50"
        :disabled="loading"
      >
        {{ loading ? 'Sending...' : 'Send' }}
      </button>
    </form>
  </div>
</template>
