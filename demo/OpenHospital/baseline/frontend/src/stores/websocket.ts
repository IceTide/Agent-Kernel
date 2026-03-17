import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { SimulationEvent, SimulationStatus } from '@/types'
import { usePatientStore } from './patient'
import { useDoctorStore } from './doctor'
import { useConversationStore } from './conversation'

export const useWebSocketStore = defineStore('websocket', () => {
  const socket = ref<WebSocket | null>(null)
  const connected = ref(false)
  const reconnecting = ref(false)
  const isInitialSystemLoading = ref(true)
  const events = ref<SimulationEvent[]>([])
  const simulationStatus = ref<SimulationStatus>({
    current_tick: 0,
    total_doctors: 0,
    total_patients: 0,
    active_consultations: 0,
    is_running: false,
  })
  const MAX_EVENTS = 1000
  let reconnectAttempts = 0
  const MAX_RECONNECT_ATTEMPTS = 10
  const RECONNECT_DELAY = 3000
  let lastPatientRefresh = 0
  const REFRESH_THROTTLE = 2000 // 2秒节流（增加节流时间）
  const lastRefreshTimes = new Map<string, number>() // 为每个患者/医生记录上次刷新时间
  function connect() {
    if (socket.value?.readyState === WebSocket.OPEN) {
      return
    }

    const wsUrl = import.meta.env.VITE_WS_URL || `ws://${window.location.hostname}:8000/ws/events`
    socket.value = new WebSocket(wsUrl)

    socket.value.onopen = () => {
      console.log('WebSocket connected')
      connected.value = true
      reconnecting.value = false
      reconnectAttempts = 0
    }

    socket.value.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data)
        if (data.type === 'event' && data.data) {
          handleEvent(data.data)
        } else if (data.type === 'connected') {
          if (data.status) {
            simulationStatus.value = { ...simulationStatus.value, ...data.status }
          }
          console.log('WebSocket connected with status:', data.status)
        } else if (data.type === 'heartbeat' || data.type === 'pong') {
        } else if (data.name) {
          handleEvent(data)
        }
      } catch (error) {
        console.error('Failed to parse WebSocket message:', error)
      }
    }

    socket.value.onclose = () => {
      console.log('WebSocket disconnected')
      connected.value = false
      if (reconnectAttempts < MAX_RECONNECT_ATTEMPTS) {
        reconnecting.value = true
        reconnectAttempts++
        console.log(`Reconnecting... attempt ${reconnectAttempts}`)
        setTimeout(connect, RECONNECT_DELAY)
      }
    }

    socket.value.onerror = (error) => {
      console.error('WebSocket error:', error)
    }
  }

  function disconnect() {
    if (socket.value) {
      socket.value.close()
      socket.value = null
    }
    connected.value = false
    reconnecting.value = false
  }

  function handleEvent(event: SimulationEvent) {
    const ignoredEvents = ['IDLE']

    if (!ignoredEvents.includes(event.name)) {
      events.value.push(event)
      if (events.value.length > MAX_EVENTS) {
        events.value.shift()
      }
    }
    simulationStatus.value.current_tick = event.tick
    if (ignoredEvents.includes(event.name)) {
      return
    }
    const patientStore = usePatientStore()
    const doctorStore = useDoctorStore()
    const conversationStore = useConversationStore()

    const now = Date.now()
    const getPatientId = (): string => {
      return (event.payload.patient_id as string) ||
             (event.payload.agent_id as string) ||
             ''
    }

    const patientId = getPatientId()

    switch (event.name) {
      case 'PATIENT_REGISTER':
        patientStore.updatePatientPhase(patientId, 'registered')
        if (event.payload.doctor_id && event.payload.department) {
          patientStore.updatePatientDoctor(
            patientId,
            event.payload.doctor_id as string,
            event.payload.department as string
          )
        }
        triggerListRefreshOnly(patientStore, now)
        break

      case 'SEND_MESSAGE':
        conversationStore.addMessage({
          sender: event.payload.sender as string || event.payload.agent_id as string,
          target: event.payload.target as string,
          content: event.payload.content as string || event.payload.content_preview as string,
          tick: event.tick,
        })
        break

      case 'SCHEDULE_EXAMINATION':
        patientStore.updatePatientPhase(patientId, 'consulting')
        triggerCurrentPatientRefresh(patientStore, now)
        break

      case 'DO_EXAMINATION':
        patientStore.updatePatientPhase(patientId, 'consulting')
        triggerCurrentPatientRefresh(patientStore, now)
        break

      case 'EXAMINATION_COMPLETE':
      case 'EXAMINATION_RESULT':
        patientStore.updatePatientPhase(patientId, 'examined')
        triggerCurrentPatientRefresh(patientStore, now)
        break

      case 'PRESCRIBE_TREATMENT':
        patientStore.updatePatientPhase(patientId, 'examined')
        triggerCurrentPatientRefresh(patientStore, now)
        break

      case 'RECEIVE_TREATMENT':
        patientStore.updatePatientPhase(patientId, 'treated')
        triggerCurrentPatientRefresh(patientStore, now)
        triggerCurrentDoctorRefresh(doctorStore, now)
        break

      case 'DOCTOR_REFLECT':
      case 'DOCTOR_REFLECTION':
        triggerCurrentDoctorRefresh(doctorStore, now)
        break

      case 'CONSULTATION_START':
      case 'CONSULTATION_END':
        triggerCurrentPatientRefresh(patientStore, now)
        triggerCurrentDoctorRefresh(doctorStore, now)
        break

      default:
        triggerCurrentPatientRefresh(patientStore, now)
        triggerCurrentDoctorRefresh(doctorStore, now)
        break
    }
  }
  async function triggerListRefreshOnly(patientStore: ReturnType<typeof usePatientStore>, now: number) {
    if (now - lastPatientRefresh < REFRESH_THROTTLE) return
    lastPatientRefresh = now
    await patientStore.silentFetchPatients()
  }
  async function triggerCurrentPatientRefresh(patientStore: ReturnType<typeof usePatientStore>, now: number) {
    if (!patientStore.selectedPatientId) return

    const lastRefresh = lastRefreshTimes.get(patientStore.selectedPatientId) || 0
    if (now - lastRefresh < REFRESH_THROTTLE) return

    lastRefreshTimes.set(patientStore.selectedPatientId, now)
    await patientStore.refreshCurrentPatient()
  }
  async function triggerCurrentDoctorRefresh(doctorStore: ReturnType<typeof useDoctorStore>, now: number) {
    if (!doctorStore.selectedDoctorId) return

    const lastRefresh = lastRefreshTimes.get(doctorStore.selectedDoctorId) || 0
    if (now - lastRefresh < REFRESH_THROTTLE) return

    lastRefreshTimes.set(doctorStore.selectedDoctorId, now)
    await doctorStore.refreshCurrentDoctor()
  }

  function clearEvents() {
    events.value = []
  }

  return {
    socket,
    connected,
    reconnecting,
    isInitialSystemLoading,
    events,
    simulationStatus,
    connect,
    disconnect,
    handleEvent,
    clearEvents,
  }
})
