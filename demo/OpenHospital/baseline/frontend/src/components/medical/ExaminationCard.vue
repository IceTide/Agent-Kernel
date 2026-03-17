<script setup lang="ts">
import { computed, ref } from 'vue'
import type { ExaminationRecord } from '@/types'

interface Props {
  examination: ExaminationRecord
}

const props = defineProps<Props>()

const expanded = ref(false)

const statusConfig = {
  pending: { text: 'Pending', type: 'warning' },
  completed: { text: 'Completed', type: 'success' },
}

const status = computed(() => statusConfig[props.examination.status])

const normalizedResults = computed<Record<string, any> | null>(() => {
  const raw = props.examination.results as any

  if (!raw) {
    return null
  }

  if (typeof raw === 'object' && !Array.isArray(raw)) {
    return raw
  }

  return null
})
</script>

<template>
  <div class="examination-report" :class="{ expanded }">
    <div class="report-header" @click="expanded = !expanded">
      <div class="header-content">
        <div class="title-bar">
          <el-icon class="report-icon"><Document /></el-icon>
          <span class="report-title">LABORATORY EXAMINATION REPORT</span>
        </div>
        <div class="header-meta">
          <span class="doctor">DR: {{ props.examination.doctor_id }}</span>
          <span class="tick">TICK: {{ props.examination.ordered_tick }}</span>
        </div>
      </div>
      <div class="header-status">
        <div class="status-stamp" :class="status.type">
          {{ status.text.toUpperCase() }}
        </div>
        <el-icon class="expand-icon" :class="{ rotated: expanded }">
          <ArrowDown />
        </el-icon>
      </div>
    </div>
    
    <el-collapse-transition>
      <div v-show="expanded" class="report-body">
        <div class="decoration-lines"></div>
        <div class="report-section">
          <h5 class="section-title">EXAMINATION ITEMS</h5>
          <div class="item-grid">
            <div 
              v-for="item in props.examination.examination_items" 
              :key="item"
              class="pixel-item-tag"
            >
              • {{ item }}
            </div>
          </div>
        </div>
        <div v-if="normalizedResults" class="report-section">
          <h5 class="section-title">TEST RESULTS</h5>
          <div class="results-table">
            <div class="table-header">
              <span class="col-name">PARAMETER</span>
              <span class="col-value">RESULT</span>
              <span class="col-ref">FLAG</span>
            </div>
            <div 
              v-for="(result, name) in normalizedResults" 
              :key="name"
              class="table-row"
            >
              <span class="col-name">{{ name }}</span>
              <span class="col-value">{{ typeof result === 'object' ? result.result : result }}</span>
              <span class="col-ref">
                <span v-if="result.abnormal" class="abnormal-flag">▲ HIGH</span>
                <span v-else class="normal-flag">NORMAL</span>
              </span>
            </div>
          </div>
        </div>
        <div class="report-footer">
          <div v-if="props.examination.completed_tick" class="completion-box">
            <span>COMPLETED AT: TICK {{ props.examination.completed_tick }}</span>
          </div>
          <div class="hospital-stamp">
            <div class="stamp-circle">FINISHED</div>
          </div>
        </div>
      </div>
    </el-collapse-transition>
  </div>
</template>

<style scoped lang="scss">
.examination-report {
  background: #fff;
  border: 0.1875rem solid #333;
  margin-bottom: 0.75rem;
  box-shadow: 0.25rem 0.25rem 0 rgba(0, 0, 0, 0.1);
  image-rendering: pixelated;

  .report-header {
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 1rem;
    background: #f8f9fa;
    border-bottom: 0.1875rem solid #333;
    cursor: pointer;

    .header-content {
      flex: 1;

      .title-bar {
        display: flex;
        align-items: center;
        gap: 0.5rem;
        margin-bottom: 0.25rem;

        .report-icon {
          color: #333;
          font-size: 1.125rem;
        }

        .report-title {
          font-family: 'Courier New', Courier, monospace;
          font-weight: 900;
          font-size: 0.875rem;
          letter-spacing: 0.0625rem;
          color: #333;
        }
      }

      .header-meta {
        display: flex;
        gap: 1rem;
        font-family: monospace;
        font-size: 0.75rem;
        color: #666;
      }
    }

    .header-status {
      display: flex;
      align-items: center;
      gap: 1rem;

      .status-stamp {
        border: 0.125rem solid;
        padding: 0.125rem 0.5rem;
        font-size: 0.75rem;
        font-weight: bold;
        font-family: monospace;
        transform: rotate(-5deg);

        &.warning {
          border-color: #e6a23c;
          color: #e6a23c;
        }

        &.success {
          border-color: #3a7b5e;
          color: #3a7b5e;
          &::after {
            content: ' ✓';
          }
        }
      }

      .expand-icon {
        transition: transform 0.3s;
        font-size: 1rem;
        &.rotated {
          transform: rotate(180deg);
        }
      }
    }
  }

  .report-body {
    padding: 1.25rem;
    position: relative;
    background: #fff;

    .decoration-lines {
      position: absolute;
      top: 0;
      left: 0.625rem;
      bottom: 0;
      width: 0.125rem;
      border-left: 0.0625rem solid #ffcccc;
      border-right: 0.0625rem solid #ffcccc;
    }

    .report-section {
      margin-bottom: 1.25rem;
      padding-left: 0.9375rem;

      .section-title {
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold;
        font-size: 0.8125rem;
        color: #8b5a2b;
        border-bottom: 0.0625rem solid #eee;
        padding-bottom: 0.25rem;
        margin-bottom: 0.625rem;
        text-transform: uppercase;
      }
    }

    .item-grid {
      display: flex;
      flex-wrap: wrap;
      gap: 0.625rem;

      .pixel-item-tag {
        font-family: monospace;
        font-size: 0.75rem;
        color: #444;
        background: #f0f0f0;
        padding: 0.25rem 0.5rem;
        border: 0.0625rem solid #ccc;
      }
    }

    .results-table {
      border: 0.125rem solid #333;
      font-family: monospace;

      .table-header {
        display: flex;
        background: #eee;
        padding: 0.5rem;
        font-weight: bold;
        font-size: 0.75rem;
        border-bottom: 0.125rem solid #333;

        span { flex: 1; }
      }

      .table-row {
        display: flex;
        padding: 0.5rem;
        font-size: 0.8125rem;
        border-bottom: 0.0625rem solid #eee;

        span { flex: 1; }

        .col-value { font-weight: bold; }

        .abnormal-flag {
          color: #ff4b4b;
          font-weight: bold;
        }

        .normal-flag {
          color: #3a7b5e;
          font-size: 0.6875rem;
        }
      }
    }

    .report-footer {
      margin-top: 1.875rem;
      display: flex;
      justify-content: space-between;
      align-items: flex-end;
      padding-left: 0.9375rem;

      .completion-box {
        font-family: monospace;
        font-size: 0.75rem;
        color: #666;
        border-left: 0.1875rem solid #ccc;
        padding-left: 0.625rem;
      }

      .hospital-stamp {
        width: 5rem;
        height: 5rem;
        border: 0.125rem dashed #ff4b4b;
        border-radius: 50%;
        display: flex;
        align-items: center;
        justify-content: center;
        opacity: 0.6;
        transform: rotate(10deg);

        .stamp-circle {
          font-size: 0.625rem;
          color: #ff4b4b;
          font-weight: bold;
          text-align: center;
          border-top: 0.0625rem solid #ff4b4b;
          border-bottom: 0.0625rem solid #ff4b4b;
        }
      }
    }
  }
}
</style>
