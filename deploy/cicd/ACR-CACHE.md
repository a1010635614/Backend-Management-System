# 杭州 ACR 基础镜像缓存

## 已完成与待验收

2026-11-24，Python、Node、PostgreSQL 三个官方 `linux/amd64` 镜像已同步至本账号杭州 ACR 的三个私有仓库，远端 manifest 摘要逐一与官方源一致。同步使用受限临时 Docker 配置，结束后已删除；仓库固定密码和短期令牌没有写入源码或回执。公开清单为 [acr-images.json](acr-images.json)，流水线变量为 [acr-images.sh](acr-images.sh)。

这次优化针对 Flow 云端构建拉取海外基础镜像卡住的问题。生产主机 pip 缓存已有独立验收：第13次约938.6秒，第14次约57.2秒。ACR 同步成功不能代替云效登录、拉取、测试、制品及生产部署验收；改动后的完整流水线和下载耗时仍待验证。

ACR 个人版用于本项目 CI 开发测试镜像缓存。阿里云说明个人版不提供 SLA，见[个人版实例](https://help.aliyun.com/zh/acr/user-guide/create-a-container-registry-personal-edition-instance/)。生产发布继续通过 Packages 传递经过检查的应用制品，生产主机的镜像配置另由受控环境管理。

## 1. 在正式构建任务中添加 Docker Login

打开正式流水线 `1456575`，编辑第一个构建任务。保持杭州、Linux/amd64、开启 Docker Daemon；在同一任务内，将步骤排列为：

1. `Docker Login`。
2. `执行命令`。
3. 原有 `构建物上传`。

后续生产部署、Packages 版本和飞书插件沿用已有配置。不要另建并行登录任务：任务之间不共享登录工作区。构建环境的“使用私有镜像仓库”用于任务容器镜像，与本步骤登录 Dockerfile 的 `FROM` 仓库用途不同。

Docker Login 中填写：

| 字段 | 值 |
| --- | --- |
| 镜像仓库地址 | `crpi-fdci37tiun8k5nzb.cn-hangzhou.personal.cr.aliyuncs.com` |
| 服务连接名称 | 例如 `blog-acr-hangzhou` |
| 仓库登录名 | 从 ACR“访问凭证”的 `docker login --username` 原样复制 |
| 密码 | 该实例的 Registry 固定密码，通过云效服务连接/证书表单手动保存 |
| 使用范围 | 私密，或仅授权运行该流水线的必要成员 |

仓库地址不加 `https://`、命名空间或镜像名称。用户名不是实例 ID；主账号与 RAM 用户的登录名规则见[官方登录说明](https://help.aliyun.com/zh/acr/user-guide/use-a-container-registry-personal-edition-instance-to-push-and-pull-images)。本步骤不使用用于 DNS 的 AccessKey。

云效官方说明空任务可添加 `Docker Login`，使用私有镜像仓库服务连接完成认证，见[自定义镜像仓库](https://help.aliyun.com/zh/yunxiao/user-guide/build-and-push-custom-image-repositories)。若页面入口或字段不同，先核对截图，不将密码粘贴到命令编辑器或聊天。

## 2. 替换构建命令中的基础镜像来源

在同一个任务中，将原来的三个 `public.ecr.aws` 镜像变量替换为公开清单的加载命令。完整命令：

```bash
set -euo pipefail
export COMMIT_SHA=$(git rev-parse HEAD)
source deploy/cicd/acr-images.sh
export PYTHON_PACKAGE_INDEX=https://mirrors.aliyun.com/pypi/simple/
bash deploy/cicd/build.sh
```

三个引用均锁定 `@sha256`，不会随同名标签更新。Python、Node、PostgreSQL 版本分别为 `3.12-slim-bookworm`、`22-bookworm-slim`、`16.15-bookworm`。保留哈希锁、TLS 验证和所有现有测试，不增加 `--no-cache` 或清理构建缓存。

配置阶段先“仅保存”。确认包含 `acr-images.sh` 的源码已经准备推送后，再让提交触发一次完整运行；不要对仍缺少该文件的旧提交点“保存并运行”。

## 3. 完整运行的验收顺序

1. Docker Login 成功，不输出明文凭据。
2. 构建日志的三个基础镜像地址均来自本杭州 ACR，摘要与公开清单一致；记录该阶段实际耗时。
3. 部署工具、真实临时 PostgreSQL/Redis、双前端测试与构建全部通过，末尾包含本次完整提交的 `Compose artifact ready`。
4. Packages 上传、主机接收器的完整提交校验与生产冒烟检查通过，`.current-release` 与本次提交一致。
5. 飞书通知的运行编号、状态和提交正确。不能只凭 Docker Login 成功宣布加速验收完成。

若出现 `unauthorized`，核对当前服务连接的 Registry 登录名、固定密码和仓库所属账号。若出现 `manifest unknown`，核对三个摘要及仓库路径。若是网络超时，保留首个错误与实际耗时；不要关闭证书校验。

必要时可在构建命令恢复[原公共镜像变量](README.md#构建任务)以保留原流程；已经健康运行的站点不依赖本次缓存配置的完成。

## 镜像清单维护

三个仓库标签与 manifest/config 摘要的映射位于 `acr-images.json`。该文件只含公开元数据，可审阅后提交；不包含账户密码。更新基础镜像时，先选定官方新摘要，核对 Linux/amd64，再同步、核验远端摘要，最后一起更新 JSON 和 shell 引用并通过完整 CI。

`deploy/sync_acr_images.py` 默认仅显示计划，不登录或写入仓库。实际同步需 `--apply`，由本机遮罩窗口收取固定密码；`--username` 可固定控制台核对的登录名。调用前需将从 [Google 官方发布页](https://github.com/google/go-containerregistry/releases)下载并核对 SHA256 的 `crane` 放入 `.local/tools/crane/crane.exe`，或用 `--crane` 指定已校验的二进制。凭据配置临时生成且限制本机访问，任何失败都清理配置。

工具会拒绝来源/目标越界、显式缺少仓库 pull/push 权限的令牌，以及不同摘要的已有目标标签。可选的本地 OCI 模式先核对全部 manifest/config/layer 摘要，再上传，避免重复下载。令牌声明检查只作提前诊断，实际授权和摘要仍由 Registry 请求确认。
