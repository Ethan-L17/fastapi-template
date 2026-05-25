import client from './client'
import type { Item, ItemCreate } from './types'

export const itemsApi = {
  list: () => client.get<Item[]>('/items/'),
  get: (id: number) => client.get<Item>(`/items/${id}`),
  create: (data: ItemCreate) => client.post<Item>('/items/', data),
  delete: (id: number) => client.delete(`/items/${id}`),
}