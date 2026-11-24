# 项目验收与交接

本次核验日期：2026-11-24，Asia/Shanghai。以下区分源码、实际运行、用户反馈与暂缓事项。运行版本以服务器 `/opt/blog-fullstack/.current-release` 和正式 Flow 最近成功记录为准；文中的提交号是历史验收基线。

## 已上线的架构

主站为 `https://kongqi.xyz/`，后台为 `/admin/`，Swagger 为 `/docs`，OpenAPI 为 `/openapi.json`。生产主机 `121.40.113.185` 上，Nginx 负责 TLS，再代理到回环网关 18080；网关分流双前端和 API，PostgreSQL/Redis 使用私有容器网络。

首次迁移提交为 `63dba62`，正式自动发布第 13 次为 `73331b7`，第 14 次为 `67d9bbf`。2026-11-24 晚间重新检查第 14 次版本：六个容器已连续健康运行约 10 小时，数据库为 0003，公开页面及发布包资源一致。

## 逐项证据

| 要求 | 代码或配置 | 实际核验与边界 |
| --- | --- | --- |
| 前台 Vue 3、Composition API、script setup、TypeScript、Vite | `frontend-web/src/`、`package.json` | 生产构建通过，公开 HTML/JS/CSS 与真实发布包匹配 |
| 前台 History Router、Pinia、Axios、Tailwind | `frontend-web/src/main.ts`、`stores/`、`lib/http.ts`、`vite.config.ts` | 实际 History 回退及资源缓存检查通过；依赖和入口已核对 |
| Markdown 与 XSS 过滤 | 两个前端的 `src/lib/markdown.ts` | Markdown-it 禁用原始 HTML，再由 DOMPurify 过滤；两个前端各 3 项 Markdown/XSS 检查 |
| 后台 Vue 3、TypeScript、Vite、Element Plus、Pinia、Axios | `frontend-admin/` | 正式后台已由用户验收；类型检查和生产构建通过 |
| 后台动态路由及 RBAC | `frontend-admin/src/router/index.ts`、`stores/auth.ts` | 新增 6 项真实 Router/Pinia/Axios 协作检查，网络边界为虚构接口；覆盖管理员深链接、编辑菜单、普通用户、退出/换账号及401失效，不以此替代后端鉴权 |
| 后端独立角色与内容归属校验 | `backend/app/core/security.py`、`api/admin.py` | 真实临时 PostgreSQL/Redis 套件覆盖角色、停用账号、权限变更及文章归属 |
| Python 3.11+、FastAPI、Pydantic v2、异步 SQLAlchemy2/asyncpg、Alembic、Uvicorn | `backend/app/`、`backend/alembic/`、哈希依赖锁 | 生产容器 Python 3.12.16、FastAPI 0.165.0、Pydantic 2.14.4、SQLAlchemy 2.0.58、asyncpg 0.32.0、Uvicorn 0.54.0 |
| PostgreSQL 15+、Redis 7+ | `deploy/docker/docker-compose.yml` | 实际 PostgreSQL 16.15、Redis 7.4.11，健康接口同时验证两者 |
| 验证码 TTL、限流、单次使用、Token 黑名单 | `backend/app/core/cache.py`、`services/auth.py`、`api/auth.py` | Redis Lua 原子操作；集成检查覆盖真实 TTL、并发、重放、错误次数、退出撤销和 Redis 故障拒绝认证 |
| 极验 v4 与异步 SMTP | `services/geetest.py`、`services/mail.py` | 用户已完成正式极验、收信和登录；SMTP 用 aiosmtplib，生产实际 5.1.3，TLS/主机名检查有独立回归 |
| 私有 COS 上传 | `services/storage.py`、后台 Editor | 用户已上传图片和 PDF 并打开；签名 PUT、上传后 HEAD 大小/类型确认，COS SDK 移至工作线程 |
| 腾讯云 CDN | `backend/app/cdn.py`、附件下载接口 | Type D/MD5/sign/t/十进制/300秒；签名协议有回归，真实浏览器图片/PDF 已验收，私有草稿与公开附件分开鉴权 |
| 百度统计与第一方统计 | `frontend-web/src/lib/analytics.ts`、`backend/app/api/analytics.py` | 用户同意后收集；6 项初始化/路由/隐私检查；用户确认正式站百度实时访问记录已有本次访问 |
| Swagger / OpenAPI | `backend/app/application.py`、网关配置 | 公开接口路径及文档页面可用，Swagger UI 资源曾实际加载核对；没有使用示例响应代替业务 API |
| Nginx HTTPS、301、History、缓存与代理 | `deploy/nginx/` | 晚间公网 HTTP301、HTTPS200、TLS1.3、CA/主机名验证和 Nginx 配置检查通过；HTML no-store、哈希资源 immutable、静态404及双前端 History 已实际核对 |
| Let's Encrypt 当前证书 | 主机 `/etc/letsencrypt/` | 当前证书有效至 2027-02-15；自动 DNS-01 续期另列为用户暂缓项 |
| Docker Compose 与重启持久化 | `deploy/docker/` | 六个生产服务 healthy；非特权/只读配置、资源限制、日志轮转、数据卷与 unless-stopped；独立环境的 Redis 重启持久化已核验 |
| 阿里云效 CI/CD | `deploy/cicd/build.sh`、`deploy/docker/ci.Dockerfile`、`scripts/flow_host.py` | 第13/14次真实 main 自动触发，经过检查、Packages、完整SHA校验和新机Compose部署；制品产出依赖真实 PG/Redis 与双前端检查阶段 |
| 飞书通知 | 已保存的 Flow 插件、可选 `scripts/notify_feishu.sh` | 用户确认新版第13次成功通知编号和提交正确；脚本预览不作为送达证明 |
| 首次迁移、失败恢复 | `native_cutover.py`、`deploy_release.py` | 正式最终备份/空目标导入/旧字段核对/0003升级/切流通过；真实失败回退在独立环境验证，没有对生产注入故障 |
| 备份与运维 | `backup.py`、`restore_drill.py`、`blog-backup.service/timer` | 新生产库真实隔离恢复通过；晚间再次核对历史归档及恢复证明摘要、root0600保护；每日timer enabled/active，旧应用与旧timer停用，旧库保留 |
| Monorepo 与示例配置 | 根目录、两个前端 `.env.example`/Vite代理、`backend/app/api,core,models,schemas,services`、`backend/alembic` | 所有命名目录、Dockerfile、Compose及两个要求的shell入口已核对存在 |
| 忽略敏感与生成文件 | `.gitignore` | Git 已跟踪文件中未发现真实 .env、.local、venv、node_modules、dist、__pycache__；哈希检查不等于对所有历史提交做了秘密审计 |
| 本地运行与部署说明 | `README.md`、`deploy/cicd/` | 包含本地初始化/启动/停止、环境变量、云效、首次迁移、备份、服务器更换和证书状态；历史说明不能直接当作当前操作指令 |

## 发布速度验收

同一台生产主机的实际 Flow 任务日志：

| 指标 | 第13次 | 第14次 |
| --- | --- | --- |
| 主机部署耗时，约 | 938.6秒 | 57.2秒 |
| pip 安装层 | 未命中缓存 | CACHED |
| pip 下载记录数 | 44 | 0 |

原因是预构建/云端使用阿里云 PyPI，而主机默认源不同；现已统一生产默认源并过滤 Runner 同名变量，保留锁版本、哈希及 HTTPS 校验。上述约94%的改善只针对主机部署阶段，且不能保证变更依赖或基础镜像后仍然零下载。

## 本轮新增检查的范围

后台9项为原有3项XSS检查加6项路由回归，使用真实 Vue Router、Pinia 与 Axios 拦截器，只替换网络边界；不向生产发验证码或制造用户。jsdom 原生不能加载外部 Element Plus CSS，按 [Vitest 官方说明](https://vitest.dev/guide/environment)将该依赖交给 Vite 处理；测试显式使用生产 `/admin/` 挂载路径。后台类型检查和生产构建通过。

已有后端真实 PG/Redis 套件为30项及25个子场景，部署工具检查70项；具体本次云端测试结果以对应运行日志为准。源码没有修改后端认证、数据库迁移或业务流程，新增检查不能冒充所有页面的视觉自动化验收。

## 唯一继续暂缓的实施项

2026-11-24 用户再次明确选择“继续暂缓证书，先做其他收尾”。DNS-01程序及受保护配置已准备，真实读取权限已验证，但 TXT 增删/清理、ACME staging、持久化 DNS-01 配置及后续 dry-run 尚未验收。当前仍是 webroot 续期配置；公网301恢复不代表续期已自动通过，也不能据此推断ICP备案状态。

恢复这一项前，先读取证书/续期配置与锁现状，再依 [TLS-RENEWAL.md](deploy/cicd/TLS-RENEWAL.md)的分阶段步骤执行。没有用户恢复指示时，不运行申请或变更DNS。旧服务器、旧库与归档保留；退役需后续明确安排。
