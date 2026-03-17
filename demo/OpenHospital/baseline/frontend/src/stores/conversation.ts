import { defineStore } from 'pinia'
import { ref } from 'vue'
import type { Conversation, ConversationMessage } from '@/types'
import { request } from '@/api/request'

export const useConversationStore = defineStore('conversation', () => {
  const conversations = ref<Map<string, Conversation>>(new Map())
  const currentConversation = ref<Conversation | null>(null)
  const loading = ref(false)
  const MAX_CONVERSATIONS = 50
  let currentAbortController: AbortController | null = null
  function getConversationId(participant1: string, participant2: string): string {
    return [participant1, participant2].sort().join('-')
  }
  function cleanupOldConversations() {
    if (conversations.value.size > MAX_CONVERSATIONS) {
      const entries = Array.from(conversations.value.entries())
      const toDelete = entries.slice(0, entries.length - MAX_CONVERSATIONS)
      toDelete.forEach(([id]) => {
        conversations.value.delete(id)
      })
    }
  }
  async function fetchConversation(patientId: string, doctorId: string) {
    if (!patientId || !doctorId) {
      console.warn('fetchConversation: missing patientId or doctorId')
      return
    }
    if (currentAbortController) {
      currentAbortController.abort()
      currentAbortController = null
    }
    currentAbortController = new AbortController()
    const signal = currentAbortController.signal
    
    loading.value = true
    const id = getConversationId(patientId, doctorId)
    
    try {
      const data = await request.get<Conversation>(
        `/conversations/between/${patientId}/${doctorId}`,
        { signal }
      )
      if (signal.aborted) {
        return
      }
      
      if (data) {
        conversations.value.set(id, data)
        currentConversation.value = data
      } else {
        const emptyConversation: Conversation = {
          id,
          type: 'consultation',
          participants: [patientId, doctorId].sort(),
          messages: []
        }
        conversations.value.set(id, emptyConversation)
        currentConversation.value = emptyConversation
      }
      cleanupOldConversations()
    } catch (error: any) {
      if (signal.aborted || error?.name === 'AbortError' || error?.name === 'CanceledError') {
        return
      }
      console.error('Failed to fetch conversation:', error)
      if (signal.aborted) {
        return
      }
      const emptyConversation: Conversation = {
        id,
        type: 'consultation',
        participants: [patientId, doctorId].sort(),
        messages: []
      }
      conversations.value.set(id, emptyConversation)
      currentConversation.value = emptyConversation
      cleanupOldConversations()
    } finally {
      if (!signal.aborted) {
        loading.value = false
      }
      currentAbortController = null
    }
  }
  
  function getConversation(patientId: string, doctorId: string): Conversation | undefined {
    const id = getConversationId(patientId, doctorId)
    return conversations.value.get(id)
  }
  
  function addMessage(payload: {
    sender: string
    target: string
    content: string
    tick: number
  }) {
    const { sender, target, content, tick } = payload
    const id = getConversationId(sender, target)
    
    const conversation = conversations.value.get(id)
    if (conversation) {
      const exists = conversation.messages.some(m => 
        m.sender === sender && 
        m.content === content && 
        m.created_at === tick
      )
      
      if (exists) return

      const newMessage: ConversationMessage = {
        id: conversation.messages.length + 1,
        sender,
        content,
        created_at: tick,
        extra: {
          type: sender.startsWith('Doctor_') ? 'doctor_to_patient' : 'patient_to_doctor'
        }
      }
      conversation.messages.push(newMessage)
    } else {
      const newConversation: Conversation = {
        id,
        type: 'consultation',
        participants: [sender, target].sort(),
        messages: [{
          id: 1,
          sender,
          content,
          created_at: tick,
          extra: {
            type: sender.startsWith('Doctor_') ? 'doctor_to_patient' : 'patient_to_doctor'
          }
        }]
      }
      conversations.value.set(id, newConversation)
    }
    if (currentConversation.value?.id === id) {
      currentConversation.value = conversations.value.get(id) || null
    }
  }
  
  function clearCurrentConversation() {
    currentConversation.value = null
  }
  
  return {
    conversations,
    currentConversation,
    loading,
    fetchConversation,
    getConversation,
    getConversationId,
    addMessage,
    clearCurrentConversation,
  }
})

