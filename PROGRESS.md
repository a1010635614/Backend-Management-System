# 实施与验证记录

## 当前交接状态

### 2026-11-18 继续准备

#### 邮件配置与备份的最新结果

用户已明确反馈“收到邮箱登陆成功”，实际收码和后台登录验收通过。本机前端 5173 与 SSH API 隧道 8000 还需以运行进程/端口复核；此反馈证明邮件登录闭环，不代表极验或其他云服务已接入。

用户通过本机遮罩窗口输入 SMTP 密码后，配置进程已成功结束：SMTP TLS/AUTH 验证通过（未发送邮件），/etc/vueblog.env 已写入发件配置及管理员 kongqi_company@163.com，main.py 和 mailer.py 已安装到当前服务器版本，vueblog 重启和健康检查通过。随后独立 verify-mail.sh 再次验证 SMTP、管理员白名单和服务健康均成功。先前“邮件字段为空/安装未完成”的记录已由本次成功结果取代。密码未写入源码或本文。

已执行 setup-native-backup.sh：每日 03:30（服务器时区，随机延迟最多 5 分钟）本地备份定时器 active，保留约七天；第一份备份 blog-20261118T095137Z.dump 已生成。verify-native-restore.sh 在独立临时库恢复成功，版本 0001，文章/用户/事件/验证码表可读，临时库自动清理，生产数据未改。尚未完成异地备份。

为实际收码测试已启动本地 Vite 127.0.0.1:5173（exec session 94788）与 SSH API 隧道 127.0.0.1:8000（session 66535），不是本地 SQLite 预览；代理健康检查已确认连接真实服务器。页面 /login 可用，极验尚未配置。已请求用户在页面发送验证码并反馈是否收到/成功登录；尚未获得邮箱投递与完整登录成功证据，不能视为邮件端到端验收完成。后续核对进程必须以实际 session/端口为准，不以本段记录推断仍在运行。

用户报告已在邮件配置脚本输入密码，但随后服务器验证显示所有 MAIL_* 字段及 ADMIN_EMAILS 仍为空，说明安装未完成；vueblog 服务仍 active。尚未确认 SMTP 密码错误、TLS错误或本机终端操作原因。没有发送测试邮件。已请求用户提供不含密码的执行结果；配置脚本增加不含输入载荷的 .local/mail-setup-status.log 状态日志，并区分 SMTP 拒绝认证码和连接异常类型，方便继续定位。当前不能标记邮件接入成功。

最新邮件/SSH进展：管理员收件邮箱确认 kongqi_company@163.com。用户重新执行了主机确认，SSH root 登录成功。查明含空格的 UserKnownHostsFile 参数未加引号，主机记录实际写到了 G:/Full；已将其中匹配 101.37.147.237 的既有信任记录迁移到项目 .local/ssh/known_hosts，并修复 setup_ssh.py、remote.py 的选项引用，严格主机检查下连接再次成功。未关闭主机检查，未自动接受新指纹。

线上只读检查：vueblog/nginx/postgresql 均 active，HTTPS health 为 UP；邮件字段和管理员白名单仍为空。新增 configure_mail.py：用户交互终端隐藏输入 SMTP 密码，经 SSH stdin 传输，在服务器校验证书并仅做 SMTP AUTH（不发信），原子更新 /etc/vueblog.env、管理员邮箱和 SSL 适配后端，重启并做健康检查，失败回退原文件。脚本尚待用户执行，因此尚未真实验证账号或发送邮件。新增两项配置序列化测试均通过，保证密码中的引号、反斜线和美元符号按字面保留，并拒绝换行注入。install-native.sh 不再 source 环境文件，改用 dotenv/interpolate=False 构造子进程环境，避免 SMTP 密码触发 shell 展开。

邮件接入更新：用户已提供阿里云 DirectMail 的 SMTP 主机 smtpdm.aliyun.com、端口 465、发信地址 noreply@mail.kongqi.xyz，SMTP 密码不记录在本文或源码中。新增 app/mailer.py，465 使用校验证书的 SMTP_SSL，其他端口保留 STARTTLS。增加 SSL 发信与失败不落库测试，本地 10 项测试 9 通过、1 PostgreSQL 专项跳过。配置和代码尚未更新到服务器，也尚未真实认证或发送邮件：known_hosts 缺失，仍需用户核对服务器指纹后恢复主机信任，并提供能收信的管理员邮箱。已提醒用户重置聊天中出现过的 SMTP 密码，后续通过受保护配置输入。

用户确认 ICP、邮件 SMTP、极验、COS、云效、ACR、飞书机器人、百度统计均未开通。新增 service-readiness.sh（只报告配置缺项）、setup-native-backup.sh（每日本地备份、约七天保留）、verify-native-restore.sh（独立测试库恢复验证），尚未执行成功。两次服务器连接因本机 .local/ssh/known_hosts 缺失而在严格主机检查阶段失败，未修改服务器，也未启用备份定时器。密钥与公钥文件仍在。setup_ssh.py 增加 --verify-host 交互模式，供用户在核对云控制台服务器指纹后重新信任主机，不绕过检查；不再重复修改既有私钥 ACL。待恢复连接后执行配置检查、备份及恢复演练。

### 服务器部署进展（2026-11-17）

用户已确认 kongqi.xyz 尚未完成 ICP 备案。等待用户在阿里云完成备案后，再复测公网 HTTP/HTTPS、ACME challenge 与证书续期；不将当前基础部署标记为完整上线完成。

SSH 专用密钥连接已验证（Windows 用户权限下使用，检查模式已修复为不再改写 ACL）。服务器实测 2 核、894MiB 内存、30GB 系统盘；采用原生 Nginx + systemd/Uvicorn + PostgreSQL，前端本地构建上传，避免服务器运行 Node 构建。服务器已安装 PostgreSQL 16.15（Ubuntu 24.04 发行版），应用角色和强随机凭据仅保存在服务器 /etc/vueblog.env，不回传本机或提交 Git。数据库和后端只监听 127.0.0.1。

代码位于 /opt/vueblog/releases，下设 current 符号链接；虚拟环境 /opt/vueblog/venv，systemd 服务 vueblog，非 root 的 blog 用户运行；Nginx 独立站点 /etc/nginx/sites-available/vueblog，未覆盖原 default。部署脚本为 bootstrap-native.sh、upload_native.py、install-native.sh；remote.py 通过已知主机和专用密钥执行。

线上基础站点 https://kongqi.xyz、/docs、/admin 与 /api/health 实测成功。生产数据库为空，未导入预览数据，邮件未配置，管理登录不可用。一次性 blog_ci PostgreSQL 测试库执行全部 8 项回归通过（含并发验证码消费），测试库及角色已自动清理；迁移及 alembic check 通过。

Let's Encrypt 证书已签发，有效期至 2027-02-15，HTTPS 配置和 certbot.timer 已启用，续期钩子会校验并重载 Nginx。测试续期已结束且失败：CA 请求 HTTP ACME challenge 收到 403，与公网云平台 Beaver 的 Non-compliance ICP Filing 拦截一致；服务器内部 HTTP 301 正常，不能视为公网跳转或证书自动续期验收通过。现有证书不受本次演练影响。需用户核查域名的阿里云备案/接入备案状态，并在修复后再次运行 certbot renew --dry-run。HTTPS 当时可访问不表示已完成备案或稳定上线。

最新部署目标：kongqi.xyz，公网 IP 101.37.147.237，Ubuntu 24.04，SSH root/22。TCP 连接成功并收到 OpenSSH 9.6p1 Ubuntu banner；尚未登录或修改服务器。用户提供的 /root/.ssh 是 Linux 目录，仍需实际本机私钥路径或明确登录方式。SSH 严格主机检查未通过（本机无已知主机记录），本机 DNS 查询超时，域名解析状态未确认。已将 Nginx 域名和证书路径样例改为 kongqi.xyz。此前“用户尚未租服务器”的记录已由本次信息取代。

用户要求暂时保留现状，等待云效、COS、极验、邮件和飞书账号准备后继续。已停止本次本地前端与后端预览进程。预览使用独立 SQLite `.preview.db`，不代表 PostgreSQL 生产验收；页面、接口、测试账号登录和后台统计在预览期间已实际返回成功。重新预览可在 backend 运行 `.venv\Scripts\python.exe preview.py`，在 frontend 运行 `npm run dev -- --host 127.0.0.1`；启动日志会生成新的一次性测试验证码。

GitHub 仓库 origin 已关联至 https://github.com/a1010635614/Backend-Management-System.git ，尚未提交或推送。用户尚未租服务器，域名与 SSH 信息后续提供。后续顺序：准备真实 PostgreSQL与服务器 → 运行集成测试 → 配置域名与 HTTPS → 配置 COS/邮件/极验/百度统计 → 配置云效和飞书 → 发布与回滚验收。

技术栈采用 Vue 3、Python FastAPI、PostgreSQL。管理后台位于 `/admin`，邮箱登录位于 `/login`。通过 `ADMIN_EMAILS` 设置逗号分隔的管理员邮箱；文章创建、更新、删除、统计查询和 COS 签名上传只允许管理员使用。

已修复 Compose 重复 DATABASE_URL 与 Java JDBC 地址，Python 容器监听 8000，开发代理及 Nginx 对应更新。邮件验证码五分钟过期、一次性使用、同邮箱有效期内拒绝重发、最多尝试五次。数据库使用行锁串行处理同一验证码消费。

已补文章详情页和首页跳转、服务异常提示、Alembic 初始数据库迁移；已清理 DEPLOYMENT.md 的 Java、Swagger 旧路径与占位说明。尚需 PostgreSQL 和真实第三方集成验证。COS 直传尚未以真实桶验证，不能据此视为已上线。

COS 已改用腾讯云原生 SDK cos-python-sdk-v5 1.9.45；离线签名测试检查 HTTPS、桶域名、q-signature、Content-Type 签入和 key 路径隔离。Swagger 改用 HTTP Bearer，可在 Authorize 中填入邮箱登录所得 JWT。增加极验失败不得进入 SMTP 流程的测试。六项后端回归通过。Dockerfile 构建时执行同组回归，但 Docker 本机未运行。

补充 Nginx 认证/事件限流、assets immutable 缓存、API/HTML no-store、ACME challenge 路由和证书续期说明。Nginx/Certbot/CDN 规则仍需在目标服务器验证。

新增 deploy/compose.test.yml 与 test-postgres.sh，在一次性 PostgreSQL 17 的 blog_ci 专库执行迁移、alembic check、业务回归及并发验证码测试；build.sh 在推送镜像前强制执行。测试只接受名为 blog_ci 的 PostgreSQL URL，避免误清生产库。发码流程新增 PostgreSQL 邮箱事务锁，以串行化同邮箱检查和发信。补 SMTP 模拟发信→取码→登录与重发限制测试。当前本地执行 8 项：7 通过、1 PostgreSQL 并发项因缺运行环境跳过；此项不视为通过。新增 Docker 上下文排除规则，前端改用 npm ci 和锁文件。

用户确认域名、服务器和 GitHub 仓库已准备，但尚未提供实际值；云效/COS/极验/邮件/飞书暂未准备。已请求具体域名、SSH Host/端口/用户/本机密钥路径、仓库 URL，等待后可继续目标服务器检查及上线配置。

依赖审计定位三个中等级别问题来自 vue-tsc 旧版的 minimatch 依赖链。已升级 vue-tsc 至 3.3.14，npm 报告 0 vulnerabilities，随后 TypeScript/Vite 生产构建通过。此前“三个漏洞待处理”的记录已被本次结果取代。

新增百度统计匿名访问同意界面、SPA pageview 上报、一方随机访客 PV/UV 采集。新增云效调用的镜像构建脚本、生产 compose、带健康检查及上一镜像回滚的部署脚本、飞书签名通知脚本。云效账号内的代码源触发及通知终态分支仍需真实配置与演练，见 deploy/YUNXIAO.md。

清理 vue-tsc 输出到源码目录的生成 JS，设置 noEmit，重新构建成功（1591 modules）。这些脚本未在云效/服务器实际执行；真实部署尚未完成。

验证：详情页加入后 `npm run build` 通过 TypeScript 检查和 Vite 生产构建（1594 modules）。依赖安装报告三个中等级别漏洞，需后续审计升级。

环境证据：PATH 未找到 Python，但已定位应用自带 Python 3.12，并创建 backend/.venv 安装全部依赖。`python -m unittest discover -s tests -v` 四项测试通过：管理权限及文章 CRUD、验证码错误上限与消费后重放、事件统计、Alembic 新库升级与重复升级。测试使用临时 SQLite，未证明 PostgreSQL 行锁或迁移兼容性。Docker/PostgreSQL 服务尚未找到，真实生产服务未部署。前端依赖安装使用工作区缓存与官方 npm registry。
