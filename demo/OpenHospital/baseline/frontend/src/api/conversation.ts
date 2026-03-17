import { request } from './request'
import type { Conversation, ConversationSummary } from '@/types'

export interface ConversationListParams {
  patient_id?: string
  doctor_id?: string
}

export const conversationApi = {
  getConversations(params?: ConversationListParams): Promise<ConversationSummary[]> {
    return request.get('/conversations', { params })
  },
  getConversation(conversationId: string): Promise<Conversation> {
    return request.get(`/conversations/${conversationId}`)
  },
  getConversationBetween(patientId: string, doctorId: string): Promise<Conversation> {
    return request.get(`/conversations/between/${patientId}/${doctorId}`)
  },
}
