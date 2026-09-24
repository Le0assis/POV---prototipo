<script setup>
import { RouterView } from 'vue-router'
</script>

<template>
  <RouterView />
</template>

<style>
/* O reset de margin/padding vem do Tailwind (preflight). Um "* { margin:0; padding:0 }"
   aqui, fora das layers, sobrescreveria todas as classes de espaçamento. */
html,
body,
#app {
  min-height: 100%;
}
</style>