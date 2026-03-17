<script setup lang="ts">
import { onMounted, onUnmounted, computed, ref, watch } from 'vue'
import { useRouter, useRoute } from 'vue-router'
import MainLayout from '@/layouts/MainLayout.vue'
import { DoctorList, PatientEvaluationCard } from '@/components/doctor'
import { PatientList, PatientTrajectory } from '@/components/patient'
import { ConversationView, DoctorConsultationDialog } from '@/components/conversation'
import { ExaminationCard, TreatmentCard } from '@/components/medical'
import { ProfileCard, StatusTimeline } from '@/components/patient'
import { useDoctorStore, usePatientStore, useConversationStore, useWebSocketStore } from '@/stores'
import { simulationApi } from '@/api'
import { FirstAidKit, Loading, OfficeBuilding, Location, ChatDotRound, User, Bell, Setting, Search } from '@element-plus/icons-vue'

const router = useRouter()
const route = useRoute()
const doctorStore = useDoctorStore()
const patientStore = usePatientStore()
const conversationStore = useConversationStore()
const wsStore = useWebSocketStore()
const CURRENT_PATIENTS_BATCH_SIZE = 12
const TREATMENT_DETAILS_BATCH_SIZE = 8

const visibleCurrentPatientsCount = ref(CURRENT_PATIENTS_BATCH_SIZE)
const visibleTreatmentDetailsCount = ref(TREATMENT_DETAILS_BATCH_SIZE)
const showConsultationDialog = ref(false)

const currentDoctorPatients = computed(() => {
  return doctorStore.currentDoctor?.current_patients || []
})

const visibleCurrentDoctorPatients = computed(() => {
  return currentDoctorPatients.value.slice(0, visibleCurrentPatientsCount.value)
})

const hasMoreCurrentDoctorPatients = computed(() => {
  return visibleCurrentPatientsCount.value < currentDoctorPatients.value.length
})

const consultationGroups = computed(() => doctorStore.consultationGroups)
const selectedConsultationPatientId = ref<string | null>(null)
const selectedConsultationGroup = computed(() => {
  if (!consultationGroups.value.length) return null
  if (!selectedConsultationPatientId.value) {
    return consultationGroups.value[0]
  }
  return consultationGroups.value.find(
    group => group.patient_id === selectedConsultationPatientId.value
  ) || consultationGroups.value[0]
})

function getDoctorAvatar(doctorId: string) {
  let hash = 0
  for (let i = 0; i < doctorId.length; i += 1) {
    hash = (hash * 31 + doctorId.charCodeAt(i)) % 1000
  }
  return hash % 2 === 0 ? '/doctor_male.png' : '/doctor_female.png'
}

watch(consultationGroups, (groups) => {
  if (!groups.length) {
    selectedConsultationPatientId.value = null
    return
  }
  if (!selectedConsultationPatientId.value) {
    selectedConsultationPatientId.value = groups[0].patient_id
  }
}, { immediate: true })
const getInitialTab = (): 'doctor' | 'patient' => {
  const queryTab = route.query.tab as string
  if (queryTab === 'doctor' || queryTab === 'patient') {
    return queryTab
  }
  if (doctorStore.selectedDoctorId) {
    return 'doctor'
  }
  return 'patient'
}
const activeTab = ref<'doctor' | 'patient'>(getInitialTab())
let backgroundRefreshTimer: ReturnType<typeof setInterval> | null = null
const BACKGROUND_REFRESH_INTERVAL = 10000
let initialDataLoaded = false
async function loadInitialData() {
  if (initialDataLoaded) return
  initialDataLoaded = true

  await Promise.all([
    doctorStore.fetchDoctors(),
    patientStore.fetchPatients(),
  ])
}
watch(() => wsStore.connected, (isConnected) => {
  if (isConnected && !initialDataLoaded) {
    loadInitialData()
  }
}, { immediate: true })

watch(() => doctorStore.selectedDoctorId, () => {
  visibleCurrentPatientsCount.value = CURRENT_PATIENTS_BATCH_SIZE
  visibleTreatmentDetailsCount.value = TREATMENT_DETAILS_BATCH_SIZE
})
const currentMessages = computed(() => {
  if (activeTab.value === 'patient' && patientStore.currentPatient) {
    const patient = patientStore.currentPatient
    if (patient.assigned_doctor) {
      const conv = conversationStore.getConversation(patient.id, patient.assigned_doctor)
      return conv?.messages || []
    }
  }
  if (activeTab.value === 'doctor' && doctorStore.currentDoctor) {
    return []
  }
  return []
})
let conversationLoadAbortController: AbortController | null = null
let conversationLoadTimer: ReturnType<typeof setTimeout> | null = null
const isMounted = ref(false)

onMounted(async () => {
  isMounted.value = true
  if (wsStore.isInitialSystemLoading) {
    setTimeout(() => {
      wsStore.isInitialSystemLoading = false
    }, 2500)
  }
})

const stopWatch = watch(
  () => patientStore.currentPatient?.id,
  async (newPatientId, oldPatientId) => {
    if (!isMounted.value) return
    if (newPatientId === oldPatientId) return
    if (conversationLoadAbortController) {
      conversationLoadAbortController.abort()
      conversationLoadAbortController = null
    }
    if (conversationLoadTimer) {
      clearTimeout(conversationLoadTimer)
      conversationLoadTimer = null
    }
    conversationLoadTimer = setTimeout(async () => {
      if (!isMounted.value) {
        conversationLoadTimer = null
        return
      }
      
      conversationLoadAbortController = new AbortController()
      
      const patient = patientStore.currentPatient
      if (patient && patient.id === newPatientId && patient.assigned_doctor && isMounted.value) {
        try {
          await conversationStore.fetchConversation(patient.id, patient.assigned_doctor)
        } catch (e) {
          if (!isMounted.value) return
          if (e instanceof Error && (e.name === 'AbortError' || e.name === 'CanceledError')) {
            return
          }
          console.error('Failed to load conversation:', e)
        }
      }
      conversationLoadTimer = null
    }, 200)
  },
  { immediate: false }
)
onUnmounted(() => {
  isMounted.value = false
  stopWatch()
  stopBackgroundRefresh()
  if (conversationLoadAbortController) {
    conversationLoadAbortController.abort()
    conversationLoadAbortController = null
  }
  if (conversationLoadTimer) {
    clearTimeout(conversationLoadTimer)
    conversationLoadTimer = null
  }
})
onMounted(async () => {
  await Promise.all([
    doctorStore.fetchDoctors(),
    patientStore.fetchPatients(),
  ])
  startBackgroundRefresh()
})
async function backgroundRefresh() {
  try {
    const status = await simulationApi.getStatus()
    wsStore.simulationStatus.current_tick = status.current_tick
  } catch (error) {
  }
  await Promise.all([
    patientStore.silentFetchPatients(),
    doctorStore.silentFetchDoctors(),
  ])
  if (activeTab.value === 'patient' && patientStore.selectedPatientId) {
    await patientStore.refreshCurrentPatient()
    const patient = patientStore.currentPatient
    if (patient?.assigned_doctor) {
      await conversationStore.fetchConversation(patient.id, patient.assigned_doctor)
    }
  }

  if (activeTab.value === 'doctor' && doctorStore.selectedDoctorId) {
    await doctorStore.refreshCurrentDoctor()
  }
}
function startBackgroundRefresh() {
  if (backgroundRefreshTimer) return
  backgroundRefreshTimer = setInterval(() => {
    backgroundRefresh()
  }, BACKGROUND_REFRESH_INTERVAL)
}
function stopBackgroundRefresh() {
  if (backgroundRefreshTimer) {
    clearInterval(backgroundRefreshTimer)
    backgroundRefreshTimer = null
  }
}

function getAvatarUrl(id: string, gender: string = 'unknown') {
  const genderPrefix = gender === 'Male' ? 'm' : (gender === 'Female' ? 'f' : 'bot')
  return `https://api.dicebear.com/7.x/pixel-art/svg?seed=${genderPrefix}_${id}&backgroundColor=b6e3f4,c0aede,d1d4f9`
}

function selectConsultationPatient(patientId: string) {
  selectedConsultationPatientId.value = patientId
}

function formatTick(value?: number) {
  if (value == null) return '-'
  return `T${value}`
}

function formatDoctorLabel(doctor: string) {
  return `Dr. ${doctor.replace(/^Doctor_/, '')}`
}
function handleDoctorSelect(_doctorId: string) {
  activeTab.value = 'doctor'
}
const formatPercentage = (value: number) => {
  return (value * 100).toFixed(1) + '%'
}
const patientTreatmentSearch = ref('')
const filteredPatientEvaluations = computed(() => {
  if (!doctorStore.evaluation?.patients) return []
  if (!patientTreatmentSearch.value.trim()) {
    return doctorStore.evaluation.patients
  }
  const searchTerm = patientTreatmentSearch.value.toLowerCase().trim()
  return doctorStore.evaluation.patients.filter(p =>
    p.patient_id.toLowerCase().includes(searchTerm)
  )
})

watch(patientTreatmentSearch, () => {
  visibleTreatmentDetailsCount.value = TREATMENT_DETAILS_BATCH_SIZE
})

const visiblePatientEvaluations = computed(() => {
  return filteredPatientEvaluations.value.slice(0, visibleTreatmentDetailsCount.value)
})

const hasMorePatientEvaluations = computed(() => {
  return visibleTreatmentDetailsCount.value < filteredPatientEvaluations.value.length
})

function loadMoreCurrentPatients() {
  visibleCurrentPatientsCount.value = Math.min(
    currentDoctorPatients.value.length,
    visibleCurrentPatientsCount.value + CURRENT_PATIENTS_BATCH_SIZE
  )
}

function loadMorePatientEvaluations() {
  visibleTreatmentDetailsCount.value = Math.min(
    filteredPatientEvaluations.value.length,
    visibleTreatmentDetailsCount.value + TREATMENT_DETAILS_BATCH_SIZE
  )
}
function handlePatientSelect(_patientId: string) {
  activeTab.value = 'patient'
}
function goToPatientDetail(patientId: string) {
  router.push({ path: `/patient/${patientId}`, query: { from: 'doctor', doctorId: doctorStore.selectedDoctorId || '' } })
}
function goToDoctorDetail(doctorId: string) {
  doctorStore.selectDoctor(doctorId)
  activeTab.value = 'doctor'
}
function openConsultation() {
  showConsultationDialog.value = true
}
</script>

<template>
  <MainLayout>
    <div class="dashboard">
      <transition name="pixel-fade">
        <div v-if="wsStore.isInitialSystemLoading" class="initial-boot-screen">
          <div class="boot-content">
            <div class="pixel-logo">
              <el-icon class="logo-icon"><FirstAidKit /></el-icon>
            </div>
            <h1 class="system-title">OPENHOSPITAL</h1>
            <div class="subtitle">OPENHOSPITAL V1.0</div>
            
            <div class="boot-messages">
              <div class="msg">INITIALIZING COMPONENTS...</div>
              <div class="msg">LOADING DATABASE...</div>
              <div class="msg">VIRTUALIZING AGENTS...</div>
              <div class="msg">READY.</div>
            </div>
          </div>
          
          <div class="loading-bar-container">
            <div class="loading-bar-fill">
              <div class="welcome-text">WELCOME</div>
            </div>
          </div>
          
          <div class="scanline"></div>
        </div>
      </transition>
      <div class="sidebar">
        <el-tabs v-model="activeTab" class="sidebar-tabs">
          <el-tab-pane label="Patients" name="patient">
            <PatientList @select="handlePatientSelect" />
          </el-tab-pane>
          <el-tab-pane label="Doctors" name="doctor">
            <DoctorList @select="handleDoctorSelect" />
          </el-tab-pane>
        </el-tabs>
      </div>
      <div class="main-panel">
        <transition name="detail-fade" mode="out-in">
          <div v-if="!patientStore.selectedPatientId && !doctorStore.selectedDoctorId" key="empty" class="empty-state">
            <el-icon :size="64"><FirstAidKit /></el-icon>
            <h2>OpenHospital</h2>
            <p>Please select a doctor or patient from the left panel to view details</p>
          </div>
          <div v-else-if="activeTab === 'patient' && patientStore.selectedPatientId && patientStore.loading" key="loading-p" class="detail-wrapper">
            <div class="detail-header skeleton-header">
              <div>
                <el-skeleton :rows="0" animated>
                  <template #template>
                    <el-skeleton-item variant="h1" style="width: 180px; height: 28px;" />
                  </template>
                </el-skeleton>
                <el-skeleton :rows="0" animated style="margin-top: 8px;">
                  <template #template>
                    <el-skeleton-item variant="text" style="width: 120px; height: 16px;" />
                  </template>
                </el-skeleton>
              </div>
            </div>

            <el-scrollbar class="detail-content">
              <div class="content-grid">
                <div class="section">
                  <div class="skeleton-profile-card">
                    <el-skeleton :rows="0" animated>
                      <template #template>
                        <div class="skeleton-profile-inner">
                          <el-skeleton-item variant="image" style="width: 100px; height: 100px;" />
                          <div class="skeleton-profile-info">
                            <el-skeleton-item variant="h3" style="width: 160px; height: 24px;" />
                            <el-skeleton-item variant="text" style="width: 100px; height: 16px; margin-top: 12px;" />
                            <el-skeleton-item variant="text" style="width: 80px; height: 16px; margin-top: 8px;" />
                            <el-skeleton-item variant="text" style="width: 120px; height: 16px; margin-top: 8px;" />
                          </div>
                        </div>
                      </template>
                    </el-skeleton>
                  </div>
                </div>
                <div class="section">
                  <h3>Visit Timeline</h3>
                  <div class="skeleton-timeline">
                    <el-skeleton :rows="0" animated>
                      <template #template>
                        <div class="skeleton-timeline-inner">
                          <el-skeleton-item v-for="i in 6" :key="i" variant="rect" style="width: 80px; height: 60px; border-radius: 4px;" />
                        </div>
                      </template>
                    </el-skeleton>
                  </div>
                </div>
                <div class="section">
                  <h3>Doctor-Patient Conversation</h3>
                  <div class="skeleton-conversation">
                    <el-skeleton :rows="0" animated>
                      <template #template>
                        <div class="skeleton-messages">
                          <div class="skeleton-msg skeleton-msg-left">
                            <el-skeleton-item variant="circle" style="width: 36px; height: 36px;" />
                            <el-skeleton-item variant="rect" style="width: 200px; height: 60px; border-radius: 12px;" />
                          </div>
                          <div class="skeleton-msg skeleton-msg-right">
                            <el-skeleton-item variant="rect" style="width: 180px; height: 50px; border-radius: 12px;" />
                            <el-skeleton-item variant="circle" style="width: 36px; height: 36px;" />
                          </div>
                          <div class="skeleton-msg skeleton-msg-left">
                            <el-skeleton-item variant="circle" style="width: 36px; height: 36px;" />
                            <el-skeleton-item variant="rect" style="width: 240px; height: 80px; border-radius: 12px;" />
                          </div>
                          <div class="skeleton-msg skeleton-msg-right">
                            <el-skeleton-item variant="rect" style="width: 160px; height: 45px; border-radius: 12px;" />
                            <el-skeleton-item variant="circle" style="width: 36px; height: 36px;" />
                          </div>
                        </div>
                      </template>
                    </el-skeleton>
                  </div>
                </div>
              </div>
            </el-scrollbar>
          </div>
          <div v-else-if="activeTab === 'patient' && patientStore.currentPatient && !patientStore.loading" key="patient-detail" class="detail-wrapper">
            <div class="detail-header">
              <div>
                <h2>{{ patientStore.currentPatient.name }}</h2>
                <span class="patient-id-subtitle">{{ patientStore.currentPatient.id }}</span>
              </div>
              <el-button
                type="primary"
                size="small"
                @click="openConsultation"
              >
                Start Consultation
              </el-button>
            </div>
            
            <el-scrollbar class="detail-content">
              <div class="content-grid">
                <ProfileCard :patient="patientStore.currentPatient" class="profile-section" />
                <div v-if="patientStore.currentPatient.assigned_doctor" class="section">
                  <h3>Assigned Doctor</h3>
                  <div class="assigned-doctor-card" @click="goToDoctorDetail(patientStore.currentPatient.assigned_doctor)">
                    <el-icon class="doctor-icon"><User /></el-icon>
                    <span class="doctor-name">{{ patientStore.currentPatient.assigned_doctor }}</span>
                    <span class="view-hint">Click to view details</span>
                  </div>
                </div>
                <div class="section timeline-section">
                  <h3>Visit Timeline</h3>
                  <StatusTimeline 
                    :current-phase="patientStore.currentPatient.current_phase || 'idle'"
                    :events="patientStore.currentPatient.trajectory"
                  />
                </div>
                <div class="section conversation-section">
                  <h3>Doctor-Patient Conversation</h3>
                  <div class="conversation-container">
                    <ConversationView 
                      :messages="currentMessages"
                      :patient-id="patientStore.currentPatient.id"
                      :doctor-id="patientStore.currentPatient.assigned_doctor"
                    />
                  </div>
                </div>
                <div v-if="patientStore.currentPatient.examinations?.length" class="section">
                  <h3>Examination Records</h3>
                  <div class="card-stack">
                    <ExaminationCard 
                      v-for="exam in patientStore.currentPatient.examinations"
                      :key="exam.id"
                      :examination="exam"
                    />
                  </div>
                </div>
                <div v-if="patientStore.currentPatient.prescriptions?.length" class="section">
                  <h3>Diagnosis & Treatment</h3>
                  <div class="card-stack">
                    <TreatmentCard 
                      v-for="prescription in patientStore.currentPatient.prescriptions"
                      :key="prescription.id"
                      :prescription="prescription"
                    />
                  </div>
                </div>
                <PatientTrajectory :patient="patientStore.currentPatient" />
              </div>
            </el-scrollbar>
          </div>
          <div v-else-if="activeTab === 'doctor' && doctorStore.selectedDoctorId && doctorStore.loading" key="loading-d" class="loading-state">
            <el-icon class="is-loading" :size="32"><Loading /></el-icon>
            <span>Loading doctor data...</span>
          </div>
          <div v-else-if="activeTab === 'doctor' && doctorStore.currentDoctor && !doctorStore.loading" key="doctor-detail" class="detail-wrapper">
            <div class="detail-header">
              <div>
                <h2>{{ doctorStore.currentDoctor.name }}</h2>
                <span class="doctor-id-subtitle">{{ doctorStore.currentDoctor.id }}</span>
              </div>
            </div>
            
            <el-scrollbar class="detail-content">
              <div class="content-grid">
                <div class="section">
                  <h3>Doctor Information</h3>
                  <div class="doctor-profile-card">
                    <div class="avatar">
                      <img :src="getDoctorAvatar(doctorStore.currentDoctor.id)" alt="Doctor" class="avatar-image" />
                    </div>
                    <div class="info">
                      <h3>{{ doctorStore.currentDoctor.name }}</h3>
                      <p class="doctor-id">{{ doctorStore.currentDoctor.id }}</p>
                      <p class="department">
                        <el-icon><OfficeBuilding /></el-icon>
                        {{ doctorStore.currentDoctor.department }}
                      </p>
                      <p class="location">
                        <el-icon><Location /></el-icon>
                        {{ doctorStore.currentDoctor.consultation_room }}
                      </p>
                    </div>
                    <div class="specialties-box">
                      <h4>Specialties</h4>
                      <div class="specialties">
                        <el-tag 
                          v-for="specialty in doctorStore.currentDoctor.specialties"
                          :key="specialty"
                          type="primary"
                        >
                          {{ specialty }}
                        </el-tag>
                      </div>
                    </div>
                  </div>
                </div>
                <div v-if="currentDoctorPatients.length" class="section">
                  <h3>Current Patients ({{ currentDoctorPatients.length }})</h3>
                  <div class="patients-grid">
                    <el-tag
                      v-for="patient in visibleCurrentDoctorPatients"
                      :key="patient.id"
                      type="success"
                      size="large"
                      class="patient-tag-clickable"
                      @click="goToPatientDetail(patient.id)"
                    >
                      {{ patient.id }}
                    </el-tag>
                  </div>
                  <div v-if="hasMoreCurrentDoctorPatients" class="load-more-wrapper">
                    <el-button plain @click="loadMoreCurrentPatients">
                      Load More ({{ visibleCurrentDoctorPatients.length }}/{{ currentDoctorPatients.length }})
                    </el-button>
                  </div>
                </div>
                <div class="section">
                  <h3>Doctor Consultations by Patient</h3>
                  <div v-if="doctorStore.consultationsLoading" class="consultation-placeholder">
                    <el-icon class="is-loading" :size="28"><Loading /></el-icon>
                    <span>Loading consultation messages...</span>
                  </div>
                  <div v-else-if="doctorStore.consultationsError" class="consultation-placeholder">
                    <span>{{ doctorStore.consultationsError }}</span>
                  </div>
                  <div v-else class="consultation-tablet">
                    <div class="tablet-frame">
                      <div class="tablet-bezel">
                        <div class="tablet-camera"></div>
                        <div class="tablet-screen">
                          <div class="tablet-app">
                            <div class="tablet-sidebar">
                              <div class="tablet-button active">
                                <el-icon :size="24"><ChatDotRound /></el-icon>
                              </div>
                              <div class="tablet-button">
                                <el-icon :size="24"><User /></el-icon>
                              </div>
                              <div class="tablet-button">
                                <el-icon :size="24"><Bell /></el-icon>
                              </div>
                              <div class="tablet-spacer"></div>
                              <div class="tablet-button">
                                <el-icon :size="24"><Setting /></el-icon>
                              </div>
                            </div>
                            <div class="tablet-content">
                              <div class="tablet-app-header">
                                <div class="app-title">Consultations</div>
                                <div class="app-meta">
                                  <span class="status-badge live">Live</span>
                                  <span>{{ consultationGroups.length }} Active</span>
                                </div>
                              </div>
                              <div class="app-body">
                                <div class="consultation-patients">
                                  <div class="list-header">Patient Queue</div>
                                  <div v-if="consultationGroups.length === 0" class="consultation-empty-list">
                                    <span>No consultations yet.</span>
                                  </div>
                                  <template v-else>
                                    <div
                                      v-for="group in consultationGroups"
                                      :key="group.patient_id"
                                      class="consultation-patient-card"
                                      :class="{ active: group.patient_id === selectedConsultationGroup?.patient_id }"
                                      @click="selectConsultationPatient(group.patient_id)"
                                    >
                                      <div class="patient-avatar-img">
                                        <img :src="getAvatarUrl(group.patient_id)" alt="Avatar" />
                                      </div>
                                      <div class="patient-info">
                                        <div class="patient-id">{{ group.patient_id }}</div>
                                        <div class="patient-preview">
                                          {{ group.messages[group.messages.length - 1]?.content.substring(0, 40) }}...
                                        </div>
                                      </div>
                                      <div class="patient-meta">
                                        <span class="time">{{ formatTick(group.last_message_tick) }}</span>
                                        <span class="badge" v-if="group.message_count > 0">{{ group.message_count }}</span>
                                      </div>
                                    </div>
                                  </template>
                                </div>
                                <div class="consultation-thread" v-if="selectedConsultationGroup">
                                  <div class="consultation-thread-header">
                                    <div class="header-info">
                                      <span class="patient-name">{{ selectedConsultationGroup.patient_id }}</span>
                                      <span class="subtitle">Consultation History</span>
                                    </div>
                                  </div>
                                  <div class="consultation-thread-body">
                                    <div
                                      v-for="message in selectedConsultationGroup.messages"
                                      :key="message.id"
                                      class="consultation-message"
                                      :class="{ 
                                        'message-out': message.sender === doctorStore.currentDoctor?.id,
                                        'message-in': message.sender !== doctorStore.currentDoctor?.id
                                      }"
                                    >
                                      <div class="message-bubble">
                                        <div class="message-sender-name" v-if="message.sender !== doctorStore.currentDoctor?.id">
                                          {{ formatDoctorLabel(message.sender) }}
                                        </div>
                                        <div class="message-content">{{ message.content }}</div>
                                        <div class="message-footer">
                                          <span class="message-tick">{{ formatTick(message.created_at) }}</span>
                                        </div>
                                      </div>
                                    </div>
                                  </div>
                                  <div class="consultation-input-area">
                                    <div class="input-placeholder">System View Only</div>
                                  </div>
                                </div>
                                <div v-else class="empty-selection">
                                  <el-icon :size="48"><ChatDotRound /></el-icon>
                                  <p v-if="consultationGroups.length">Select a consultation to view details</p>
                                  <p v-else>No consultations yet.</p>
                                </div>
                              </div>
                            </div>
                          </div>
                        </div>
                      </div>
                    </div>
                  </div>
                </div>
                                <template v-if="doctorStore.evaluation">
                  <div class="section">
                    <h3>Clinical Evaluation</h3>
                    <div class="stats-grid">
                      <div class="stat-card">
                        <div class="stat-value">{{ doctorStore.evaluation.summary.total_patients }}</div>
                        <div class="stat-label">Total Patients</div>
                      </div>
                      <div class="stat-card">
                        <div class="stat-value">
                          {{ doctorStore.evaluation.summary.correct_diagnoses }} / {{ doctorStore.evaluation.summary.total_diagnoses }}
                        </div>
                        <div class="stat-label">Correct / Total Diagnoses</div>
                      </div>
                      <div class="stat-card">
                        <div class="stat-value" :style="{ 
                          color: doctorStore.evaluation.summary.diagnosis_accuracy >= 0.8 ? '#67c23a' : 
                                 doctorStore.evaluation.summary.diagnosis_accuracy >= 0.5 ? '#e6a23c' : '#f56c6c' 
                        }">
                          {{ doctorStore.evaluation.summary.diagnosis_accuracy != null ? formatPercentage(doctorStore.evaluation.summary.diagnosis_accuracy) : 'N/A' }}
                        </div>
                        <div class="stat-label">Diagnosis Accuracy</div>
                      </div>
                      <div class="stat-card">
                        <div class="stat-value">{{ doctorStore.evaluation.summary.total_examinations }}</div>
                        <div class="stat-label">Total Examinations</div>
                      </div>
                      <div class="stat-card">
                        <div class="stat-value" :style="{ 
                          color: doctorStore.evaluation.summary.average_examination_precision >= 0.8 ? '#67c23a' : 
                                 doctorStore.evaluation.summary.average_examination_precision >= 0.5 ? '#e6a23c' : '#f56c6c' 
                        }">
                          {{ doctorStore.evaluation.summary.average_examination_precision != null ? formatPercentage(doctorStore.evaluation.summary.average_examination_precision) : 'N/A' }}
                        </div>
                        <div class="stat-label">Examination Precision</div>
                      </div>
                      <div class="stat-card">
                        <el-tag v-if="doctorStore.evaluation.summary.has_ground_truth" type="success">
                          Has Ground Truth
                        </el-tag>
                        <el-tag v-else type="info">
                          No Ground Truth
                        </el-tag>
                        <div class="stat-label">Data Source</div>
                      </div>
                    </div>
                  </div>
                  <div class="section">
                    <h3>Patient Treatment Details ({{ filteredPatientEvaluations.length }})</h3>
                    <div class="search-box">
                      <el-input
                        v-model="patientTreatmentSearch"
                        placeholder="Search by Patient ID..."
                        clearable
                        :prefix-icon="Search"
                      />
                    </div>
                    <div class="evaluation-cards">
                      <PatientEvaluationCard
                        v-for="patientEval in visiblePatientEvaluations"
                        :key="patientEval.patient_id"
                        :evaluation="patientEval"
                      />
                      <div v-if="hasMorePatientEvaluations" class="load-more-wrapper">
                        <el-button plain @click="loadMorePatientEvaluations">
                          Load More ({{ visiblePatientEvaluations.length }}/{{ filteredPatientEvaluations.length }})
                        </el-button>
                      </div>
                      <div v-if="filteredPatientEvaluations.length === 0 && patientTreatmentSearch" class="no-results">
                        No patients found matching "{{ patientTreatmentSearch }}"
                      </div>
                    </div>
                  </div>
                </template>
                <div v-else-if="doctorStore.evaluationLoading" class="section">
                  <div class="loading-placeholder">
                    <el-icon class="is-loading" :size="32"><Loading /></el-icon>
                    <span>Loading evaluation data...</span>
                  </div>
                </div>
                <div v-else class="section">
                  <el-alert
                    title="No Evaluation Data"
                    type="info"
                    description="This doctor has not treated any patients yet, or the ground truth data file does not exist"
                    :closable="false"
                  />
                </div>
              </div>
            </el-scrollbar>
          </div>
          <div v-else key="fallback" class="empty-state">
            <el-icon :size="64"><FirstAidKit /></el-icon>
            <h2>OpenHospital</h2>
            <p>Please select a doctor or patient from the left panel to view details</p>
          </div>
        </transition>
      </div>
    </div>
    <DoctorConsultationDialog
      v-model:visible="showConsultationDialog"
      :patient-name="patientStore.currentPatient?.name || 'Patient'"
      :patient-id="patientStore.currentPatient?.id"
      @close="showConsultationDialog = false"
    />
  </MainLayout>
</template>

<style scoped lang="scss">
.initial-boot-screen {
  position: fixed;
  top: 0;
  left: 0;
  width: 100vw;
  height: 100vh;
  background: #3da5ff;
  z-index: 9999;
  display: flex;
  align-items: center;
  justify-content: center;
  flex-direction: column;
  image-rendering: pixelated;
  overflow: hidden;

  .boot-content {
    text-align: center;
    color: #fff;
    padding: 2.5rem;
    border: 0.5rem solid #fff;
    background: #0088ff;
    box-shadow: 0.75rem 0.75rem 0 rgba(0, 0, 0, 0.2);
    position: relative;
    max-width: 31.25rem;
    width: 90%;
  }

  .pixel-logo {
    .logo-icon {
      font-size: 5rem;
      color: #ffcc00;
      filter: drop-shadow(0.25rem 0.25rem 0 #0044aa);
      margin-bottom: 1.25rem;
      animation: pixel-bounce 0.8s infinite;
    }
  }

  .system-title {
    font-family: 'Press Start 2P', cursive;
    font-size: 1.5rem;
    margin: 0.625rem 0;
    letter-spacing: 0.125rem;
    text-shadow: 0.25rem 0.25rem 0 #0044aa;
  }

  .subtitle {
    font-family: monospace;
    font-weight: bold;
    font-size: 0.875rem;
    margin-bottom: 1.875rem;
    background: #ffcc00;
    color: #0044aa;
    display: inline-block;
    padding: 0.25rem 0.75rem;
  }

  .loading-bar-container {
    position: absolute;
    left: 0;
    top: 0;
    width: 1.25rem;
    height: 100vh;
    border: none;
    background: rgba(255, 255, 255, 0.1);
    z-index: 100;
    overflow: visible;

    .loading-bar-fill {
      width: 100%;
      height: 0%;
      background: #ffcc00;
      animation: load-and-expand 2.5s forwards cubic-bezier(0.4, 0, 0.2, 1);
      box-shadow: 0.25rem 0 0 rgba(0, 0, 0, 0.1);
      display: flex;
      align-items: center;
      justify-content: center;
      overflow: hidden;

      .welcome-text {
        font-family: 'Press Start 2P', cursive;
        font-size: 6rem;
        color: #0044aa;
        opacity: 0;
        white-space: nowrap;
        animation: welcome-appear 2.5s forwards;
        text-shadow: 0.25rem 0.25rem 0 rgba(0, 0, 0, 0.1);
        letter-spacing: 0.625rem;
      }
    }
  }

  .boot-messages {
    font-family: monospace;
    font-size: 0.75rem;
    text-align: left;
    height: 5rem;

    .msg {
      margin-bottom: 0.25rem;
      overflow: hidden;
      white-space: nowrap;
      border-right: 0.125rem solid transparent;
      opacity: 0;
      animation: type-msg 2s forwards steps(40);

      &:nth-child(1) { animation-delay: 0.2s; }
      &:nth-child(2) { animation-delay: 0.7s; }
      &:nth-child(3) { animation-delay: 1.2s; }
      &:nth-child(4) { animation-delay: 1.8s; color: #ffcc00; font-weight: bold; }
    }
  }

  .scanline {
    position: absolute;
    top: 0;
    left: 0;
    width: 100%;
    height: 100%;
    background: linear-gradient(
      rgba(18, 16, 16, 0) 50%,
      rgba(0, 0, 0, 0.1) 50%
    );
    background-size: 100% 0.25rem;
    z-index: 10;
    pointer-events: none;
    animation: scanline 10s linear infinite;
  }
}

@keyframes pixel-bounce {
  0%, 100% { transform: translateY(0); }
  50% { transform: translateY(-0.625rem); }
}

@keyframes load-and-expand {
  0% {
    height: 0%;
    width: 1.25rem;
  }
  80% {
    height: 100%;
    width: 1.25rem;
  }
  100% {
    height: 100%;
    width: 100vw;
  }
}

@keyframes type-msg {
  from { opacity: 0; width: 0; }
  to { opacity: 1; width: 100%; }
}

@keyframes scanline {
  0% { transform: translateY(0); }
  100% { transform: translateY(0.25rem); }
}

@keyframes welcome-appear {
  0%, 85% {
    opacity: 0;
    transform: scale(0.5);
  }
  100% {
    opacity: 1;
    transform: scale(1);
  }
}

.pixel-fade-leave-active {
  transition: all 0.5s cubic-bezier(1, 0, 0, 1);
}
.pixel-fade-leave-to {
  opacity: 0;
  transform: scale(1.1) rotate(1deg);
}

.detail-fade-enter-active {
  transition: all 0.3s ease-out;
}
.detail-fade-leave-active {
  transition: all 0.2s ease-in;
}
.detail-fade-enter-from {
  opacity: 0;
  transform: translateY(0.625rem);
}
.detail-fade-leave-to {
  opacity: 0;
}

.dashboard {
  display: flex;
  height: 100%;
  gap: 0;
  background: #b3e5fc;

  .sidebar {
    width: 21.25rem;
    flex-shrink: 0;
    background: #f0f9ff;
    border-right: 0.25rem solid #0066cc;
    display: flex;
    flex-direction: column;
    box-shadow: 0.25rem 0 0 rgba(0, 0, 0, 0.05);
    z-index: 100;
    position: relative;
    overflow: visible;

    .sidebar-tabs {
      height: 100%;
      display: flex;
      flex-direction: column;
      background: #3da5ff;
      overflow: visible;

      :deep(.el-tabs__header) {
        margin: 0;
        padding: 0;
        background: #3da5ff;
        border-bottom: 0.125rem solid #0066cc;
      }

      :deep(.el-tabs__nav-wrap::after) {
        display: none;
      }

      :deep(.el-tabs__nav) {
        display: flex;
        width: 100%;
      }

      :deep(.el-tabs__item) {
        font-family: monospace;
        font-weight: bold;
        font-size: 0.8125rem;
        height: 2.375rem;
        flex: 1;
        display: flex;
        align-items: center;
        justify-content: center;
        border: 0.125rem solid #0066cc;
        border-bottom: none;
        margin-right: 0;
        padding: 0 1.25rem !important;
        background: #0088ff;
        color: rgba(255, 255, 255, 0.8);
        border-radius: 0;
        transition: none;

        &:first-child {
          border-right: 0.0625rem solid #0066cc;
        }

        &.is-active {
          background: #f0f9ff;
          color: #0066cc;
          border-color: #0066cc #0066cc #f0f9ff #0066cc;
          margin-bottom: -0.125rem;
          position: relative;
          z-index: 2;
          height: 2.5rem;
        }
      }

      :deep(.el-tabs__content) {
        flex: 1;
        overflow: hidden;

        .el-tab-pane {
          height: 100%;
          overflow: hidden;
        }
      }

      :deep(.el-tabs__active-bar) {
        display: none;
      }
    }
  }
  
  .main-panel {
    flex: 1;
    display: flex;
    flex-direction: column;
    background: #fafafa;
    overflow: hidden;
    position: relative;

    .empty-state, .loading-state, .detail-wrapper {
      flex: 1;
      display: flex;
      flex-direction: column;
      overflow: hidden;
    }

    .empty-state, .loading-state {
      align-items: center;
      justify-content: center;
      color: #3da5ff;
      gap: 1rem;

      .el-icon {
        font-size: 4rem;
        color: #3da5ff;
        filter: drop-shadow(0.25rem 0.25rem 0 rgba(0, 68, 170, 0.1));
      }

      h2 {
        margin: 0;
        font-family: 'Press Start 2P', cursive;
        font-size: 1rem;
        color: #0044aa;
        text-shadow: 0.125rem 0.125rem 0 rgba(255, 255, 255, 0.5);
      }

      p {
        margin: 0;
        font-size: 0.75rem;
        font-family: monospace;
        font-weight: bold;
      }
    }

    .detail-header {
      display: flex;
      align-items: center;
      justify-content: space-between;
      padding: 0.75rem 1.5rem;
      background: #2ecc71;
      border-bottom: 0.25rem solid #166534;
      box-shadow: inset 0 0.125rem 0 rgba(255, 255, 255, 0.4);

      h2 {
        margin: 0;
        font-family: 'Courier New', Courier, monospace;
        font-weight: 900;
        font-size: 1.375rem;
        text-transform: uppercase;
        color: #fff;
        text-shadow: 0.125rem 0.125rem 0 #166534;
      }

      .patient-id-subtitle,
      .doctor-id-subtitle {
        margin-left: 0.75rem;
        font-family: monospace;
        font-size: 0.75rem;
        color: #fff;
        background: #166534;
        padding: 0.1875rem 0.5rem;
        border: 0.125rem solid #fff;
        font-weight: bold;
      }
    }

    .detail-content {
      flex: 1;
      background: #f0fdf4;

      .content-grid {
        padding: 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 2rem;
      }

      .section {
        h3 {
          margin: 0 0 1rem 0;
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

      .card-stack {
        display: flex;
        flex-direction: column;
        gap: 1rem;
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

      .assigned-doctor-card {
        display: flex;
        align-items: center;
        gap: 0.75rem;
        padding: 1rem 1.25rem;
        background: #fff;
        border: 0.25rem solid #166534;
        cursor: pointer;
        transition: all 0.15s;
        box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.15);

        &:hover {
          transform: translate(-0.125rem, -0.125rem);
          box-shadow: 0.5rem 0.5rem 0 rgba(22, 101, 52, 0.2);
          background: #f0fdf4;

          .view-hint {
            opacity: 1;
          }
        }

        &:active {
          transform: translate(0, 0);
          box-shadow: 0.25rem 0.25rem 0 rgba(22, 101, 52, 0.1);
        }

        .doctor-icon {
          font-size: 1.5rem;
          color: #2ecc71;
          background: #ffcc00;
          padding: 0.5rem;
          border: 0.1875rem solid #166534;
        }

        .doctor-name {
          font-family: 'Courier New', Courier, monospace;
          font-weight: 900;
          font-size: 1rem;
          color: #166534;
        }

        .view-hint {
          margin-left: auto;
          font-size: 0.75rem;
          color: #2ecc71;
          font-family: monospace;
          opacity: 0.6;
          transition: opacity 0.15s;
        }
      }

      .doctor-profile-card {
        display: flex;
        gap: 2rem;
        padding: 1.5rem;
        background: #ffffff;
        border: 0.25rem solid #166534;
        box-shadow:
          inset 0.25rem 0.25rem 0 rgba(255, 255, 255, 0.8),
          0.5rem 0.5rem 0 rgba(22, 101, 52, 0.15);

        .avatar {
          width: 7.5rem;
          height: 7.5rem;
          background: #ffffff;
          border: 0.25rem solid #166534;
          padding: 0.5rem;
          flex-shrink: 0;
          box-shadow: inset 0.25rem 0.25rem 0 rgba(0,0,0,0.05);

          .avatar-image {
            width: 100%;
            height: 100%;
            object-fit: contain;
            image-rendering: pixelated;
          }
        }

        .info {
          width: 37.5rem;
          flex-shrink: 0;

          h3 {
            margin: 0 0 0.5rem 0;
            font-size: 1.625rem;
            font-family: 'Courier New', Courier, monospace;
            font-weight: 900;
            color: #000;
          }

          .doctor-id {
            margin: 0 0 1rem 0;
            font-family: monospace;
            color: #2ecc71;
            font-size: 0.875rem;
            font-weight: bold;
          }

          .department, .location {
            display: flex;
            align-items: center;
            gap: 0.625rem;
            margin: 0 0 0.625rem 0;
            font-size: 0.875rem;
            font-weight: 900;
            color: #166534;

            .el-icon {
              color: #ffcc00;
              font-size: 1.125rem;
              filter: drop-shadow(0.0625rem 0.0625rem 0 #166534);
            }
          }
        }

        .specialties-box {
          flex: 1;
          min-width: 20rem;
          border-left: 0.1875rem dashed #f0fdf4;
          padding-left: 1.5rem;

          h4 {
            margin: 0 0 1rem 0;
            font-size: 0.75rem;
            font-family: monospace;
            color: #2ecc71;
            text-transform: uppercase;
            font-weight: 900;
          }

          .specialties {
            display: flex;
            flex-wrap: wrap;
            gap: 0.5rem;
          }
        }
      }

      .patients-grid {
        display: flex;
        flex-wrap: wrap;
        gap: 0.75rem;

        .patient-tag-clickable {
          cursor: pointer;
          border: 0.1875rem solid #166534 !important;
          border-radius: 0 !important;
          background: #ffea00 !important;
          color: #166534 !important;
          font-family: monospace;
          font-weight: 900;
          transition: all 0.1s;
          box-shadow: 0.25rem 0.25rem 0 rgba(22, 101, 52, 0.2);

          &:hover {
            transform: translate(-0.125rem, -0.125rem);
            box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.3);
            background: #fff !important;
          }

          &:active {
            transform: translate(0, 0);
            box-shadow: 0 0 0 transparent;
          }
        }
      }

      .load-more-wrapper {
        margin-top: 1rem;
        display: flex;
        justify-content: center;
      }

      .stats-grid {
        display: grid;
        grid-template-columns: repeat(auto-fit, minmax(12.5rem, 1fr));
        gap: 1.25rem;

        .stat-card {
          background: #fff;
          border: 0.25rem solid #166534;
          padding: 1.5rem;
          text-align: center;
          display: flex;
          flex-direction: column;
          align-items: center;
          gap: 0.75rem;
          box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.1);

          .stat-value {
            font-size: 1.75rem;
            font-family: 'Press Start 2P', cursive;
            color: #2ecc71;
            line-height: 1;
            text-shadow: 0.125rem 0.125rem 0 rgba(22, 101, 52, 0.1);
          }

          .stat-label {
            font-size: 0.6875rem;
            font-family: monospace;
            text-transform: uppercase;
            color: #166534;
            font-weight: 900;
          }
        }
      }

      .evaluation-cards {
        display: flex;
        flex-direction: column;
        gap: 1.25rem;
      }

      .search-box {
        margin-bottom: 1rem;

        :deep(.el-input) {
          .el-input__wrapper {
            border: 0.1875rem solid #166534;
            border-radius: 0;
            box-shadow: 0.25rem 0.25rem 0 rgba(22, 101, 52, 0.1);
            background: #fff;

            &:hover, &:focus-within {
              box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.15);
            }
          }

          .el-input__inner {
            font-family: monospace;
            font-weight: bold;
          }

          .el-input__prefix {
            color: #2ecc71;
          }
        }
      }

      .no-results {
        text-align: center;
        padding: 2.5rem 1.25rem;
        color: #95a5a6;
        font-family: monospace;
        font-size: 0.875rem;
        background: #fff;
        border: 0.1875rem dashed #166534;
      }

      .loading-placeholder {
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        gap: 1rem;
        padding: 5rem 1.25rem;
        color: #95a5a6;
        font-family: monospace;
      }
    }
  }
}

.consultation-placeholder {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.75rem;
  border-radius: 0.5rem;
  background: #f0f9ff;
  color: #1a4b8c;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.consultation-tablet {
  display: flex;
  justify-content: center;
  padding: 1.25rem 0;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

.tablet-frame {
  width: 100%;
  max-width: 75rem;
  background: #1d1d1f;
  border-radius: 2.25rem;
  padding: 0.75rem;
  box-shadow:
    0 1.25rem 3.125rem -0.75rem rgba(0, 0, 0, 0.5),
    0 0 0 0.0625rem rgba(0, 0, 0, 0.1);
  position: relative;
}

.tablet-bezel {
  background: #000;
  border-radius: 1.75rem;
  padding: 0.75rem;
  position: relative;
  overflow: hidden;
}

.tablet-camera {
  width: 0.375rem;
  height: 0.375rem;
  background: #1a1a1a;
  border-radius: 50%;
  position: absolute;
  top: 0.75rem;
  left: 50%;
  transform: translateX(-50%);
  box-shadow: inset 0 0 0.125rem rgba(255,255,255,0.1);
  z-index: 10;
}

.tablet-screen {
  background: #fff;
  border-radius: 1.25rem;
  overflow: hidden;
  height: 37.5rem;
  position: relative;
}

.tablet-app {
  display: flex;
  height: 100%;
  background: #f5f5f7;
}

.tablet-sidebar {
  width: 4.375rem;
  background: rgba(255, 255, 255, 0.85);
  backdrop-filter: blur(1.25rem);
  -webkit-backdrop-filter: blur(1.25rem);
  border-right: 0.0625rem solid rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  align-items: center;
  padding: 1.25rem 0;
  gap: 1.5rem;
  z-index: 2;
}

.tablet-spacer {
  flex: 1;
}

.tablet-button {
  width: 2.75rem;
  height: 2.75rem;
  border-radius: 0.75rem;
  display: flex;
  align-items: center;
  justify-content: center;
  color: #8e8e93;
  transition: all 0.2s;
  cursor: pointer;

  &:hover {
    background: rgba(0,0,0,0.05);
    color: #007aff;
  }

  &.active {
    background: #e4ebf5;
    color: #007aff;
  }
}

.tablet-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  background: #fff;
}

.tablet-app-header {
  height: 3.75rem;
  background: rgba(255, 255, 255, 0.8);
  backdrop-filter: blur(1.25rem);
  border-bottom: 0.0625rem solid rgba(0,0,0,0.05);
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0 1.5rem;
  z-index: 1;
}

.app-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #000;
  letter-spacing: -0.03125rem;
}

.app-meta {
  display: flex;
  align-items: center;
  gap: 0.75rem;
  font-size: 0.8125rem;
  color: #8e8e93;
}

.status-badge {
  padding: 0.25rem 0.5rem;
  border-radius: 0.75rem;
  font-size: 0.6875rem;
  font-weight: 600;
  text-transform: uppercase;

  &.live {
    background: #e5f9ed;
    color: #34c759;
  }
}

.app-body {
  display: flex;
  flex: 1;
  overflow: hidden;
}

.consultation-patients {
  width: 16.25rem;
  background: #fff;
  border-right: 0.0625rem solid rgba(0,0,0,0.05);
  display: flex;
  flex-direction: column;
  overflow-y: auto;
}

.consultation-patients::-webkit-scrollbar,
.consultation-thread-body::-webkit-scrollbar {
  width: 0.375rem;
}
.consultation-patients::-webkit-scrollbar-track,
.consultation-thread-body::-webkit-scrollbar-track {
  background: transparent;
}
.consultation-patients::-webkit-scrollbar-thumb,
.consultation-thread-body::-webkit-scrollbar-thumb {
  background: rgba(0, 0, 0, 0.2);
  border-radius: 0.1875rem;
}
.consultation-patients::-webkit-scrollbar-thumb:hover,
.consultation-thread-body::-webkit-scrollbar-thumb:hover {
  background: rgba(0, 0, 0, 0.4);
}

.list-header {
  padding: 1rem 1.25rem;
  font-size: 0.8125rem;
  font-weight: 600;
  color: #8e8e93;
  background: rgba(251, 251, 251, 0.95);
  backdrop-filter: blur(0.625rem);
  text-transform: uppercase;
  position: sticky;
  top: 0;
  z-index: 10;
  border-bottom: 0.0625rem solid rgba(0,0,0,0.05);
}

.consultation-empty-list {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 1.5rem 1rem;
  color: #c7c7cc;
  font-size: 0.875rem;
  text-align: center;
}

.consultation-patient-card {
  display: flex;
  padding: 0.75rem 1rem;
  gap: 0.75rem;
  cursor: pointer;
  transition: all 0.2s cubic-bezier(0.25, 0.1, 0.25, 1);
  border-bottom: 0.0625rem solid #f5f5f7;
  border-radius: 0.75rem;
  margin: 0.25rem 0.5rem;

  &.active {
    background: #e4ebf5;
    border-left: none;
    box-shadow: 0 0.125rem 0.5rem rgba(0, 0, 0, 0.04);
  }

  &:hover:not(.active) {
    background: #f5f5f7;
  }

  .patient-avatar-img {
    width: 3rem;
    height: 3rem;
    border-radius: 50%;
    overflow: hidden;
    background: #f0f0f0;
    flex-shrink: 0;
    border: 0.125rem solid #fff;
    box-shadow: 0 0.125rem 0.25rem rgba(0,0,0,0.1);

    img {
      width: 100%;
      height: 100%;
      object-fit: cover;
    }
  }

  .patient-info {
    flex: 1;
    min-width: 0;
    display: flex;
    flex-direction: column;
    justify-content: center;
    gap: 0.25rem;
  }

  .patient-id {
    font-size: 0.9375rem;
    font-weight: 600;
    color: #1d1d1f;
    line-height: 1.2;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
  }

  .patient-preview {
    font-size: 0.8125rem;
    color: #86868b;
    white-space: nowrap;
    overflow: hidden;
    text-overflow: ellipsis;
    line-height: 1.2;
  }

  .patient-meta {
    display: flex;
    flex-direction: column;
    align-items: flex-end;
    gap: 0.375rem;
    min-width: 2.5rem;
    margin-top: 0.125rem;
  }
}

.consultation-thread {
  flex: 1;
  display: flex;
  flex-direction: column;
  background: #fff;
}

.consultation-thread-header {
  padding: 1rem 1.5rem;
  border-bottom: 0.0625rem solid #f5f5f7;

  .header-info {
    display: flex;
    flex-direction: column;
  }

  .patient-name {
    font-size: 1.0625rem;
    font-weight: 600;
    color: #000;
  }

  .subtitle {
    font-size: 0.8125rem;
    color: #8e8e93;
  }
}

.consultation-thread-body {
  flex: 1;
  padding: 1.25rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
  overflow-y: auto;
  background: #f9f9f9;
}

.consultation-message {
  display: flex;
  max-width: 80%;

  &.message-in {
    align-self: flex-start;
    .message-bubble {
      background: #e9e9eb;
      color: #000;
      border-bottom-left-radius: 0.25rem;
    }
  }

  &.message-out {
    align-self: flex-end;
    .message-bubble {
      background: #007aff;
      color: #fff;
      border-bottom-right-radius: 0.25rem;

      .message-sender-name, .message-tick {
        color: rgba(255,255,255,0.7);
      }
    }
  }
}

.message-bubble {
  padding: 0.75rem 1rem;
  border-radius: 1.125rem;
  position: relative;
  box-shadow: 0 0.0625rem 0.125rem rgba(0,0,0,0.1);

  .message-sender-name {
    font-size: 0.6875rem;
    font-weight: 600;
    margin-bottom: 0.375rem;
    color: #8e8e93;
  }

  .message-content {
    font-size: 0.9375rem;
    line-height: 1.6;
    word-break: break-word;
  }

  .message-footer {
    display: flex;
    justify-content: flex-end;
    margin-top: 0.375rem;
  }

  .message-tick {
    font-size: 0.625rem;
    color: #8e8e93;
  }
}

.consultation-input-area {
  padding: 1rem;
  border-top: 0.0625rem solid #f5f5f7;
  background: #fff;

  .input-placeholder {
    width: 100%;
    height: 2.5rem;
    background: #f5f5f7;
    border-radius: 1.25rem;
    display: flex;
    align-items: center;
    padding: 0 1rem;
    color: #c7c7cc;
    font-size: 0.875rem;
  }
}

.empty-selection {
  flex: 1;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  color: #c7c7cc;
  gap: 1rem;

  p {
    font-size: 1rem;
    font-weight: 500;
  }
}

@media (max-width: 68.75rem) {
  .tablet-frame {
    max-width: 100%;
  }
  .app-body {
    flex-direction: column;
  }
  .consultation-patients {
    width: 100%;
    height: 12.5rem;
    overflow-y: auto;
    border-right: none;
    border-bottom: 0.0625rem solid #f5f5f7;
  }
}
@media (max-width: 80rem) {
  .dashboard {
    .sidebar {
      width: 18rem;
    }

    .main-panel {
      .detail-content {
        .doctor-profile-card {
          .info {
            width: 25rem;
          }

          .specialties-box {
            min-width: 15rem;
          }
        }
      }
    }
  }
}
@media (max-width: 64rem) {
  .dashboard {
    .sidebar {
      width: 16rem;
    }

    .main-panel {
      .detail-header {
        padding: 0.5rem 1rem;

        h2 {
          font-size: 1.125rem;
        }
      }

      .detail-content {
        .content-grid {
          padding: 1rem;
          gap: 1.5rem;
        }

        .doctor-profile-card {
          flex-direction: column;
          gap: 1rem;

          .info {
            width: 100%;
          }

          .specialties-box {
            border-left: none;
            border-top: 0.1875rem dashed #f0fdf4;
            padding-left: 0;
            padding-top: 1rem;
            min-width: unset;
          }
        }

        .conversation-container {
          min-height: 28rem;
          height: 28rem;
        }
      }
    }
  }

  .initial-boot-screen {
    .system-title {
      font-size: 1.25rem;
    }

    .loading-bar-container .loading-bar-fill .welcome-text {
      font-size: 4rem;
    }
  }
}
@media (max-width: 48rem) {
  .dashboard {
    flex-direction: column;

    .sidebar {
      width: 100%;
      height: auto;
      max-height: 40vh;
      border-right: none;
      border-bottom: 0.25rem solid #0066cc;

      .sidebar-tabs {
        :deep(.el-tabs__content) {
          max-height: calc(40vh - 2.5rem);
          overflow-y: auto;
        }
      }
    }

    .main-panel {
      flex: 1;
      min-height: 60vh;

      .empty-state, .loading-state {
        .el-icon {
          font-size: 3rem;
        }

        h2 {
          font-size: 0.875rem;
        }
      }

      .detail-header {
        h2 {
          font-size: 1rem;
        }

        .patient-id-subtitle,
        .doctor-id-subtitle {
          font-size: 0.625rem;
          padding: 0.125rem 0.375rem;
        }
      }

      .detail-content {
        .content-grid {
          padding: 0.75rem;
          gap: 1rem;
        }

        .doctor-profile-card {
          padding: 1rem;

          .avatar {
            width: 5rem;
            height: 5rem;
          }

          .info h3 {
            font-size: 1.25rem;
          }
        }

        .conversation-container {
          min-height: 22rem;
          height: 22rem;
        }

        .stats-grid {
          grid-template-columns: repeat(2, 1fr);
          gap: 0.75rem;

          .stat-card {
            padding: 1rem;

            .stat-value {
              font-size: 1.25rem;
            }
          }
        }
      }
    }
  }

  .initial-boot-screen {
    .boot-content {
      padding: 1.5rem;
      max-width: 90%;
    }

    .system-title {
      font-size: 1rem;
    }

    .subtitle {
      font-size: 0.75rem;
    }

    .boot-messages .msg {
      font-size: 0.625rem;
    }

    .loading-bar-container .loading-bar-fill .welcome-text {
      font-size: 2.5rem;
      letter-spacing: 0.25rem;
    }

    .pixel-logo .logo-icon {
      font-size: 3.5rem;
    }
  }

  .consultation-tablet {
    padding: 0.5rem;

    .tablet-frame {
      border-radius: 1rem;
      padding: 0.5rem;
    }

    .tablet-bezel {
      border-radius: 0.75rem;
    }

    .tablet-screen {
      border-radius: 0.5rem;
      height: 25rem;
    }

    .tablet-sidebar {
      width: 3rem;
      padding: 0.75rem 0;
      gap: 1rem;

      .tablet-button {
        width: 2rem;
        height: 2rem;
        font-size: 0.875rem;
      }
    }

    .consultation-patients {
      height: 8rem;
    }
  }
}
@media (max-width: 37.5rem) {
  .dashboard {
    .sidebar {
      max-height: 35vh;

      .sidebar-tabs {
        :deep(.el-tabs__item) {
          font-size: 0.6875rem;
          padding: 0 0.75rem !important;
        }
      }
    }

    .main-panel {
      .detail-content {
        .section h3 {
          font-size: 0.875rem;

          &::before {
            width: 0.5rem;
            height: 1rem;
          }
        }

        .assigned-doctor-card {
          padding: 0.75rem;

          .doctor-icon {
            font-size: 1.25rem;
            padding: 0.375rem;
          }

          .doctor-name {
            font-size: 0.875rem;
          }
        }
      }
    }
  }

  .consultation-tablet {
    .tablet-sidebar {
      display: none;
    }

    .consultation-patient-card {
      padding: 0.5rem 0.75rem;

      .patient-avatar-img {
        width: 2.5rem;
        height: 2.5rem;
      }

      .patient-id {
        font-size: 0.8125rem;
      }

      .patient-preview {
        font-size: 0.6875rem;
      }
    }

    .consultation-thread-header {
      padding: 0.75rem 1rem;

      .patient-name {
        font-size: 0.9375rem;
      }
    }

    .consultation-thread-body {
      padding: 0.75rem;

      .message-bubble {
        padding: 0.5rem 0.75rem;

        .message-content {
          font-size: 0.8125rem;
        }
      }
    }
  }
}
@media (max-width: 30rem) {
  .dashboard {
    .sidebar {
      max-height: 30vh;
    }

    .main-panel {
      .detail-content {
        .doctor-profile-card {
          .avatar {
            width: 4rem;
            height: 4rem;
          }

          .info h3 {
            font-size: 1rem;
          }

          .department, .location {
            font-size: 0.75rem;

            .el-icon {
              font-size: 1rem;
            }
          }
        }

        .stats-grid {
          grid-template-columns: 1fr;
        }

        .conversation-container {
          min-height: 18rem;
          height: 18rem;
        }
      }
    }
  }

  .initial-boot-screen {
    .boot-content {
      padding: 1rem;
      border-width: 0.25rem;
    }

    .system-title {
      font-size: 0.75rem;
      letter-spacing: 0.0625rem;
    }

    .subtitle {
      font-size: 0.625rem;
      margin-bottom: 1rem;
    }

    .pixel-logo .logo-icon {
      font-size: 2.5rem;
      margin-bottom: 0.75rem;
    }

    .boot-messages {
      height: auto;

      .msg {
        font-size: 0.5rem;
        margin-bottom: 0.125rem;
      }
    }

    .loading-bar-container .loading-bar-fill .welcome-text {
      font-size: 1.5rem;
      letter-spacing: 0.125rem;
    }
  }
}
.skeleton-header {
  background: #a8d8a8 !important;
}

.skeleton-profile-card {
  background: #fff;
  border: 0.25rem solid #166534;
  padding: 1.5rem;
  box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.1);

  .skeleton-profile-inner {
    display: flex;
    gap: 1.5rem;
    align-items: flex-start;
  }

  .skeleton-profile-info {
    display: flex;
    flex-direction: column;
  }
}

.skeleton-timeline {
  background: #fdf6e3;
  border: 0.5rem solid #d4a373;
  padding: 1.25rem;
  box-shadow: 0.5rem 0.5rem 0 rgba(0, 0, 0, 0.2);

  .skeleton-timeline-inner {
    display: flex;
    gap: 1rem;
    justify-content: center;
  }
}

.skeleton-conversation {
  background: #fff;
  border: 0.25rem solid #166534;
  padding: 1.5rem;
  min-height: 18.75rem;
  box-shadow: 0.375rem 0.375rem 0 rgba(22, 101, 52, 0.1);

  .skeleton-messages {
    display: flex;
    flex-direction: column;
    gap: 1rem;
  }

  .skeleton-msg {
    display: flex;
    gap: 0.75rem;
    align-items: flex-end;

    &.skeleton-msg-left {
      justify-content: flex-start;
    }

    &.skeleton-msg-right {
      justify-content: flex-end;
    }
  }
}
</style>
