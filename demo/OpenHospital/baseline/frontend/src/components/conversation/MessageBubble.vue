<script setup lang="ts">
import { computed } from 'vue'
import type { ConversationMessage } from '@/types'

interface Props {
  message: ConversationMessage
  patientId?: string
  doctorId?: string
}

const props = defineProps<Props>()

const isDoctor = computed(() => {
  return props.message.sender.startsWith('Doctor_')
})

const senderName = computed(() => {
  if (isDoctor.value) {
    return `🩺 ${props.message.sender}`
  }
  return `👤 ${props.message.sender}`
})

const bubbleClass = computed(() => {
  return isDoctor.value ? 'doctor-bubble' : 'patient-bubble'
})
</script>

<template>
  <div class="message-bubble" :class="bubbleClass">
    <div class="bubble-header">
      <span class="sender">{{ senderName }}</span>
      <span class="tick">Tick {{ props.message.created_at }}</span>
    </div>
    <div class="bubble-content">
      {{ props.message.content }}
    </div>
  </div>
</template>

<style scoped lang="scss">
.message-bubble {
  max-width: 100%;
  width: 100%;

  .bubble-header {
    display: flex;
    align-items: center;
    gap: 0.5rem;
    margin-bottom: 0.25rem;

    .sender {
      font-size: 0.9rem;
      line-height: 2.2;
      letter-spacing: 0;
      font-weight: 400;
    }

    .tick {
      font-size: 0.75rem;
      line-height: 2.2;
      letter-spacing: 0;
      color: var(--text-placeholder);
    }
  }

  .bubble-content {
    padding: 0.9375rem 1.375rem;
    border-radius: 0;
    font-size: 0.8rem !important;
    line-height: 2;
    letter-spacing: 0;
    white-space: pre-wrap;
    word-break: break-word;
    overflow-wrap: break-word;
    text-align: left;
    border: 0.1875rem solid;
    box-shadow: 0.25rem 0.25rem 0 rgba(0, 0, 0, 0.15);
    position: relative;
    &::after {
      content: '';
      position: absolute;
      width: 0;
      height: 0;
      border-style: solid;
    }
  }

  &.doctor-bubble {
    text-align: right;

    .bubble-header {
      justify-content: flex-end;

      .sender {
        color: #8b9dc3;
      }
    }

    .bubble-content {
      background: #dfe7f5;
      color: #2c3e50;
      border-color: #b8c5db;
      &::after {
        right: -0.75rem;
        top: 0.625rem;
        border-width: 0.375rem 0 0.375rem 0.75rem;
        border-color: transparent transparent transparent #b8c5db;
      }

      &::before {
        content: '';
        position: absolute;
        right: -0.5625rem;
        top: 0.625rem;
        width: 0;
        height: 0;
        border-style: solid;
        border-width: 0.375rem 0 0.375rem 0.5625rem;
        border-color: transparent transparent transparent #dfe7f5;
      }
    }
  }

  &.patient-bubble {
    text-align: left;

    .bubble-header {
      .sender {
        color: #7cb8a8;
      }
    }

    .bubble-content {
      background: #e8f5f1;
      color: #2c3e50;
      border-color: #b3d9cc;
      &::after {
        left: -0.75rem;
        top: 0.625rem;
        border-width: 0.375rem 0.75rem 0.375rem 0;
        border-color: transparent #b3d9cc transparent transparent;
      }

      &::before {
        content: '';
        position: absolute;
        left: -0.5625rem;
        top: 0.625rem;
        width: 0;
        height: 0;
        border-style: solid;
        border-width: 0.375rem 0.5625rem 0.375rem 0;
        border-color: transparent #e8f5f1 transparent transparent;
      }
    }
  }
}
@media (max-width: 48rem) {
  .message-bubble {
    max-width: 90%;

    .bubble-header {
      .sender {
        font-size: 0.5rem;
      }

      .tick-label {
        font-size: 0.4375rem;
      }
    }

    .bubble-content {
      padding: 0.375rem 0.625rem;
      font-size: 0.6875rem;
      line-height: 1.5;
    }
  }
}

@media (max-width: 30rem) {
  .message-bubble {
    max-width: 95%;

    .bubble-header {
      margin-bottom: 0.125rem;
    }

    .bubble-content {
      padding: 0.25rem 0.5rem;
      font-size: 0.625rem;
      border-width: 0.0625rem;
    }
  }
}
</style>
