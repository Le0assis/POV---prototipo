import { createRouter, createWebHistory } from 'vue-router'

import HomeView from '../views/HomeView.vue'
import RecorderView from '../views/RecorderView.vue'

const routes = [
  {
    path: '/',
    name: 'home',
    component: HomeView,
  }, {
    path: '/recorder',
    name: 'recorder',
    component: RecorderView,
  }
]

const router = createRouter({
  history: createWebHistory(),
  routes,
})

export default router