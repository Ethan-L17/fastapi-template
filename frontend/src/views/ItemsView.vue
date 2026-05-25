<script setup lang="ts">
import { ref, onMounted } from 'vue'
import { itemsApi } from '../api/items'
import type { Item } from '../api/types'

const items = ref<Item[]>([])
const loading = ref(false)
const error = ref('')

const form = ref({ name: '', description: '', price: 0 })

async function load() {
  loading.value = true
  error.value = ''
  try {
    const { data } = await itemsApi.list()
    items.value = data
  } catch (e: any) {
    error.value = e.message
  } finally {
    loading.value = false
  }
}

async function create() {
  if (!form.value.name || !form.value.price) return
  try {
    await itemsApi.create({
      name: form.value.name,
      description: form.value.description || null,
      price: form.value.price,
    })
    form.value = { name: '', description: '', price: 0 }
    await load()
  } catch (e: any) {
    error.value = e.message
  }
}

async function remove(id: number) {
  try {
    await itemsApi.delete(id)
    await load()
  } catch (e: any) {
    error.value = e.message
  }
}

onMounted(load)
</script>

<template>
  <div class="max-w-3xl mx-auto p-6">
    <h1 class="text-2xl font-bold mb-6">Items CRUD</h1>

    <!-- Create Form -->
    <form @submit.prevent="create" class="flex gap-3 mb-6 flex-wrap">
      <input
        v-model="form.name"
        placeholder="Name"
        class="border rounded px-3 py-2 flex-1 min-w-[140px]"
      />
      <input
        v-model="form.description"
        placeholder="Description"
        class="border rounded px-3 py-2 flex-1 min-w-[140px]"
      />
      <input
        v-model.number="form.price"
        type="number"
        step="0.01"
        placeholder="Price"
        class="border rounded px-3 py-2 w-28"
      />
      <button
        type="submit"
        class="bg-blue-600 text-white px-4 py-2 rounded hover:bg-blue-700"
      >
        Create
      </button>
    </form>

    <!-- Error -->
    <p v-if="error" class="text-red-600 mb-4">{{ error }}</p>

    <!-- Loading -->
    <p v-if="loading" class="text-gray-500">Loading...</p>

    <!-- Items List -->
    <table v-if="items.length" class="w-full border-collapse">
      <thead>
        <tr class="border-b text-left">
          <th class="py-2 pr-4">ID</th>
          <th class="py-2 pr-4">Name</th>
          <th class="py-2 pr-4">Description</th>
          <th class="py-2 pr-4">Price</th>
          <th class="py-2">Action</th>
        </tr>
      </thead>
      <tbody>
        <tr v-for="item in items" :key="item.id" class="border-b">
          <td class="py-2 pr-4">{{ item.id }}</td>
          <td class="py-2 pr-4">{{ item.name }}</td>
          <td class="py-2 pr-4">{{ item.description ?? '-' }}</td>
          <td class="py-2 pr-4">{{ item.price }}</td>
          <td class="py-2">
            <button
              @click="remove(item.id)"
              class="text-red-600 hover:underline"
            >
              Delete
            </button>
          </td>
        </tr>
      </tbody>
    </table>

    <p v-else-if="!loading" class="text-gray-400">No items yet.</p>

    <button @click="load" class="mt-4 text-blue-600 hover:underline">Refresh</button>
  </div>
</template>