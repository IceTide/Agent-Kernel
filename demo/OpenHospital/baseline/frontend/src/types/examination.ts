export interface ExaminationRecord {
  id: string
  patient_id: string
  doctor_id: string
  examination_items: string[]   // e.g., ["血常规", "心电图", "胸部CT"]
  ordered_tick: number
  status: ExaminationStatus
  completed_tick?: number
  results?: Record<string, ExaminationResult>
}

export type ExaminationStatus = 'pending' | 'completed'

export interface ExaminationResult {
  name: string
  result: string
  reference_range?: string
  abnormal?: boolean
}

