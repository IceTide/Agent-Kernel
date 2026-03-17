<script setup lang="ts">
import { onMounted, onUnmounted, onErrorCaptured } from 'vue'
import { useWebSocketStore } from '@/stores/websocket'

const wsStore = useWebSocketStore()
onErrorCaptured((err, _instance, info) => {
  console.error('Component error captured:', err, info)
  return false
})
function handleUnhandledRejection(event: PromiseRejectionEvent) {
  console.error('Unhandled promise rejection:', event.reason)
  event.preventDefault()
}

onMounted(() => {
  wsStore.connect()
  window.addEventListener('unhandledrejection', handleUnhandledRejection)
})

onUnmounted(() => {
  wsStore.disconnect()
  window.removeEventListener('unhandledrejection', handleUnhandledRejection)
})
</script>

<template>
  <router-view />
</template>

<style>
html, body, #app {
  margin: 0;
  padding: 0;
  height: 100%;
  width: 100%;
}
</style>

