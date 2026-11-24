# 首次从原生部署切换至 Compose

当前状态：2026-11-24 经用户明确批准，**首次正式切流已完成**：原生 `f62dc92` / 0002 → Compose `63dba62` / 0003。迁移任务 exit 0、阶段 complete、六个服务 healthy、公开健康 200/UP；旧应用停止，旧库和最终备份保留。本文以下控制器流程用于审计和恢复理解，不得再次执行同一首次迁移。

2026-11-24 用户已通过镜像迁移到 `121.40.113.185`，新机已包含原生服务与 0002 数据库，因此现在满足本文“同机原生→Compose”的拓扑前提。按 [新机实际状态](SERVER-REPLACEMENT.md) 继续；不能把该结论套用于没有原生数据的空主机。

## 2026-11-24 已验证的准备

- 独立新机真实应用失败回退、合成数据保留、Redis 重启持久化通过；用户已确认新版前后台登录、菜单、发布文章与 History 刷新正常。候选与本机隧道验收后已停止，卷保留。
- 新机正式库在线备份已在无网络临时 PostgreSQL 中恢复，六表计数及内容摘要与稳定源相同：用户 1、文章 2、附件 6。正式停写后的最终备份仍须由切流控制器重新执行，不能把这份在线备份冒充最终冻结快照。
- 旧安装的 `/opt/vueblog` 顶层原由 blog 用户拥有；已仅改属主为 root，保留 0755、GID 与全部子目录文件属主，版本指针未变、原生健康正常。旧备份目录/锁已为 root 私有，不需要放松控制器权限检查。
- 用户已明确授权 15 项生产必要配置白名单，新生产 `/opt/blog-fullstack/shared/runtime.env` 已生成，root 0600，数据库/Redis/JWT 独立新建；源未改、服务未重启。不得再次索要密钥或将它复制到候选。
- 实际 CI 制品 `63dba62` 已暂存到 `incoming/<完整提交号>` 并解包到 `releases/<完整提交号>`，五个应用镜像已按顺序预构建并保存镜像 ID；生产 Compose 配置解析通过。准备后原生健康仍为 200、Nginx/运行时未变，没有启动新应用或导入数据库，也没有发布 `current`。
- 新 Runner 独立注册并 active/enabled，用户已保存正式任务的新主机组；旧原生接收器仍在，必须在合入 main 前更新正式发布入口。
- 主站证书部分应用户要求暂停。现有有效证书和续期配置保留，取消了阻塞的手动 HTTP dry-run；没有把 DNS-01 单元检查当作实际续期通过。

独立流水线 `1456871` 第 3 次已在 `set -eu` 修正后完整成功，实际主机日志与用户反馈均已核对；该制品与预构建版本一致。首次迁移随后通过独立 systemd oneshot 执行，任务 `blog-first-cutover-63dba629.service` 的状态为 success/exit 0，日志为 `shared/native-migration/state.json` 的 complete。用户已验收新正式站核心登录、文章和附件流程。

## 执行前的准备

1. 在独立分支、独立构建流水线中产出通过全部检查的 format 2 制品；核对完整提交号和 SHA-256。正式流水线只触发 main。验证流水线可通过“主机部署”类型的任务下载制品，但脚本固定为 `verify_flow.py`，只校验、不执行应用发布，也不添加通知插件；具体字段见 [独立验证步骤](README.md#独立验证制品上传与新机校验)。
2. 完成候选双前端浏览器验收和失败恢复演练；这两项已在新机通过。继续按顺序安排镜像构建、集成检查与候选预览，避免复现旧 894MiB 主机上多套应用与构建并发造成的资源压力。
3. 新生产专用 `/opt/blog-fullstack/shared/runtime.env` 已按用户授权生成，root 0600，PostgreSQL、Redis 和 JWT 使用新随机密钥；只迁移了必要的 SMTP/极验/COS/CDN/统计/管理员配置。本次无需重复准备。旧数据库连接、JWT、GitHub App 私钥、飞书 Webhook 不复制到候选环境或制品。
4. 此前自动审批拒绝的是复制整份生产第三方配置到候选环境；本次 15 项白名单到新生产配置的明确授权已经取得并执行。后续沿用该授权范围，扩大源、目标或字段范围时再展示差异，不重复索要相同批准，也不通过备份、容器环境或日志绕过原边界。
5. 确认旧应用、Nginx、原 PostgreSQL 健康，现有证书可读，磁盘有空间保留最终备份、新数据库和镜像。维护窗口内不执行其他数据库写入或 Nginx 配置变更。
6. 准备主机接收器升级。旧接收器仍负责现有原生制品，新格式合入 main 前必须替换并验证。

## 控制器流程

生产配置准备工具为 `deploy/scripts/prepare_runtime.py`。默认运行只显示以下计划，不打开源配置：

```bash
python3 deploy/scripts/prepare_runtime.py
```

复制白名单为 `ADMIN_EMAILS`、`MAIL_HOST/PORT/USERNAME/PASSWORD/FROM`、`GEETEST_ID/KEY`、`COS_REGION/BUCKET/SECRET_ID/SECRET_KEY`、`CDN_BASE_URL/AUTH_KEY` 和 `BAIDU_HM_ID`。固定源 `/etc/vueblog.env`，固定目标 `/opt/blog-fullstack/shared/runtime.env`；只创建新文件、不覆盖已存在配置、不改源文件、不重启服务。新的数据库/Redis/JWT 密钥独立生成。

取得对这份计划的明确授权后，使用已有包含 python-dotenv 的受控环境执行：

```bash
/opt/vueblog/venv/bin/python VERIFIED_SOURCE/deploy/scripts/prepare_runtime.py \
  --apply --copy-production-integrations
```

该文件专供 Compose `--env-file` 使用：双引号转义及 `$$` 保留密码中的美元符号；已使用真实隔离 Compose 容器验证引号、反斜杠、空格和美元符号的实际环境值。不要将此文件作为 shell 脚本 source，也不要用它替换旧 systemd EnvironmentFile。生成后只核对权限和无值的准备收据，不输出配置正文。

`deploy/scripts/native_cutover.py` 只针对已有原生实例：`vueblog.service`、peer 认证的 PostgreSQL `blog`、`/etc/nginx/sites-available/vueblog`。它不读取 `/etc/vueblog.env`。

持有新部署锁及旧原生发布/备份锁后，按以下顺序执行：

1. 验证旧完整提交号、0002 结构、Nginx 活动站点和证书；拒绝已有 Compose current、迁移日志、导入标记或流量标记，防止重放。
2. 验证并解包新制品，构建预编译双前端和后端镜像、累积哈希资源，启动新 PostgreSQL/Redis，确认目标库为空。旧站继续运行。
3. 写受保护的迁移日志及旧 Nginx 配置；停止旧应用写入，生成 custom 格式最终备份和逐表摘要。备份前后源数据变化即失败。
4. 仅向空目标库事务恢复，比较所有旧表的计数和内容摘要，再写绑定提交号与项目名的导入标记。
5. 执行 0003、启动新应用并检查回环地址的实际双前端 HTML、资源哈希、History、Swagger、健康及匿名权限。删除新增字段后再次核对旧业务数据摘要，确认源库仍未变化。
6. 备份新库，渲染已有证书路径的 Nginx 配置并通过 `nginx -t`。**reload 前持久化 `traffic_may_have_changed=true`**，随后 reload 并检查公开 HTTPS 的实际资源。
7. 仅公开检查通过后写 `current`、`.current-release` 和 `traffic-ready.json`，允许后续 Flow 发布。

下面是维护窗口中的执行入口，不能现在直接用于未准备的生产环境：

```bash
python3 VERIFIED_SOURCE/deploy/scripts/native_cutover.py \
  --artifacts VERIFIED_ARTIFACT_DIRECTORY \
  --commit FULL_40_CHARACTER_COMMIT \
  --apply
```

没有 `--apply` 时不读取生产数据库或停止服务。默认目标 `/opt/blog-fullstack`、项目 `blog-production-v2`、回环 18080/18000、主机 `kongqi.xyz`，必须与接收器及备份任务一致。

## 故障与恢复边界

日志为 `/opt/blog-fullstack/shared/native-migration/state.json`，目录 0700，最终原生备份及配置副本 0600。日志记录阶段、路径、版本、计数和摘要，不记录正文或密钥。终端被强制结束后先看日志及实际服务状态，不能直接重跑。

| 阶段 | 含义与处理 |
| --- | --- |
| `prepared` / `stopping-native` / `native-stopped` / `import-verified` / `compose-checked` | 控制器尚未 reload。正常异常路径恢复旧配置、停止新应用并重启原生应用，保留目标数据和日志。进程被 kill 时，人工确认 Nginx 尚未加载新配置再恢复原生服务。 |
| `aborted-before-cutover` | 检查 `recovery_errors`。为空才表示清理动作均完成；不能把进入清理当成已恢复。导入 gate 已删除，重放被阻止。 |
| `reload-attempted` / `recovery-required`，或 `traffic_may_have_changed=true` | 新库可能已有写入。保持原生应用停止，修复 Compose/Nginx 并使用新库继续服务。不能仅改 Nginx 回旧站或重启原生应用，否则会造成两份库分叉。 |
| `complete` | 当前正式流量与完整源码通过公开检查；继续真实登录、文章、附件和统计验收，安装新备份任务及更新 Flow 接收器。 |

控制器不删除旧数据库、不自动降级 Alembic、不删除数据卷，也不把残留目标库当作空库重用。需要返回旧应用时，必须另行设计兼容新数据的导出/恢复及停写流程，不能用旧快照覆盖新写入。

单元检查使用隔离文件和模拟系统命令验证切流边界；真实临时 PostgreSQL 检查覆盖 0002→0003 内容保留及 custom 恢复。它们不能替代正式切流、真实第三方登录和浏览器验收。
