<script setup lang="ts">
</script>

<template>
  <nav class="bg-white border-b sticky top-0 z-10">
    <div class="max-w-4xl mx-auto px-6 flex items-center gap-6 h-14">
      <span class="font-bold text-lg">FastAPI Test</span>
      <router-link to="/items" class="text-gray-600 hover:text-gray-900">Items</router-link>
      <router-link to="/mcp" class="text-gray-600 hover:text-gray-900">MCP</router-link>
      <router-link to="/agent" class="text-gray-600 hover:text-gray-900">Agent</router-link>
    </div>
  </nav>
  <router-view />
</template>