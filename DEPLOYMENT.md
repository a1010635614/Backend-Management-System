# 上线与第三方服务接入

## 域名、HTTPS 与 CDN

1. 准备一台部署主机或容器服务；生产数据库建议使用云 PostgreSQL（开启自动备份、私网访问和 TLS），避免将数据库端口暴露公网。
2. 在 DNS 添加 `A` 记录：`@` 指向站点入口，`api` 指向 API 入口。若前后端同域，使用 Nginx `/api` 代理即可。
3. 使用云厂商证书或 Let's Encrypt 申请证书。Nginx 站点配置示例见 `deploy/nginx-ssl.conf.example`，80 端口跳转 443，设置 TLS 1.2/1.3、安全响应头及自动续期。
4. CDN 加速静态站点和 COS 图片资源。HTML 不缓存或短缓存；带 hash 的 `/assets/*` 设一年 immutable；API 禁止 CDN 缓存，上传和登录接口限流。回源使用 HTTPS，启用 Web 防护和访问日志。
5. `.env` 填真实强随机密码；生产覆盖 `DATABASE_URL` 等变量。仓库内 compose 端口仅示范，生产应由云负载均衡/Nginx 暴露 80/443。

## 腾讯云 COS 海量文件上传

当前实现浏览器直传 COS：API 使用服务器密钥签发五分钟有效的 PUT URL，限定对象 key 和内容类型。前端将返回的资源地址写入文章。配置 COS CORS 仅允许本站域名与 PUT、Content-Type 头；使用最小权限 CAM 密钥，配置生命周期规则。严禁把 SecretKey 放在 Vue 环境变量或浏览器代码中。当前 10MB 限制仅在客户端，生产还需要云侧大小/内容审查；私有桶的展示资源需要配置 CDN 鉴权或下载签名。

已实现 `/api/uploads/presign`，通过腾讯云原生 Python SDK 生成预签名地址；尚需使用真实腾讯云桶验证上传。并未实现 STS 临时凭证模式。`COS_PUBLIC_BASE_URL` 填可访问的 CDN 资源域名，不要填上传签名地址。参考[腾讯云预签名文档](https://cloud.tencent.com/document/product/436/35153)。

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

在云效流水线创建 GitHub 源码连接和 webhook，监听目标分支 push；流水线步骤依次执行前端构建、后端构建、镜像构建推送至 ACR、通过部署主机/ACK 滚动更新，并配置健康检查与失败回滚。将数据库密码、JWT 密钥、COS/邮件凭证保存在云效凭据库或部署平台密钥管理中。

仓库提供可执行构建、部署和飞书文本通知脚本及生产 compose，操作见 [云效接入步骤](deploy/YUNXIAO.md)。密钥存云效加密变量，成功/失败分支各配置一次通知。尚未在你的账号创建流水线或验证 GitHub webhook。

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
