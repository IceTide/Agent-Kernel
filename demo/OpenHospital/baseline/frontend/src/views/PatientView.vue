<script setup lang="ts">
import { onMounted, computed, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { ProfileCard, StatusTimeline, PatientTrajectory } from '@/components/patient'
import { ConversationView } from '@/components/conversation'
import { ExaminationCard, TreatmentCard } from '@/components/medical'
import { usePatientStore, useConversationStore, useDoctorStore } from '@/stores'
import { ArrowLeft, UserFilled, OfficeBuilding, Location, Loading, CircleClose, Warning } from '@element-plus/icons-vue'

const route = useRoute()
const router = useRouter()
const patientStore = usePatientStore()
const conversationStore = useConversationStore()
const doctorStore = useDoctorStore()

const patientId = computed(() => route.params.id as string)
const fromDoctor = computed(() => route.query.from === 'doctor')
const fromDoctorId = computed(() => route.query.doctorId as string)
const groundTruthData = ref<Record<string, any>>({})

const currentMessages = computed(() => {
  const patient = patientStore.currentPatient
  if (patient?.assigned_doctor) {
    const conv = conversationStore.getConversation(patient.id, patient.assigned_doctor)
    return conv?.messages || []
  }
  return []
})

const referenceTreatment = computed(() => {
  const patientData = groundTruthData.value[patientId.value]
  return patientData?.treatment_plan || ''
})

async function loadGroundTruth() {
  try {
    const response = await fetch('/data/ground_truth/ground_truth.json')
    if (response.ok) {
      const data = await response.json()
      groundTruthData.value = data
    }
  } catch (error) {
    console.warn('Failed to load ground truth data:', error)
    try {
      const apiResponse = await fetch('/api/doctors/ground-truth')
      if (apiResponse.ok) {
        groundTruthData.value = await apiResponse.json()
      }
    } catch (apiError) {
      console.warn('Failed to load ground truth from API:', apiError)
    }
  }
}

onMounted(async () => {
  if (patientId.value) {
    patientStore.selectedPatientId = patientId.value
    await Promise.all([
      patientStore.fetchPatientDetail(patientId.value),
      loadGroundTruth()
    ])
    
    const patient = patientStore.currentPatient
    if (patient?.assigned_doctor) {
      await conversationStore.fetchConversation(patient.id, patient.assigned_doctor)
    }
  }
})

function goBack() {
  if (fromDoctor.value && fromDoctorId.value) {
    doctorStore.selectDoctor(fromDoctorId.value)
    router.push({ path: '/', query: { tab: 'doctor' } })
  } else {
    router.back()
  }
}

function goToDoctor(doctorId: string) {
  router.push(`/doctor/${doctorId}`)
}

async function retryLoad() {
  if (patientId.value) {
    patientStore.selectedPatientId = patientId.value
    await Promise.all([
      patientStore.fetchPatientDetail(patientId.value),
      loadGroundTruth()
    ])

    const patient = patientStore.currentPatient
    if (patient?.assigned_doctor) {
      await conversationStore.fetchConversation(patient.id, patient.assigned_doctor)
    }
  }
}
</script>

<template>
  <MainLayout>
    <div class="patient-view">
      <div class="view-header">
        <el-button :icon="ArrowLeft" @click="goBack">Back</el-button>
        <h1 v-if="patientStore.currentPatient">
          {{ patientStore.currentPatient.name }} - Patient Details
        </h1>
      </div>
      
      <el-scrollbar v-if="patientStore.currentPatient" class="view-content no-grey-bottom">
        <div class="content-wrapper">
          <section class="section">
            <h2>Patient Info</h2>
            <ProfileCard :patient="patientStore.currentPatient" />
          </section>
          <section class="section">
            <h2>Visit Timeline</h2>
            <div class="pixel-notice-board">
              <div class="board-header">
                <div class="pin pin-left"></div>
                <span>HOSPITAL STATUS BOARD</span>
                <div class="pin pin-right"></div>
              </div>
              <StatusTimeline 
                :current-phase="patientStore.currentPatient.current_phase || 'idle'"
                :events="patientStore.currentPatient.trajectory"
              />
            </div>
          </section>
          <section v-if="patientStore.currentPatient.assigned_doctor" class="section">
            <h2>Assignment Info</h2>
            <div class="pixel-assignment-panel">
              <div class="panel-header">MEDICAL ASSIGNMENT</div>
              <div class="panel-body">
                <div class="assignment-item clickable" @click="goToDoctor(patientStore.currentPatient.assigned_doctor)">
                  <div class="icon-box"><el-icon><UserFilled /></el-icon></div>
                  <div class="item-content">
                    <span class="label">ATTENDING DOCTOR</span>
                    <span class="value">{{ patientStore.currentPatient.assigned_doctor }}</span>
                  </div>
                </div>
                <div class="assignment-item">
                  <div class="icon-box"><el-icon><OfficeBuilding /></el-icon></div>
                  <div class="item-content">
                    <span class="label">DEPARTMENT</span>
                    <span class="value">{{ patientStore.currentPatient.department }}</span>
                  </div>
                </div>
                <div class="assignment-item">
                  <div class="icon-box"><el-icon><Location /></el-icon></div>
                  <div class="item-content">
                    <span class="label">CONSULTATION ROOM</span>
                    <span class="value">{{ patientStore.currentPatient.consultation_room }}</span>
                  </div>
                </div>
              </div>
            </div>
          </section>
          <section class="section conversation-section">
            <h2>Doctor-Patient Conversation</h2>
            <div class="conversation-container">
              <ConversationView
                :messages="currentMessages"
                :patient-id="patientStore.currentPatient.id"
                :doctor-id="patientStore.currentPatient.assigned_doctor"
              />
            </div>
          </section>
          <section v-if="patientStore.currentPatient.examinations?.length" class="section">
            <h2>Examination Records ({{ patientStore.currentPatient.examinations.length }})</h2>
            <div class="card-list">
              <ExaminationCard 
                v-for="exam in patientStore.currentPatient.examinations"
                :key="exam.id"
                :examination="exam"
              />
            </div>
          </section>
          <section v-if="patientStore.currentPatient.prescriptions?.length" class="section">
            <h2>Diagnosis & Treatment ({{ patientStore.currentPatient.prescriptions.length }})</h2>
            <div class="card-list">
              <TreatmentCard 
                v-for="prescription in patientStore.currentPatient.prescriptions"
                :key="prescription.id"
                :prescription="prescription"
                :patient-id="patientId"
                :reference-treatment="referenceTreatment"
              />
            </div>
          </section>
          <PatientTrajectory :patient="patientStore.currentPatient" />
        </div>
      </el-scrollbar>
      <div v-else-if="patientStore.error" class="error-state">
        <el-icon :size="48" color="#f56c6c"><CircleClose /></el-icon>
        <h3>Loading Failed</h3>
        <p>{{ patientStore.error }}</p>
        <el-button type="primary" @click="retryLoad">Retry</el-button>
        <el-button @click="goBack">Back Home</el-button>
      </div>
      <div v-else-if="patientStore.loading" class="loading-state">
        <el-icon class="is-loading" :size="32"><Loading /></el-icon>
        <span>Loading...</span>
      </div>
      <div v-else class="empty-state">
        <el-icon :size="48"><Warning /></el-icon>
        <h3>Patient data not found</h3>
        <el-button @click="goBack">Back Home</el-button>
      </div>
    </div>
  </MainLayout>
</template>

<style scoped lang="scss">
.patient-view {
  height: 100%;
  display: flex;
  flex-direction: column;

  .view-header {
    display: flex;
    align-items: center;
    gap: 1rem;
    padding: 1rem 1.5rem;
    background: white;
    border-bottom: 0.0625rem solid var(--border-color-lighter);

    h1 {
      margin: 0;
      font-size: 1.25rem;
    }
  }

  .view-content {
    flex: 1;
    background: #e1f5fe;

    &.no-grey-bottom {
      :deep(.el-scrollbar__view) {
        min-height: 100%;
        background: #e1f5fe;
        display: flex;
        flex-direction: column;
      }
    }

    .content-wrapper {
      max-width: 75rem;
      margin: 0 auto;
      padding: 1.5rem;
      flex: 1;
    }

    .section {
      margin-bottom: 2rem;

      h2 {
        margin: 0 0 1rem 0;
        font-size: var(--font-size-lg);
        font-weight: 400;
        color: var(--text-primary);
      }
    }

    .conversation-container {
      min-height: 56.25rem;
      height: 56.25rem;
      background: transparent;
      border-radius: 0;
      display: flex;
      flex-direction: column;
      padding: 0;
      overflow: visible;
    }

    .pixel-notice-board {
      background: #fdf6e3; // 淡黄色
      border: 0.5rem solid #d4a373;
      box-shadow: 0.5rem 0.5rem 0 rgba(0, 0, 0, 0.2);
      position: relative;
      padding: 0.625rem;
      image-rendering: pixelated;

      .board-header {
        background: #f0e68c; // 纸张黄
        margin: -0.625rem -0.625rem 0.625rem -0.625rem;
        padding: 0.5rem;
        text-align: center;
        font-family: 'Press Start 2P', cursive;
        font-size: 0.625rem;
        color: #8b5a2b; // 褐色文字
        border-bottom: 0.25rem solid #d4a373;
        display: flex;
        justify-content: space-between;
        align-items: center;

        .pin {
          width: 0.75rem;
          height: 0.75rem;
          background: #ff4b4b;
          border: 0.125rem solid #000;
          border-radius: 0; // 像素方块销子
          box-shadow: 0.125rem 0.125rem 0 rgba(0,0,0,0.2);
        }
      }

      :deep(.status-timeline) {
        background: transparent !important;
        border: none !important;
        box-shadow: none !important;
        padding: 0.625rem 0 !important;

        &::after {
          display: none; // 移除组件自带的木纹，统一由容器控制
        }
      }
    }

    .pixel-assignment-panel {
      background: #fff;
      border: 0.25rem solid #000;
      box-shadow: 0.5rem 0.5rem 0 rgba(0, 0, 0, 0.1);
      image-rendering: pixelated;

      .panel-header {
        background: #000;
        color: #fff;
        padding: 0.5rem 1rem;
        font-family: 'Press Start 2P', cursive;
        font-size: 0.75rem;
        letter-spacing: 0.0625rem;
      }

      .panel-body {
        padding: 1.25rem;
        display: flex;
        gap: 1.875rem;
        flex-wrap: wrap;
      }

      .assignment-item {
        display: flex;
        align-items: center;
        gap: 0.75rem;

        &.clickable {
          cursor: pointer;
          transition: transform 0.1s;

          &:hover {
            transform: translateY(-0.125rem);

            .icon-box {
              background: #ffe066;
            }

            .value {
              color: #1976d2;
              text-decoration: underline;
            }
          }
        }

        .icon-box {
          width: 2.5rem;
          height: 2.5rem;
          background: #ffcc00;
          border: 0.1875rem solid #000;
          display: flex;
          align-items: center;
          justify-content: center;
          box-shadow: 0.25rem 0.25rem 0 rgba(0, 0, 0, 0.05);

          .el-icon {
            font-size: 1.25rem;
            color: #000;
          }
        }

        .item-content {
          display: flex;
          flex-direction: column;

          .label {
            font-size: 0.625rem;
            font-weight: bold;
            color: #666;
            margin-bottom: 0.125rem;
          }

          .value {
            font-family: 'Courier New', Courier, monospace;
            font-weight: 900;
            font-size: 1rem;
            color: #000;
          }
        }
      }
    }
  }

  .loading-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 0.75rem;
    color: var(--text-secondary);
  }

  .error-state, .empty-state {
    flex: 1;
    display: flex;
    flex-direction: column;
    align-items: center;
    justify-content: center;
    gap: 1rem;
    color: var(--text-secondary);

    h3 {
      margin: 0;
      font-size: 1.125rem;
      color: var(--text-primary);
    }

    p {
      margin: 0;
      font-size: 0.875rem;
    }
  }
}
</style>

