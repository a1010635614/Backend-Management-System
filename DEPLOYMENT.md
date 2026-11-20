# 上线与第三方服务接入

本文同时包含实际原生部署说明与其他环境的参考配置。截至 2026-11-20，生产为 Vue 3 + FastAPI + Ubuntu PostgreSQL 16.15，使用 Nginx/systemd/版本虚拟环境；下文容器方案供本地或另行选择容器的环境使用。具体已验证证据见 [实施记录](PROGRESS.md)。

## 域名、HTTPS 与 CDN

1. 准备一台部署主机或容器服务；生产数据库建议使用云 PostgreSQL（开启自动备份、私网访问和 TLS），避免将数据库端口暴露公网。
2. 在 DNS 添加 `A` 记录：`@` 指向站点入口，`api` 指向 API 入口。若前后端同域，使用 Nginx `/api` 代理即可。
3. 使用云厂商证书或 Let's Encrypt 申请证书。Nginx 站点配置示例见 `deploy/nginx-ssl.conf.example`，80 端口跳转 443，设置 TLS 1.2/1.3、安全响应头及自动续期。
4. 当前腾讯云 CDN 仅用于 COS 图片/PDF 附件，域名 `cdn.kongqi.xyz`，中国境外区域、HTTPS 私有回源及 Type D 访客鉴权；前端站点、HTML 和 `/api/*` 仍由主站提供。应用自己的带 hash 资源可设置长期缓存，HTML/API 使用 no-store。具体参数、计费限制与验收见 [CDN 接入](deploy/CDN-SETUP.md)。
5. `.env` 填真实强随机密码；生产覆盖 `DATABASE_URL` 等变量。仓库内 compose 端口仅示范，生产应由云负载均衡/Nginx 暴露 80/443。

实际 DNS 服务为阿里云，两个权威 NS 为 `dns7.hichina.com`、`dns8.hichina.com`；CDN CNAME 为 `cdn.kongqi.xyz.cdn.dnsv1.com`，已直接向两个权威服务器核对匹配。CDN 子域名使用腾讯云证书；主站使用 Certbot/Let's Encrypt。主站 HTTP-01 续期曾因公网 403 失败，仍待处理；ICP备案按用户要求暂缓。

## 腾讯云 COS 海量文件上传

浏览器直传 COS：`POST /api/uploads/presign` 接收 JSON filename/contentType/size，服务端拒绝非图片/PDF、空文件和超过 10MiB 的声明，生成限定 key、Content-Type、Content-Length 的五分钟 PUT 签名。上传成功后调用 `/api/uploads/{id}/complete`，后端通过 HEAD 核对实际大小和类型，附件才能写入文章。文件名与对象 key 分离，客户端不能指定桶内路径。

私有桶附件在文章中保存 `[[asset:UUID]]` 标记。仅完成确认且被现有文章引用的附件，才可通过 `/api/media/{id}` 获取五分钟 GET 签名跳转；文章删除后入口返回 404，已发出的签名会在有效期后失效。预览图片与 PDF 链接由 Vue 渲染，不把长期签名写入文章。CDN 支持使用 `CDN_BASE_URL` 和 `CDN_AUTH_KEY` 两项配置：均空时保留 COS 签名下载，完整启用后改为腾讯云 Type D 签名跳转，部分或无效配置返回 503；上传始终直传 COS。真实 COS 和正式浏览器上传已验收；云端 CDN 已独立通过内容比对、有效签名、暖缓存后无签名/错误/过期签名拒绝及 Cache Hit，应用新版本发布和切换尚待完成。当前没有使用 STS。大小/MIME 校验不等同于文件内容安全扫描。参考[预签名 URL](https://cloud.tencent.com/document/product/436/35153)与[对象元数据](https://cloud.tencent.com/document/product/436/65828)。

创建私有读写桶；受限子账号只授权对应桶 `uploads/*` 的上传和读取（包含 HEAD 查询）权限。当前 CORS 已保留 `http://127.0.0.1:5173` 并新增 `https://kongqi.xyz`，允许 PUT/GET/HEAD 与 Content-Type、Content-Length 头，暴露 ETag；两套预请求及正式浏览器图片/PDF 流程已验收。密钥只在服务器环境配置。暂未使用的上传对象需要按业务保留规则清理；当前不会自动删除用户文件。

## 极验 + 邮箱验证码登录

- 浏览器加载极验官方前端 SDK 完成挑战，后端使用 `GEETEST_ID` 和 `GEETEST_KEY` 调官方二次校验接口；只有服务端校验通过才发登录验证码/建立会话。
- 邮箱验证码由 Python smtplib 发出：465 端口使用 SMTP_SSL 隐式 TLS，其余端口使用 STARTTLS；两种方式都校验证书和主机名。验证码随机生成、哈希存储，五分钟过期，单次使用，同邮箱有效期内不能重发，最多错误五次。IP 限频在入口反向代理配置。
- 登录签发一小时 JWT，前端保存在 sessionStorage 并通过 Authorization Bearer 发送。当前没有刷新令牌，过期后需重新登录。`ADMIN_EMAILS` 设置有写作和后台权限的邮箱，普通用户无管理权限。生产必须设置强随机 `JWT_SECRET`。
- 邮件服务器参数通过 `MAIL_*` 环境变量配置。不要在日志中记录验证码或令牌。

## Swagger / OpenAPI

开发与本地容器访问 `/docs`，OpenAPI JSON 位于 `/openapi.json`。生产建议通过反向代理做登录保护或仅在内网开放。通过邮箱验证接口取得 access_token 后，点击 Swagger Authorize 填入 JWT，即可调用受保护管理接口。

## 百度统计与业务 PV/UV

`BAIDU_HM_ID` 通过后端公开配置接口下发站点 ID，访客明确同意后才加载百度脚本。Vue Router 切换通过 `_trackPageview` 手动上报。本站 `/api/analytics/events` 使用随机匿名标识另采集 PV/UV，后台统计按 UTC 当日计算；不采集查询参数和完整来源地址。上线需配置数据保留和清理策略。

## 阿里云效 CI/CD + GitHub + 飞书

当前原生链路：GitHub `main` push → 云效 Flow → Docker 构建环境中的后端/真实隔离 PostgreSQL 检查及前端构建 → Packages 通用制品仓库 → `blog-production` 主机组 Runner → 版本虚拟环境、迁移、健康检查与当前版本切换 → 飞书通知。服务器不运行生产 Docker，当前方案无需 ACR 或 ACK。将数据库密码、JWT 密钥、COS/邮件凭证保存在服务器受限环境文件或对应凭据管理中。

第 11 次运行已由真实 `c2d4c75` 提交自动触发，构建、上传、生产部署和正确飞书群成功通知均已验收。源码 CDN 支持提交 `f62dc92` 的首次 Webhook 超时，经一次重投后云效接收成功；用户确认该次运行正在进行，服务器尚未看到此版本标记。具体操作见 [云效接入步骤](deploy/YUNXIAO.md)。部署脚本在健康检查失败时恢复上版代码和服务，数据库结构不自动降级；真实故障回滚及失败/取消通知仍未演练。

## 容器部署

```bash
cp .env.example .env
# 编辑 .env 后：
docker compose up -d --build
docker compose logs -f api
```

站点示例监听 8080。正式上线请将 TLS 终止放到 Nginx/负载均衡，持久化 PostgreSQL，配置备份恢复演练、日志轮转、监控告警和发布回滚。

具体证书首次签发、续期钩子及 CDN 缓存验收见 [TLS/CDN 操作](deploy/TLS-CDN.md)。

## 数据库迁移与本地回归

容器启动执行 `alembic upgrade head`，随后启动 Uvicorn。生产部署应串行执行，禁止多副本同时迁移；未来多副本需改为独立迁移任务。没有自动插入演示文章，管理员登录后自行创建。

本地 Python：在 backend 目录创建虚拟环境，安装 requirements.txt，设置 DATABASE_URL 后执行 `python -m alembic upgrade head` 和 `python -m uvicorn app.main:app --reload`。项目自带测试可执行 `python -m unittest discover -s tests -v`，使用临时 SQLite 验证业务流程，不替代 PostgreSQL 行锁和真实云服务测试。

如果已经运行过早期 create_all 版本，先备份数据库，再对比结构并补齐 email_codes.attempts；不得直接 stamp 版本跳过结构审计。全新部署使用迁移创建表，不会遇到这类历史差异。
