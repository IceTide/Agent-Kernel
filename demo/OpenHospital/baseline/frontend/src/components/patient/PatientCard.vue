<script setup lang="ts">
import { computed } from 'vue'
import type { PatientSummary } from '@/types'
import { PHASE_CONFIG } from '@/types/patient'

interface Props {
  patient: PatientSummary
  selected?: boolean
  index?: number
}

const props = withDefaults(defineProps<Props>(), {
  selected: false,
  index: 0,
})

const emit = defineEmits<{
  click: []
}>()

const handleClick = () => {
  emit('click')
}

const phaseInfo = computed(() => {
  return PHASE_CONFIG[props.patient.current_phase || 'idle']
})
const avatarUrl = computed(() => {
  const genderPrefix = props.patient.demographics.gender === 'Male' ? 'm' : 'f'
  return `https://api.dicebear.com/7.x/pixel-art/svg?seed=${genderPrefix}_${props.patient.id}&backgroundColor=b6e3f4,c0aede,d1d4f9`
})
const barcodeBars = computed(() => {
  const bars = []
  const id = props.patient.id
  for (let i = 0; i < 15; i++) {
    const charCode = id.charCodeAt(i % id.length) || 65
    const width = ((charCode * (i + 1)) % 30 + 10) / 10
    bars.push(width.toFixed(2) + 'px')
  }
  return bars
})
</script>

<template>
  <div class="card-wrapper">
    <div
      class="patient-id-card"
      :class="{ selected: props.selected }"
      @click="handleClick"
    >
      <div class="card-top-header">
        <div class="header-inner">
          <el-icon class="hosp-icon"><FirstAidKit /></el-icon>
          <span>PATIENT ID CARD</span>
        </div>
        <div class="chip"></div>
      </div>
      <div class="card-main">
        <div class="photo-section">
          <div class="photo-frame">
            <img :src="avatarUrl" :alt="props.patient.name" class="pixel-avatar" loading="lazy" />
          </div>
          <div class="status-indicator" :class="phaseInfo.type">
            <div class="led"></div>
            <span class="status-text">{{ phaseInfo.label.toUpperCase() }}</span>
          </div>
        </div>
        <div class="info-section">
          <div class="info-row">
            <label>NAME</label>
            <div class="val name">{{ props.patient.name }}</div>
          </div>
          <div class="info-row grid">
            <div class="sub-row">
              <label>AGE</label>
              <div class="val">{{ props.patient.demographics.age }}</div>
            </div>
            <div class="sub-row">
              <label>SEX</label>
              <div class="val">{{ props.patient.demographics.gender === 'Male' ? 'M' : 'F' }}</div>
            </div>
          </div>
          <div v-if="props.patient.department" class="info-row">
            <label>DEPT</label>
            <div class="val dept">{{ props.patient.department }}</div>
          </div>
        </div>
      </div>
      <div class="card-footer-strip">
        <div class="id-number">{{ props.patient.id }}</div>
        <div class="barcode">
          <div v-for="(width, idx) in barcodeBars" :key="idx" class="bar" :style="{ width }"></div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.card-wrapper {
  padding: 0.375rem 0.75rem;
  box-sizing: border-box;
}

.patient-id-card {
  background: #ffffff;
  border: 0.1875rem solid #0044aa;
  border-radius: 0;
  cursor: pointer;
  position: relative;
  transition: transform 0.2s cubic-bezier(0.2, 1, 0.3, 1), box-shadow 0.2s cubic-bezier(0.2, 1, 0.3, 1), background 0.2s ease;
  image-rendering: pixelated;
  overflow: hidden;
  box-shadow:
    inset 0.125rem 0.125rem 0 rgba(255, 255, 255, 0.8),
    0.25rem 0.25rem 0 rgba(0, 68, 170, 0.2);

  &.selected {
    border-color: #ffcc00;
    background: #f0faff;
    box-shadow:
      0 0 0 0.125rem #ffcc00,
      0.375rem 0.375rem 0 rgba(255, 204, 0, 0.2);

    .card-top-header {
      background: #ffcc00;
      color: #000;
      .chip { background: #fff; border-color: #ffcc00; }
    }
  }

  &:hover {
    transform: translateX(0.375rem);
    background: #f0f9ff;
    box-shadow:
      inset 0.125rem 0.125rem 0 rgba(255, 255, 255, 0.8),
      0.5rem 0.5rem 0 rgba(0, 68, 170, 0.15);
  }

  .card-top-header {
    background: #3da5ff;
    height: 1.875rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0.625rem;
    border-bottom: 0.1875rem solid #0044aa;
    color: #fff;
    text-shadow: 0.0625rem 0.0625rem 0 #0044aa;

    .header-inner {
      display: flex;
      align-items: center;
      gap: 0.375rem;
      font-family: monospace;
      font-size: 0.6875rem;
      font-weight: bold;
      letter-spacing: 0.0625rem;

      .hosp-icon {
        font-size: 0.875rem;
        filter: drop-shadow(0.0625rem 0.0625rem 0 #0044aa);
      }
    }

    .chip {
      width: 1.25rem;
      height: 0.875rem;
      background: #ffea00;
      border: 0.125rem solid #0044aa;
      border-radius: 0.125rem;
    }
  }

  .card-main {
    padding: 0.75rem;
    display: flex;
    gap: 0.75rem;

    .photo-section {
      display: flex;
      flex-direction: column;
      gap: 0.5rem;

      .photo-frame {
        width: 3.375rem;
        height: 3.375rem;
        background: #e1f5fe;
        border: 0.1875rem solid #0044aa;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;
        box-shadow: inset 0.125rem 0.125rem 0 rgba(0,0,0,0.05);

        .pixel-avatar {
          width: 100%;
          height: 100%;
          image-rendering: pixelated;
          object-fit: cover;
        }
      }

      .status-indicator {
        display: flex;
        align-items: center;
        justify-content: center;
        gap: 0.25rem;
        background: #0044aa;
        padding: 0.1875rem 0.375rem;
        border-radius: 0;

        .led {
          width: 0.375rem;
          height: 0.375rem;
          border-radius: 50%;
          background: #666;
        }

        .status-text {
          font-family: monospace;
          font-size: 0.5625rem;
          color: #fff;
          font-weight: bold;
        }

        &.success .led { background: #39ff14; box-shadow: 0 0 0.375rem #39ff14; }
        &.warning .led { background: #ffea00; box-shadow: 0 0 0.375rem #ffea00; }
        &.info .led { background: #00e5ff; box-shadow: 0 0 0.375rem #00e5ff; }
        &.danger .led { background: #ff4b4b; box-shadow: 0 0 0.375rem #ff4b4b; }
      }
    }

    .info-section {
      flex: 1;
      display: flex;
      flex-direction: column;
      gap: 0.375rem;

      .info-row {
        display: flex;
        flex-direction: column;

        &.grid {
          flex-direction: row;
          gap: 0.625rem;
        }

        label {
          font-family: monospace;
          font-size: 0.5625rem;
          color: #3da5ff;
          font-weight: 900;
          text-transform: uppercase;
        }

        .val {
          font-family: 'Courier New', Courier, monospace;
          font-size: 0.8125rem;
          color: #0044aa;
          font-weight: 900;
          border-bottom: 0.125rem solid #e1f5fe;
          padding-bottom: 0.125rem;

          &.name {
            font-size: 0.9375rem;
            color: #000;
            white-space: normal;
            overflow-wrap: anywhere;
            word-break: break-word;
            line-height: 1.2;
          }

          &.dept {
            font-size: 0.6875rem;
            color: #27ae60;
          }
        }

        .sub-row {
          flex: 1;
          display: flex;
          flex-direction: column;
        }
      }
    }
  }

  .card-footer-strip {
    height: 1.625rem;
    background: #e1f5fe;
    border-top: 0.1875rem solid #0044aa;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0.625rem;

    .id-number {
      font-family: monospace;
      font-size: 0.625rem;
      font-weight: bold;
      color: #0044aa;
    }

    .barcode {
      display: flex;
      align-items: center;
      gap: 0.0625rem;
      height: 0.875rem;

      .bar {
        height: 100%;
        background: #0044aa;
      }
    }
  }
}
@media (max-width: 48rem) {
  .card-wrapper {
    padding: 0.25rem 0.5rem;
  }

  .patient-id-card {
    .card-top-header {
      height: 1.5rem;
      padding: 0 0.5rem;

      .header-inner {
        font-size: 0.5625rem;
        gap: 0.25rem;

        .hosp-icon {
          font-size: 0.75rem;
        }
      }

      .chip {
        width: 1rem;
        height: 0.75rem;
      }
    }

    .card-main {
      padding: 0.5rem;
      gap: 0.5rem;

      .photo-section {
        .photo-frame {
          width: 2.75rem;
          height: 2.75rem;
        }

        .status-indicator {
          padding: 0.125rem 0.25rem;

          .led {
            width: 0.3125rem;
            height: 0.3125rem;
          }

          .status-text {
            font-size: 0.4375rem;
          }
        }
      }

      .info-section {
        gap: 0.25rem;

        .info-row {
          label {
            font-size: 0.5rem;
          }

          .val {
            font-size: 0.6875rem;

            &.name {
              font-size: 0.75rem;
            }

            &.dept {
              font-size: 0.5625rem;
            }
          }
        }
      }
    }

    .card-footer-strip {
      height: 1.375rem;
      padding: 0 0.5rem;

      .id-number {
        font-size: 0.5rem;
      }

      .barcode {
        height: 0.625rem;
      }
    }
  }
}

@media (max-width: 30rem) {
  .patient-id-card {
    .card-main {
      .photo-section {
        .photo-frame {
          width: 2.25rem;
          height: 2.25rem;
        }
      }

      .info-section {
        .info-row {
          .val {
            font-size: 0.625rem;

            &.name {
              font-size: 0.6875rem;
            }
          }
        }
      }
    }
  }
}
</style>
