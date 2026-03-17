export interface ConversationMessage {
  id: number
  sender: string              // 发送者 ID
  content: string             // 消息内容
  created_at: number          // tick 时间戳
  extra?: {
    type: MessageType
  }
}

export type MessageType = 'doctor_to_patient' | 'patient_to_doctor' | 'agent_to_agent'

export interface Conversation {
  id: string                  // e.g., "Doctor_Cardiology_001-Patient_001"
  type: string                // "consultation"
  participants: string[]      // [patient_id, doctor_id]
  messages: ConversationMessage[]
}

export interface ConversationSummary {
  id: string
  participants: string[]
  message_count: number
  last_message_tick?: number
}

export interface DoctorConsultationMessage {
  id: number
  sender: string
  receiver: string
  content: string
  created_at: number
  patient_id: string
  message_type?: MessageType
}

export interface DoctorConsultationGroup {
  patient_id: string
  message_count: number
  last_message_tick?: number
  messages: DoctorConsultationMessage[]
}
