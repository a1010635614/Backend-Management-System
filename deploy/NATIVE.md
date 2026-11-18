# kongqi.xyz 当前原生部署

目标：Ubuntu 24.04，2 核、894MiB 内存。现采用 Nginx、systemd/Uvicorn、PostgreSQL 16.15；Docker/ACR 流水线配置作为后续方案保留，尚未执行。该服务器不承担 Node 构建。

## 目录与进程

- `/opt/vueblog/releases/<timestamp>`：后端源码与前端 dist。
- `/opt/vueblog/current`：当前版本符号链接。
- `/opt/vueblog/venv`：Python 依赖。
- `/etc/vueblog.env`：数据库密码、JWT 密钥与第三方配置；root:blog，权限 640，不回传、不提交。
- `/etc/systemd/system/vueblog.service`：非 root 服务用户 blog，API 只监听 127.0.0.1:8000。
- `/etc/nginx/sites-available/vueblog`：域名站点，静态文件与 API 代理。
- PostgreSQL 只监听本机，业务库 blog。
- `/etc/letsencrypt/live/kongqi.xyz`：HTTPS 证书，certbot.timer 与续期 reload 钩子。

## 日常操作（SSH 登录后）

```bash
systemctl status vueblog nginx postgresql --no-pager
journalctl -u vueblog -n 80 --no-pager
curl -fsS http://127.0.0.1:8000/api/health
nginx -t
systemctl restart vueblog
systemctl reload nginx
```

修改第三方配置可使用 `sudoedit /etc/vueblog.env`，随后重启 vueblog。邮件、极验、COS、百度统计配置与 .env.example 对应。2026-11-18 已配置 SMTP_SSL 465 与管理员白名单，用户反馈收到验证码并成功登录。生产没有启用本地预览登录码。

阿里云 SMTP 465 与管理员邮箱接入：用户在项目目录的交互 PowerShell 运行 `backend/.venv/Scripts/python.exe deploy/configure_mail.py`。脚本会先验证 SSH 主机，随后隐藏输入 SMTP 密码，不在本地保存密码；只验证 SMTP TLS/AUTH，不自动发送邮件；成功后更新后端代码、发件配置和管理员 kongqi_company@163.com。服务重启及健康检查失败会还原原代码和配置。邮箱接收与实际登录需要用户之后在登录页面触发验证。

## 数据备份

```bash
umask 077
runuser -u postgres -- pg_dump blog > /root/blog-$(date +%Y%m%d%H%M%S).sql
```

2026-11-18 已执行 setup-native-backup.sh，vueblog-backup.timer 每日 03:30（服务器时区，随机延迟最多 5 分钟）生成自定义格式备份至 /var/backups/vueblog，目录权限 700，文件权限 600，保留约七天。首份备份已成功恢复到隔离临时库并验证版本及各业务表。仍需另行准备异地加密备份，服务器本地备份不覆盖整机损坏。

## 当前发布流程

在 Windows 项目中执行 `npm run build`（frontend），通过 `upload_native.py` 上传明确选定的源文件和构建产物，再用 `remote.py deploy/install-native.sh` 安装；这些操作需以有权读取专用 SSH 密钥的 Windows 用户运行。脚本保留已存在的 Nginx 配置，避免后续发布覆盖 HTTPS。生产更新前仍需备份数据库，并考虑迁移兼容性；自动回滚脚本目前属于 Docker 方案，尚未用于原生部署。

## 验证与剩余事项

真实 PostgreSQL 16 的迁移与结构检查通过，最新极验校验修正版本在隔离测试库的 14 项回归全部通过；测试库 blog_ci 已删除。HTTPS、API 健康检查、Swagger 和前端路由入口实测成功；用户已通过极验 4.0 行为验证、收到邮件验证码并成功登录后台。

公网 HTTP 返回云平台 Non-compliance ICP Filing 拦截页，而服务器内部 HTTP 301 正常。请在阿里云核查首次备案或接入备案；不能因为 HTTPS 当时可访问就视为域名稳定上线。域名解析正常和 SSL 证书有效均不代表备案状态已完成。

证书已签发，有效期至 2027-02-15。certbot.timer 已启用，但 `certbot renew --dry-run` 实际失败：CA 的 HTTP challenge 验证收到 403。当前不能声称自动续期已经验收通过，备案拦截处理后需重新演练。Certbot 测试默认可能随机等待数分钟，可在人工复验时加 `--no-random-sleep-on-renew`，避免把等待误判成进程卡死。

私有附件 0002 迁移及对应代码已部署，管理员用户保留，服务健康。2026-11-18 COS 子账号凭据已配置，私有桶上传/下载与本机 CORS 检查通过，用户实际完成图片/PDF 上传、保存文章和打开附件，数据库关联记录已核对。

后续：百度统计实联；云效/ACR/飞书联调；CDN、异地备份、发布回滚与完整上线验收。ICP 按用户要求暂缓，续期问题仍需解决。GitHub main 最近已核对为基础提交 d7bc812，附件提交 33f7ab8 及后续验收记录尚未推送。极验操作说明见 [GEETEST-SETUP.md](GEETEST-SETUP.md)，下一步准备见 [BAIDU-SETUP.md](BAIDU-SETUP.md)。
