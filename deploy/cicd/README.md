# 云效 Flow：双前端与异步后端

此目录是新版 Compose 流水线。2026-11-24 已从原生 `f62dc92` 完成首次正式迁移，首次切流版本为 `63dba62` / schema 0003，独立验证流水线 `1456871` 第 3 次成功。正式 `1456575` 保存下述三项配置后，第 13 次已由 main 提交 `73331b7` 自动触发并完成真实主机部署和公网资源校验；新版飞书送达仍待用户确认。实际运行版本以主机 `.current-release` 及该次流水线记录为准。

## 当前阶段：独立验证流水线

用户已确认正式流水线 1456575 的提交触发只包含 main。另建 `blog-monorepo-validation` 空模板，复用现有 GitHub 服务连接和同一仓库；默认分支为 `codex/production-monorepo`，工作目录 `blog`。验证任务选择杭州、Linux/amd64、开启 Docker Daemon，执行下节的同一构建命令。

验证流水线首先只运行构建/检查，不添加应用部署脚本或飞书通知。接入新机后，为取得这次实际 CI 构建的制品，按下节增加上传与只校验任务；后者只解包、校验源码绑定，不读取生产配置或切换应用。

检查该次 `git log -1` 的完整源码对应提交，成功末尾须包含 `Compose artifact ready for commit ... in artifacts/`，并核对格式 2 manifest。构建验证通过不代表正式发布成功；不要将此前原生运行编号或旧 `Native artifact ready` 记录用于新版验收。

### 独立验证制品上传与新机校验

画布中的白色块是任务，修改名称不会改变任务类型。构建任务（例如“构建验证”）内依次放“执行命令”和“构建物上传”；后续任务“制品校验”使用“主机部署”类型。两个构建任务的工作目录不会因为前后相连就自动共享，因此不要把上传单独放在另一个只下载源码的构建任务中。已有后续任务时先点开：出现“下载路径、执行用户、部署脚本”即可复用；若出现“构建环境、执行命令”，它仍是构建任务，需要另建后续主机任务。不要把新机校验命令填到云端构建容器中，也不要添加为与构建并行的任务。

官方对任务内步骤共享工作空间的定义见 [YAML 初步体验](https://help.aliyun.com/zh/yunxiao/user-guide/yaml-preliminary-experience/)，构建后先上传、再供后续部署任务下载的说明见 [构建物管理常见问题](https://help.aliyun.com/zh/yunxiao/user-guide/issues-in-building)。本项目采用相同任务内构建/上传、跨任务经 Packages 传递制品的安排。

1. 在独立流水线已有构建任务中，将“构建物上传”放在执行命令之后：私有通用仓库 `blog-artifacts`、制品名称 `blog-compose-validation`、版本 `${BUILD_NUMBER}`、打包路径 `artifacts/`，勾选“制品中包含打包路径的目录”。独立名称避免与正式流水线同号运行的制品冲突。
2. 在后续阶段添加名为“制品校验”的“主机部署”任务，仅用它下载和校验文件。主机组必须只含新机 `121.40.113.185`；制品来源选择本次上游上传的 `blog-compose-validation`，不要选择旧版本或正式 `blog-native` 包。
3. 下载路径填写 `/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz`，执行用户 `root`，取消“变量进行编码”。这里的文件名用于兼容元数据解析，不调用原生发布器。
4. 先运行本机 `python deploy/install_flow_verifier.py`，将四个审阅过的公开校验脚本安装到新机 `/usr/local/lib/blog-flow-validation/`；安装器拒绝覆盖不同内容。然后任务脚本仅填写：

   ```sh
   set -eu
   /usr/bin/python3 /usr/local/lib/blog-flow-validation/verify_flow.py
   ```

5. 保存后运行验证分支的最新完整提交。保留构建完成标记，以及该任务输出的 `verified: true`、`format: 2`、匹配的完整提交和下载路径。后续首次切流使用这个真实 CI 制品；本步骤本身没有应用发布、数据库导入、Nginx 切流或通知。

`verify_flow.py` 固定以 `verify_only=True` 调用接收器，不接受部署开关。它使用与正式入口一致的完整提交、流水线/运行编号检查及归档校验。2026-11-24，独立流水线 `1456871` 第 2 次的实际 `63dba62` 格式 2 包已下载到新机并独立校验通过；Flow 主机脚本先前因 `/bin/sh` 不支持 `pipefail` 而失败。兼容写法已在同主机、同包上真实通过，仍需修改云效配置并发起新运行取得整条流水线成功证据。上传目录选项及主机下载步骤可对照官方[制品上传](https://help.aliyun.com/zh/yunxiao/user-guide/upload-general-product-warehouse)和[主机部署](https://help.aliyun.com/zh/yunxiao/user-guide/host-deployment-1)说明。

主机任务实际使用 `/bin/sh`，上述两行脚本没有管道，使用 POSIX `set -eu` 即可。不要在这里填写 Bash 专用的 `set -euo pipefail`；云端“执行命令”构建步骤的 Bash 设置保留不变。

## 构建任务

代码源选择 GitHub `a1010635614/Backend-Management-System`，工作目录 `blog`，默认分支 `main`，开启提交触发。GitHub App 的私钥全文保存在云效证书库中，不放在源码或变量明文中。

使用杭州构建集群、Linux/amd64，开启 Docker Daemon。Flow Docker 服务不支持网络管理，因此本构建不执行 `docker compose`、不创建自定义 Docker 网络；真实 PostgreSQL 和 Redis 测试在单个 Docker 构建步骤内运行。

“执行命令”填写：

```bash
set -euo pipefail
export COMMIT_SHA=$(git rev-parse HEAD)
export PYTHON_BUILD_IMAGE=public.ecr.aws/docker/library/python:3.12-slim-bookworm
export NODE_BUILD_IMAGE=public.ecr.aws/docker/library/node:22-bookworm-slim
export POSTGRES_TEST_IMAGE=public.ecr.aws/docker/library/postgres:16.15-bookworm
export PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
bash deploy/cicd/build.sh
```

`deploy/build-flow.sh` 保留为调用新脚本的兼容入口。新脚本只构建当前完整 Git 提交，拒绝修改过的受跟踪输入和已有 `artifacts/`；Docker 构建上下文来自 `git archive`，不会发送工作区 `.env` 或本机密钥。Python 安装使用完整哈希锁，两个前端使用 `npm ci`。

阶段顺序为部署工具检查 → 临时 PostgreSQL/Redis 迁移和异步接口检查 → 前台测试及构建 → 后台测试及构建 → format 2 制品打包。任一失败即停止，不上传、不发布。当前具体测试数量以该次日志为准。

## 构建物上传

- 选择已有私有通用仓库 `blog-artifacts`。
- 制品名称保留 `blog-native`，版本 `${BUILD_NUMBER}`，这样不必同时改已有下载路径；这个兼容名称不代表新包采用原生部署。
- 打包路径 `artifacts/`，勾选“制品中包含打包路径的目录”。
- 内层仅包含 `manifest.json`、`blog-<完整提交>.tar.gz` 和对应 `.sha256`。
- 新 manifest 必须为 `format: 2`、`stack: compose`，同时匹配本次源码完整 SHA。

## 主机发布

主机组沿用 `blog-production`。主机需要真实 Docker/Compose，不能复用 Flow 的受限 Docker 服务。公网只开放 Nginx 80/443；PostgreSQL/Redis 不映射端口，候选和生产容器网关均只绑定回环。

首次切流已完成，正式主机任务应改用新 `current` 内的版本化接收器，不再调用旧 `/usr/local/sbin/vueblog-flow-deploy`。保持下载路径 `/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz`，取消“变量进行编码”，主机组仅含新 IP `121.40.113.185`。保留现有飞书插件，配置阶段先“仅保存”，主分支源码更新后再由提交触发。

```sh
set -eu
/usr/bin/python3 /opt/blog-fullstack/current/deploy/scripts/flow_host.py
```

`flow_host.py` 从 `CI_COMMIT_SHA_1` 或单一代码源的 `CI_COMMIT_SHA` 获取完整提交；短提交号 `CI_COMMIT_ID`、编码值或两个来源不一致时停止。它只向同一已解析版本目录中的 `receive.py` 传递分离参数，接收器继续验证外层归档、格式 2 manifest、源码 SHA 和已完成切流的 gate；实际发布仍持有部署锁。官方变量范围和编码注意事项见 [环境变量](https://help.aliyun.com/zh/yunxiao/user-guide/environment-variables/) 与 [主机部署问题](https://help.aliyun.com/zh/yunxiao/user-guide/common-issues-in-host-deployment/)。

当前 `current` 已建立、首次导入与流量 gate 均通过，可以配置上述接收入口。正式 Flow 的三项配置保存并核对前，先不推送 main。首次迁移已通过停写备份、导入、0003 升级、数据比较和切流；不能再次运行首次控制器或用 `--initialize-empty` 覆盖现有库。旧 native 工具仅保留作历史恢复材料。

## 环境变量

| 位置 | 变量 | 用途 |
| --- | --- | --- |
| 构建普通变量 | `COMMIT_SHA`、三个 `*_BUILD_IMAGE` / `POSTGRES_TEST_IMAGE`、`PYTHON_PACKAGE_INDEX` | 源码绑定及公开依赖源，无业务密钥 |
| 主机 `shared/runtime.env`，root 0600 | `APP_ENV=production`、`DATABASE_URL`、`REDIS_URL`、`POSTGRES_*`、`REDIS_PASSWORD`、`JWT_SECRET` | 私有数据与会话 |
| 同一主机配置 | `ADMIN_EMAILS`、`ALLOWED_HOSTS`、`CORS_ORIGINS`、`MAIL_*`、`GEETEST_*`、`COS_*`、`CDN_*`、`BAIDU_HM_ID` | 必要业务集成；值只由受控配置工具管理 |
| 云效飞书通知插件 | Webhook、签名密钥 | 成功/失败/取消结果通知 |
| 可选脚本通知的加密变量 | `FEISHU_WEBHOOK`、`FEISHU_SIGNING_SECRET` | 仅在不用插件时配置，避免重复通知 |

构建环境不需要 SMTP、COS、极验或 CDN 密钥。候选环境使用独立测试密码、空第三方配置。未经批准不能把整份生产环境复制到候选环境。

## 通知与验收

沿用已经实际验收的飞书插件，选择成功、失败与取消状态，包含流水线编号、代码提交、环境及网站地址。`deploy/scripts/notify_feishu.sh <success|failure|cancelled>` 是可选替代；`--preview` 只展示消息，不能证明送达。

新版第 13 次已经取得真实 GitHub 提交 → Flow → Packages → 主机 Compose → 正式网页的一致证据；飞书是否收到该次通知仍需用户确认。旧第 12 次通知只证明旧原生版本的送达。

## 生产依赖下载与缓存

云效构建的 `PYTHON_PACKAGE_INDEX` 只作用于云端步骤，不会自动传到生产机。生产 Compose 覆盖文件为 backend/migrate 默认使用 `https://mirrors.aliyun.com/pypi/simple/`，与首次镜像预构建及上述云端命令保持一致。否则默认 PyPI 与镜像源这两个不同的构建参数会使依赖安装层无法复用，表现为生产部署再次逐个下载 wheel。

主机发布器会移除 Runner 环境中的同名变量；需要更换源时，由管理员在主机 `shared/runtime.env` 设置公开的 HTTPS `PYTHON_PACKAGE_INDEX`。只改变构建源，不改变已锁定版本、`--require-hashes` 和 TLS 验证。基础镜像、锁文件和对应构建步骤未变且本机缓存仍在时，后续仅修改业务代码或文章前端的发布可以复用依赖层；不承诺所有部署都零下载。不要在日常流水线执行 `docker builder prune` 或加 `--no-cache`。

Docker 对构建参数和层缓存失效的规则见[官方缓存说明](https://docs.docker.com/build/cache/invalidation/)，包摘要校验见 [pip 安全安装](https://pip.pypa.io/en/stable/topics/secure-installs/)。
