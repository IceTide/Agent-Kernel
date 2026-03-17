# Hospital Simulation Backend API

医院仿真后端 API 服务，为前端提供数据接口和实时事件推送。

## 功能特性

- **REST API**: 提供医生、患者、对话等资源的 CRUD 接口
- **WebSocket**: 实时推送仿真事件到前端
- **Redis 集成**: 从 Redis 读取仿真数据，支持 Pub/Sub 事件流

## 安装

```bash
cd baseline/backend
pip install -r requirements.txt
```

## 配置

可以通过环境变量或 `.env` 文件配置：

| 环境变量 | 默认值 | 描述 |
|---------|--------|------|
| `HOSPITAL_API_HOST` | `0.0.0.0` | 服务监听地址 |
| `HOSPITAL_API_PORT` | `8000` | 服务监听端口 |
| `HOSPITAL_API_DEBUG` | `true` | 调试模式 |
| `HOSPITAL_API_REDIS_HOST` | `localhost` | Redis 服务器地址 |
| `HOSPITAL_API_REDIS_PORT` | `6379` | Redis 端口 |
| `HOSPITAL_API_REDIS_DB` | `0` | Redis 数据库 |

## 启动

### 方式一：直接运行

```bash
cd baseline/backend
python run.py
```

### 方式二：使用 uvicorn

```bash
cd baseline
uvicorn backend.main:app --reload --host 0.0.0.0 --port 8000
```

## API 文档

启动服务后访问:
- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc

## API 端点

### 医生 API (`/api/doctors`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/doctors` | 获取所有医生列表 |
| GET | `/api/doctors/{doctor_id}` | 获取医生详情 |
| GET | `/api/doctors/{doctor_id}/reflections` | 获取医生反思记录 |
| GET | `/api/doctors/{doctor_id}/patients` | 获取医生的患者列表 |
| GET | `/api/doctors/{doctor_id}/statistics` | 获取医生统计数据 |

### 患者 API (`/api/patients`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/patients` | 获取所有患者列表 |
| GET | `/api/patients?phase=consulting` | 按状态过滤患者 |
| GET | `/api/patients?doctor_id=xxx` | 按医生过滤患者 |
| GET | `/api/patients/{patient_id}` | 获取患者基本信息 |
| GET | `/api/patients/{patient_id}/detail` | 获取患者完整详情 |
| GET | `/api/patients/{patient_id}/trajectory` | 获取患者轨迹 |
| GET | `/api/patients/{patient_id}/examinations` | 获取患者检查记录 |
| GET | `/api/patients/{patient_id}/prescriptions` | 获取患者处方记录 |

### 对话 API (`/api/conversations`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/conversations/{conversation_id}` | 获取对话详情 |
| GET | `/api/conversations/between/{agent1}/{agent2}` | 获取两人之间的对话 |
| GET | `/api/conversations/agent/{agent_id}` | 获取 Agent 的所有对话 |
| GET | `/api/conversations/{conversation_id}/messages` | 获取对话消息 |

### 医院信息系统 API (`/api/hospital`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/hospital/locations` | 获取所有地点 |
| GET | `/api/hospital/locations/{id}` | 获取地点详情 |
| GET | `/api/hospital/departments` | 获取科室映射 |
| GET | `/api/hospital/examinations` | 获取所有检查记录 |
| GET | `/api/hospital/prescriptions` | 获取所有处方记录 |
| GET | `/api/hospital/registrations` | 获取所有挂号记录 |
| GET | `/api/hospital/catalog/examinations` | 获取检查项目目录 |
| GET | `/api/hospital/catalog/diseases` | 获取疾病目录 |
| GET | `/api/hospital/ground-truth/{patient_id}` | 获取患者真实诊断 |

### 仿真 API (`/api/simulation`)

| 方法 | 路径 | 描述 |
|------|------|------|
| GET | `/api/simulation/status` | 获取仿真状态 |
| GET | `/api/simulation/tick` | 获取当前 Tick |
| GET | `/api/simulation/statistics` | 获取仿真统计 |
| GET | `/api/simulation/agents/ids` | 获取所有 Agent ID |

### WebSocket (`/ws`)

连接 WebSocket 后可以发送 JSON 消息订阅特定主题：

```json
// 订阅 agent 事件
{"action": "subscribe", "topic": "agent"}

// 取消订阅
{"action": "unsubscribe", "topic": "agent"}

// 心跳
{"action": "ping"}
```

也可以连接特定 Agent 的 WebSocket：

```
ws://localhost:8000/ws/agent/{agent_id}
```

## Redis 数据格式

此后端 API 读取的 Redis 数据格式与 `run_simulation.py` 保持一致：

| Key 格式 | 类型 | 描述 |
|----------|------|------|
| `{agent_id}:profile` | Hash | Agent 配置信息 |
| `{doctor_id}:consultation_reflections` | JSON | 医生诊疗反思 |
| `{doctor_id}:medical_reflections` | JSON | 医生医学反思 |
| `trajectory:{agent_id}` | List | Agent 轨迹事件 |
| `examination:{record_id}` | JSON | 单个检查记录 |
| `his:examination_records` | JSON | 所有检查记录 |
| `his:prescription_records` | JSON | 所有处方记录 |
| `his:registrations` | JSON | 挂号记录 |
| `his:doctor_patient_bindings` | JSON | 医生-患者绑定 |
| `hospital:ground_truth:{patient_id}` | JSON | 患者真实诊断 |
| `hospital:space:location:{id}` | JSON | 地点信息 |
| `hospital:catalog:examinations` | JSON | 检查项目目录 |
| `hospital:catalog:diseases` | JSON | 疾病目录 |

## 项目结构

```
backend/
├── __init__.py
├── main.py              # FastAPI 应用入口
├── config.py            # 配置管理
├── run.py               # 运行脚本
├── requirements.txt     # 依赖
├── README.md
├── schemas/             # Pydantic 数据模型
│   ├── __init__.py
│   ├── doctor.py
│   ├── patient.py
│   ├── conversation.py
│   ├── examination.py
│   ├── prescription.py
│   └── event.py
├── services/            # 服务层
│   ├── __init__.py
│   ├── redis_service.py
│   └── websocket_manager.py
└── routers/             # API 路由
    ├── __init__.py
    ├── doctor.py
    ├── patient.py
    ├── conversation.py
    ├── simulation.py
    ├── hospital.py
    └── websocket.py
```
