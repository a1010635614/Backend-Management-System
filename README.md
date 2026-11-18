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

2026-11-17 已将基础站点部署到 https://kongqi.xyz ，采用 Nginx + Python systemd 服务 + Ubuntu PostgreSQL 16.15；仓库 Compose 仍为 PostgreSQL 17 方案。服务名 `vueblog`，目录 `/opt/vueblog/current`，环境文件 `/etc/vueblog.env`。2026-11-18 邮箱验证码投递与管理员登录已实际验收；附件的私有桶访问代码与 0002 迁移已部署，12 项隔离 PostgreSQL 测试通过。真实 COS、极验、云效、ACR、飞书与百度统计尚待配置联调。COS 子账号和跨域准备见 [COS 接入清单](deploy/COS-SETUP.md)。

域名公网 HTTP 检查遇到云平台未备案拦截，需要核查备案/接入备案状态。当前 HTTPS 实测可访问，不能视为整体上线验收完成。部署和测试记录见 PROGRESS.md。
