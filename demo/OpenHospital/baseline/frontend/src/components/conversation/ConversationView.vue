<script setup lang="ts">
import { ref, watch, nextTick, onUnmounted, onMounted } from 'vue'
import type { ConversationMessage } from '@/types'
import type { ScrollbarInstance } from 'element-plus'
import MessageBubble from './MessageBubble.vue'

interface Props {
  messages: ConversationMessage[]
  patientId?: string
  doctorId?: string
}

const props = withDefaults(defineProps<Props>(), {
  messages: () => [],
})

const scrollbarRef = ref<ScrollbarInstance | null>(null)
let scrollTimer: ReturnType<typeof setTimeout> | null = null
const isMounted = ref(false)
const isMonitorOn = ref(true)
const isWindowOpen = ref(true)
const isStartMenuOpen = ref(false)
const showCodeDialog = ref(false)
const codeInput = ref('')
const showSuccessDialog = ref(false)
const showErrorDialog = ref(false)
const currentTime = ref('')
const currentDate = ref('')
function updateTime() {
  const now = new Date()
  currentTime.value = now.toLocaleTimeString('zh-CN', { 
    hour: '2-digit', 
    minute: '2-digit',
    hour12: false 
  })
  currentDate.value = now.toLocaleDateString('zh-CN', {
    year: 'numeric',
    month: '2-digit',
    day: '2-digit'
  })
}

let timeInterval: ReturnType<typeof setInterval> | null = null

onMounted(() => {
  isMounted.value = true
  updateTime()
  timeInterval = setInterval(updateTime, 1000)
})

onUnmounted(() => {
  isMounted.value = false
  if (scrollTimer) {
    clearTimeout(scrollTimer)
    scrollTimer = null
  }
  if (timeInterval) {
    clearInterval(timeInterval)
    timeInterval = null
  }
  scrollbarRef.value = null
})
function scrollToBottom() {
  if (!isMounted.value) return
  
  if (scrollTimer) {
    clearTimeout(scrollTimer)
  }
  
  scrollTimer = setTimeout(() => {
    if (!isMounted.value || !scrollbarRef.value) return
    
    nextTick(() => {
      if (!isMounted.value || !scrollbarRef.value) return
      
      try {
        const wrapEl = scrollbarRef.value.wrapRef
        if (wrapEl && props.messages.length > 0) {
          scrollbarRef.value.setScrollTop(wrapEl.scrollHeight)
        }
      } catch (e) {
        if (isMounted.value) {
          console.warn('Scroll error:', e)
        }
      }
    })
  }, 50)
}
const stopMessagesWatch = watch(
  () => props.messages.length,
  () => {
    if (isMounted.value) {
      scrollToBottom()
    }
  },
  { immediate: false }
)
const stopPatientIdWatch = watch(
  () => props.patientId,
  () => {
    if (!isMounted.value) return
    
    if (scrollTimer) {
      clearTimeout(scrollTimer)
      scrollTimer = null
    }
    
    nextTick(() => {
      if (!isMounted.value || !scrollbarRef.value) return
      
      try {
        scrollbarRef.value.setScrollTop(0)
        scrollToBottom()
      } catch (e) {
        if (isMounted.value) {
          console.warn('Scroll reset error:', e)
        }
      }
    })
  }
)
onUnmounted(() => {
  stopMessagesWatch()
  stopPatientIdWatch()
})
function toggleMonitor() {
  isMonitorOn.value = !isMonitorOn.value
  if (isMonitorOn.value) {
    setTimeout(() => {
      isWindowOpen.value = true
    }, 500)
  } else {
    isWindowOpen.value = false
  }
}
function closeWindow() {
  isWindowOpen.value = false
}
function openConversationLog() {
  isWindowOpen.value = true
  isStartMenuOpen.value = false
}
function toggleStartMenu() {
  isStartMenuOpen.value = !isStartMenuOpen.value
}
function closeStartMenu() {
  isStartMenuOpen.value = false
}
function openCodeDialog() {
  isStartMenuOpen.value = false
  showCodeDialog.value = true
  codeInput.value = ''
}
function closeCodeDialog() {
  showCodeDialog.value = false
  codeInput.value = ''
}
function submitCode() {
  if (codeInput.value.trim() === 'Happy DALAB') {
    showCodeDialog.value = false
    showSuccessDialog.value = true
    codeInput.value = ''
  } else {
    showErrorDialog.value = true
  }
}
function closeSuccessDialog() {
  showSuccessDialog.value = false
}
function closeErrorDialog() {
  showErrorDialog.value = false
}
</script>

<template>
  <div class="conversation-view">
    <div class="computer-shell">
      <div class="monitor-bezel">
        <div class="screen" :class="{ 'monitor-off': !isMonitorOn }">
          <div class="desktop" v-show="isMonitorOn" @click="closeStartMenu">
            <div class="desktop-icons">
              <div class="desktop-icon" @dblclick="openConversationLog">
                <div class="icon-image">
                  <el-icon><Document /></el-icon>
                </div>
                <div class="icon-label">Conversation Log</div>
              </div>
            </div>
            <div class="taskbar" @click.stop>
              <div class="start-button" :class="{ 'active': isStartMenuOpen }" @click.stop="toggleStartMenu">
                <div class="windows-logo">
                  <div class="logo-square tl"></div>
                  <div class="logo-square tr"></div>
                  <div class="logo-square bl"></div>
                  <div class="logo-square br"></div>
                </div>
                <span class="start-text">Start</span>
              </div>
              <div v-if="isStartMenuOpen" class="start-menu" @click.stop>
                <div class="start-menu-header">
                  <div class="menu-title">Windows 95</div>
                </div>
                <div class="start-menu-items">
                  <div class="menu-item" @click="openConversationLog">
                    <el-icon class="menu-icon"><Document /></el-icon>
                    <span>Conversation Log</span>
                  </div>
                  <div class="menu-item" @click="openCodeDialog">
                    <el-icon class="menu-icon"><Key /></el-icon>
                    <span>Enter Code</span>
                  </div>
                  <div class="menu-item" @click="toggleMonitor">
                    <div class="menu-icon power-icon">⚡</div>
                    <span>Shut Down</span>
                  </div>
                </div>
              </div>
              <div class="taskbar-apps">
                <div class="taskbar-app active">
                  <el-icon><ChatDotSquare /></el-icon>
                  <span>Doctor-Patient Chat</span>
                </div>
              </div>
              <div class="system-tray">
                <div class="tray-icons">
                  <el-icon class="tray-icon"><Connection /></el-icon>
                  <el-icon class="tray-icon"><Microphone /></el-icon>
                  <el-icon class="tray-icon"><Bell /></el-icon>
                </div>
                <div class="datetime">
                  <div class="time">{{ currentTime }}</div>
                  <div class="date">{{ currentDate }}</div>
                </div>
              </div>
            </div>
            <div v-show="isWindowOpen" class="window-frame">
              <div class="window-titlebar">
                <div class="window-title">
                  <el-icon class="window-icon"><ChatDotSquare /></el-icon>
                  <span>Doctor-Patient Conversation Log</span>
                </div>
                <div class="window-controls">
                  <div class="control-btn minimize">_</div>
                  <div class="control-btn maximize">□</div>
                  <div class="control-btn close" @click="closeWindow">×</div>
                </div>
              </div>
              <div class="window-content">
                <div v-if="props.messages.length === 0" class="empty-conversation">
                  <el-icon :size="48"><ChatDotSquare /></el-icon>
                  <p>No Conversation Record</p>
                </div>
                
                <el-scrollbar v-else ref="scrollbarRef" class="message-scroll">
                  <div class="message-list">
                    <MessageBubble
                      v-for="message in props.messages"
                      :key="message.id"
                      :message="message"
                      :patient-id="props.patientId"
                      :doctor-id="props.doctorId"
                    />
                  </div>
                </el-scrollbar>
              </div>
              <div class="window-statusbar">
                <div class="status-info">
                  <el-icon class="status-icon"><CircleCheck /></el-icon>
                  <span>{{ props.messages.length }} messages</span>
                </div>
                <div class="resize-handle">⋰</div>
              </div>
            </div>
          </div>
        </div>
        <div class="monitor-controls">
          <div class="power-light" :class="{ 'power-on': isMonitorOn }"></div>
          <div class="power-btn" @click="toggleMonitor" :title="isMonitorOn ? 'Click to turn off' : 'Click to turn on'"></div>
        </div>
      </div>
      <div class="monitor-stand">
        <div class="stand-neck"></div>
        <div class="stand-base"></div>
      </div>
    </div>
    <div v-if="showCodeDialog" class="code-dialog-overlay" @click.self="closeCodeDialog">
      <div class="code-dialog" @click.stop>
        <div class="dialog-header">
          <div class="dialog-title">Enter Verification Code</div>
          <div class="dialog-close" @click="closeCodeDialog">×</div>
        </div>
        <div class="dialog-body">
          <input 
            v-model="codeInput" 
            type="text" 
            class="code-input"
            placeholder="Enter code here..."
            @keyup.enter="submitCode"
            autofocus
          />
        </div>
        <div class="dialog-footer">
          <button class="dialog-btn cancel-btn" @click="closeCodeDialog">Cancel</button>
          <button class="dialog-btn submit-btn" @click="submitCode">Submit</button>
        </div>
      </div>
    </div>
    <div v-if="showSuccessDialog" class="code-dialog-overlay" @click.self="closeSuccessDialog">
      <div class="code-dialog success-dialog" @click.stop>
        <div class="dialog-header">
          <div class="dialog-title">Congratulations!</div>
          <div class="dialog-close" @click="closeSuccessDialog">×</div>
        </div>
        <div class="dialog-body">
          <div class="success-message">
            <p>Congratulations! You found the Easter Egg!</p>
            <p>If you are among the first few people to discover this Easter egg, you have a chance to receive a gift! Please send an email to <strong>xxx</strong> with your address.</p>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="dialog-btn submit-btn" @click="closeSuccessDialog">OK</button>
        </div>
      </div>
    </div>
    <div v-if="showErrorDialog" class="code-dialog-overlay" @click.self="closeErrorDialog">
      <div class="code-dialog error-dialog" @click.stop>
        <div class="dialog-header error-header">
          <div class="dialog-title">Error</div>
          <div class="dialog-close" @click="closeErrorDialog">×</div>
        </div>
        <div class="dialog-body">
          <div class="error-message">
            <p>Invalid code. Please try again.</p>
          </div>
        </div>
        <div class="dialog-footer">
          <button class="dialog-btn submit-btn" @click="closeErrorDialog">OK</button>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped lang="scss">
.conversation-view {
  height: 100%;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  padding: 0.625rem;
  overflow: hidden;

  .computer-shell {
    display: flex;
    flex-direction: column;
    align-items: center;
    width: 100%;
    max-width: 87.5rem;
    margin-top: 0.5rem;
    height: calc(100% - 5rem);
    min-height: 0;

    .monitor-bezel {
      background: #333;
      padding: 0.5rem 0.5rem 2rem 0.5rem;
      position: relative;
      height: 100%;
      display: flex;
      flex-direction: column;
      min-height: 0;
      width: 100%;
      border: 0.25rem solid #1a1a1a;
      box-shadow:
        inset 0.25rem 0.25rem 0 #4a4a4a,
        inset -0.25rem -0.25rem 0 #222,
        0.625rem 0.625rem 0 rgba(0, 0, 0, 0.2);
      &::after {
        content: '................................................................';
        position: absolute;
        top: 0.25rem;
        left: 50%;
        transform: translateX(-50%);
        color: #111;
        font-size: 0.5rem;
        letter-spacing: 0.125rem;
        opacity: 0.5;
      }

      .screen {
        width: 100%;
        height: 100%;
        min-height: 0;
        background: #000;
        overflow: hidden;
        border: 0.25rem solid #111;
        transition: opacity 0.3s ease;
        position: relative;
        z-index: 1;

        &.monitor-off {
          opacity: 0.1;
        }

        .desktop {
          position: absolute;
          top: 0;
          left: 0;
          right: 0;
          bottom: 0;
          background: #3a7b5e;
          display: flex;
          flex-direction: column;
          overflow: hidden;
          .desktop-icons {
            position: absolute;
            top: 1.25rem;
            left: 1.25rem;
            display: flex;
            flex-direction: column;
            gap: 1.25rem;
            z-index: 1;

            .desktop-icon {
              display: flex;
              flex-direction: column;
              align-items: center;
              gap: 0.25rem;
              cursor: pointer;
              padding: 0.5rem;
              border: 0.125rem solid transparent;
              user-select: none;

              &:hover {
                background: rgba(255, 255, 255, 0.1);
                border-color: rgba(255, 255, 255, 0.3);
              }

              &:active {
                background: rgba(255, 255, 255, 0.2);
              }

              .icon-image {
                width: 3rem;
                height: 3rem;
                background: #c0c0c0;
                border: 0.125rem solid;
                border-color: #ffffff #808080 #808080 #ffffff;
                display: flex;
                align-items: center;
                justify-content: center;
                box-shadow: inset 0.0625rem 0.0625rem 0 #808080;

                .el-icon {
                  font-size: 2rem;
                  color: #0078d4;
                }
              }

              .icon-label {
                font-size: 0.6875rem;
                color: #ffffff;
                text-shadow: 0.0625rem 0.0625rem 0 #000;
                text-align: center;
                max-width: 5rem;
                word-wrap: break-word;
                font-family: 'MS Sans Serif', sans-serif;
              }
            }
          }
          .taskbar {
            position: absolute;
            bottom: 0;
            left: 0;
            right: 0;
            height: 2.5rem;
            background: #c0c0c0;
            border-top: 0.125rem solid #ffffff;
            box-shadow: inset 0 -0.0625rem 0 #808080, inset 0 0.0625rem 0 #ffffff;
            display: flex;
            align-items: center;
            padding: 0 0.25rem;
            gap: 0.25rem;
            z-index: 2000;
            pointer-events: auto;

            .start-button {
              height: 1.875rem;
              padding: 0 0.75rem;
              display: flex;
              align-items: center;
              gap: 0.375rem;
              background: #c0c0c0;
              border: 0.125rem solid;
              border-color: #ffffff #808080 #808080 #ffffff;
              font-weight: bold;
              font-size: 0.75rem;
              cursor: pointer;
              position: relative;
              z-index: 2001;
              pointer-events: auto;

              &.active {
                border-color: #808080 #ffffff #ffffff #808080;
                background: #e0e0e0;
                padding: 0.0625rem 0.6875rem -0.0625rem 0.8125rem;
              }

              &:active:not(.active) {
                border-color: #808080 #ffffff #ffffff #808080;
                padding: 0.0625rem 0.6875rem -0.0625rem 0.8125rem;
              }

              .start-text {
                font-family: 'MS Sans Serif', sans-serif;
                color: #000;
                font-weight: bold;
              }

              .windows-logo {
                width: 1rem;
                height: 0.875rem;
                display: grid;
                grid-template-columns: 1fr 1fr;
                grid-template-rows: 1fr 1fr;
                gap: 0.0625rem;

                .logo-square {
                  &.tl { background: #ff4b4b; }
                  &.tr { background: #61e061; }
                  &.bl { background: #4b4bff; }
                  &.br { background: #ffff4b; }
                }
              }
            }
            .start-menu {
              position: absolute;
              bottom: 2.5rem;
              left: 0;
              width: 12.5rem;
              background: #c0c0c0;
              border: 0.125rem solid;
              border-color: #ffffff #808080 #808080 #ffffff;
              box-shadow: 0.25rem -0.25rem 0 rgba(0, 0, 0, 0.2);
              z-index: 3000;
              pointer-events: auto;

              .start-menu-header {
                background: #0078d4;
                padding: 0.5rem 0.75rem;
                border-bottom: 0.125rem solid #0052a3;

                .menu-title {
                  color: white;
                  font-weight: bold;
                  font-size: 0.875rem;
                  font-family: 'MS Sans Serif', sans-serif;
                }
              }

              .start-menu-items {
                padding: 0.25rem 0;

                .menu-item {
                  display: flex;
                  align-items: center;
                  gap: 0.5rem;
                  padding: 0.375rem 0.75rem;
                  cursor: pointer;
                  font-size: 0.75rem;
                  color: #000;
                  font-family: 'MS Sans Serif', sans-serif;

                  &:hover {
                    background: #0078d4;
                    color: white;
                  }

                  .menu-icon {
                    font-size: 1rem;

                    &.power-icon {
                      font-size: 1.125rem;
                      line-height: 1;
                    }
                  }
                }
              }
            }

            .taskbar-apps {
              flex: 1;
              display: flex;
              gap: 0.25rem;

              .taskbar-app {
                height: 1.875rem;
                min-width: 7.5rem;
                padding: 0 0.5rem;
                display: flex;
                align-items: center;
                gap: 0.375rem;
                background: #c0c0c0;
                border: 0.125rem solid;
                border-color: #ffffff #808080 #808080 #ffffff;
                font-size: 0.75rem;
                color: #000;

                &.active {
                  background: #e0e0e0;
                  border-color: #808080 #ffffff #ffffff #808080;
                  font-weight: bold;
                }
              }
            }

            .system-tray {
              display: flex;
              align-items: center;
              gap: 0.125rem;
              height: 1.875rem;
              padding: 0 0.5rem;
              background: #c0c0c0;
              border: 0.125rem solid;
              border-color: #808080 #ffffff #ffffff #808080;

              .tray-icons {
                display: flex;
                gap: 0.25rem;
                margin-right: 0.5rem;

                .tray-icon {
                  font-size: 0.875rem;
                  color: #000;
                }
              }

              .datetime {
                display: flex;
                align-items: center;
                gap: 0.5rem;

                .time {
                  font-size: 0.75rem;
                  color: #000;
                  font-family: monospace;
                }
              }
            }
          }
        }
      }
      .monitor-controls {
        position: absolute;
        bottom: 0.5rem;
        right: 1.25rem;
        display: flex;
        align-items: center;
        gap: 0.625rem;
        z-index: 10000;
        pointer-events: auto;

        .power-light {
          width: 0.625rem;
          height: 0.625rem;
          background: #000;
          border: 0.125rem solid #333;
          image-rendering: pixelated;
          transition: all 0.2s ease;

          &.power-on {
            background: #00ff00;
            border-color: #00ff00;
            box-shadow:
              0 0 0 0.0625rem #000,
              0 0 0.25rem #00ff00;
            animation: pixel-blink 1.5s infinite step-end;
          }
        }

        .power-btn {
          width: 2.5rem;
          height: 1.25rem;
          background: #000;
          border: 0.125rem solid #333;
          border-radius: 0;
          cursor: pointer;
          transition: all 0.1s ease;
          position: relative;
          image-rendering: pixelated;
          box-shadow:
            inset 0.125rem 0.125rem 0 #333,
            inset -0.125rem -0.125rem 0 #000,
            0.125rem 0.125rem 0 #000;

          &::after {
            content: 'PWR';
            position: absolute;
            top: 50%;
            left: 50%;
            transform: translate(-50%, -50%);
            font-size: 0.5rem;
            font-weight: bold;
            color: #666;
            font-family: 'Courier New', monospace;
            letter-spacing: 0.0625rem;
            text-shadow: 0.0625rem 0.0625rem 0 #000;
          }

          &:hover {
            background: #111;
            border-color: #444;
            box-shadow:
              inset 0.125rem 0.125rem 0 #444,
              inset -0.125rem -0.125rem 0 #000,
              0.125rem 0.125rem 0 #000;

            &::after {
              color: #888;
            }
          }

          &:active {
            background: #000;
            transform: translate(0.0625rem, 0.0625rem);
            box-shadow:
              inset 0.125rem 0.125rem 0 #000,
              inset -0.125rem -0.125rem 0 #333,
              0.0625rem 0.0625rem 0 #000;

            &::after {
              color: #555;
            }
          }
        }
      }
    }

    @keyframes pixel-blink {
      0%, 100% {
        opacity: 1;
        box-shadow:
          0 0 0 0.0625rem #000,
          0 0 0.25rem #00ff00;
      }
      50% {
        opacity: 0.5;
        box-shadow:
          0 0 0 0.0625rem #000,
          0 0 0.125rem #00ff00;
      }
    }

    .monitor-stand {
      display: flex;
      flex-direction: column;
      align-items: center;

      .stand-neck {
        width: 6.25rem;
        height: 1.875rem;
        background: #2a2a2a;
        border-left: 0.25rem solid #1a1a1a;
        border-right: 0.25rem solid #3a3a3a;
      }

      .stand-base {
        width: 15.625rem;
        height: 0.9375rem;
        background: #333;
        border: 0.25rem solid #1a1a1a;
        box-shadow: inset 0.125rem 0.125rem 0 #4a4a4a;
        position: relative;
        &::after {
          content: '';
          position: absolute;
          bottom: -0.625rem;
          left: 0.625rem;
          right: 0.625rem;
          height: 0.375rem;
          background: rgba(0, 0, 0, 0.2);
        }
      }
    }
  }

  .desktop .window-frame {
    width: 100%;
    max-width: none;
    position: absolute;
    top: 0;
    bottom: 2.5rem;
    left: 0;
    right: 0;
    transform: none;
    display: flex;
    flex-direction: column;
    background: #f0f0f0;
    border: 0.1875rem solid #c0c0c0;
    box-shadow:
      inset -0.0625rem -0.0625rem 0 #808080,
      inset 0.0625rem 0.0625rem 0 #ffffff;
    z-index: 100;

    .window-titlebar {
      background: linear-gradient(180deg, #0078d4 0%, #0066b8 100%);
      padding: 0.25rem 0.375rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 0.125rem solid #0052a3;
      min-height: 2rem;
      cursor: move;
      flex-shrink: 0;

      .window-title {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        color: white;
        font-size: var(--font-size-sm);
        font-weight: 600;
        letter-spacing: 0;

        .window-icon {
          font-size: 0.875rem;
        }
      }

      .window-controls {
        display: flex;
        gap: 0.125rem;

        .control-btn {
          width: 1.25rem;
          height: 1.25rem;
          display: flex;
          align-items: center;
          justify-content: center;
          background: #e0e0e0;
          border: 0.125rem solid;
          border-color: #ffffff #808080 #808080 #ffffff;
          font-size: 0.875rem;
          font-weight: bold;
          cursor: pointer;
          user-select: none;
          line-height: 1;
          padding-bottom: 0.125rem;

          &:hover {
            background: #f0f0f0;
          }

          &:active {
            border-color: #808080 #ffffff #ffffff #808080;
            background: #d0d0d0;
          }

          &.minimize {
            color: #000;
          }

          &.maximize {
            color: #000;
            font-size: 0.75rem;
          }

          &.close {
            color: #000;
            font-size: 1.125rem;
            line-height: 0.9;

            &:hover {
              background: #e81123;
              color: white;
              border-color: #e81123;
            }
          }
        }
      }
    }

    .window-content {
      flex: 1;
      background: #ffffff;
      position: relative;
      overflow: hidden;
      border: 0.125rem solid #d4d4d4;
      border-top: none;
      min-height: 0;

      .empty-conversation {
        height: 100%;
        display: flex;
        flex-direction: column;
        align-items: center;
        justify-content: center;
        color: var(--text-placeholder);

        .el-icon {
          color: #0078d4;
        }

        p {
          margin-top: 0.75rem;
          font-size: var(--font-size-sm);
          line-height: 2.2;
          letter-spacing: 0;
          color: var(--text-secondary);
        }
      }

      .message-scroll {
        height: 100%;

        :deep(.el-scrollbar__wrap) {
          background: #fafafa;
          max-height: 100%;
        }

        :deep(.el-scrollbar__view) {
          min-height: 100%;
        }

        :deep(.el-scrollbar__bar) {
          background: #e0e0e0;
          border: 0.125rem solid;
          border-color: #ffffff #808080 #808080 #ffffff;
          width: 1rem !important;
          right: 0 !important;
        }

        :deep(.el-scrollbar__bar.is-vertical) {
          width: 1rem !important;
        }

        :deep(.el-scrollbar__thumb) {
          background: #c0c0c0;
          border: 0.125rem solid;
          border-color: #ffffff #808080 #808080 #ffffff;
          width: 100% !important;

          &:hover {
            background: #b0b0b0;
          }

          &:active {
            background: #a0a0a0;
          }
        }
      }

      .message-list {
        padding: 1.25rem 1.5rem;
        display: flex;
        flex-direction: column;
        gap: 0.875rem;
        min-height: fit-content;
        width: 100%;
        max-width: 100%;
        margin: 0 auto;
        box-sizing: border-box;
      }
    }

    .window-statusbar {
      background: #f0f0f0;
      padding: 0.25rem 0.5rem;
      border-top: 0.125rem solid #d4d4d4;
      display: flex;
      align-items: center;
      justify-content: space-between;
      min-height: 1.5rem;
      border: 0.125rem solid;
      border-color: #ffffff #808080 #808080 #ffffff;
      border-top-color: #808080;
      flex-shrink: 0;

      .status-info {
        display: flex;
        align-items: center;
        gap: 0.375rem;
        font-size: var(--font-size-xs);
        color: var(--text-secondary);

        .status-icon {
          font-size: 0.75rem;
          color: #0078d4;
        }
      }

      .resize-handle {
        font-size: 0.75rem;
        color: #808080;
        cursor: nwse-resize;
        user-select: none;
        line-height: 1;
      }
    }
  }
  .code-dialog-overlay {
    position: fixed;
    top: 0;
    left: 0;
    right: 0;
    bottom: 0;
    background: rgba(0, 0, 0, 0.5);
    display: flex;
    align-items: center;
    justify-content: center;
    z-index: 100000;
  }

  .code-dialog {
    background: #c0c0c0;
    border: 0.1875rem solid;
    border-color: #ffffff #808080 #808080 #ffffff;
    box-shadow:
      inset -0.0625rem -0.0625rem 0 #000,
      inset 0.0625rem 0.0625rem 0 #ffffff,
      0.25rem 0.25rem 0 rgba(0, 0, 0, 0.3);
    min-width: 25rem;
    max-width: 31.25rem;
    font-family: 'MS Sans Serif', sans-serif;

    .dialog-header {
      background: #0078d4;
      padding: 0.375rem 0.5rem;
      display: flex;
      align-items: center;
      justify-content: space-between;
      border-bottom: 0.125rem solid #0052a3;

      .dialog-title {
        color: white;
        font-weight: bold;
        font-size: 0.8125rem;
      }

      .dialog-close {
        width: 1.25rem;
        height: 1.25rem;
        display: flex;
        align-items: center;
        justify-content: center;
        background: #c0c0c0;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;
        font-size: 1rem;
        font-weight: bold;
        color: #000;
        cursor: pointer;
        line-height: 1;

        &:hover {
          background: #e0e0e0;
        }

        &:active {
          border-color: #808080 #ffffff #ffffff #808080;
          background: #d0d0d0;
        }
      }
    }

    .dialog-body {
      padding: 1.25rem;
      background: #c0c0c0;

      .code-input {
        width: 100%;
        padding: 0.5rem;
        border: 0.125rem solid;
        border-color: #808080 #ffffff #ffffff #808080;
        background: #ffffff;
        font-family: 'Courier New', monospace;
        font-size: 0.875rem;
        box-sizing: border-box;

        &:focus {
          outline: none;
          border-color: #0078d4;
        }
      }

      .success-message {
        text-align: center;
        color: #000;
        font-size: 0.8125rem;
        line-height: 1.6;

        p {
          margin: 0.625rem 0;

          strong {
            color: #0078d4;
            font-weight: bold;
          }
        }
      }
    }

    .dialog-footer {
      padding: 0.625rem;
      display: flex;
      justify-content: flex-end;
      gap: 0.5rem;
      background: #c0c0c0;
      border-top: 0.125rem solid #808080;

      .dialog-btn {
        min-width: 5rem;
        height: 1.5rem;
        padding: 0 1rem;
        border: 0.125rem solid;
        border-color: #ffffff #808080 #808080 #ffffff;
        background: #c0c0c0;
        font-family: 'MS Sans Serif', sans-serif;
        font-size: 0.75rem;
        font-weight: bold;
        cursor: pointer;
        color: #000;

        &:hover {
          background: #e0e0e0;
        }

        &:active {
          border-color: #808080 #ffffff #ffffff #808080;
          background: #d0d0d0;
        }

        &.submit-btn {
          background: #0078d4;
          color: white;
          border-color: #0052a3 #ffffff #ffffff #0052a3;

          &:hover {
            background: #0066b8;
          }

          &:active {
            border-color: #0052a3 #ffffff #ffffff #0052a3;
            background: #0052a3;
          }
        }
      }
    }

    &.success-dialog {
      .dialog-body {
        padding: 1.875rem 1.25rem;
      }
    }

    &.error-dialog {
      .dialog-header.error-header {
        background: #e81123;
        border-bottom-color: #c50e1f;
      }

      .error-message {
        text-align: center;
        color: #000;
        font-size: 0.8125rem;
        padding: 0.625rem 0;
      }
    }
  }
}
@media (max-width: 80rem) {
  .conversation-view {
    .computer-shell {
      .monitor-bezel {
        .screen {
          width: 100%;
        }
      }
    }
  }
}
@media (max-width: 64rem) {
  .conversation-view {
    padding: 0.375rem;

    .computer-shell {
      margin-top: 1rem;

      .monitor-bezel {
        padding: 0.5rem 0.5rem 2rem 0.5rem;

        .screen {
          width: 100%;
          .desktop {
            .desktop-icons {
              top: 0.75rem;
              left: 0.75rem;
              gap: 0.75rem;

              .desktop-icon {
                .icon-image {
                  width: 2.5rem;
                  height: 2.5rem;

                  .el-icon {
                    font-size: 1.5rem;
                  }
                }

                .icon-label {
                  font-size: 0.5625rem;
                  max-width: 4rem;
                }
              }
            }

            .taskbar {
              height: 2rem;

              .start-btn {
                height: 1.5rem;
                padding: 0 0.5rem;
                font-size: 0.6875rem;
              }

              .taskbar-app {
                height: 1.5rem;
                padding: 0 0.5rem;
                font-size: 0.5625rem;
              }
            }

            .window-frame {
              bottom: 2rem;
            }
          }
        }
      }

      .monitor-stand {
        width: 10rem;
        height: 3rem;
      }

      .monitor-base {
        width: 14rem;
        height: 0.75rem;
      }
    }
  }
}
@media (max-width: 48rem) {
  .conversation-view {
    padding: 0.25rem;

    .computer-shell {
      margin-top: 0.5rem;

      .monitor-bezel {
        padding: 0.375rem 0.375rem 1.5rem 0.375rem;
        border-width: 0.1875rem;

        &::after {
          font-size: 0.375rem;
        }

        .screen {
          border-width: 0.1875rem;

          .desktop {
            .desktop-icons {
              display: none;
            }

            .taskbar {
              height: 1.75rem;

              .start-btn {
                height: 1.25rem;
                padding: 0 0.375rem;
                font-size: 0.5625rem;

                .win-logo {
                  width: 0.75rem;
                  height: 0.75rem;
                }
              }

              .taskbar-app {
                height: 1.25rem;
                padding: 0 0.375rem;
                max-width: 8rem;
                font-size: 0.5rem;
              }

              .system-tray {
                padding: 0 0.25rem;
                font-size: 0.5rem;
              }
            }

            .window-frame {
              bottom: 1.75rem;
            }
          }
        }

        .power-section {
          bottom: 0.375rem;
          right: 0.5rem;

          .power-btn {
            width: 0.75rem;
            height: 0.75rem;
          }
        }
      }

      .monitor-stand {
        width: 8rem;
        height: 2.5rem;
      }

      .monitor-base {
        width: 12rem;
        height: 0.625rem;
      }
    }
  }
}
@media (max-width: 30rem) {
  .conversation-view {
    padding: 0.125rem;

    .computer-shell {
      margin-top: 0.25rem;

      .monitor-bezel {
        padding: 0.25rem 0.25rem 1.25rem 0.25rem;

        .screen {
          .desktop {
            .taskbar {
              height: 1.5rem;

              .start-btn {
                height: 1rem;
                font-size: 0.5rem;

                .win-logo {
                  width: 0.625rem;
                  height: 0.625rem;
                }
              }

              .taskbar-app {
                height: 1rem;
                max-width: 6rem;
                font-size: 0.4375rem;
              }

              .system-tray {
                font-size: 0.4375rem;
              }
            }

            .window-frame {
              bottom: 1.5rem;
            }
          }
        }
      }

      .monitor-stand {
        width: 6rem;
        height: 2rem;
      }

      .monitor-base {
        width: 10rem;
        height: 0.5rem;
      }
    }
  }
}
</style>

