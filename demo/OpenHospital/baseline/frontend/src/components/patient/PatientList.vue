<script setup lang="ts">
import { usePatientStore } from '@/stores/patient'
import { SearchBar } from '@/components/common'
import PatientCard from './PatientCard.vue'
import type { PatientPhase } from '@/types'
import { PHASE_CONFIG } from '@/types/patient'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

const patientStore = usePatientStore()

const emit = defineEmits<{
  select: [patientId: string]
}>()

const phaseOptions = Object.entries(PHASE_CONFIG).map(([key, value]) => ({
  value: key as PatientPhase,
  label: value.label,
}))

function handleSelect(patientId: string) {
  patientStore.selectPatient(patientId)
  emit('select', patientId)
}
</script>

<template>
  <div class="patient-list">
    <div class="list-header">
      <h3 class="title">
        <el-icon><User /></el-icon>
        Patient List
      </h3>
      <el-badge :value="patientStore.filteredPatients.length" :max="9999" type="success" />
    </div>

    <div class="filters">
      <SearchBar
        v-model="patientStore.searchQuery"
        placeholder="SearchPatient..."
      />

      <el-select
        v-model="patientStore.selectedPhase"
        placeholder="AllStatus"
        clearable
        size="small"
        class="phase-select"
      >
        <el-option
          v-for="phase in phaseOptions"
          :key="phase.value"
          :label="phase.label"
          :value="phase.value"
        />
      </el-select>
    </div>

    <div class="list-content">
      <DynamicScroller
        v-if="patientStore.filteredPatients.length > 0"
        class="scroller"
        :items="patientStore.filteredPatients"
        :min-item-size="160"
        key-field="id"
      >
        <template #default="{ item, index, active }">
          <DynamicScrollerItem
            :item="item"
            :active="active"
            :data-index="index"
          >
            <PatientCard
              :patient="item"
              :selected="patientStore.selectedPatientId === item.id"
              :index="index"
              @click="handleSelect(item.id)"
            />
          </DynamicScrollerItem>
        </template>
      </DynamicScroller>

      <div v-else class="empty-tip">
        No Patient Data
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.patient-list {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: var(--bg-color);
  border-radius: 0;

  .list-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0.75rem 1rem;
    border-bottom: 0.0625rem solid var(--border-color-lighter);

    .title {
      display: flex;
      align-items: center;
      gap: 0.5rem;
      font-size: var(--font-size-md);
      font-weight: 400;
      margin: 0;
      color: var(--text-primary);
    }
  }

  .filters {
    padding: 0.75rem;
    display: flex;
    flex-direction: column;
    gap: 0.5rem;
    border-bottom: 0.0625rem solid var(--border-color-lighter);

    .phase-select {
      width: 100%;
    }
  }

  .list-content {
    flex: 1;
    overflow: hidden;

    .scroller {
      height: 100%;
    }

    .empty-tip {
      text-align: center;
      color: var(--text-secondary);
      padding: 1.5rem;
    }
  }
}
@media (max-width: 48rem) {
  .patient-list {
    .list-header {
      padding: 0.5rem 0.75rem;

      .title {
        font-size: var(--font-size-sm);
        gap: 0.375rem;
      }
    }

    .filters {
      padding: 0.5rem;
      gap: 0.375rem;
    }

    .list-content {
      .empty-tip {
        padding: 1rem;
        font-size: var(--font-size-xs);
      }
    }
  }
}
</style>

