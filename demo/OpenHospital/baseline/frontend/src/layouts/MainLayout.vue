<script setup lang="ts">
import { computed } from 'vue'
import { useRouter } from 'vue-router'
import { Clock } from '@element-plus/icons-vue'
import { useWebSocketStore } from '@/stores/websocket'

const router = useRouter()
const wsStore = useWebSocketStore()

const connectionStatus = computed(() => {
  if (wsStore.connected) return { text: 'Connected', type: 'success' as const }
  if (wsStore.reconnecting) return { text: 'Reconnecting...', type: 'warning' as const }
  return { text: 'Disconnected', type: 'danger' as const }
})

function goHome() {
  router.push('/')
}
</script>

<template>
  <el-container class="main-layout">
    <el-header class="header">
      <div class="header-left" @click="goHome">
        <img src="/logo.png" alt="Logo" class="logo-icon" />
        <h1 class="title">OpenHospital</h1>
      </div>
      
      <div class="header-right">
        <div class="status-item">
          <el-icon><Clock /></el-icon>
          <span>Tick: {{ wsStore.simulationStatus.current_tick }}</span>
        </div>
        
        <el-divider direction="vertical" />
        
        <div class="status-item">
          <el-tag :type="connectionStatus.type">
            {{ connectionStatus.text }}
          </el-tag>
        </div>
      </div>
    </el-header>
    <el-main class="main-content">
      <slot />
    </el-main>
  </el-container>
</template>

<style scoped lang="scss">
.main-layout {
  height: 100vh;
  width: 100%;
  display: flex;
  flex-direction: column;
  background-color: #e1f5fe; // 确保整个容器背景统一
}

.header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 1.5rem;
  background: #3da5ff; // 亮丽的天蓝色
  color: #fff;
  height: 4rem;
  border-bottom: 0.25rem solid #0066cc; // 深蓝色底边
  box-shadow:
    inset 0 0.25rem 0 rgba(255, 255, 255, 0.4), // 顶部高光
    0 0.25rem 0 rgba(0, 0, 0, 0.1);
  z-index: 100;

  .header-left {
    display: flex;
    align-items: center;
    gap: 0.75rem;
    cursor: pointer;
    transition: transform 0.1s;

    &:hover {
      transform: scale(1.05);
    }

    .logo-icon {
      width: 3rem;
      height: 3rem;
      image-rendering: pixelated;
      filter: drop-shadow(0.125rem 0.125rem 0 rgba(0,0,0,0.2));
    }

    .title {
      font-size: 1rem;
      font-family: 'Press Start 2P', cursive !important;
      color: #fff;
      text-shadow:
        0.125rem 0.125rem 0 #0066cc, // 蓝色投影
        -0.0625rem -0.0625rem 0 #0066cc,
        0.0625rem -0.0625rem 0 #0066cc,
        -0.0625rem 0.0625rem 0 #0066cc;
      margin: 0;
      letter-spacing: 0.0625rem;
    }
  }

  .header-right {
    display: flex;
    align-items: center;
    gap: 1rem;

    .status-item {
      display: flex;
      align-items: center;
      gap: 0.75rem;
      font-family: monospace;
      font-size: 0.9375rem !important;
      font-weight: bold;
      color: #fff;
      text-shadow: 0.0625rem 0.0625rem 0 rgba(0,0,0,0.2);

      span {
        font-size: 0.9375rem !important;
      }

      .el-icon {
        color: #fff;
        font-size: 1.125rem !important;
        filter: drop-shadow(0.0625rem 0.0625rem 0 #0066cc);
      }

      :deep(.el-tag) {
        font-size: 1.375rem !important;
        height: 2.625rem !important;
        padding: 0 1rem;
        line-height: 2.375rem;
        font-weight: 900;
        border: 0.125rem solid currentColor;
        background: rgba(255, 255, 255, 0.9);
      }
    }

    .el-divider {
      height: 2.5rem;
      border-color: rgba(255, 255, 255, 0.4);
    }
  }
}

.main-content {
  flex: 1;
  padding: 0;
  background-color: #e1f5fe; // 极浅的蓝色背景
  overflow: hidden;
}
@media (max-width: 64rem) {
  .header {
    padding: 0 1rem;
    height: 3.5rem;

    .header-left {
      gap: 0.5rem;

      .logo-icon {
        width: 2.5rem;
        height: 2.5rem;
      }

      .title {
        font-size: 0.875rem;
      }
    }

    .header-right {
      gap: 0.75rem;

      .status-item {
        gap: 0.5rem;
        font-size: 0.8125rem !important;

        span {
          font-size: 0.8125rem !important;
        }

        .el-icon {
          font-size: 1rem !important;
        }

        :deep(.el-tag) {
          font-size: 1rem !important;
          height: 2rem !important;
          padding: 0 0.75rem;
          line-height: 1.75rem;
        }
      }

      .el-divider {
        height: 2rem;
      }
    }
  }
}
@media (max-width: 48rem) {
  .header {
    padding: 0 0.75rem;
    height: 3rem;

    .header-left {
      .logo-icon {
        width: 2rem;
        height: 2rem;
      }

      .title {
        font-size: 0.75rem;
        letter-spacing: 0;
      }
    }

    .header-right {
      gap: 0.5rem;

      .status-item {
        gap: 0.375rem;
        font-size: 0.6875rem !important;

        span {
          font-size: 0.6875rem !important;
        }

        .el-icon {
          font-size: 0.875rem !important;
        }

        :deep(.el-tag) {
          font-size: 0.75rem !important;
          height: 1.5rem !important;
          padding: 0 0.5rem;
          line-height: 1.25rem;
        }
      }

      .el-divider {
        height: 1.5rem;
        margin: 0 0.25rem;
      }
    }
  }
}
@media (max-width: 30rem) {
  .header {
    padding: 0 0.5rem;
    height: 2.75rem;

    .header-left {
      .logo-icon {
        width: 1.75rem;
        height: 1.75rem;
      }

      .title {
        font-size: 0.625rem;
        max-width: 6rem;
        overflow: hidden;
        text-overflow: ellipsis;
        white-space: nowrap;
      }
    }

    .header-right {
      .status-item {
        span {
          display: none;
        }

        .el-icon {
          font-size: 0.75rem !important;
        }

        :deep(.el-tag) {
          font-size: 0.625rem !important;
          height: 1.25rem !important;
          padding: 0 0.375rem;
          line-height: 1rem;
        }
      }

      .el-divider {
        display: none;
      }
    }
  }
}
</style>
