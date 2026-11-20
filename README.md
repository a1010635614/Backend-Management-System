# 纸间博客 · Blog Fullstack

Vue 3 双前端、异步 FastAPI 后端，以及 PostgreSQL、Redis、私有 COS 和 CDN。前台浏览 Markdown 文章，后台按角色管理草稿、发布内容、用户和访问统计。

**迁移状态：** 当前工作分支正在实现新版 monorepo。上次正式验收的线上版本为 `f62dc92`，仍采用原生部署；新版 Compose 尚未接管正式流量。CDN 的正式图片/PDF 已由用户验收。完整进度和未完成项见 [迁移记录](MONOREPO-MIGRATION.md)，不能将旧版上线证据视为新版已发布。

## 技术与目录

| 目录 | 技术与职责 |
| --- | --- |
| `frontend-web/` | Vue 3 Composition API、`<script setup>`、TypeScript、Vite、History Router、Pinia、Axios、Tailwind、Markdown-it + DOMPurify |
| `frontend-admin/` | Vue 3、TypeScript、Vite、Element Plus 按需加载、Pinia、Axios、服务端菜单与动态路由/RBAC |
| `backend/app/api,core,models,schemas,services/` | Python 3.11+、FastAPI、Pydantic v2、SQLAlchemy 2.0 AsyncSession、asyncpg、Uvicorn |
| `backend/alembic/` | PostgreSQL 迁移；0003 保留旧用户/文章/附件并新增角色、草稿及作者字段 |
| `deploy/docker/` | PostgreSQL 16、Redis 7、后端、双前端、网关和一次性迁移服务的 Compose 配置 |
| `deploy/nginx/` | 主机 HTTPS/301、代理、History fallback、HTML 不缓存、哈希资源长期缓存 |
| `deploy/scripts/` | 制品验证、部署/回退、健康检查、飞书通知和本地配置初始化 |
| `deploy/cicd/` | 云效构建入口、步骤及环境变量清单 |

后端通过 Redis Lua 原子处理验证码 TTL、尝试次数、单次消费与限流；JWT 使用 jti 黑名单退出，服务端始终校验数据库中的角色和账号状态。邮件使用 aiosmtplib；极验使用异步 HTTPX；同步 COS SDK 移至线程执行。Swagger 位于 `/docs`，OpenAPI 位于 `/openapi.json`。

## 本地启动

完整容器方式需要 Docker Engine/Desktop 和 Compose v2。先使用 Python 3.11+ 生成独立的本地配置：

```bash
python deploy/scripts/init_local.py
docker compose --env-file .env up -d --build --wait
```

初始化程序生成随机数据库、Redis 和 JWT 配置，遇到已有 `.env` 会停止并保留原文件；已有配置请按 `.env.example` 手动合并。不要把生产环境复制到本地。容器依赖镜像默认来自官方 public ECR library；网络可直连 Docker Hub 时可通过环境变量切换官方同名镜像。

- 前台：`http://127.0.0.1:8080/`
- 后台：`http://127.0.0.1:8080/admin/`
- 接口文档：`http://127.0.0.1:8080/docs`
- 健康检查：`http://127.0.0.1:8080/api/health`，同时检查 PostgreSQL 和 Redis。

登录需要配置真实的 `MAIL_*`、`GEETEST_*` 和 `ADMIN_EMAILS`；空配置只允许浏览公开内容，不会返回模拟验证码。上传需要 `COS_*`。首次数据库为空，使用管理员邮箱登录后创建文章。公开注册用户默认为 viewer，管理员可授予 editor；editor 只能修改自己创建的内容。

停止服务执行 `docker compose --env-file .env stop`。日常停止不要加 `down -v`，以保留数据库和 Redis 持久化卷。

### 前后端开发服务器

需要 Node.js 22.12+、Python 3.11+。先启动仅绑定回环的数据服务：

```bash
docker compose --env-file .env -f deploy/docker/docker-compose.yml -f deploy/docker/docker-compose.dev.yml up -d postgres redis
cd backend
python -m venv .venv
```

激活虚拟环境（Windows：`.venv\Scripts\activate`；Linux/macOS：`source .venv/bin/activate`），然后：

```bash
python -m pip install --require-hashes -r requirements-dev.txt
python -m alembic upgrade head
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

初始化生成的 `backend/.env` 使用本机 PostgreSQL 15432、Redis 16379，密码与根目录本地配置一致。另外打开两个终端，分别运行：

```bash
cd frontend-web
npm ci
npm run dev
```

```bash
cd frontend-admin
npm ci
npm run dev
```

前台为 5173，后台为 5174/admin/；两个 Vite 项目均将 `/api` 代理至 8000。生产构建使用同域 `/api`、`/admin/`，不要把本机端口写入生产包。

## 配置第三方服务

| 变量 | 配置 |
| --- | --- |
| `MAIL_HOST, MAIL_PORT, MAIL_USERNAME, MAIL_PASSWORD, MAIL_FROM` | SMTP，465 隐式 TLS；其他支持端口采用 STARTTLS，始终校验证书 |
| `GEETEST_ID, GEETEST_KEY` | 极验行为验证 4.0；生产必须开启二次验证 |
| `COS_REGION, COS_BUCKET, COS_SECRET_ID, COS_SECRET_KEY` | 上海私有 COS 桶，权限限制在 `uploads/*`；图片/PDF 最大 10MiB |
| `CDN_BASE_URL, CDN_AUTH_KEY` | 腾讯云 Type D、MD5、sign/t、十进制、300 秒；两项同时配置才启用 |
| `BAIDU_HM_ID` | 公开跟踪 ID；用户同意后才加载脚本并发送路由 PV |
| `ADMIN_EMAILS` | 初始管理员收件邮箱，可用英文逗号分隔 |

浏览器直传走 COS 签名 PUT；确认上传后由服务端 HEAD 核对大小和类型。公开文章的附件通过后端短时 307 转到 CDN/COS，响应 `private,no-store` 和 `no-referrer`；草稿附件需要登录和权限。COS CORS 必须包含实际前台/后台来源，不能靠开放桶读取权限解决跨域。

云端服务的操作步骤见 [COS](deploy/COS-SETUP.md)、[极验](deploy/GEETEST-SETUP.md)、[百度](deploy/BAIDU-SETUP.md)、[飞书](deploy/FEISHU-SETUP.md)、[CDN](deploy/CDN-SETUP.md)。上述旧配置工具针对原生版本，迁移期间不要将其误用于新版运行时。

## 检查与构建

```bash
cd frontend-web
npm test
npm run build
```

后台执行同样的三个命令。Linux 下后端使用独立临时 PostgreSQL/Redis 检查，永不回退到生产连接：

```bash
CI_PYTHON_BIN=backend/.venv/bin/python POSTGRES_BIN=/usr/lib/postgresql/16/bin bash deploy/scripts/test-backend.sh
python -m unittest discover -s deploy/tests -v
```

后端测试要求 Python 环境已安装开发哈希锁，且系统有 `initdb/pg_ctl/createdb` 和 Redis 7+。测试临时随机端口、结束清理；Windows 可通过 Linux 容器/WSL 运行。集成套件覆盖验证码并发/重放/过期、JWT 退出、服务端 RBAC、迁移数据保留、上传元数据和异步 SMTP TLS。

## 上线与运维

新版生产架构为主机 Nginx + Let's Encrypt → 回环网关 18080 → 双前端/API → 私网 PostgreSQL/Redis。服务使用非 root 用户、只读根文件系统、内存/进程限制和日志轮转，数据库与 Redis 独立持久化。

生产配置保存在 `/opt/blog-fullstack/shared/runtime.env`，root 0600；代码位于 `releases/<完整提交号>`，`current` 为成功版本。`deploy/scripts/deploy.sh` 验证完整制品和源码 SHA，构建镜像、备份数据库、运行迁移、检查实际 HTML/资源哈希后记录版本；健康失败恢复上一套兼容的 Compose 应用，不自动降级数据库。它不替代首次原生数据库迁移、Nginx 切流和证书续期配置。

云效构建/上传/主机发布/飞书配置见 [新流水线](deploy/cicd/README.md)，首次停写、复制旧数据及切流见 [首次迁移](deploy/cicd/FIRST-CUTOVER.md)，数据库恢复演练和定时任务见 [备份](deploy/cicd/BACKUP.md)。生产主机需要 Compose，但 Flow 构建仅依赖 Docker build/run；ACR 并非这个通用制品方案的必需项。控制器和隔离检查已完成，正式迁移、接收器升级、完整生产回滚及新版端到端发布仍待验收，详见 [MONOREPO-MIGRATION.md](MONOREPO-MIGRATION.md)。

用户已决定换成 2vCPU/2GiB/40GB 新轻量实例，按 [新服务器迁移](deploy/cicd/SERVER-REPLACEMENT.md) 保留旧数据并完成跨主机切流，不能在新机用空库初始化替代旧站迁移。

DNS 沿用阿里云，COS/CDN 和附件证书采用腾讯云；主站为 Let's Encrypt。主站 HTTP-01 续期曾因平台 403 失败，需要完成可自动续期的 DNS-01 验证。ICP备案按用户要求暂缓，不能用附件 CDN 验收替代这项准备。历史操作与证据保存在 [PROGRESS.md](PROGRESS.md) 和 [DEPLOYMENT.md](DEPLOYMENT.md)。
