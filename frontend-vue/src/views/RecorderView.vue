<script setup>
import { RouterLink } from 'vue-router'
</script>

<template>
  <main class="container">

    <RouterLink to="/">
      ← Voltar
    </RouterLink>

    <h1>Gravador</h1>

    <p>
      Captura e telemetria dos sensores.
    </p>

  </main>
</template>

<style scoped>
.container {
  min-height: 100vh;
  background: #0f172a;
  color: white;
  padding: 30px;
}

a {
  color: #38bdf8;
}
</style>