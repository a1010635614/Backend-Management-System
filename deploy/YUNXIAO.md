# GitHub → 云效 Flow → 服务器 → 飞书

这些文件是 Flow 命令步骤调用的脚本，需在你的云效组织创建流水线，不能仅凭仓库文件自动开通云服务。

1. 创建 Flow 流水线，添加 GitHub 代码源，授权仓库，选择 main 分支。开启代码源触发，在 GitHub 设置 Flow 生成的 Webhook，勾选 push，按 main 过滤。参考 [官方代码源触发说明](https://help.aliyun.com/zh/yunxiao/user-guide/code-source-trigger)。
2. 构建任务选择带 Docker Compose v2 的 Linux runner。使用云效凭据进行 ACR 登录，把代码源提交 SHA 映射到 COMMIT_SHA，配置 IMAGE_PREFIX，然后执行 `bash deploy/build.sh`。脚本首先启动隔离 PostgreSQL 17 测试环境，执行迁移、结构一致性检查及接口回归（包含并发验证码单次消费）；失败则停止，不推送镜像。随后前后端 Dockerfile 执行依赖安装和构建。
3. 部署主机安装 Docker Compose v2、curl、flock。将 compose.production.yml 放到专用部署目录，把生产环境配置保存为同目录 .env，DATABASE_URL 指向托管 PostgreSQL；服务器配置 ACR 只读凭据。云效使用主机部署步骤传入 IMAGE_PREFIX、COMMIT_SHA，在该目录执行 release.sh。禁止将 .env 放入构建产物。
4. 在成功和失败两个分支各添加通知步骤（配置失败也执行）：设置 FEISHU_WEBHOOK、FEISHU_SIGNING_SECRET 加密变量，并映射 DEPLOY_ENV、COMMIT_SHA、BRANCH_NAME、SITE_URL、PIPELINE_URL，分别执行 `python3 deploy/notify.py success` 或 `python3 deploy/notify.py failure`。签名遵循[飞书机器人文档](https://open.feishu.cn/document/client-docs/bot-v3/add-custom-bot)。
5. 发布健康检查失败时脚本切回上一镜像标签。数据库变更必须采用兼容前后两个版本的迁移；回滚镜像不会回滚数据库。首次发布没有上一版本时只返回失败，需要修复后重新发布。

验收：向 main 提交代码 → 查看 Flow 的该 SHA 运行实例 → 确认镜像 tag、服务器 .current-release 与 SHA 相同 → 请求站点 /api/health → 在飞书核对最终通知。还需实际故障演练一次回滚与失败通知。

## 当前小内存服务器的原生发布选项

### 构建环境联调

2026-11-18 实际 Flow 命令日志确认：工作目录为代码源的 blog，架构 x86_64；`build-steps/alinux3:latest` 中有 Git、Docker 26.1.3 和 Compose v2.27.0，但没有 Node/npm，Python 为 3.6.8。该环境不能直接执行下面需要 Python 3.12+ 和 Node 的原生构建命令。

后续 Docker 验证在第一条命令即报 `Cannot connect to the Docker daemon at tcp://127.0.0.1:2375`，因此尚未执行 Python/Node 容器，不能认定镜像拉取正常。先在任务设置中查找并启用“开启 Docker Daemon”，保存后发起新运行，再验证：

```bash
set -e
docker version
docker run --rm python:3.12-slim-bookworm python --version
docker run --rm node:22-bookworm-slim node --version
```

成功应包含 Docker 的 Client/Server 信息，以及 Python 3.12.x、Node v22.x。官方说明确认公共构建集群提供“开启 Docker Daemon”开关，参见[构建集群说明](https://help.aliyun.com/zh/yunxiao/user-guide/build-a-cluster/)。开关在当前 Region 站的具体位置仍以用户界面为准。仅启用构建任务的 Docker 服务，不需要开放业务服务器的 2375 端口。

21:57 的后续日志已显示 Docker Server，之前的服务连接问题已解决；随后 Python 镜像拉取在 `https://registry-1.docker.io/v2/` 超时，Node 尚未执行。曾按[官方 Docker Hub 超时排查](https://help.aliyun.com/zh/yunxiao/user-guide/cloud-effect-pipeline-image-construction-and-push-to-image-warehouse)建议切换中国香港集群，但用户确认当前组织没有该选项。保留杭州集群和 Docker Daemon 开关，改为验证 Docker 官方在 ECR Public 发布的镜像：

```bash
set -e
docker run --rm public.ecr.aws/docker/library/python:3.12-slim-bookworm python --version
docker run --rm public.ecr.aws/docker/library/node:22-bookworm-slim node --version
docker run --rm public.ecr.aws/docker/library/postgres:16-alpine postgres --version
```

[Docker 官方说明](https://www.docker.com/blog/news-from-aws-reinvent-docker-official-images-on-amazon-ecr-public/)确认该发布渠道。三个标签的公开 manifest 已在本机网络检查为 HTTP 200，均有 Linux/amd64 平台；随后用户明确反馈在杭州执行上述命令后，Python、Node、PostgreSQL 版本均正常输出。镜像拉取和容器启动已通过，完整构建与发布尚待执行。若今后该渠道不可用，再评估将官方基础镜像同步至用户自己的 ACR。

### 原生制品与发布

现有服务器运行 Nginx + systemd，后续按原生制品发布接入 Flow。当前方案不需要开通 ACR；上面的 Docker/ACR 业务镜像方案保留用于以后切换。先完成前述 Docker/镜像验证，然后让本次运行检出包含 `deploy/build-flow.sh` 的最新 main，在代码源工作目录 blog 下执行：

```bash
set -euo pipefail
export COMMIT_SHA=$(git rev-parse HEAD)
bash deploy/build-flow.sh
```

`build-flow.sh` 只要求任务环境提供 Bash、Git、Docker 和 Compose。它用 Python 3.12 工具镜像执行隔离检查，再执行 PostgreSQL 16 真实集成检查，用 Node 22 容器构建前端，最后输出原生 artifacts 发布包。构建读取指定提交中的跟踪文件，通过 `git archive` 和 `docker cp` 传输，不依赖任务容器与 Docker 服务共享相同宿主机路径，也不挂载密钥或传入生产配置。前端/打包容器必须以状态 exited、退出码 0 完成；构建失败不导出制品。脚本只清理自身创建的临时容器，不清理其他容器或构建缓存。Docker 文件传输语义参见[官方 docker cp 说明](https://docs.docker.com/reference/cli/docker/container/cp/)。

默认基础镜像来自 Docker Hub。支持通过 PYTHON_BUILD_IMAGE、NODE_BUILD_IMAGE、POSTGRES_TEST_IMAGE 配置镜像来源；Python 变量同时传入工具镜像和后端 PostgreSQL 检查镜像，避免部分步骤意外回到默认仓库。三条 ECR 验证全部通过后，可使用：

```bash
set -euo pipefail
export COMMIT_SHA=$(git rev-parse HEAD)
export PYTHON_BUILD_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
export NODE_BUILD_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
export POSTGRES_TEST_IMAGE=public.ecr.aws/docker/library/postgres:16-alpine
bash deploy/build-flow.sh
```

构建包包含 tar.gz、SHA256 校验文件、manifest、匹配该提交的 release-native.sh 和 stage_native_artifact.py；不在业务服务器执行 Node 构建。脚本拒绝 COMMIT_SHA 与实际检出提交不一致、已修改的跟踪构建输入或已存在 artifacts 路径；重跑应使用新的干净工作区。工具镜像在每次 Flow 构建服务中生成，无需发布至 ACR。若 runner 已具备 Python 3.12+、Node 20+ 和 Docker/Compose，仍可使用 `bash deploy/build-native.sh`，两条入口复用同一制品打包模块。

在“构建物上传”中选择 artifacts 目录，勾选“制品中包含打包路径的目录”，归档至云效公共存储空间，供后续主机部署下载；仅上传这些构建产物，禁止上传 .env、.local 或整个工作区。主机部署需同时拿到压缩包、校验文件与 release-native.sh，不能假设服务器已有当前仓库的发布脚本。参见[构建物上传参数](https://help.aliyun.com/zh/yunxiao/user-guide/python-test-build)、[主机部署](https://help.aliyun.com/zh/yunxiao/user-guide/host-deployment-1)。具体主机组与部署任务需在用户的 Flow 组织配置并实际演练。

原生控制流程检查入口为 `python3 deploy/test-native-release.py`，容器入口在工具镜像构建时执行该检查。该工具要求 Linux 和 Python 3.12+；以 root 运行时会复制测试源码到临时目录，再通过 runuser/nobody 降权执行。当前源码的 28 项检查包含真实临时文件打包/校验和外层归档接收，以及用模拟 Git/Docker、pip、迁移、systemctl 和 HTTP 命令检查构建失败停止、成功切换、失败回退、归档路径/链接拒绝与并发锁；不调用真实 Docker 服务、生产服务或业务数据库。此控制流程检查不能代替真实 Flow 构建、主机部署和生产回滚验收。

构建产物同时包含 stage_native_artifact.py，作为主机部署入口。将本次 Flow 运行下载的可信制品解压后，对包含 manifest.json 的 artifacts 目录执行 `python3 <解压目录>/artifacts/stage_native_artifact.py <解压目录>/artifacts`。入口要求完整提交 SHA、准确的归档名称、manifest/校验文件/实际归档的 SHA-256 一致，以及同包内的 release-native.sh；若部署任务传入 COMMIT_SHA，还必须与该次制品一致。失败在复制/发布前停止，校验通过后将归档及校验文件原子放入 `/opt/vueblog/incoming`，调用该包附带的发布脚本。可加 `--verify-only` 仅检查而不复制或部署。该入口只用于可信 Flow 制品，不提供对任意来源脚本的授权保证。

### 已有服务器的接收命令

`python deploy/install_flow_receiver.py` 使用本机既有专用 SSH 连接，安装独立的 `/usr/local/sbin/vueblog-flow-deploy`。安装时校验源码 SHA-256 并执行 `--help`；已有同名文件内容不一致时停止，供人工检查，不覆盖其他工具。此步骤只安装接收命令，实际发布由之后的 Flow 主机任务调用。

接收器 `receive_flow_artifact.py` 在私有临时目录解开 Flow 外层归档，使用 Python 3.12 的 data 过滤并拒绝链接/特殊文件，调用包内匹配版本的 stage_native_artifact.py；结束时清理临时文件。若上传时遗漏“制品中包含打包路径的目录”，会在调用入口前报告路径错误。它只用于来自本次可信 Flow 运行的归档，内容哈希检查不承担验证第三方脚本来源的职责。

在上传步骤中，制品名称可设为 `blog-native`，打包路径为 `artifacts/` 并勾选包含目录。随后添加“主机部署”任务，选择同次运行的该制品与 `blog-production` 主机组，执行用户为 root。下载路径建议使用界面内置的 PIPELINE_ID、BUILD_NUMBER 变量组成 `/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz`，避免不同运行覆盖同一个下载文件；实际变量展开及下载位置需通过首次任务日志确认。

首次主机任务先检查真实下载包：

```bash
set -euo pipefail
: "${PIPELINE_ID:?}" "${BUILD_NUMBER:?}"
/usr/local/sbin/vueblog-flow-deploy \
  "/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz" --verify-only
```

该步骤成功后，将最后的 `--verify-only` 去掉即可进入原生发布。若配置 COMMIT_SHA，使用界面变量选择器映射本次 GitHub 源的完整提交号；不填固定的旧 SHA。不能只将文件下载成功当作部署成功，最终必须核对 `/opt/vueblog/.current-release`、服务健康、实际网站与本次源提交。

发布脚本要求已安装 vueblog-backup，发布前备份数据库，校验压缩包、拒绝不安全归档路径，在独立版本虚拟环境安装依赖并执行测试和迁移；切换 current 后检查 API 和站点，失败则恢复上一版本代码及 systemd 服务。数据库不自动降级，迁移必须兼容上一版本。此选项不使用 ACR，后续若选择容器化仍使用原镜像方案。

**当前验证边界**：原生流水线脚本仅作准备，尚未在 Flow 运行，也未在生产执行新版发布/故障回滚演练。服务器上的首次部署仍由 install-native.sh 完成。接入账号后需在测试环境完成流水线与回滚验收，再切换正式发布方式。两种方案只能选定一种用于同一服务，避免相互覆盖。
