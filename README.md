# Image Portal

对话生图门户：秘钥登录、会话历史、多轮改图、管理端分配额度。上游对接 OpenAI 兼容图片接口（chatgpt2api / New API）。

## 功能

- 用户：秘钥登录、对话式文生图、基于上图多轮改图、剩余额度
- 管理：
  - 单口令登录
  - **上游配置**（Base URL / API Key / 默认模型 / response_format）存 SQLite
  - 创建/禁用秘钥、设置额度、用量记录
- 上游调用（对齐 `newapi-image-test.html`）：
  - `POST {base}/v1/images/generations`
  - `POST {base}/v1/images/edits`
  - `Authorization: Bearer …`
  - 默认 `response_format: url`
- 成功出图按张数扣额度；失败不扣

## 快速启动（Docker）

```bash
cd image-portal
cp .env.example .env
# 编辑 .env：仅需 ADMIN_PASSWORD / JWT_SECRET
docker compose up -d --build
```

浏览器：`http://localhost:8080`

1. 打开 `/admin/login`，用 `ADMIN_PASSWORD` 登录  
2. 在 **上游连接** 填写 Base URL、API Key、默认模型并保存  
3. 创建用户秘钥并发放  
4. 用户用秘钥登录生图  

## 环境变量（仅这些）

| 变量 | 说明 |
|------|------|
| `ADMIN_PASSWORD` | 管理口令 |
| `JWT_SECRET` | JWT 密钥 |
| `PORT` | 对外端口，默认 8080 |
| `UPSTREAM_TIMEOUT_SECONDS` | 上游超时，默认 300 |
| `DATABASE_URL` | 一般不用改（容器内 sqlite） |

**不要**再在 `.env` 里写 `UPSTREAM_BASE_URL` / `UPSTREAM_API_KEY` / `DEFAULT_MODEL`，改管理后台。

## 本地开发

### 后端

```bash
cd backend
python -m venv .venv
# Windows: .venv\Scripts\activate
pip install -r requirements.txt
set DATABASE_URL=sqlite:///./portal.db
set ADMIN_PASSWORD=admin
set JWT_SECRET=dev-secret
uvicorn app.main:app --reload --port 8000
```

### 前端

```bash
cd frontend
npm install
npm run dev
```

## 主要 API

| 方法 | 路径 | 说明 |
|------|------|------|
| POST | `/api/auth/login` | 用户秘钥登录 |
| GET | `/api/auth/me` | 当前额度 |
| POST | `/api/admin/login` | 管理员口令 |
| GET/PUT | `/api/admin/settings` | 上游配置 |
| CRUD | `/api/admin/keys` | 秘钥管理 |
| GET | `/api/admin/usage` | 用量 |
| CRUD | `/api/conversations` | 会话 |
| POST | `/api/generate` | 文生图 |
| POST | `/api/edit` | 改图 |

## 注意

- 创建秘钥时明文只返回一次。
- 上游 API Key 回显脱敏；保存时留空表示不修改。
- 生图可能较慢，默认超时 300s。
