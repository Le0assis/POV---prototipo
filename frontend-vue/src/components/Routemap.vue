<script setup>
import { computed } from 'vue'

const props = defineProps({
  nodes: { type: Array, default: () => [] },
  edges: { type: Array, default: () => [] },
  route: { type: Array, default: () => [] },
  current: { type: String, default: '' },
})

const W = 800, H = 560, M = 80

// Escala uniforme (mantém a proporção real do prédio) e centraliza o mapa.
const pos = computed(() => {
  const xs = props.nodes.map((n) => n.x), ys = props.nodes.map((n) => n.y)
  const minX = Math.min(...xs), minY = Math.min(...ys)
  const rx = (Math.max(...xs) - minX) || 1, ry = (Math.max(...ys) - minY) || 1
  const s = Math.min((W - 2 * M) / rx, (H - 2 * M) / ry)
  const ox = (W - rx * s) / 2, oy = (H - ry * s) / 2
  return Object.fromEntries(props.nodes.map((n) => [n.id, { x: ox + (n.x - minX) * s, y: oy + (n.y - minY) * s, label: n.label }]))
})

const lines = computed(() =>
  props.edges.filter((e) => pos.value[e.source] && pos.value[e.target])
    .map((e) => ({ a: pos.value[e.source], b: pos.value[e.target] })))

const routeLine = computed(() =>
  props.route.map((id) => pos.value[id]).filter(Boolean).map((p) => `${p.x},${p.y}`).join(' '))
</script>

<template>
  <svg v-if="nodes.length" :viewBox="`0 0 ${W} ${H}`" class="h-full w-full" role="img"
    aria-label="Mapa do prédio com a rota até o destino">
    <line v-for="(l, i) in lines" :key="i" :x1="l.a.x" :y1="l.a.y" :x2="l.b.x" :y2="l.b.y"
      stroke="#3b404a" stroke-width="12" stroke-linecap="round" />
    <polyline v-if="routeLine" :points="routeLine" fill="none" stroke="#22d3ee" stroke-width="5"
      stroke-linecap="round" stroke-linejoin="round" style="filter: drop-shadow(0 0 6px #22d3ee)" />
    <g v-for="(p, id) in pos" :key="id">
      <circle :cx="p.x" :cy="p.y" r="8" :fill="id === current ? '#22d3ee' : '#d4d4d8'" />
      <circle v-if="id === current" :cx="p.x" :cy="p.y" r="15" fill="none" stroke="#22d3ee" stroke-width="2" />
      <text :x="p.x" :y="p.y - 20" text-anchor="middle" font-size="13" fill="#a1a1aa">{{ p.label }}</text>
    </g>
  </svg>
</template>