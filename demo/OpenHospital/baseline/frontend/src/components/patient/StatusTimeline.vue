<script setup lang="ts">
import { computed } from 'vue'
import type { PatientPhase, TrajectoryEvent } from '@/types'
import { PHASE_CONFIG } from '@/types/patient'

interface Props {
  currentPhase: PatientPhase
  events?: TrajectoryEvent[]
}

const props = withDefaults(defineProps<Props>(), {
  events: () => [],
})
const steps = [
  { phase: 'home' as PatientPhase, title: 'Home' },
  { phase: 'registered' as PatientPhase, title: 'Registered' },
  { phase: 'consulting' as PatientPhase, title: 'Consulting' },
  { phase: 'examined' as PatientPhase, title: 'Examined' },
  { phase: 'treated' as PatientPhase, title: 'Treated' },
  { phase: 'finish' as PatientPhase, title: 'Completed' },
]

const phaseOrder: PatientPhase[] = ['home', 'registered', 'consulting', 'examined', 'treated', 'finish']

const currentStepIndex = computed(() => {
  const idx = phaseOrder.indexOf(props.currentPhase)
  return idx >= 0 ? idx : 0
})

function getStepStatus(phase: PatientPhase) {
  const stepIdx = phaseOrder.indexOf(phase)
  if (stepIdx < currentStepIndex.value) return 'finish'
  if (stepIdx === currentStepIndex.value) return 'process'
  return 'wait'
}
</script>

<template>
  <div class="status-timeline">
    <div class="pixel-steps">
      <div 
        v-for="(step, index) in steps" 
        :key="step.phase"
        class="pixel-step"
        :class="getStepStatus(step.phase)"
      >
        <div v-if="index > 0" class="connector"></div>
        <div class="step-box">
          <div v-if="getStepStatus(step.phase) === 'process'" class="current-arrow">
            ▼
          </div>
          <div class="icon-wrapper">
            <el-icon :size="28">
              <component :is="PHASE_CONFIG[step.phase].icon" />
            </el-icon>
          </div>
          <div class="step-info">
            <div class="step-title">{{ step.title }}</div>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.status-timeline {
  padding: 1.875rem 1.25rem;
  background: #fdf6e3; // 淡黄色（复古纸张色）
  border: 0.5rem solid #d4a373; // 浅褐色边框
  position: relative;
  image-rendering: pixelated;
  overflow-x: auto;
  box-shadow:
    inset 0.25rem 0.25rem 0 rgba(255, 255, 255, 0.1),
    inset -0.25rem -0.25rem 0 rgba(0, 0, 0, 0.2),
    0.5rem 0.5rem 0 rgba(0, 0, 0, 0.15);
  &::after {
    content: '';
    position: absolute;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background-image:
      linear-gradient(rgba(0,0,0,0.05) 50%, transparent 50%),
      linear-gradient(90deg, rgba(0,0,0,0.05) 50%, transparent 50%);
    background-size: 100% 0.25rem, 0.25rem 100%;
    pointer-events: none;
    opacity: 0.3;
  }

  .pixel-steps {
    display: flex;
    justify-content: space-between;
    align-items: flex-start;
    min-width: 50rem;
    padding: 1.25rem 0;
    position: relative;
    z-index: 2;
  }

  .pixel-step {
    flex: 1;
    position: relative;
    display: flex;
    flex-direction: column;
    align-items: center;

    .connector {
      position: absolute;
      left: -50%;
      right: 50%;
      top: 1.5625rem;
      height: 0.375rem;
      background: #ccc;
      border: 0.125rem solid #333;
      z-index: 1;
    }

    .step-box {
      position: relative;
      z-index: 2;
      display: flex;
      flex-direction: column;
      align-items: center;
      gap: 0.75rem;

      .current-arrow {
        position: absolute;
        top: -1.5625rem;
        font-size: 1.125rem;
        color: #ff4b4b;
        animation: bounce 0.6s infinite alternate;
        text-shadow: 0.125rem 0.125rem 0 #000;
      }
    }

    .icon-wrapper {
      width: 3.125rem;
      height: 3.125rem;
      background: #fff;
      border: 0.1875rem solid #333;
      display: flex;
      align-items: center;
      justify-content: center;
      box-shadow: 0.25rem 0.25rem 0 #ccc;
      transition: all 0.2s;

      .el-icon {
        color: #666;
      }
    }

    .step-info {
      text-align: center;

      .step-title {
        font-family: 'Courier New', Courier, monospace;
        font-weight: bold;
        font-size: 1rem;
        color: #333;
        text-transform: uppercase;
        margin-bottom: 0.25rem;
        transition: all 0.2s;
      }

      .tick-label {
        font-family: monospace;
        font-size: 0.8125rem;
        font-weight: bold;
        color: #1e3c2e;
        background: #eef9f5;
        padding: 0.125rem 0.375rem;
        border: 0.0625rem solid #3a7b5e;
      }

      .tick-placeholder {
        font-size: 0.75rem;
        color: #999;
      }
    }
    &.finish {
      .connector {
        background: #3a7b5e;
      }
      .icon-wrapper {
        background: #eef9f5;
        border-color: #3a7b5e;
        box-shadow: 0.25rem 0.25rem 0 #b3d9cc;
        .el-icon {
          color: #3a7b5e;
        }
      }
      .step-title {
        color: #3a7b5e;
      }
    }

    &.process {
      .connector {
        background: repeating-linear-gradient(
          45deg,
          #ff4b4b,
          #ff4b4b 0.625rem,
          #fff 0.625rem,
          #fff 1.25rem
        );
        animation: slide 1s linear infinite;
      }
      .icon-wrapper {
        background: #ff4b4b; // 改为醒目的红色
        border-color: #000;
        box-shadow: 0 0 0 0.25rem #ff4b4b44, 0.375rem 0.375rem 0 #333;
        transform: scale(1.2);
        animation: pulse 1.5s infinite;

        .el-icon {
          color: #fff;
        }
      }
      .step-title {
        color: #ff4b4b;
        font-size: 1.125rem;
        text-decoration: underline;
        text-shadow: 0.0625rem 0.0625rem 0 rgba(0,0,0,0.1);
      }
    }

    &.wait {
      opacity: 0.7;
      .icon-wrapper {
        border-style: dashed;
      }
    }
  }
}

@keyframes bounce {
  from { transform: translateY(0); }
  to { transform: translateY(-0.3125rem); }
}

@keyframes slide {
  from { background-position: 0 0; }
  to { background-position: 2.5rem 0; }
}

@keyframes pulse {
  0% { box-shadow: 0 0 0 0rem #ff4b4b66, 0.375rem 0.375rem 0 #333; }
  70% { box-shadow: 0 0 0 0.625rem #ff4b4b00, 0.375rem 0.375rem 0 #333; }
  100% { box-shadow: 0 0 0 0rem #ff4b4b00, 0.375rem 0.375rem 0 #333; }
}
@media (max-width: 64rem) {
  .status-timeline {
    .pixel-steps {
      min-width: 40rem;
    }

    .pixel-step {
      .icon-wrapper {
        width: 2.5rem;
        height: 2.5rem;

        .el-icon {
          font-size: 1rem;
        }
      }

      .step-title {
        font-size: 0.625rem;
      }

      .connector {
        top: 1.25rem;
        height: 0.25rem;
      }

      .step-box .current-arrow {
        top: -1.25rem;
        font-size: 0.875rem;
      }
    }
  }
}

@media (max-width: 48rem) {
  .status-timeline {
    padding: 0.5rem;
    border-width: 0.375rem;

    .pixel-steps {
      min-width: 30rem;
      padding: 0.75rem 0;
    }

    .pixel-step {
      .icon-wrapper {
        width: 2rem;
        height: 2rem;
        border-width: 0.125rem;
        box-shadow: 0.125rem 0.125rem 0 #ccc;

        .el-icon {
          font-size: 0.875rem;
        }
      }

      .step-title {
        font-size: 0.5rem;
        max-width: 3rem;
      }

      .connector {
        top: 1rem;
        height: 0.1875rem;
        border-width: 0.0625rem;
      }

      .step-box {
        gap: 0.5rem;

        .current-arrow {
          top: -1rem;
          font-size: 0.75rem;
        }
      }

      &.process {
        .step-title {
          font-size: 0.625rem;
        }
      }
    }
  }
}

@media (max-width: 30rem) {
  .status-timeline {
    padding: 0.375rem;
    overflow-x: auto;

    .pixel-steps {
      min-width: 25rem;
      padding: 0.5rem 0;
    }

    .pixel-step {
      .icon-wrapper {
        width: 1.75rem;
        height: 1.75rem;
      }

      .step-title {
        font-size: 0.4375rem;
        max-width: 2.5rem;
      }
    }
  }
}
</style>

