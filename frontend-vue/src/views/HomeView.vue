<script setup>
import { ref, computed, onMounted, nextTick } from 'vue'
import PlaceIcon from '../components/PlaceIcon.vue'
import RouteMap from '../components/RouteMap.vue'
import { getMap, getRoute } from '../services/pov'
import { placeMeta, CATEGORIAS } from '../data/places'

const HOSPITAL = 'Hospital Beneficente UNIMAR'
const step = ref('inicio') // inicio | destino | rota
const modo = ref('mapa') // mapa | ra
const map = ref({ nodes: [], edges: [] })
const origem = ref('')
const destino = ref('')
const rota = ref([])
const busca = ref('')
const filtro = ref('')
const erro = ref('')
const searchEl = ref(null)

const btnPrimario = 'w-full rounded-xl bg-black py-3 text-sm font-semibold text-white transition hover:bg-neutral-800'
const btnSecundario = 'w-full rounded-xl border border-neutral-300 py-3 text-xs text-neutral-600 transition hover:border-neutral-500'
const chip = 'rounded-full border border-neutral-300 px-4 py-1.5 text-xs text-neutral-600'
const campo = 'rounded-xl border border-neutral-300 px-3 py-2'

onMounted(async () => {
  try {
    map.value = await getMap()
    origem.value = map.value.nodes.find((n) => n.id === 'Recepcao')?.id ?? map.value.nodes[0]?.id ?? ''
  } catch {
    erro.value = 'Não foi possível carregar o mapa. Verifique a conexão com o servidor.'
  }
})

const andarAtual = computed(() => placeMeta(origem.value).andar)
const meta = computed(() => placeMeta(destino.value))

const destinos = computed(() => {
  const q = busca.value.trim().toLowerCase()
  return map.value.nodes
    .filter((n) => n.id !== origem.value)
    .map((n) => ({ ...n, ...placeMeta(n.id) }))
    .filter((d) => (!q || d.label.toLowerCase().includes(q) || d.sala.includes(q))
      && (!filtro.value || (filtro.value === 'Favoritos' ? d.favorito : d.categoria === filtro.value)))
})

function abrirDestino(focar = false) {
  erro.value = ''
  step.value = 'destino'
  if (focar) nextTick(() => searchEl.value?.focus())
}

async function escolher(id) {
  erro.value = ''
  try {
    rota.value = (await getRoute(origem.value, id)).path_sequence
    destino.value = id
    modo.value = 'mapa'
    step.value = 'rota'
  } catch {
    erro.value = 'Não há caminho entre esses dois pontos.'
  }
}

function voltar() {
  erro.value = ''
  if (step.value === 'rota') rota.value = []
  step.value = step.value === 'rota' ? 'destino' : 'inicio'
}

function comecarCaminhada() {
  // Próxima etapa: iniciar a captura de sensores e acompanhar a posição.
}
</script>

<template>
  <main class="min-h-screen bg-[#f8f6f1] text-[#1f2229] lg:grid lg:grid-cols-[440px_1fr]">
    <section class="order-2 flex flex-col justify-end p-6 lg:order-1 lg:justify-center lg:p-10">
      <div v-if="step === 'inicio'" class="rounded-3xl bg-white p-5 shadow-sm">
        <div class="flex items-center gap-3">
          <PlaceIcon />
          <div>
            <p class="text-xs text-neutral-500">Localização</p>
            <p class="font-semibold leading-tight">{{ HOSPITAL }}</p>
          </div>
        </div>
        <div class="mt-4 grid grid-cols-2 gap-3">
          <div :class="campo">
            <p class="text-xs text-neutral-500">Andar atual</p>
            <p class="text-sm font-semibold">{{ andarAtual }}º andar</p>
          </div>
          <label :class="campo">
            <span class="block text-xs text-neutral-500">Você está</span>
            <select v-model="origem" class="w-full bg-transparent text-sm font-semibold outline-none">
              <option v-for="n in map.nodes" :key="n.id" :value="n.id">{{ n.label }}</option>
            </select>
          </label>
        </div>
        <button :class="[btnPrimario, 'mt-4']" :disabled="!origem" @click="abrirDestino()">Escolher destino</button>
      </div>

      <div v-else-if="step === 'destino'" class="flex max-h-screen flex-col">
        <button class="self-start text-xs text-neutral-600" @click="voltar">← Voltar</button>
        <h2 class="mt-6 text-3xl font-extrabold">Selecione o destino</h2>
        <input ref="searchEl" v-model="busca" type="search" placeholder="Pesquise departamentos, salas..."
          class="mt-5 w-full rounded-xl border border-neutral-300 bg-white px-4 py-3 text-sm outline-none focus:border-cyan-500" />
        <div class="mt-3 flex gap-2">
          <button v-for="c in CATEGORIAS" :key="c" :class="[chip, filtro === c && 'bg-black text-white']"
            @click="filtro = filtro === c ? '' : c">{{ c }}</button>
        </div>
        <ul class="mt-4 space-y-3 overflow-y-auto pb-4">
          <li v-for="d in destinos" :key="d.id">
            <button class="flex w-full items-center gap-4 rounded-2xl border border-neutral-300 bg-white p-4 text-left transition hover:border-cyan-500"
              @click="escolher(d.id)">
              <PlaceIcon />
              <span>
                <span class="block text-lg font-bold">{{ d.label }}</span>
                <span class="flex gap-6 text-xs text-neutral-500"><span>Sala {{ d.sala }}</span><span>Andar {{ d.andar }}</span></span>
              </span>
            </button>
          </li>
          <li v-if="!destinos.length" class="text-sm text-neutral-500">Nenhum destino encontrado. Tente outro nome ou número.</li>
        </ul>
      </div>

      <div v-else>
        <button class="text-xs text-neutral-600" @click="voltar">← Voltar</button>
        <div class="mt-4 inline-flex rounded-full border border-neutral-800 p-1 text-xs font-bold">
          <button :class="['rounded-full px-6 py-1.5', modo === 'mapa' ? 'bg-black text-white' : '']" @click="modo = 'mapa'">MAPA</button>
          <button :class="['rounded-full px-6 py-1.5', modo === 'ra' ? 'bg-black text-white' : '']" @click="modo = 'ra'">REALIDADE AUMENTADA</button>
        </div>
        <p v-if="modo === 'ra'" class="mt-4 text-sm text-neutral-500">A realidade aumentada será liberada em uma próxima etapa. Use o mapa por enquanto.</p>
        <div class="mt-6 rounded-3xl border border-neutral-300 bg-white p-5">
          <div class="flex items-center gap-3">
            <PlaceIcon />
            <div>
              <p class="text-lg font-bold leading-tight">{{ destino }}</p>
              <p class="flex gap-6 text-xs text-neutral-500"><span>Sala {{ meta.sala }}</span><span>Andar {{ meta.andar }}</span></p>
            </div>
          </div>
          <p class="mt-3 text-xs text-neutral-500">Passa por: {{ rota.join(', ') }}</p>
          <button :class="[btnPrimario, 'mt-4']" @click="comecarCaminhada">Comece a caminhar</button>
        </div>
      </div>

      <p v-if="erro" role="alert" class="mt-3 text-sm text-red-600">{{ erro }}</p>
    </section>

    <section class="relative order-1 min-h-[45vh] bg-[#22252b] lg:order-2 lg:min-h-screen">
      <h1 class="absolute left-8 top-7 text-3xl font-extrabold text-white">POV</h1>
      <RouteMap :nodes="map.nodes" :edges="map.edges" :route="step === 'rota' ? rota : []" :current="origem" />
    </section>
  </main>
</template>