<script setup lang="ts">
interface Props {
  description?: string
  icon?: string
}

const props = withDefaults(defineProps<Props>(), {
  description: 'No Data',
  icon: 'Folder',
})
</script>

<template>
  <div class="empty-state">
    <el-empty :description="props.description">
      <template #image>
        <el-icon :size="64" class="empty-icon">
          <component :is="props.icon" />
        </el-icon>
      </template>
    </el-empty>
  </div>
</template>

<style scoped lang="scss">
.empty-state {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 2.5rem;
  
  .empty-icon {
    color: var(--text-placeholder);
  }
}
</style>

