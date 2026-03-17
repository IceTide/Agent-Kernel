<script setup lang="ts">
interface Props {
  modelValue: string
  placeholder?: string
}

const props = withDefaults(defineProps<Props>(), {
  placeholder: 'Search...',
})

const emit = defineEmits<{
  'update:modelValue': [value: string]
}>()

function handleInput(value: string) {
  emit('update:modelValue', value)
}

function handleClear() {
  emit('update:modelValue', '')
}
</script>

<template>
  <el-input
    :model-value="props.modelValue"
    :placeholder="props.placeholder"
    clearable
    class="search-bar"
    @input="handleInput"
    @clear="handleClear"
  >
    <template #prefix>
      <el-icon><Search /></el-icon>
    </template>
  </el-input>
</template>

<style scoped lang="scss">
.search-bar {
  width: 100%;
}
</style>

