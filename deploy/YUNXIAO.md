# GitHub → 云效 Flow → 服务器 → 飞书

这些文件是 Flow 命令步骤调用的脚本，需在你的云效组织创建流水线，不能仅凭仓库文件自动开通云服务。

1. 创建 Flow 流水线，添加 GitHub 代码源，授权仓库，选择 main 分支。开启代码源触发，在 GitHub 设置 Flow 生成的 Webhook，勾选 push，按 main 过滤。参考 [官方代码源触发说明](https://help.aliyun.com/zh/yunxiao/user-guide/code-source-trigger)。
2. 构建任务选择带 Docker Compose v2 的 Linux runner。使用云效凭据进行 ACR 登录，把代码源提交 SHA 映射到 COMMIT_SHA，配置 IMAGE_PREFIX，然后执行 `bash deploy/build.sh`。脚本首先启动隔离 PostgreSQL 17 测试环境，执行迁移、结构一致性检查及接口回归（包含并发验证码单次消费）；失败则停止，不推送镜像。随后前后端 Dockerfile 执行依赖安装和构建。
3. 部署主机安装 Docker Compose v2、curl、flock。将 compose.production.yml 放到专用部署目录，把生产环境配置保存为同目录 .env，DATABASE_URL 指向托管 PostgreSQL；服务器配置 ACR 只读凭据。云效使用主机部署步骤传入 IMAGE_PREFIX、COMMIT_SHA，在该目录执行 release.sh。禁止将 .env 放入构建产物。
4. 在成功和失败两个分支各添加通知步骤（配置失败也执行）：设置 FEISHU_WEBHOOK、FEISHU_SIGNING_SECRET 加密变量，并映射 DEPLOY_ENV、COMMIT_SHA、BRANCH_NAME、SITE_URL、PIPELINE_URL，分别执行 `python3 deploy/notify.py success` 或 `python3 deploy/notify.py failure`。签名遵循[飞书机器人文档](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)。
5. 发布健康检查失败时脚本切回上一镜像标签。数据库变更必须采用兼容前后两个版本的迁移；回滚镜像不会回滚数据库。首次发布没有上一版本时只返回失败，需要修复后重新发布。

验收：向 main 提交代码 → 查看 Flow 的该 SHA 运行实例 → 确认镜像 tag、服务器 .current-release 与 SHA 相同 → 请求站点 /api/health → 在飞书核对最终通知。还需实际故障演练一次回滚与失败通知。

## 当前小内存服务器的原生发布选项

现有服务器运行 Nginx + systemd，后续按原生制品发布接入 Flow。当前方案不需要开通 ACR；上面的 Docker/ACR 方案保留用于以后切换。Flow 构建命令先执行 `export COMMIT_SHA=$(git rev-parse HEAD)`，再执行 `bash deploy/build-native.sh`：runner 执行 PostgreSQL 16 专项回归和前端构建，输出 artifacts 中的 tar.gz、SHA256 校验文件、manifest 和匹配该提交的 release-native.sh；不在服务器执行 Node 构建。构建脚本会拒绝 COMMIT_SHA 与实际检出提交不一致的情况。

在“构建物上传”中选择 artifacts 目录，供后续主机部署下载；仅上传这些构建产物，禁止上传 .env、.local 或整个工作区。主机部署需同时拿到压缩包、校验文件与 release-native.sh，不能假设服务器已有当前仓库的发布脚本。参见[云效构建物管理](https://help.aliyun.com/zh/yunxiao/user-guide/issues-in-building)、[主机部署](https://help.aliyun.com/zh/yunxiao/user-guide/host-deployment-1)。具体主机组与部署任务需在用户的 Flow 组织创建后配置并实际演练。

原生构建首先运行 `python3 deploy/test-native-release.py`。该工具要求 Linux 和 Python 3.12+；以 root 运行时会复制测试源码到临时目录，再通过 runuser/nobody 降权执行。测试模拟 pip、迁移、systemctl 和 HTTP 命令，验证成功切换、失败回退、校验失败、归档路径/链接拒绝与并发锁；不调用真实服务或业务数据库。此控制流程检查不能代替真实主机部署和生产回滚验收。

主机部署步骤把同一提交的压缩包和校验文件上传到 `/opt/vueblog/incoming`（首次需创建该目录），然后执行 `COMMIT_SHA=<同一SHA> bash release-native.sh`。脚本要求已安装 vueblog-backup，发布前备份数据库，校验压缩包、拒绝不安全归档路径，在独立版本虚拟环境安装依赖并执行测试和迁移；切换 current 后检查 API 和站点，失败则恢复上一版本代码及 systemd 服务。数据库不自动降级，迁移必须兼容上一版本。此选项不使用 ACR，后续若选择容器化仍使用原镜像方案。

**当前验证边界**：原生流水线脚本仅作准备，尚未在 Flow 运行，也未在生产执行新版发布/故障回滚演练。服务器上的首次部署仍由 install-native.sh 完成。接入账号后需在测试环境完成流水线与回滚验收，再切换正式发布方式。两种方案只能选定一种用于同一服务，避免相互覆盖。
