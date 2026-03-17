<script setup lang="ts">
import { computed } from 'vue'

interface Props {
  tags: string[]
  type?: 'primary' | 'success' | 'warning' | 'danger' | 'info'
  size?: 'large' | 'default' | 'small'
  maxShow?: number
}

const props = withDefaults(defineProps<Props>(), {
  type: 'info',
  size: 'small',
  maxShow: 5,
})

const displayTags = computed(() => {
  if (props.maxShow && props.tags.length > props.maxShow) {
    return props.tags.slice(0, props.maxShow)
  }
  return props.tags
})

const hasMore = computed(() => {
  return props.maxShow && props.tags.length > props.maxShow
})

const moreCount = computed(() => {
  return props.tags.length - props.maxShow
})
</script>

<template>
  <div class="tag-list">
    <el-tag
      v-for="tag in displayTags"
      :key="tag"
      :type="props.type"
      :size="props.size"
      class="tag-item"
    >
      {{ tag }}
    </el-tag>
    <el-tag
      v-if="hasMore"
      :type="props.type"
      :size="props.size"
      class="tag-item more-tag"
    >
      +{{ moreCount }}
    </el-tag>
  </div>
</template>

<style scoped lang="scss">
.tag-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.25rem;
  
  .tag-item {
    margin: 0;
  }
  
  .more-tag {
    opacity: 0.7;
  }
}
</style>

