<script setup lang="ts">
import { computed, ref, watch, onUnmounted } from 'vue'
import type { PatientDetail } from '@/types'

interface Props {
  patient: PatientDetail
}

const props = defineProps<Props>()

const trajectoryNodesCount = computed(() => props.patient?.trajectory?.length || 0)
const avatarUrl = computed(() => {
  if (!props.patient) return ''
  const genderPrefix = props.patient.demographics?.gender === 'Male' ? 'm' : 'f'
  return `https://api.dicebear.com/7.x/pixel-art/svg?seed=${genderPrefix}_${props.patient.id}&backgroundColor=b6e3f4,c0aede,d1d4f9`
})

const activeNodeIdx = ref(0)
const mapContainer = ref<HTMLElement | null>(null)
let trajectoryTimer: any = null
const isDragging = ref(false)
watch(activeNodeIdx, (newIdx) => {
  if (mapContainer.value) {
    const nodeWidth = 180
    const containerWidth = mapContainer.value.clientWidth
    const characterX = 15 + newIdx * nodeWidth
    const characterWidth = 70
    const targetScrollLeft = characterX + (characterWidth / 2) - (containerWidth / 2)
    
    mapContainer.value.scrollTo({
      left: Math.max(0, targetScrollLeft),
      behavior: isDragging.value ? 'auto' : 'smooth'
    })
  }
})

const characterStyle = computed(() => {
  const idx = activeNodeIdx.value
  const isOdd = idx % 2 === 0
  const x = 15 + idx * 180 
  const y = isOdd ? -65 : -5 
  return {
    left: `${x}px`,
    top: '50%',
    marginTop: `${y}px`,
    transition: idx === 0 || isDragging.value ? 'none' : 'all 1.5s cubic-bezier(0.4, 0, 0.2, 1)'
  }
})

function startTrajectoryLoop() {
  if (trajectoryTimer) clearInterval(trajectoryTimer)
  if (!isDragging.value && trajectoryNodesCount.value > 1) {
    trajectoryTimer = setInterval(() => {
      activeNodeIdx.value = (activeNodeIdx.value + 1) % trajectoryNodesCount.value
    }, 1500)
  }
}

function handleSliderInput(val: number | number[]) {
  isDragging.value = true
  if (trajectoryTimer) {
    clearInterval(trajectoryTimer)
    trajectoryTimer = null
  }
  activeNodeIdx.value = Array.isArray(val) ? val[0] : val
}

function handleSliderChange() {
  isDragging.value = false
  startTrajectoryLoop()
}

watch(() => trajectoryNodesCount.value, (newCount) => {
  if (newCount > 0) {
    activeNodeIdx.value = 0
    startTrajectoryLoop()
  }
}, { immediate: true })

onUnmounted(() => {
  if (trajectoryTimer) clearInterval(trajectoryTimer)
})
</script>

<template>
  <div v-if="patient.trajectory?.length" class="patient-trajectory-component">
    <div class="section-title">
      <h3>Patient Trajectory ({{ patient.trajectory.length }})</h3>
    </div>
    
    <div class="smartphone-wrapper">
      <div class="smartphone-frame">
        <div class="phone-notch"></div>
        <div class="phone-screen">
          <div class="pixel-game-map" ref="mapContainer">
            <div class="pixel-character" :style="characterStyle">
              <div class="character-avatar-box">
                <img :src="avatarUrl" class="character-avatar-img" />
              </div>
            </div>

            <div class="map-path">
              <div 
                v-for="(event, idx) in patient.trajectory" 
                :key="idx"
                class="map-node"
                :class="{ 
                  'is-last': idx === patient.trajectory.length - 1,
                  'is-active': idx === activeNodeIdx,
                  'success': event.status === 'success',
                  'warning': event.status !== 'success',
                  'is-odd': idx % 2 === 0,
                  'is-even': idx % 2 !== 0
                }"
              >
                <div class="node-info">
                  <div class="info-tick">TICK {{ event.tick }}</div>
                  <div class="info-event">{{ event.event_type }}</div>
                </div>

                <div class="node-icon">
                  <template v-if="idx === patient.trajectory.length - 1">
                    <span class="flag">🚩</span>
                  </template>
                  <template v-else>
                    {{ idx + 1 }}
                  </template>
                </div>
                
                <div v-if="idx < patient.trajectory.length - 1" class="path-line"></div>
              </div>
            </div>
          </div>
          <div class="phone-controls">
            <div class="slider-label">TICK PROGRESS</div>
            <el-slider 
              v-model="activeNodeIdx" 
              :max="trajectoryNodesCount > 0 ? trajectoryNodesCount - 1 : 0" 
              :step="1"
              :show-tooltip="false"
              @input="handleSliderInput"
              @change="handleSliderChange"
            />
          </div>
        </div>
        <div class="phone-home-indicator"></div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.patient-trajectory-component {
  margin-top: 1.5rem;

  .section-title {
    margin-bottom: 1rem;
    h3 {
      margin: 0;
      font-family: 'Courier New', Courier, monospace;
      font-weight: 900;
      font-size: 1rem;
      color: #166534;
      text-transform: uppercase;
      display: flex;
      align-items: center;
      gap: 0.625rem;

      &::before {
        content: '';
        width: 0.625rem;
        height: 1.25rem;
        background: #ffcc00;
        display: inline-block;
        border: 0.125rem solid #166534;
      }
    }
  }
}

.smartphone-wrapper {
  max-width: 56.25rem;
  margin: 0 auto;
  padding: 1.25rem 0;
}

.smartphone-frame {
  background: #1e293b;
  border-radius: 2.5rem;
  padding: 0.75rem;
  position: relative;
  box-shadow: 0 1.25rem 3.125rem rgba(0,0,0,0.2);
  border: 0.25rem solid #334155;

  .phone-notch {
    position: absolute;
    top: 50%;
    right: 0;
    transform: translateY(-50%);
    width: 1.5625rem;
    height: 9.375rem;
    background: #1e293b;
    border-top-left-radius: 1.25rem;
    border-bottom-left-radius: 1.25rem;
    z-index: 10;
  }

  .phone-screen {
    background: #fff;
    border-radius: 1.875rem;
    overflow: hidden;
    height: 23.75rem;
    display: flex;
    flex-direction: column;
  }

  .phone-home-indicator {
    position: absolute;
    bottom: 0.5rem;
    left: 50%;
    transform: translateX(-50%);
    width: 6.25rem;
    height: 0.25rem;
    background: #334155;
    border-radius: 0.125rem;
  }

  .phone-controls {
    background: #f8fafc;
    padding: 0.9375rem 1.5rem 1.5625rem;
    border-top: 0.0625rem solid #e2e8f0;

    .slider-label {
      font-family: 'Press Start 2P', cursive;
      font-size: 0.5rem;
      color: #64748b;
      margin-bottom: 0.75rem;
      text-align: center;
      letter-spacing: 0.0625rem;
    }

    :deep(.el-slider) {
      --el-slider-main-bg-color: #4285f4;
      --el-slider-runway-bg-color: #e2e8f0;
      --el-slider-stop-bg-color: #4285f4;
      height: 1.25rem;

      .el-slider__button {
        border: 0.1875rem solid #4285f4;
        width: 1.125rem;
        height: 1.125rem;
        background-color: #fff;
        box-shadow: 0 0.125rem 0.25rem rgba(0,0,0,0.1);
      }

      .el-slider__runway {
        height: 0.375rem;
      }

      .el-slider__bar {
        height: 0.375rem;
      }
    }
  }
}

.pixel-game-map {
  background: #e5eef5;
  border: none;
  flex: 1;
  padding: 5rem 2.5rem;
  image-rendering: auto;
  position: relative;
  overflow-x: auto;
  overflow-y: hidden;
  box-shadow: inset 0 0.125rem 0.625rem rgba(0,0,0,0.05);

  .pixel-character {
    position: absolute;
    width: 4.375rem;
    height: 4.375rem;
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 30;
    pointer-events: none;
    animation: character-float 2.5s ease-in-out infinite;

    .character-avatar-box {
      width: 100%;
      height: 100%;
      background: #fff;
      border: 0.1875rem solid #4285f4;
      padding: 0.125rem;
      border-radius: 50%;
      box-shadow: 0 0.25rem 0.75rem rgba(66, 133, 244, 0.3);
      overflow: hidden;
      display: flex;
      align-items: center;
      justify-content: center;
      position: relative;

      &::after {
        content: '';
        position: absolute;
        bottom: -0.5rem;
        left: 50%;
        transform: translateX(-50%);
        border: 0.5rem solid transparent;
        border-top-color: #4285f4;
      }

      .character-avatar-img {
        width: 100%;
        height: 100%;
        object-fit: cover;
        border-radius: 50%;
      }
    }
  }

  .map-path {
    display: flex;
    align-items: center;
    gap: 7.5rem;
    min-width: fit-content;
    position: relative;
    z-index: 5;
    padding: 1.25rem 6.25rem 1.25rem 1.25rem;

    &::before {
      content: '';
      position: absolute;
      top: -6.25rem; left: -6.25rem; right: -6.25rem; bottom: -6.25rem;
      background-image:
        linear-gradient(#fff 0.125rem, transparent 0.125rem),
        linear-gradient(90deg, #fff 0.125rem, transparent 0.125rem);
      background-size: 3.125rem 3.125rem;
      z-index: -1;
      opacity: 0.6;
    }
  }

  .map-node {
    display: flex;
    align-items: center;
    justify-content: center;
    position: relative;
    width: 3.75rem;
    height: 3.75rem;
    flex-shrink: 0;

    &.is-odd {
      transform: translateY(-1.875rem);
      .path-line { transform: rotate(18.5deg); width: 11.875rem; left: 1.875rem; }
    }
    &.is-even {
      transform: translateY(1.875rem);
      .path-line { transform: rotate(-18.5deg); width: 11.875rem; left: 1.875rem; }
    }

    .node-info {
      position: absolute;
      width: 9.375rem;
      text-align: center;
      left: 50%;
      transform: translateX(-50%);
      font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Arial, sans-serif;
      pointer-events: none;
      z-index: 20;
      background: rgba(255, 255, 255, 0.95);
      padding: 0.5rem 0.75rem;
      border-radius: 1.25rem;
      box-shadow: 0 0.25rem 0.9375rem rgba(0,0,0,0.08);
      opacity: 0;
      transition: all 0.4s ease;
      transform: translateX(-50%) translateY(0.625rem);

      .info-tick {
        font-size: 0.625rem;
        color: #70757a;
        margin-bottom: 0.125rem;
        font-weight: 600;
      }

      .info-event {
        font-size: 0.6875rem;
        color: #202124;
        line-height: 1.2;
        font-weight: 500;
      }
    }

    &.is-active {
      .node-info {
        opacity: 1;
        transform: translateX(-50%) translateY(0);
      }

      .node-icon {
        transform: scale(1.2);
        background: #4285f4;
        color: #fff;
        box-shadow: 0 0 0 0.375rem rgba(66, 133, 244, 0.2);
      }
    }

    &.is-odd .node-info { bottom: 4.375rem; }
    &.is-even .node-info { top: 4.375rem; }

    .node-icon {
      width: 2rem;
      height: 2rem;
      background: #fff;
      border: 0.125rem solid #4285f4;
      border-radius: 50%;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 0.75rem;
      font-weight: bold;
      color: #4285f4;
      z-index: 10;
      transition: all 0.3s cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0 0.125rem 0.375rem rgba(0,0,0,0.1);

      .flag {
        font-size: 1.125rem;
      }
    }

    .path-line {
      position: absolute;
      height: 0.375rem;
      background: #4285f4;
      opacity: 0.4;
      z-index: 2;
      transform-origin: left center;
      border-radius: 0.1875rem;

      &::after {
        content: '';
        position: absolute;
        top: 0; left: 0; right: 0; bottom: 0;
        background-image: linear-gradient(90deg, #fff 50%, transparent 50%);
        background-size: 0.625rem 100%;
        opacity: 0.3;
      }
    }

    &.success {
      .node-icon { border-color: #34a853; color: #34a853; }
      &.is-active .node-icon { background: #34a853; color: #fff; box-shadow: 0 0 0 0.375rem rgba(52, 168, 83, 0.2); }
    }

    &.warning {
      .node-icon { border-color: #fbbc05; color: #fbbc05; }
      &.is-active .node-icon { background: #fbbc05; color: #fff; box-shadow: 0 0 0 0.375rem rgba(251, 188, 5, 0.2); }
    }
  }
}

@keyframes character-float {
  0%, 100% { transform: translateY(0) rotate(0deg); }
  50% { transform: translateY(-1.875rem) rotate(5deg); }
}
</style>
