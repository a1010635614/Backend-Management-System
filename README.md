# VueBlog

一个 Vue 3 + Python FastAPI + PostgreSQL 博客项目。包含文章浏览与发布、管理后台、极验 4.0 与邮箱验证码登录、私有 COS 附件、Swagger、访问统计，以及 GitHub → 云效 → 服务器部署 → 飞书通知。

## 本地运行

需要 Node.js 20+、Python 3.12+、Docker Compose。

```powershell
docker compose up -d --build
```

另开终端：

```powershell
cd frontend; npm install; npm run dev
```

容器站点访问 `http://localhost:8080`，Swagger UI 为 `http://localhost:8080/docs`。前端开发服务器代理 `/api` 到容器 API 的 `http://localhost:8000`。管理后台 `/admin`，邮箱登录 `/login`。在 `.env` 中设置 `ADMIN_EMAILS`、`MAIL_*`，配置后使用管理员邮箱验证码登录。只有管理员可以发布、修改和删除文章。

`BAIDU_HM_ID` 配置百度统计站点 ID，访客同意统计后加载脚本并上报路由 pageview。云效可执行步骤见 [部署流水线](deploy/YUNXIAO.md)。

## 生产部署

当前生产使用 Ubuntu 上的 Nginx + systemd + Python 虚拟环境 + PostgreSQL 原生部署。云效构建并上传通用制品，主机 Runner 发布到版本目录，健康检查通过后切换当前版本。具体步骤见 [云效接入](deploy/YUNXIAO.md)，不需要在这台服务器上运行 Docker 或使用 ACR。

仓库 Compose 保留为本地及其他环境的参考方案。使用时复制 `.env.example` 为 `.env`，填入真实配置。原生生产环境使用 `/etc/vueblog.env`，第三方密钥通过遮罩配置工具传入；不要将环境文件或云密钥提交 Git。

详细接入步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 当前服务器

截至 2026-11-20，站点为 https://kongqi.xyz ，生产数据库为 PostgreSQL 16.15；仓库 Compose 为 PostgreSQL 17 参考方案。服务名 `vueblog`，目录 `/opt/vueblog/current`，环境文件 `/etc/vueblog.env`。

- 极验 4.0 → 邮箱验证码 → 管理员登录已经真实验收。
- 私有 COS 上传、HEAD 确认、签名下载、正式网站 CORS，以及图片/PDF 上传、保存文章和打开附件已验收。
- 百度统计已由用户确认正式域名的访问记录或 PV/UV。
- 第 11 次流水线已验证 main 提交自动触发、Packages 上传、原生主机部署及正确飞书群成功通知，提交为 `c2d4c75`。失败/取消通知和真实故障回滚仍未演练。
- DNS 沿用阿里云；COS、附件 CDN 和 `cdn.kongqi.xyz` 的 CDN 证书使用腾讯云。云端 CDN 已通过图片/PDF 内容比对、有效签名下载、无签名/错误/过期签名拒绝及重复下载 Cache Hit。包含应用 CDN 支持的 `f62dc92` 已推送，用户确认云效正在构建；应用尚未切换 CDN，待发布后启用配置并做正式浏览器验收。

各服务步骤见 [COS](deploy/COS-SETUP.md)、[极验](deploy/GEETEST-SETUP.md)、[百度统计](deploy/BAIDU-SETUP.md)、[飞书](deploy/FEISHU-SETUP.md)、[云效](deploy/YUNXIAO.md)与[CDN](deploy/CDN-SETUP.md)。本次 CDN 源码已在隔离 PostgreSQL 环境通过 20 项后端检查；云端验证与应用发布状态分别记录，不能相互替代。

ICP备案按用户要求暂缓。主站 HTTPS 实测可访问，但公网 HTTP 曾出现平台拦截，Certbot HTTP-01 续期演练曾因 403 失败；主站证书续期仍需处理。腾讯云 CDN 子域名证书已签发不代表主站续期问题解决。部署和测试记录见 [PROGRESS.md](PROGRESS.md)。
