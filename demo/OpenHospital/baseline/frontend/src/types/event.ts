export interface SimulationEvent {
  category: EventCategory
  name: string
  payload: Record<string, unknown>
  tick: number
}

export type EventCategory = 'agent' | 'system' | 'environment'
export type EventType = 
  | 'PATIENT_MOVE'
  | 'PATIENT_REGISTER'
  | 'DO_EXAMINATION'
  | 'RECEIVE_TREATMENT'
  | 'SCHEDULE_EXAMINATION'
  | 'PRESCRIBE_TREATMENT'
  | 'SEARCH_MEDICAL_KNOWLEDGE'
  | 'SEND_MESSAGE'
  | 'IDLE'
  | 'LLM_INFERENCE'
export interface SimulationStatus {
  current_tick: number
  total_doctors: number
  total_patients: number
  active_consultations: number
  is_running: boolean
}

export interface SimulationStatistics {
  diagnosis_accuracy: number
  examination_precision: number
  total_tokens: number
}
