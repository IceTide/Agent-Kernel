<script setup lang="ts">
interface Props {
  loading: boolean
  text?: string
}

const props = withDefaults(defineProps<Props>(), {
  text: 'Loading...',
})
</script>

<template>
  <div v-if="props.loading" class="loading-spinner">
    <el-icon class="is-loading" :size="32">
      <Loading />
    </el-icon>
    <span class="loading-text">{{ props.text }}</span>
  </div>
  <slot v-else />
</template>

<style scoped lang="scss">
.loading-spinner {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 2.5rem;
  color: var(--text-secondary);
  
  .loading-text {
    margin-top: 0.75rem;
    font-size: var(--font-size-xs);
  }
}
</style>

