# GitHub → 云效 Flow → 服务器 → 飞书

这些文件是 Flow 命令步骤调用的脚本，需在你的云效组织创建流水线，不能仅凭仓库文件自动开通云服务。以下前五步为保留的 Docker/ACR 容器化方案，要求 runner 支持 Compose；当前小内存服务器采用后文的原生制品方案。

1. 创建 Flow 流水线，添加 GitHub 代码源，授权仓库，选择 main 分支。先完成手动构建和发布验收，再开启代码源触发，在 GitHub 设置 Flow 生成的 Webhook，勾选 push，按 main 过滤。参考 [官方代码源触发说明](https://help.aliyun.com/zh/yunxiao/user-guide/code-source-trigger)。
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

实际旧版 Flow 运行在后端镜像导出后返回 `flow not support`，清理阶段明确报 `failed to list networks`。镜像构建期间的 14 项检查带 skipped=1，不代表 PostgreSQL 集成已运行。针对该环境，新版 build-flow.sh 不调用 Compose、Docker 网络管理、容器复制或检查接口，只使用已验证可用的 info/build/run。

新版只要求任务环境有 Bash、Git、Docker 和 tar。Dockerfile.flow-build 使用多阶段构建：在同为 Debian bookworm 的 PostgreSQL 16 与 Python 3.12 官方运行时中启动独立临时数据库，执行迁移、结构检查和全部后端检查，要求零跳过；接着由 Node 22 构建前端，再用共享模块打包并校验原生制品。前端阶段依赖后端实际检查完成，未通过则无法构建最终导出镜像。多阶段机制参见[Docker 官方说明](https://docs.docker.com/build/building/multi-stage/)。

第 6 次 Flow 运行已实际检出 3ee905c，三个基础镜像完成拉取，随后在 Debian 官方源的 bookworm 软件包索引下载阶段多次重试，最终恢复并于 2026-11-19 00:11:41 完成完整构建。后续版本仅在 Flow 检查镜像内，将 Debian 主源及安全更新源改为阿里云公开 HTTPS 镜像，并设置连接及数据传输超时 30 秒、重试两次；保留 Debian 签名和 HTTPS 证书校验。此设置不修改业务服务器的软件源，不会改变已开始的运行。镜像地址参见[阿里云 Debian 镜像](https://developer.aliyun.com/mirror/debian)。新镜像源的实际速度仍待之后的 Flow 运行验证。

源码从指定提交通过 git archive 传给构建，不挂载工作区或传入生产配置。完成后运行本地制品镜像，将 tar 输出直接解到新的私有临时目录；导出进程退出码、解压或必需文件检查有任一失败则清理本次临时目录，成功才移动为 artifacts。临时 PostgreSQL 只监听回环地址，使用全新数据目录和随机端口，结束时停止并清理；不依赖跨容器网络。

默认基础镜像来自 Docker Hub。支持通过 PYTHON_BUILD_IMAGE、NODE_BUILD_IMAGE、POSTGRES_TEST_IMAGE 配置来源。新版 PostgreSQL 必须使用 16-bookworm，与 Python 的 bookworm 运行时一致；旧的 16-alpine 配置会在构建前明确报错。ECR 的 16-bookworm 标签已确认有 Linux/amd64 manifest，实际组合镜像仍待云效验证。当前命令为：

```bash
set -euo pipefail
export COMMIT_SHA=$(git rev-parse HEAD)
export PYTHON_BUILD_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
export NODE_BUILD_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
export POSTGRES_TEST_IMAGE=public.ecr.aws/docker/library/postgres:16-bookworm
export PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
bash deploy/build-flow.sh
```

构建包包含 tar.gz、SHA256 校验文件、manifest、匹配该提交的 release-native.sh 和 stage_native_artifact.py；不在业务服务器执行 Node 构建。脚本拒绝 COMMIT_SHA 与实际检出提交不一致、已修改的跟踪构建输入或已存在 artifacts 路径；重跑应使用新的干净工作区。导出镜像只在构建环境使用，无需发布至 ACR。若 runner 已具备 Python 3.12+、Node 20+ 和完整 Docker/Compose，仍可使用 `bash deploy/build-native.sh`，两条入口复用同一制品打包模块。

当前 Region 站实际显示的“构建物上传”表单使用 Packages 通用制品仓库，包含服务连接、仓库、制品名称、制品版本与打包路径，没有显示上传方式切换项。先在同一组织的“制品仓库 Packages → 新建制品仓库”创建私有的通用制品仓库 `blog-artifacts`，再回到上传步骤选择该仓库；创建仓库时保留尚未保存的流水线编辑页。用户截图已确认，仓库地址左侧为云效固定前缀，右侧可编辑部分与仓库名称均填写 `blog-artifacts`，模式保留支持存储的 Hybrid 综合模式。仓库类型须为“通用制品”，GitHub 代码仓库与 ACR 镜像仓库不能代替它。已有的 Packages 服务连接可选择到该仓库时直接使用，无须另建凭据。参见[新建制品仓库](https://help.aliyun.com/zh/yunxiao/user-guide/create-repositories)。

上传步骤的制品名称设为 `blog-native`，版本保留 `${BUILD_NUMBER}`，打包路径填 `artifacts/`，勾选“制品中包含打包路径的目录”。这会保留主机接收器要求的 `artifacts/` 目录层级；仅上传这些构建产物，禁止上传 .env、.local 或整个工作区。制品版本不能重复，后续主机任务必须引用同次运行上传的准确版本，不能选择不确定的“最新版本”。主机部署需同时拿到压缩包、校验文件与 release-native.sh，不能假设服务器已有当前仓库的发布脚本。参见[构建物上传参数](https://help.aliyun.com/zh/yunxiao/user-guide/upload-general-product-warehouse)、[主机部署](https://help.aliyun.com/zh/yunxiao/user-guide/host-deployment-1)。具体仓库、主机组与部署任务仍需在用户的 Flow 组织配置并实际演练。

原生控制流程检查入口为 `python3 deploy/test-native-release.py`，新版容器在后端检查阶段执行。该工具要求 Linux 和 Python 3.12+；以 root 运行时复制测试源码到临时目录，再通过 runuser/nobody 降权执行。当前源码的 29 项检查包含真实临时文件打包/校验和外层归档接收，以及用模拟 Git/Docker、pip、迁移、systemctl 和 HTTP 命令检查构建失败停止、成功切换、失败回退、归档路径/链接拒绝与并发锁。模拟 Docker 客户端拒绝 Compose/network/create/cp/inspect 等操作，检查新的宿主导出流程不会依赖它们。此控制流程检查不调用真实 Docker 或业务数据库，不能代替真实 Flow 构建、主机部署和生产回滚验收。

数据库脚本可通过 `python deploy/verify-flow-postgres.py` 单独检查：先检查服务器内存余量，再用新的数据目录/随机端口运行临时 PostgreSQL 16 及上传的测试源码。已实测版本 160015，14 项接口/迁移检查通过且零跳过；不使用线上数据库，也不切换 current。该结果证明脚本逻辑，不能代替 Flow 中新的组合镜像构建。

构建产物同时包含 stage_native_artifact.py，作为主机部署入口。将本次 Flow 运行下载的可信制品解压后，对包含 manifest.json 的 artifacts 目录执行 `python3 <解压目录>/artifacts/stage_native_artifact.py <解压目录>/artifacts`。入口要求完整提交 SHA、准确的归档名称、manifest/校验文件/实际归档的 SHA-256 一致，以及同包内的 release-native.sh；若部署任务传入 COMMIT_SHA，还必须与该次制品一致。失败在复制/发布前停止，校验通过后将归档及校验文件原子放入 `/opt/vueblog/incoming`，调用该包附带的发布脚本。可加 `--verify-only` 仅检查而不复制或部署。该入口只用于可信 Flow 制品，不提供对任意来源脚本的授权保证。

### 已有服务器的接收命令

`python deploy/install_flow_receiver.py` 使用本机既有专用 SSH 连接，安装独立的 `/usr/local/sbin/vueblog-flow-deploy`。安装时校验源码 SHA-256 并执行 `--help`；已有同名文件内容不一致时停止，供人工检查，不覆盖其他工具。此步骤只安装接收命令，实际发布由之后的 Flow 主机任务调用。

接收器 `receive_flow_artifact.py` 在私有临时目录解开 Flow 外层归档，使用 Python 3.12 的 data 过滤并拒绝链接/特殊文件，调用包内匹配版本的 stage_native_artifact.py；结束时清理临时文件。若上传时遗漏“制品中包含打包路径的目录”，会在调用入口前报告路径错误。它只用于来自本次可信 Flow 运行的归档，内容哈希检查不承担验证第三方脚本来源的职责。

在上传步骤中，制品名称可设为 `blog-native`，打包路径为 `artifacts/` 并勾选包含目录。随后添加“主机部署”任务，选择同次运行的该制品与 `blog-production` 主机组，执行用户为 root。下载路径建议使用界面内置的 PIPELINE_ID、BUILD_NUMBER 变量组成 `/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz`，避免不同运行覆盖同一个下载文件；实际变量展开及下载位置需通过首次任务日志确认。

Python 包下载可通过 PYTHON_PACKAGE_INDEX 选择公开 HTTPS 包源，默认仍为 https://pypi.org/simple。该变量传入后端测试镜像构建，也由原生 release-native.sh 接收；可配置为 `https://mirrors.aliyun.com/pypi/simple/`。当前日志中 SQLAlchemy 的 3.2MB 下载速度仅 12.7kB/s，本机从阿里云官方镜像成功下载同一 Linux wheel，尚未在当前云效运行中验证镜像速度。此设置供下一次检出新脚本的运行使用，不会修改当前已经启动的 pip 进程。包源说明见[阿里云 PyPI 镜像](https://developer.aliyun.com/mirror/pypi)，参数见[pip install](https://pip.pypa.io/en/stable/cli/pip_install/)。使用 HTTPS 并保留证书校验，不添加 trusted-host。

首次主机任务先检查真实下载包：

```bash
set -euo pipefail
: "${PIPELINE_ID:?}" "${BUILD_NUMBER:?}"
export PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
/usr/local/sbin/vueblog-flow-deploy \
  "/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz" --verify-only
```

该步骤成功后，将最后的 `--verify-only` 去掉即可进入原生发布。若配置 COMMIT_SHA，使用界面变量选择器映射本次 GitHub 源的完整提交号；不填固定的旧 SHA。不能只将文件下载成功当作部署成功，最终必须核对 `/opt/vueblog/.current-release`、服务健康、实际网站与本次源提交。

发布脚本要求已安装 vueblog-backup，发布前备份数据库，校验压缩包、拒绝不安全归档路径，在独立版本虚拟环境安装依赖并执行测试和迁移；切换 current 后检查 API 和站点，失败则恢复上一版本代码及 systemd 服务。数据库不自动降级，迁移必须兼容上一版本。此选项不使用 ACR，后续若选择容器化仍使用原镜像方案。

**当前验证边界**：旧版 Flow 曾因 Compose 网络接口被拒绝而失败。新版在真实 Flow 第 6 次运行（源码 3ee905c）已完成 29 项发布控制/制品检查、真实临时 PostgreSQL 16.16 的 14 项业务检查（零跳过）、Vue 类型检查及生产构建、制品打包/校验/导出，执行命令步骤明确 SUCCESS。Packages 上传、主机发布、真实故障回滚、飞书终态通知与 GitHub 提交触发仍待实际验收；后续 Debian 镜像源调整也尚未在 Flow 验证。服务器上的首次部署仍由 install-native.sh 完成。两种发布方案只能选定一种用于同一服务，避免相互覆盖。
