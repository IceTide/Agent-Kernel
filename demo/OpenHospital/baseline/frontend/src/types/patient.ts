export interface Patient {
  id: string                     // e.g., "Patient_001"
  name: string                   // e.g., "Zhang San"
  template: string               // "PatientAgent"
  initial_location: string       // "community"
  demographics: Demographics
  persona: string                // 详细的性格描述
  initial_complaint?: string     // 初始Chief Complaint (兼容旧格式)
  communication_style_label?: string  // Communication Style (兼容旧格式)
  appearance?: string            // Appearance描述 (兼容旧格式)
  present_illness_history?: PresentIllnessHistory
  medical_history?: MedicalHistory
  personal_history?: PersonalHistory
  family_history?: FamilyHistory
  current_phase?: PatientPhase
  assigned_doctor?: string
  department?: string
  consultation_room?: string
  current_location?: string
  position?: [number, number]
}
export interface PresentIllnessHistory {
  chief_complaint?: string
  triggers_of_disease?: string
  symptoms_and_progression?: string
  current_general_status?: {
    diet?: string
    sleep?: string
    excretion?: string
    weight_change?: string
  }
}
export interface MedicalHistory {
  previous_diseases?: string[]
  long_term_medication?: string
  surgery_or_trauma?: string
  allergies?: {
    food?: string[]
    drug?: string[]
  }
  infectious_diseases?: string[]
  blood_transfusion?: string
  vaccinations?: string
}
export interface PersonalHistory {
  smoking?: string
  alcohol?: string
  obstetric_history?: string
  menstrual_history?: string
}
export interface FamilyHistory {
  similar_illness?: string
  hereditary_diseases?: string
}

export interface Demographics {
  age: number
  gender: string  // 'Male' | 'Female' or other values
  name?: string
  marital_status?: string
  occupation?: string
}

export type PatientPhase =
  | 'idle'              // Idle
  | 'home'              // 初始Status（在家/社区）
  | 'registered'        // 已Registered
  | 'consulting'        // 就诊中
  | 'examined'          // 检查完成
  | 'treated'           // 治疗完成
  | 'finish'            // 流程结束

export interface PatientSummary {
  id: string
  name: string
  demographics: Demographics
  current_phase: PatientPhase
  assigned_doctor?: string
  department?: string
}

export interface PatientState {
  current_phase: PatientPhase
  assigned_doctor?: string
  department?: string
  consultation_room?: string
  current_location?: string
  treatment_result?: 'success' | 'failure'
}

export interface PatientDetail extends Patient {
  state: PatientState
  examinations: ExaminationRecord[]
  prescriptions: PrescriptionRecord[]
  trajectory: TrajectoryEvent[]
}

export interface TrajectoryEvent {
  tick: number
  event_type: string
  agent_id: string
  status: string
  payload: Record<string, unknown>
}
import type { ExaminationRecord } from './examination'
import type { PrescriptionRecord } from './prescription'
export const PHASE_CONFIG: Record<PatientPhase, { label: string; type: string; icon: string }> = {
  idle: { label: 'Idle', type: 'info', icon: 'House' },
  home: { label: 'Home', type: 'info', icon: 'House' },
  registered: { label: 'Registered', type: 'primary', icon: 'Ticket' },
  consulting: { label: 'Consulting', type: 'warning', icon: 'ChatDotRound' },
  examined: { label: 'Examined', type: 'success', icon: 'Document' },
  treated: { label: 'Treated', type: 'success', icon: 'CircleCheck' },
  finish: { label: 'Completed', type: 'success', icon: 'CircleCheck' },
}
