<script setup lang="ts">
import { computed } from 'vue'
import type { DoctorSummary } from '@/types'

interface Props {
  doctor: DoctorSummary
  selected?: boolean
}

const props = withDefaults(defineProps<Props>(), {
  selected: false,
})

const emit = defineEmits<{
  click: []
}>()

const handleClick = () => {
  emit('click')
}

const statusConfig = {
  idle: { text: 'Idle', type: 'success' },
  consulting: { text: 'Consulting', type: 'warning' },
}

const status = computed(() => {
  return statusConfig[props.doctor.current_status || 'idle']
})

const avatarSrc = computed(() => {
  const id = props.doctor.id || ''
  let hash = 0
  for (let i = 0; i < id.length; i += 1) {
    hash = (hash * 31 + id.charCodeAt(i)) % 1000
  }
  return hash % 2 === 0 ? '/doctor_male.png' : '/doctor_female.png'
})
</script>

<template>
  <div class="card-wrapper">
    <div
      class="doctor-id-badge"
      :class="{ selected: props.selected }"
      @click="handleClick"
    >
      <div class="badge-top">
        <div class="hosp-name">HOSPITAL STAFF</div>
        <div class="chip"></div>
      </div>

      <div class="badge-body">
        <div class="badge-photo">
          <div class="photo-inner">
            <img :src="avatarSrc" alt="Doctor" class="avatar-image" />
          </div>
        </div>

        <div class="badge-info">
          <div class="name">{{ props.doctor.name }}</div>
          <div class="dept">{{ props.doctor.department.toUpperCase() }}</div>

          <div class="status-indicator" :class="status.type">
            <div class="led"></div>
            <span class="status-text">{{ status.text.toUpperCase() }}</span>
          </div>
        </div>
      </div>

      <div class="badge-footer">
        <div class="badge-id">DOC-{{ props.doctor.id.split('_').pop() }}</div>
        <div class="patient-count">
          <el-icon><User /></el-icon>
          <span>{{ props.doctor.patient_count || 0 }}</span>
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

.doctor-id-badge {
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

    .badge-top {
      background: #ffcc00;
      color: #000;
      .chip { background: #fff; border-color: #ffcc00; }
    }
  }

  &:hover {
    transform: translateX(0.375rem);
    background: #f0faff;
    box-shadow:
      inset 0.125rem 0.125rem 0 rgba(255, 255, 255, 0.8),
      0.5rem 0.5rem 0 rgba(0, 68, 170, 0.15);
  }

  .badge-top {
    background: #3da5ff;
    height: 1.875rem;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0.625rem;
    border-bottom: 0.1875rem solid #0044aa;
    color: #fff;
    text-shadow: 0.0625rem 0.0625rem 0 #0044aa;

    .hosp-name {
      color: #fff;
      font-family: monospace;
      font-size: 0.625rem;
      font-weight: bold;
      letter-spacing: 0.0625rem;
    }

    .chip {
      width: 1rem;
      height: 0.625rem;
      background: #ffea00;
      border: 0.125rem solid #0044aa;
      border-radius: 0.0625rem;
    }
  }

  .badge-body {
    padding: 0.75rem;
    display: flex;
    gap: 0.75rem;

    .badge-photo {
      width: 3.75rem;
      height: 3.75rem;
      background: #ffffff;
      border: 0.1875rem solid #0044aa;
      padding: 0.25rem;
      flex-shrink: 0;
      box-shadow: inset 0.125rem 0.125rem 0 rgba(0,0,0,0.05);

      .photo-inner {
        width: 100%;
        height: 100%;
        background: #fff;
        display: flex;
        align-items: center;
        justify-content: center;
        overflow: hidden;

        .avatar-image {
          width: 100%;
          height: 100%;
          object-fit: contain;
          image-rendering: pixelated;
        }
      }
    }

    .badge-info {
      flex: 1;
      display: flex;
      flex-direction: column;
      justify-content: center;
      gap: 0.25rem;

      .name {
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 1rem;
        color: #000;
      }

      .dept {
        font-family: monospace;
        font-size: 0.625rem;
        color: #3da5ff;
        font-weight: 900;
        text-transform: uppercase;
      }

      .status-indicator {
        display: inline-flex;
        align-items: center;
        justify-content: center;
        gap: 0.375rem;
        margin-top: 0.25rem;
        background: #0044aa;
        padding: 0.1875rem 0.5rem;
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

        &.success {
          .status-text { color: #fff; }
          .led { background: #39ff14; box-shadow: 0 0 0.375rem #39ff14; }
        }

        &.warning {
          .status-text { color: #fff; }
          .led { background: #ffea00; box-shadow: 0 0 0.375rem #ffea00; }
        }

        &.info {
          .status-text { color: #fff; }
          .led { background: #00e5ff; box-shadow: 0 0 0.375rem #00e5ff; }
        }
      }
    }
  }

  .badge-footer {
    height: 1.625rem;
    background: #e1f5fe;
    border-top: 0.1875rem solid #0044aa;
    display: flex;
    align-items: center;
    justify-content: space-between;
    padding: 0 0.625rem;

    .badge-id {
      font-family: monospace;
      font-size: 0.625rem;
      font-weight: bold;
      color: #0044aa;
    }

    .patient-count {
      display: flex;
      align-items: center;
      gap: 0.25rem;
      font-family: monospace;
      font-size: 0.625rem;
      color: #0044aa;
      font-weight: 900;

      .el-icon {
        font-size: 0.75rem;
      }
    }
  }
}
@media (max-width: 48rem) {
  .card-wrapper {
    padding: 0.25rem 0.5rem;
  }

  .doctor-id-badge {
    .badge-top {
      height: 1.5rem;
      padding: 0 0.5rem;

      .hosp-name {
        font-size: 0.5rem;
      }

      .chip {
        width: 0.75rem;
        height: 0.5rem;
      }
    }

    .badge-body {
      padding: 0.5rem;
      gap: 0.5rem;

      .badge-photo {
        width: 3rem;
        height: 3rem;
        padding: 0.1875rem;
      }

      .badge-info {
        gap: 0.1875rem;

        .name {
          font-size: 0.875rem;
        }

        .dept {
          font-size: 0.5rem;
        }

        .status-indicator {
          padding: 0.125rem 0.375rem;
          gap: 0.25rem;

          .led {
            width: 0.3125rem;
            height: 0.3125rem;
          }

          .status-text {
            font-size: 0.5rem;
          }
        }
      }
    }

    .badge-footer {
      height: 1.375rem;
      padding: 0 0.5rem;

      .badge-id {
        font-size: 0.5rem;
      }

      .patient-count {
        font-size: 0.5rem;

        .el-icon {
          font-size: 0.625rem;
        }
      }
    }
  }
}

@media (max-width: 30rem) {
  .doctor-id-badge {
    .badge-body {
      .badge-photo {
        width: 2.5rem;
        height: 2.5rem;
      }

      .badge-info {
        .name {
          font-size: 0.75rem;
        }
      }
    }
  }
}
</style>
