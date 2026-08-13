# Image Portal

对话生图门户：秘钥登录、会话历史、多轮改图、管理端分配额度。上游对接 OpenAI 兼容图片接口。

源码前后端分离；**Docker 单容器**对外；本地无 Docker 可分别启动调试。

## 功能

- 用户：秘钥登录、对话式文生图、基于上图多轮改图、模型选择、剩余额度
- 管理：
  - 单口令登录
  - **上游配置**（Base URL / API Key / 默认模型 / response_format）存 SQLite
  - WebDAV 图片存储配置与全部生成图片浏览
  - 创建/禁用秘钥、设置额度、用量记录
- 上游：文生图模型统一使用 `/v1/images/generations`；图生图固定使用 `gpt-image-2` 的 `/v1/images/edits`；成功按张扣额度
- 视频：独立配置上游 Base URL / API Key / 模型，调用 `/v1/videos/generations` 后轮询 `/v1/videos/{request_id}`；不写入对话、图库或本地存储

## Docker（单容器）

```bash
cd image-portal
cp .env.example .env
# 编辑 ADMIN_PASSWORD / JWT_SECRET
docker compose up -d --build
```

浏览器：`http://localhost:8080`

### 移动端 PWA

- 生产构建会生成应用清单、Android/iOS 多尺寸图标和 Service Worker。
- 手机浏览器打开后可使用浏览器菜单添加到主屏幕；支持安装提示的浏览器会显示应用内“安装”按钮。
- 应用外壳与本站 `/media/` 下已浏览的生成图片会缓存，断网时仍可打开已缓存的页面与图片；生成、登录及其他 API 请求仍需网络。
- 除 `localhost` 外，PWA 需要通过 HTTPS 访问。

1. `/admin/login` 用 `ADMIN_PASSWORD` 登录  
2. **上游连接** 填 Base URL、API Key、默认模型（`gpt-image-2` 或 `grok-imagine-image`）
3. 创建用户秘钥  
4. 用户用秘钥登录生图  

若要将生成图保存至 WebDAV，在管理后台的 **WebDAV 存储** 填写地址、账号、密码和远端目录。远端目录留空时，图片保存至 `image-portal/YYYY-MM-DD/`；填写时用该目录替代 `image-portal`。图片展示地址默认使用 WebDAV 地址；当 WebDAV 地址不适合浏览器直接访问时，填写映射到同一目录的 **公开访问基址**。

镜像：多阶段构建前端 → 拷入 Python 镜像，由 FastAPI 托管静态 + `/api`。

## 环境变量

| 变量 | 说明 |
|------|------|
| `ADMIN_PASSWORD` | 管理口令 |
| `JWT_SECRET` | JWT 密钥 |
| `PORT` | 宿主机映射端口，默认 8080 |
| `UPSTREAM_TIMEOUT_SECONDS` | 上游超时，默认 300 |
| `DATABASE_URL` | 默认容器内 `sqlite:////data/portal.db` |
| `STATIC_DIR` | 容器内静态目录，默认 `/app/static`（本地开发勿设） |
| `MEDIA_DIR` | 生成图落盘目录；本地默认 `./media`，容器 `/data/media` |

**不要**在 `.env` 写 `UPSTREAM_*` / `DEFAULT_MODEL`，改管理后台。

## 本地开发（无 Docker）

前后端分开跑；Vite 把 `/api` 代理到后端。

### 后端

```powershell
cd backend
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
$env:DATABASE_URL = "sqlite:///./portal.db"
$env:ADMIN_PASSWORD = "admin"
$env:JWT_SECRET = "dev-secret"
# 不要设 STATIC_DIR
uvicorn app.main:app --reload --port 8000
```

### 前端

```powershell
cd frontend
npm install
npm run dev
```

或脚本（两终端）：

```powershell
.\scripts\dev-backend.ps1
.\scripts\dev-frontend.ps1
```

浏览器：`http://localhost:5173`（代理 → `http://127.0.0.1:8000`）

### 可选：本地预览生产静态

```powershell
cd frontend; npm run build
cd ..\backend
$env:STATIC_DIR = "..\frontend\dist"
$env:DATABASE_URL = "sqlite:///./portal.db"
uvicorn app.main:app --reload --port 8000
```

访问 `http://localhost:8000`。

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
| POST | `/v1/images/generations` | OpenAI 兼容文生图，`Bearer` 可直接使用分配的 API Key |
| POST | `/v1/images/edits` | OpenAI 兼容图生图，`Bearer` 可直接使用分配的 API Key |
| POST | `/v1/videos/generations` | 创建视频生成任务，`Bearer` 可直接使用分配的 API Key |
| GET | `/v1/videos/{request_id}` | 查询视频生成进度和结果，使用同一认证 |
| GET/DELETE | `/api/gallery` | 用户图库（本地或 WebDAV 持久化） |
| GET | `/api/admin/images` | 管理员查看全部生成图片 |

## 注意

- 创建秘钥时明文只返回一次。
- 外部客户端可直接使用 `Authorization: Bearer <分配的 API Key>` 调用图片接口；请求体采用 `model`、`prompt`、`n`、`response_format`，图生图额外传 `images: [{"url": "..."}]`。
- 图片接口返回完整可直接访问的图片 URL，例如 `https://images.example.com/media/12/abc.png`；本地存储文件按识别到的图片类型保留 `.png`、`.jpg`、`.webp` 等扩展名。反向代理场景可配置 `PUBLIC_BASE_URL` 固定外网域名。
- 门户界面通过 `X-Conversation-Id` 关联本地会话；该请求头对外部 OpenAI 兼容客户端为可选。
- 对外部署默认关闭 `/docs`、`/redoc` 和 `/openapi.json`；仅本地调试时设置 `ENABLE_DOCS=true`。
- 上游 API Key 回显脱敏；保存时留空表示不修改。
- 生图可能较慢，默认超时 300s。
