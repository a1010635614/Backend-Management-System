# 实施与验证记录

## 当前交接状态

### 2026-11-18 继续准备

#### 原生发布控制流程检查与 Flow 页面进展

新增 test_native_release.py、test-native-release.py 与 verify-native-release.py。已在服务器独立验证目录运行，以 nobody 用户在临时目录执行 8 项检查，全部通过：成功切换、API/站点/重启失败恢复代码与 unit、后续版本失败退回前一个原生版本、依赖/测试/迁移/备份失败前置停止、校验和失败、路径穿越、软/硬链接拒绝、并发锁。外部 runtime/systemctl/HTTP 命令均为替身，没有调用真实业务服务、生产环境文件或数据库；此结果仅证明受测 shell 控制流程，不等同于生产故障回滚演练。

build-native.sh 已加入该控制流程检查作为构建前置门槛，要求 Linux/Python 3.12+，root 运行会通过 runuser/nobody 降权。真实 Flow runner 的环境、主机部署、提交触发和完整通知仍需实际验收。

用户截图已证明成功进入 Region 站工作台，随后进入“流水线 Flow / 我的流水线”，当前列表为空。已指引从右上角“新建流水线”选择空模板，再添加 GitHub 代码源；尚无实际流水线 ID、服务连接或运行实例，不能记录为自动部署已完成。

#### 飞书机器人真实通知验收通过，准备云效

GitHub 最新核对与同步：本机曾暂时无法解析 github.com；随后系统 DNS 和 HTTPS 检查恢复，使用原有账号正常快进推送 main，从 d7bc812 到 fc08a26ff5a6f44d6e6bd4aa27e27cbc05862405，远程 SHA 已独立复核一致。同步包含 COS、极验、百度及飞书相关源码/工具和文档，不含凭据。此为该次同步的确定记录，后续文档更新或提交以实时 Git 状态为准。

用户反馈“正在创建组织或开通 Flow”，尚未提供已进入流水线列表或实际配置完成的信息。待其完成组织开通后，继续配置 GitHub 代码源、主机组、制品部署和加密通知变量；当前未创建真实 Flow 运行实例，也未验证提交触发自动部署。

随后用户提供云效标准版实例管理截图：Kongqi-Agent项目开发组织已存在，地域为华东1（杭州），个人使用模式，状态“使用中”。组织创建已有界面证据，尚未进入组织内部的 Flow 列表。已指引点击蓝色组织名进入工作台，再打开“流水线 Flow”；后续服务连接应按其实际 Region 站页面操作，不套用未经核对的中心站授权步骤。

用户确认机器人准备好后，启动 configure_feishu.py（session 31319）。用户在本机遮罩窗口输入群备注、Webhook 和签名密钥，并在完整正文预览中确认发送；工具仅尝试发送一条“机器人接入验证 / 配置测试”通知，飞书返回成功，进程 exit 0。用户随后明确反馈“正确的群已收到”，机器人签名、发送与目标群收取验收通过。

Webhook/签名密钥未写入本机文件、源码或服务器环境；工具退出后不再持有凭据。后续应由用户填入云效 FEISHU_WEBHOOK、FEISHU_SIGNING_SECRET 加密变量。此单条测试不代表 GitHub→Flow→部署→飞书的自动链路已经验收。

新增 configure_feishu.py 以及通知函数测试；notify.py 增加仅正文预览、精确 HTTPS Webhook 地址校验、禁止重定向、HTTP/API 结果检查、固定安全错误和缺少签名配置时拒绝发送。测试覆盖取消不得发信、确认后单条发送、预览与正文一致、协议签名已知值、API 拒绝及凭据不泄露。部署目录共 16 项自动化检查通过，真实发送仅在用户确认后执行。

原生构建脚本要求 COMMIT_SHA 与实际检出的完整提交一致，并把对应 release-native.sh 一起放入 artifacts，补上后续主机部署需要的脚本。尚未在 Flow 执行该构建与发布，不能把准备状态当作流水线验收。

已请求用户进入云效组织与流水线 Flow，等待页面状态，以便配置真实 GitHub 代码源、构建制品、主机部署和通知变量。当前原生方案不使用 ACR，容器方案保留。云效触发与完整发布通知、CDN、异地备份、故障回滚、备案和证书续期仍未验收。

#### 百度统计真实域名 PV/UV 验收通过

用户在本机完整刷新后仍未看到百度报告数据，随后按请求访问 https://kongqi.xyz/、同意统计并浏览文章，明确反馈“已有访问记录或 PV/UV”。当前百度统计真实站点收集验收通过；本机 127.0.0.1 的无数据反馈保留为联调历史，不再作为真实域名链路的阻塞。没有据此断言本机无数据的唯一根因是域名限制或数据延迟。

邮件验证码登录、极验 4.0、COS 图片/PDF 和百度真实域名统计均已获得实际用户成功反馈。下一步飞书机器人与云效流水线：用户确认飞书自定义机器人尚未创建，需要操作步骤。尚未收集 Webhook/签名密钥，也未发送测试消息；需先展示具体测试通知并获得确认，再执行真实发送。云效触发、自动发布、飞书最终通知、CDN、异地备份、真实发布回滚及完整域名上线仍未验收，目标保持未完成。

#### 百度统计排查历史（当前验收结果以上方为准）

用户反馈站点约五分钟前创建，首页代码状态“无法完成检查”，并提供了与当前配置完全一致的 hm.src 地址。根据官方首页状态说明，该提示表示百度服务器未能正常访问网站，不能直接等同于代码安装错误；新建设置一般约二十分钟生效也只是可能原因，未据此断言空脚本根因。2026-11-18T11:44:58Z 的对照检查中，同一网络获取百度官网/极验官网使用的 hm.js 分别为 66002/30304 字节，本项目仍为 0 字节，缩小到当前站点配置侧。

2026-11-18T11:49:57Z 再次检查，本项目 hm.js 已返回 HTTP 200、application/javascript、解压后 29896 字节，空脚本状态已被新证据取代。用户随后反馈本机刷新仍无数据，但真实域名出现记录，最新验收结论见上方。该次只读检查公网 HTTPS 主页 200，HTTP 502；未据此认定备案或完整公网发布已完成。

只读数据库核对：UTC 当日一方 PV=30、UV=5，最近 15 分钟 PV=12、UV=4，说明已有用户访问进入本站数据库；这些计数不能代替百度报告验收。新增 check-analytics-progress.sh 仅输出聚合结果，不发送埋点。

原生发布脚本的 API/HTTPS 健康探测补充连接及总超时，避免请求悬挂而迟迟无法进入失败回退。全部 20 个部署 Bash 脚本通过 bash -n，未执行实际 Flow 发布和回滚，不以脚本语法检查代替完整验收。

用户已提供公开 hm.js 跟踪 ID，configure_baidu.py 进程 session 60804 以 exit 0 结束：仅 BAIDU_HM_ID 被更新，服务健康与 /api/public/config 匹配检查通过。已请求用户通过新的无痕窗口同意匿名统计、浏览首页和文章，并在其百度统计账号核对实时访客或今日 PV/UV；目前等待反馈。配置成功不证明百度后台已经采集到访问数据，不能标记整项完成。

早期只读脚本检查曾发现：本机（默认请求、本机来源和 kongqi.xyz 来源）及服务器网络请求 https://hm.baidu.com/hm.js?<用户提供的ID> 均返回 HTTP 200、0 字节、text/plain。新增 verify-baidu.sh 仅获取公开配置及脚本，不发送浏览埋点；空脚本时明确失败。此空响应现象为历史，当前脚本可用性和报告待验收状态见上方最新记录。

本地已保存提交 e9fe56c（COS/极验验收与百度配置工具），尚未推送；其后的空脚本诊断脚本及本段记录尚在工作区。远程 main 最近核对仍为 d7bc812，未在本轮重新获取远程状态。

#### 极验 4.0 真实登录验收通过

用户通过 Blog GeeTest configuration 遮罩窗口输入 ID/Key，配置进程 session 31553 已以 exit 0 结束。服务器 GEETEST_ID/GEETEST_KEY 已配置，API 健康与公开 captcha ID 匹配检查通过。随后用户明确反馈“极验通过，收到邮件并登录成功”，当前本机预览使用真实服务器后端的极验→邮件→后台登录流程验收通过。凭据未写入本机文件、日志、命令参数或 Git。仅配置/健康检查时的待验收状态已被实际登录反馈取代。

新增 configure_geetest.py / configure_geetest_remote.py：本机遮罩输入、严格 SSH 连接、32 位输入检查、只更新极验字段、原子配置写入、重启及健康/ID 核对，失败恢复原配置。5 项极验配置测试通过，连同原邮件配置测试共 7 项通过。尚未在真实凭据配置中制造故障以验证回退，只能按自动化覆盖范围描述。

后端二次校验新增非 200 状态及非对象 JSON 拒绝、空验证参数检查、只向极验转发四项必要证明与服务器签名；部分配置也会阻止发码。模拟完整极验→邮件验证码→登录、异常响应不得发送邮件的回归已通过。最新服务器独立 PostgreSQL 测试库的 14 项回归全部通过，迁移一致性检查通过；随后通过正常原生发布安装校验修正，HTTPS/API 健康和三个服务状态通过。

本次发布前备份 blog-20261118T112858Z.dump 已在独立临时库恢复并自动清理，schema 0002；恢复文章 2、用户 1、事件 28、验证码记录 2、附件 2，生产数据未改。备份恢复脚本补充 assets 表检查。异地备份仍未准备。

新增 BAIDU-SETUP.md、configure_baidu.py / configure_baidu_remote.py，仅更新 BAIDU_HM_ID，核对公开配置并在失败时恢复环境。百度配置的字段保留/回退和错误 ID 测试通过；连同极验与邮件共 9 项配置测试通过。用户随后已提供真实 ID 并安装成功，当前报告验收状态见上方最新记录，不能把一方统计代替百度接入完成。

#### 最新验收与下一步

COS 图片/PDF 端到端验收通过。用户明确反馈“图片和 PDF 都上传成功且能打开”；随后只读核对数据库：ready image/png 1、ready application/pdf 1，文章关联附件也分别为 1。CORS 对 content-type、content-length 的 PUT 预请求已返回 200 并允许相应请求头。此前尚未配置密钥、AccessDenied、CORS 未就绪和未收到浏览器验收的记录均为下方联调历史，不代表当前状态。

真实私有桶上传、HEAD 元数据、短时签名下载和匿名读取拒绝已通过；凭据仅保存在服务器。邮件收码与管理员登录此前亦已实际验收。COS 验收范围为当前私有预览 Origin 的图片/PDF 上传、文章保存和附件打开；CDN、STS、内容扫描和生产网站 Origin 的跨域配置仍未验收。

极验账号准备指引见 deploy/GEETEST-SETUP.md；用户最初尚未创建，随后已准备并配置，当前状态以上方最新记录为准。百度统计、云效、ACR、飞书、CDN、异地备份及真实发布回滚仍需准备和联调。ICP 按用户要求暂缓，证书续期演练此前失败，完整上线目标继续保持未完成。

Git 最近核对：本地提交 33f7ab8，远程 main 最近已验证提交为 d7bc812；本轮验收记录和 COS 诊断改动仍在工作区，尚未推送。服务保持运行。

#### COS 私有附件进展

##### COS 联调历史（当前状态以上方最新验收为准）

用户保存 CORS 后，OPTIONS（Origin http://127.0.0.1:5173，请求方法 PUT，请求头 content-type）实测 200，Allow-Origin 精确匹配且 PUT/GET/HEAD 已允许。响应 Allow-Headers 为 content-type,`content-length`，第二项仍带反引号，已提醒用户改为纯文本 Content-Length；不能把完整规则清理视为已完成。已启动本机 Vite session 32564（5173）及 SSH 隧道 session 84342（8000），供用户在真实服务器环境进行浏览器图片/PDF 上传、保存文章与展示验收。后续需以实际端口/进程复核；当前尚未收到页面上传成功反馈。

用户明确说明此前上海策略没有保存，随后提供已保存的正确 ap-shanghai/uploads/* 资源。重新配置进程 session 53172 已以 exit 0 结束：真实 COS PutObject、HEAD 元数据、短时签名下载、无签名读取403全部通过；SecretId/SecretKey 已原子保存到服务器，服务重启和 API 健康检查通过。此前“未配置凭据/AccessDenied未解决”的记录已被本次成功结果取代，现不需要重新索取密钥。

目前唯一已明确的 COS 浏览器阻塞是 CORS：用户要求了详细控制台指引，已提供；最新 OPTIONS 复测仍返回403/AccessForbidden且没有 Access-Control 响应头。待用户在 COS 控制台保存来源 http://127.0.0.1:5173 的 PUT/GET/HEAD 规则后复测。测试对象 uploads/verification/090f23e3a979b5e654bdb53ae4e9696d.png 保持私有供检查。浏览器上传、文章附件展示尚未验收，不可把整个 COS 功能标记完成。本机 5173/8000 当前无监听，待 CORS 通过后再启动私有预览和隧道。

新的 COS 配置进程 session 31688 已终止：三次尝试均在 PutObject 返回 status 403/code AccessDenied，没有保存凭据或改动业务配置。用户此前确认策略已关联，但最近提供的可见策略资源仍为 ap-guangzhou；尚未获得保存后的上海策略资源证据。已请求只提供当前已保存的 resource 字符串（不要密钥）。匿名 HEAD 上海端点403、广州端点404，与上海桶信息一致；不能据此证明身份策略已正确生效。下一步先核对实际生效地域/资源与密钥所属子用户，避免盲目重复输入。诊断程序现在只输出安全错误码及经过字符限制的 RequestId，不输出凭据或签名 URL。

首次真实 COS 配置尝试在 PutObject 阶段返回 403，服务器凭据未改动。用户随后提供其 CAM 策略，资源地域为 ap-guangzhou，而真实桶为 ap-shanghai；已明确指出此资源范围不匹配，要求在腾讯云将策略改为上海地域。建议使用仓库 cos-policy.json 的 uploads/* 范围和 PutObject/HeadObject/GetObject/OptionsObject。新的配置进程已打开遮罩输入窗口（exec session 31688，状态以实际进程为准），增强了安全错误码输出与内存凭据重试，等待用户保存正确策略并输入；不能视为 COS 已接通。

最小权限准备已具体化为 deploy/cos-policy.json：目标桶 uploads/* 的 PutObject、HeadObject、GetObject、OptionsObject。根据腾讯云当前 API 授权文档，HEAD 与 OPTIONS 有独立 action，已显式列出，避免遗漏权限导致后续确认失败。新增 cos-cors.json（Python SDK 配置格式）与 COS-SETUP.md，说明在控制台配置精确本机 Origin 与请求头，且不需要为应用账号授予修改桶权限。JSON 语法及目标资源范围已检查通过；真正的 CAM 策略关联和 CORS 设置仍需用户在腾讯云执行。当前继续等待受限子账号密钥准备情况，尚未启动 COS 密钥输入窗口或运行真实验证。

用户已提供桶 kongqi-agent-1317119844、地域 ap-shanghai，密钥尚待通过本机窗口配置。新增 assets 数据表及 0002 迁移：上传签名绑定类型和长度、10MiB 上限、HEAD 核对与确认、附件所有者检查；只有被文章引用的已确认附件，才通过 /api/media/{id} 发放短时 GET 签名。Vue 写作和详情页支持图片/PDF 附件标记及展示。文章删除后媒体入口关闭，已发出的 URL 在有效期后失效。未加入 STS 或 CDN 鉴权，内容字节安全扫描仍非已实现功能。

本地 12 项测试 11 通过、1 PostgreSQL 项跳过；新代码上传独立 verification 目录后，在真实 PostgreSQL 隔离库全部 12 项通过，迁移与结构一致性检查通过。随后已部署附件适配及 0002 到生产，复核 assets 表存在、原管理员用户保留、HTTPS health 为 UP；原邮件配置和 JWT 未替换。真实 COS 上传/下载与 CORS 尚未验收，因此不可标记 COS 接入完成。

新增 configure_cos.py / configure_cos_remote.py：通过两项遮罩输入收集子账号凭据，验证该桶上传、HEAD、签名下载及非签名读取被拒绝，写入服务器环境并检查服务健康，检测浏览器 CORS。仅在 uploads/verification/ 留一个小私有测试对象供检查，不删除用户原文件。已完成 Python 语法与 SDK 参数检查，尚未运行真实凭据配置；等待用户确认密钥准备情况。上述附件更新尚未提交/推送到 GitHub（远程仍为已批准的 d7bc812）。

GitHub 最新进展：用户明确批准推送提交 d7bc812 到 main。首次推送因本机缓存账号 a1010635614-sketch 无写入权限被拒绝；随后用户通过浏览器为 a1010635614 完成 GCM 授权。使用指定账号正常推送，无强制覆盖；远程 main 已核对为 d7bc812464fea17c285bc4a7701e154f6580fb71，本地 main 已跟踪 origin/main。此段是推送完成后的本地交接记录，尚未包含在该提交中。云效尚未开通/连接，代码推送不代表流水线部署验收完成。

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
