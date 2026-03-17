<script setup lang="ts">
import { useDoctorStore } from '@/stores/doctor'
import { SearchBar } from '@/components/common'
import DoctorCard from './DoctorCard.vue'
import { DynamicScroller, DynamicScrollerItem } from 'vue-virtual-scroller'
import 'vue-virtual-scroller/dist/vue-virtual-scroller.css'

const doctorStore = useDoctorStore()

const emit = defineEmits<{
  select: [doctorId: string]
}>()

function handleSelect(doctorId: string) {
  doctorStore.selectDoctor(doctorId)
  emit('select', doctorId)
}
</script>

<template>
  <div class="doctor-list">
    <div class="list-header">
      <h3 class="title">
        <el-icon><UserFilled /></el-icon>
        Doctor List
      </h3>
      <el-badge :value="doctorStore.filteredDoctors.length" type="info" />
    </div>

    <div class="filters">
      <SearchBar
        v-model="doctorStore.searchQuery"
        placeholder="SearchDoctor..."
      />

      <el-select
        v-model="doctorStore.selectedDepartment"
        placeholder="AllDepartment"
        clearable
        size="small"
        class="department-select"
      >
        <el-option
          v-for="dept in doctorStore.departments"
          :key="dept"
          :label="dept"
          :value="dept"
        />
      </el-select>
    </div>

    <div class="list-content">
      <DynamicScroller
        v-if="doctorStore.filteredDoctors.length > 0"
        class="scroller"
        :items="doctorStore.filteredDoctors"
        :min-item-size="140"
        key-field="id"
      >
        <template #default="{ item, index, active }">
          <DynamicScrollerItem
            :item="item"
            :active="active"
            :data-index="index"
          >
            <DoctorCard
              :doctor="item"
              :selected="doctorStore.selectedDoctorId === item.id"
              @click="handleSelect(item.id)"
            />
          </DynamicScrollerItem>
        </template>
      </DynamicScroller>

      <div v-else class="empty-tip">
        No Doctor Data
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.doctor-list {
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

    .department-select {
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
  .doctor-list {
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
