# VueBlog

一个 Vue 3 + Python FastAPI + PostgreSQL 博客全栈示例。包含文章浏览与发布、邮箱验证码登录、极验/COS 接入、Swagger、访问统计、容器部署与云效/飞书流水线示例。

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

复制 `.env.example` 为 `.env` 并填入强密码及服务密钥。配置 DNS 将域名解析到服务器，在 Nginx 配置证书路径并运行 `docker compose up -d --build`。生产建议使用托管 PostgreSQL、COS 私有桶+短时签名上传、CDN 回源 HTTPS，并由 certbot/云证书服务续期证书。不要将 `.env` 或云密钥提交 Git。

详细接入步骤见 [DEPLOYMENT.md](DEPLOYMENT.md)。

## 当前服务器

2026-11-17 已将基础站点部署到 https://kongqi.xyz ，采用 Nginx + Python systemd 服务 + Ubuntu PostgreSQL 16.15；仓库 Compose 仍为 PostgreSQL 17 方案。服务名 `vueblog`，目录 `/opt/vueblog/current`，环境文件 `/etc/vueblog.env`。2026-11-18 邮箱验证码投递与管理员登录已实际验收；私有附件 0002 迁移和后续极验校验修正已部署，最新 14 项隔离 PostgreSQL 测试通过。真实 COS 上传、HEAD、签名下载、私有读取限制和本机浏览器 CORS 已验证；用户确认图片/PDF 上传、保存文章和打开附件成功，数据库附件关联已核对。极验 4.0 通过真实行为验证、收码和后台登录验收。百度统计已在真实域名访问后获得用户确认的访问记录或 PV/UV。飞书签名测试通知已由用户确认发送并在正确的群收取，云效自动发布与成功/失败通知尚待联调；当前原生方案无需 ACR。CDN 与完整上线验收仍待完成。准备步骤见 [COS 接入清单](deploy/COS-SETUP.md)、[极验 4.0 指引](deploy/GEETEST-SETUP.md)、[百度统计说明](deploy/BAIDU-SETUP.md)、[飞书说明](deploy/FEISHU-SETUP.md)和[云效接入](deploy/YUNXIAO.md)。

域名公网 HTTP 检查遇到云平台未备案拦截，需要核查备案/接入备案状态。当前 HTTPS 实测可访问，不能视为整体上线验收完成。部署和测试记录见 PROGRESS.md。
