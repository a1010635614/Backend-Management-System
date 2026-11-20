# 双前端与异步后端迁移

用户 2026-11-20 更新的目标以本文件所列范围为准。当前在 `codex/production-monorepo` 分支实施；线上仍为已验收的 `f62dc92`，本次重构没有发布。

## 已有生产基线

- `kongqi.xyz`：Nginx + systemd + PostgreSQL 16.15；管理员极验/邮件登录、正式 COS 上传、百度统计、云效第 12 次发布与飞书通知已验收。
- `cdn.kongqi.xyz`：腾讯云 CDN 私有回源、Type D/MD5/sign/t/十进制/300 秒；图片/PDF 内容一致、暖缓存鉴权及 Cache Hit 均通过。CDN 配置已启用，用户确认正式浏览器图片/PDF 正常。
- DNS 为阿里云，CDN 和 CDN 证书为腾讯云。主站仍为 Let's Encrypt，HTTP-01 续期 403 尚待改为可验证的续期方案。

## 本次实现与验证

- [x] 新建 `frontend-web`：Vue 3/TypeScript/Vite/History Router/Pinia/Axios/Tailwind/Markdown-it/DOMPurify。
- [x] 新建 `frontend-admin`：Vue 3/TypeScript/Vite/Element Plus/Pinia/Axios、服务端下发动态路由与 RBAC。
- [x] 拆分后端 `app/api`、`core`、`models`、`schemas`、`services`；SQLAlchemy 2.0 AsyncSession + asyncpg。
- [x] Redis 验证码 TTL、原子尝试计数与单次消费、共享限流、极验凭证防重放、JWT jti 黑名单。
- [x] 异步 aiosmtplib 发信；异步 HTTPX 极验；阻塞 COS SDK 移至工作线程；复用已验收 CDN 协议。
- [x] 双前端生产构建和各 3 项 Markdown/XSS 测试通过。
- [x] 真实隔离 PostgreSQL + Redis 7.4.11 下 20 项后端检查通过；没有读取生产环境或数据库。
- [x] 已有 0002 数据升级/降级的迁移检查通过；原用户/文章/附件保留，21 项真实隔离检查全部通过。
- [x] 已生成跨平台 Python 3.11+ 生产与开发完整依赖/哈希锁；全新 Linux 隔离虚拟环境已在 `--require-hashes` 下安装成功。
- [x] 新增 SMTP 错误恢复/TLS、真实 TTL、过期 Token 边界检查；锁定依赖的新建 Linux 环境中 26 项真实检查全部通过。
- [ ] `deploy/nginx`、`deploy/docker`、`deploy/scripts`、`deploy/cicd`：完整双前端 Compose 构建、发布、健康与回退。
- [ ] 替换旧 Flow/native 构建入口，完成新链路的真实 GitHub 提交、部署与飞书验收。
- [ ] 更新 README/环境变量/运维说明；旧原生部署仅作为历史基线，不能冒充新架构完成。
- [ ] 新版本完整浏览器登录、角色权限、文章编辑、附件、统计及 History 深链路验证。
- [ ] 主站 Let's Encrypt 自动续期、完整生产 Compose 的资源和恢复验收。

## 当前运行记录

隔离工具目录为服务器 `/opt/vueblog/verification/monorepo-v2`，仅用于测试：官方 Redis 7.4.11 源码经 Redis 官方哈希清单核对，以非特权 blog 用户编译；独立虚拟环境不复用生产依赖。测试脚本每次启动随机端口、仅监听本机的临时 PostgreSQL/Redis，退出停止并删除临时目录。

本地辅助脚本位于忽略目录 `.local`；不得将真实环境、密钥或临时数据库归档提交 Git。旧 `frontend/`、原后端 Dockerfile/preview 和旧测试已归档至 `deploy/legacy-native/`；目前线上原生部署仍需使用完整 Git 基线 `f62dc92`。根目录原生维护工具暂留用于现有生产，不能与新版代码混用。

## 待落实的部署设计

- 新 Compose 包含独立 web/admin/backend/PostgreSQL/Redis 服务；主机现有 Nginx 继续负责 Let's Encrypt TLS，代理到仅绑定回环的容器端口，避免占用当前 80/443。前台 `/`、后台 `/admin/`、API `/api/` 分流，配置 History fallback 和静态资源缓存。
- 本地 Compose 从源码构建；生产使用云效已经构建的两个 dist 与锁定后端依赖，避免在小内存生产主机执行 Node 构建。应提供生产构建覆盖文件或等效明确入口。
- 当前 Flow Docker 服务不支持网络管理 API，新的 CI 检查仍应在单个含临时 PostgreSQL/Redis 的构建容器内执行，不依赖 Flow 中的 Docker Compose 网络创建。制品通过现有 Packages/主机 Runner 传递；主机实际运行生产 Compose。
- 主机现有原生 PostgreSQL 必须先备份，再复制到新容器数据库并执行 0003，不能把新架构直接指向并修改旧数据库后宣称可无损回退。首次切换需控制旧服务写入并验证数据数量、附件、管理员登录；成功前保留旧版本和配置。
- 初始服务器没有 Docker/Redis，约 398MB 可用内存、无 swap。已启用 1GiB swap；Docker 官方下载地址连接重置后，改用 Ubuntu 签名更新/安全仓库，安装 Docker 29.1.3、Compose 2.40.3、Buildx 0.30.1，原 vueblog/nginx/postgresql 均保持 active。
- 已有 Flow 主机命令调用 `/usr/local/sbin/vueblog-flow-deploy`；新部署需要审核并更新接收器或明确兼容入口，防止把新格式制品交给旧 native 释放脚本。不要仅更新构建而忽略主机发布入口。
- 新代码完成前不推送 main 触发半成品发布。工作分支为 `codex/production-monorepo`，本地基线检查点 `7280598` 仅保存已验收的旧生产文档。

## 候选环境与审批边界

自动审批拒绝了把生产 `/etc/vueblog.env` 第三方密钥复制到持久化候选环境的命令，理由是扩大凭据暴露范围、未明确授权复制全部生产密钥；该命令未执行。随后已完全移除读取生产环境的代码，使用独立随机测试密码、空 SMTP/极验/COS/CDN 配置，通过审批并完成真实 Compose 配置解析。不要改用间接方式重新复制生产密钥；正式发布内容准备完成后，再就必要生产配置迁移取得明确授权。

候选项目为 `blog-verification-v2`，服务器目录 `/opt/vueblog/verification/compose-v2-work`，候选网关/后端只绑定回环 18082/18002。服务器到官方公共镜像 CDN 的链路曾不可达，已通过本机从 Docker 官方 library 仓库按不可变摘要获取 Python/PostgreSQL/Redis/Nginx，再校验传输 SHA、配置和文件层离线导入；Google `go-containerregistry` crane v0.22.1 也核对了官方发布资产 SHA-256。

首次真实启动发现 YAML flow 数组中的 tmpfs 选项被逗号拆开，已将整段挂载选项加引号。随后六个常驻容器全部 healthy，一次性 Alembic 迁移 exit 0；原生 vueblog/nginx/postgresql 同时保持 active。候选真实 HTTP 检查通过：数据库/Redis UP、双前端 HTML 与发布目录一致、JS/CSS 哈希及 immutable 缓存、HTML no-store、History 深链接、缺失静态文件 404、匿名后台/会话 401、Swagger/OpenAPI；独立测试库文章数 0。

新增部署脚本和单元检查在 Linux 上 17 项通过，覆盖校验归档、遍历/链接拒绝、健康失败保持旧版本标记并恢复应用、保留数据、旧哈希静态资源和密钥文件权限。该结果不代表整套容器发布/失败回退已演练。新流水线入口为 `deploy/cicd/build.sh` 和 `deploy/docker/ci.Dockerfile`，旧 `deploy/build-flow.sh` 仅兼容转发；尚未完成真实构建，主机接收器仍是旧版，不可直接推 main。

后续重建在 Docker BuildKit worker 连接处失败，候选原容器仍 healthy；接着新增 29 项后端套件在首个接口 fixture 处出现 E，未取得详细结果即 SSH 超时。不能把本次记为通过，也不能仅凭连接超时断定测试根因。Node 官方镜像已在本机按摘要校验，服务器导入因公网 SSH 超时未确认。

最后一次只读主机观测：894MiB RAM，约 206MiB available，1GiB swap 未使用，负载回落至 1.09；原生三个服务和 Docker active，候选六个容器 healthy。此后从本机对公网 22/443、域名 443 的 TCP/TLS 探测均超时，未改安全组、未重启主机。已请用户通过 ECS 控制台核对实例运行状态与远程连接；恢复后先读取失败检查日志、核对生产健康和临时测试进程，再继续，不能直接重复构建。

用户确认实例运行中且控制台可进入后，下一次无认证探测已恢复：SSH banner 正常，IP/域名 TLS 1.3 握手通过。独立核对原生 API `UP`、原生三个服务/Docker active，候选六容器 healthy，完整候选 HTTP 检查再次通过。高负载曾达到 5 分钟约 20，内存约 198MiB available、swap 未使用；有一个 Python 进程 CPU 100%，正在只读识别其是否为临时验证进程，尚未结束进程或重启服务。短暂连接超时的根因尚未确认。

进一步只读进程检查没有发现遗留测试；当次最高占用的短时 Python 为检查进程自身，不能据此判断持续 CPU 耗尽。用户在 ECS 控制台提供的连续采样显示 CPU idle 94%～96%、available 215MiB、swap 0、22/443 正常监听，UFW inactive。没有据此更改安全组/防火墙或重启服务器，网络超时原因仍未确定。

测试启动脚本曾将虚拟环境 Python 用 `realpath` 解引用为系统解释器，导致找不到 redis；已改为 `realpath -s` 保留虚拟环境链接。首个接口独立诊断 0.32 秒通过；20 项部署工具检查均已在 Linux 通过。用户从控制台取回完整日志后确认：19 项接口、2 项 SMTP 通过，随后卡在旧数据迁移检查，不能把它误记为首个接口 fixture 卡死。迁移独立诊断已确认 `upgrade 0002` 能完成，`upgrade head` 子进程等待异常；正在增加超时和独立 CLI 等待方式定位，完整 29 项还未通过。

本地检查点 `980528e4d20fd8f43c448659508bda01ef81a605` 保存了双前端、异步后端及初版 Compose/发布脚本；后续诊断与归档有未提交改动。没有推送 main。新 `receive.py` 对外层归档和完整提交号做验证，首次原生迁移及 Nginx 切流未完成时拒绝自动发布；主机尚未安装新版接收器。DNS-01 的独立 RAM 策略模板与证书准备文档已写入 `deploy/cicd/`，尚无凭据或 hook 实施。

#### 资源隔离后的迁移复验通过

进一步采集到明显 PSI 等待：memory full avg10=32.52%、io full avg10=65.50%，当时 cpu some 6.21%。这与单次 CPU idle/可用内存采样不同，不能仅据 idle 较高就排除内存回收/I/O 等待。已仅停止 `blog-verification-v2` 候选容器并保留数据卷；正式原生三个服务 active、API UP。可用内存回升至 328MiB，根盘约 20GiB 可用；没有遗留运行中的临时数据库进程，旧临时目录保留用于诊断。

候选停止后，真实隔离迁移检查 4.37 秒通过：升级至 0002、插入旧用户/文章/附件、升级 head、结构 check、内容/计数保留、降级 0002 以及再次升级 head。CLI 调用移至独立受控线程并设置超时，仍执行真实 Alembic 和 asyncpg 数据核对，没有跳过迁移。此前超时不能认定为已复现的迁移逻辑死锁；现正以候选关闭的同一资源安排完成完整 29 项回归。

后续只按顺序运行 CI 构建/集成测试和候选预览，避免在这台 894MiB 主机上同时保留两套应用并运行开发检查。候选当前为有意停止状态，恢复前应完成验证并使用调整后的 15/30 秒健康检查间隔；不能把之前的 healthy 状态写成此刻仍在运行。

同样资源安排下最新完整结果：Linux 20 项部署工具检查通过；真实 PostgreSQL 16.15 + Redis 7.4.11 后端 29 项、25 个子场景全部通过，零跳过，总计 7.14 秒，最慢迁移 4.74 秒。覆盖新增私网代理 CIDR、迁移数据保留及原接口/邮件检查。测试进程和临时集群退出清理；正式应用未改。此前不完整运行保留为故障诊断历史，不能与这次最终成功混写。
