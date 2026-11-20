# 云效 Flow：双前端与异步后端

此目录是新版 Compose 流水线。线上当前仍运行已验收的原生版本 `f62dc92`；先完成候选验收、数据迁移和主机接收器更新，再将新版合入 `main`。仅替换构建命令不能完成迁移。

## 当前阶段：独立验证流水线

用户已确认正式流水线 1456575 的提交触发只包含 main。另建 `blog-monorepo-validation` 空模板，复用现有 GitHub 服务连接和同一仓库；默认分支为 `codex/production-monorepo`，工作目录 `blog`。验证任务选择杭州、Linux/amd64、开启 Docker Daemon，执行下节的同一构建命令。

验证流水线只运行构建/检查，不添加正式主机组、部署脚本或飞书通知。可选上传至私有 `blog-artifacts`，但制品名称使用 `blog-compose-validation`，版本 `${BUILD_NUMBER}`，路径 `artifacts/` 并保留目录。这样验证包不会被误当成既有 `blog-native` 正式包。

检查该次 `git log -1` 的完整源码对应提交，成功末尾须包含 `Compose artifact ready for commit ... in artifacts/`，并核对格式 2 manifest。构建验证通过不代表正式发布成功；不要将此前原生运行编号或旧 `Native artifact ready` 记录用于新版验收。

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

首次切流完成后，主机任务改用新 `current` 内的版本化接收器，不再调用旧 `/usr/local/sbin/vueblog-flow-deploy`。保持下载路径 `/opt/vueblog/flow/${PIPELINE_ID}/${BUILD_NUMBER}/blog-native.tgz`，取消“变量进行编码”。先用 `--inspect` 核对本次完整代码源 SHA、流水线/运行编号和下载路径，再启用实际发布。

```bash
set -euo pipefail
python3 /opt/blog-fullstack/current/deploy/scripts/flow_host.py
```

`flow_host.py` 从 `CI_COMMIT_SHA_1` 或单一代码源的 `CI_COMMIT_SHA` 获取完整提交；短提交号 `CI_COMMIT_ID`、编码值或两个来源不一致时停止。它只向同一已解析版本目录中的 `receive.py` 传递分离参数，接收器继续验证外层归档、格式 2 manifest、源码 SHA 和已完成切流的 gate；实际发布仍持有部署锁。官方变量范围和编码注意事项见 [环境变量](https://help.aliyun.com/zh/yunxiao/user-guide/environment-variables/) 与 [主机部署问题](https://help.aliyun.com/zh/yunxiao/user-guide/common-issues-in-host-deployment/)。

新 `current` 尚未建立时不能提前使用此命令；旧主机步骤继续服务当前原生 main，待维护窗口完成后再替换。首次迁移必须先备份、停止旧写入、导入新库、执行 0003、核对数据及切流，不得用 `--initialize-empty` 代替。旧 native 维护脚本仅保留作历史恢复材料，不得再用于新数据库或新制品。

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

新版尚需真实 GitHub 提交 → Flow → Packages → 主机 Compose → 正式网页 → 飞书验收。旧第 12 次成功记录只证明旧原生版本的链路。
