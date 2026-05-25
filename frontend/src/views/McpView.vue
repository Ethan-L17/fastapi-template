<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { mcpApi } from '../api/mcp'
import type { McpServer, McpTool } from '../api/types'

const servers = ref<Record<string, McpServer>>({})
const selectedServer = ref('')
const tools = ref<McpTool[]>([])
const loading = ref(false)
const error = ref('')
const reloadResult = ref('')

// Tool call state
const callToolName = ref('')
const callArgs = ref('{}')
const callResult = ref('')

async function loadServers() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await mcpApi.listServers()
    servers.value = data
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function loadTools(name: string) {
  selectedServer.value = name
  tools.value = []
  callResult.value = ''
  try {
    const { data } = await mcpApi.listTools(name)
    tools.value = data.tools
  } catch (e: any) {
    error.value = e.message
  }
}

async function callTool() {
  if (!callToolName.value) return
  callResult.value = ''
  try {
    const args = JSON.parse(callArgs.value)
    const { data } = await mcpApi.callTool(selectedServer.value, callToolName.value, args)
    callResult.value = JSON.stringify(data, null, 2)
  } catch (e: any) {
    callResult.value = `Error: ${e.message}`
  }
}

async function reload() {
  reloadResult.value = ''
  try {
    const { data } = await mcpApi.reload()
    reloadResult.value = JSON.stringify(data, null, 2)
    await loadServers()
  } catch (e: any) {
    reloadResult.value = `Error: ${e.message}`
  }
}

async function reconnect(name: string) {
  try {
    await mcpApi.reconnect(name)
    await loadServers()
  } catch (e: any) {
    error.value = e.message
  }
}

onMounted(loadServers)
</script>

<template>
  <div class="max-w-4xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">MCP Servers</h1>

    <!-- Actions -->
    <div class="flex gap-3 mb-6">
      <button
        @click="loadServers"
        class="bg-gray-200 px-4 py-2 rounded hover:bg-gray-300"
      >
        Refresh
      </button>
      <button
        @click="reload"
        class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
      >
        Reload Config
      </button>
    </div>

    <p v-if="error" class="text-red-600 mb-4">{{ error }}</p>
    <p v-if="loading" class="text-gray-500">Loading...</p>

    <!-- Reload Result -->
    <pre v-if="reloadResult" class="bg-gray-100 p-3 rounded mb-4 text-sm overflow-auto">{{ reloadResult }}</pre>

    <!-- Servers Table -->
    <table v-if="Object.keys(servers).length" class="w-full border-collapse mb-6">
      <thead>
        <tr class="border-b text-left">
          <th class="py-2 pr-4">Name</th>
          <th class="py-2 pr-4">Transport</th>
          <th class="py-2 pr-4">Enabled</th>
          <th class="py-2">Actions</th>
        </tr>
      </thead>
      <tbody>
        <tr
          v-for="(info, name) in servers"
          :key="name"
          class="border-b"
          :class="{ 'bg-blue-50': selectedServer === name }"
        >
          <td class="py-2 pr-4 font-mono">{{ name }}</td>
          <td class="py-2 pr-4">{{ info.transport }}</td>
          <td class="py-2 pr-4">{{ info.enabled ? 'Yes' : 'No' }}</td>
          <td class="py-2 flex gap-2">
            <button @click="loadTools(name as string)" class="text-blue-600 hover:underline">
              Tools
            </button>
            <button @click="reconnect(name as string)" class="text-orange-600 hover:underline">
              Reconnect
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-else-if="!loading" class="text-gray-400">No servers connected.</p>

    <!-- Tools Panel -->
    <div v-if="selectedServer" class="border rounded p-4">
      <h2 class="text-lg font-semibold mb-3">
        Tools — <span class="font-mono">{{ selectedServer }}</span>
      </h2>

      <div v-if="tools.length" class="mb-4">
        <div
          v-for="tool in tools"
          :key="tool.name"
          class="border rounded p-3 mb-2 cursor-pointer hover:bg-gray-50"
          :class="{ 'border-blue-500 bg-blue-50': callToolName === tool.name }"
          @click="callToolName = tool.name"
        >
          <p class="font-mono font-medium">{{ tool.name }}</p>
          <p v-if="tool.description" class="text-sm text-gray-500 mt-1">{{ tool.description }}</p>
        </div>
      </div>
      <p v-else class="text-gray-400 mb-4">No tools found.</p>

      <!-- Call Tool Form -->
      <div v-if="callToolName" class="border-t pt-4">
        <h3 class="font-medium mb-2">Call: <code>{{ callToolName }}</code></h3>
        <textarea
          v-model="callArgs"
          rows="3"
          class="w-full border rounded px-3 py-2 font-mono text-sm mb-2"
          placeholder="{}"
        />
        <button
          @click="callTool"
          class="bg-green-600 text-white px-4 py-2 rounded hover:bg-green-700"
        >
          Execute
        </button>
        <pre v-if="callResult" class="bg-gray-100 p-3 rounded mt-3 text-sm overflow-auto">{{ callResult }}</pre>
      </div>
    </div>
  </div>
</template>