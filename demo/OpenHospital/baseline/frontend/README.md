# OpenHospital Frontend

基于 Vue 3 + TypeScript + Element Plus 构建的 OpenHospital 可视化前端。

## 功能特性

- 📋 **医生列表**: 展示所有医生，支持搜索和按科室筛选
- 🧑 **患者列表**: 展示所有患者，支持搜索和按状态筛选
- 💬 **医患对话**: 实时展示医生与患者之间的对话记录
- 📊 **就诊流程**: 可视化患者的就诊状态时间线
- 🔬 **检查记录**: 展示患者的检查项目和结果
- 💊 **诊断治疗**: 展示医生的诊断和治疗方案
- 📝 **医生反思**: 展示医生的咨询反思和医学反思
- 🔄 **实时更新**: 通过 WebSocket 接收模拟事件并自动更新界面

## 技术栈

- **框架**: Vue 3 (Composition API)
- **语言**: TypeScript
- **UI 组件库**: Element Plus
- **状态管理**: Pinia
- **路由**: Vue Router
- **HTTP 客户端**: Axios
- **构建工具**: Vite
- **样式**: SCSS

## 项目结构

```
src/
├── api/                    # API 请求模块
│   ├── doctor.ts          # 医生相关接口
│   ├── patient.ts         # 患者相关接口
│   ├── conversation.ts    # 对话相关接口
│   └── request.ts         # Axios 封装
├── assets/                 # 静态资源
│   └── styles/
│       └── main.scss      # 全局样式
├── components/             # 组件
│   ├── common/            # 通用组件
│   ├── doctor/            # 医生相关组件
│   ├── patient/           # 患者相关组件
│   ├── conversation/      # 对话组件
│   └── medical/           # 医疗记录组件
├── layouts/                # 布局组件
│   └── MainLayout.vue
├── router/                 # 路由配置
│   └── index.ts
├── stores/                 # Pinia 状态管理
│   ├── doctor.ts
│   ├── patient.ts
│   ├── conversation.ts
│   └── websocket.ts
├── types/                  # TypeScript 类型定义
│   ├── doctor.ts
│   ├── patient.ts
│   ├── conversation.ts
│   ├── examination.ts
│   ├── prescription.ts
│   └── event.ts
├── views/                  # 页面视图
│   ├── Dashboard.vue      # 主仪表板
│   ├── DoctorView.vue     # 医生详情页
│   └── PatientView.vue    # 患者详情页
├── App.vue                # 根组件
└── main.ts                # 入口文件
```

## 快速开始

### 前置要求

- Node.js >= 18
- npm >= 9

### 安装依赖

```bash
cd frontend
npm install
```

### 启动开发服务器

```bash
npm run dev
```

前端将在 `http://localhost:3000` 启动。

### 构建生产版本

```bash
npm run build
```

## 配置说明

### 代理配置

开发模式下，API 请求会代理到后端服务器。在 `vite.config.ts` 中配置：

```typescript
proxy: {
  '/api': {
    target: 'http://localhost:8000',
    changeOrigin: true,
  },
  '/ws': {
    target: 'ws://localhost:8000',
    ws: true,
  },
}
```

### 环境变量

可以创建 `.env.development` 和 `.env.production` 文件配置不同环境：

```env
VITE_API_BASE_URL=http://localhost:8000
VITE_WS_URL=ws://localhost:8000
```

## 后端 API 要求

前端期望后端提供以下 REST API 端点：

### 医生相关
- `GET /api/doctors` - 获取医生列表
- `GET /api/doctors/{id}` - 获取医生详情
- `GET /api/doctors/{id}/reflections` - 获取医生反思

### 患者相关
- `GET /api/patients` - 获取患者列表
- `GET /api/patients/{id}` - 获取患者详情

### 对话相关
- `GET /api/conversations/between/{patient_id}/{doctor_id}` - 获取医患对话

### WebSocket
- `WS /ws/events` - 实时事件推送

## 截图预览

(待添加)

## 开发计划

- [ ] 添加事件日志查看器
- [ ] 添加统计数据可视化图表
- [ ] 添加深色模式支持
- [ ] 添加国际化支持
- [ ] 性能优化（虚拟列表等）

## 许可证

MIT

