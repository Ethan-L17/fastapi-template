import { createRouter, createWebHistory } from 'vue-router'

const router = createRouter({
  history: createWebHistory(),
  routes: [
    { path: '/', redirect: '/items' },
    { path: '/items', name: 'items', component: () => import('../views/ItemsView.vue') },
    { path: '/mcp', name: 'mcp', component: () => import('../views/McpView.vue') },
    { path: '/agent', name: 'agent', component: () => import('../views/AgentView.vue') },
  ],
})

export default router