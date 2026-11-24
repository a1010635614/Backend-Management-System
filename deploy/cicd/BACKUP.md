# Compose 备份和恢复演练

当前状态（2026-11-24）：新生产 0003 的真实备份已在无网络临时 PostgreSQL 中恢复，归档/元数据/恢复证明的摘要与 root 0600 权限核对通过，临时容器已清理。实际 `blog-backup.service` 的成功输出与同一次 journal InvocationID 的 `JOB_RESULT=done` 已匹配；新 `blog-backup.timer` 已 enabled/active。旧 `vueblog-backup.timer` 已停用，旧库和历史归档保留。

## 新生产发布后的备份

```bash
python3 /opt/blog-fullstack/current/deploy/scripts/backup.py --drill --retention-days 7
```

脚本要求已有验证通过的 Compose current，持有与部署相同的锁，执行容器内 `pg_dump --format=custom`。密码由受保护配置传递，不放在命令行或日志中。备份位于 `/opt/blog-fullstack/backups`：

- `.dump`：数据库归档，0600。
- `.dump.json` / `.dump.sha256`：内容 SHA、字节数、结构版本和源码标记。
- `.dump.restore.json`：隔离恢复时间、逐表计数及内容摘要。未传入停写源摘要时 `source_compared=false`，不能声称核对了运行中数据库同一时刻的内容。

`--drill` 在私有临时目录启动一次性 PostgreSQL：不发布端口、`--network none`、192MiB 内存上限、独立随机密码、磁盘数据目录。仅向空库单事务恢复，验证结构并读取摘要，之后核对容器身份标签再清理。Docker 状态不明时保留目录，避免删除仍在挂载的数据。

保留策略只清理文件名、摘要和成功恢复证明都符合要求的过期备份，至少保留最新两份已验证备份；未验证备份不自动删除。部署前备份也保留，不冒充已完成恢复演练。

## 安装定时任务

首次切流后，可先安装 service，执行一次真实备份/恢复验收，再启用 timer。本次已完成这些步骤，以下供复核和重建使用：

```bash
install -m 644 /opt/blog-fullstack/current/deploy/docker/blog-backup.service /etc/systemd/system/blog-backup.service
systemctl daemon-reload
systemctl start --no-block blog-backup.service
journalctl -u blog-backup.service --since today --no-pager
# 确认本次 backup/restore passed、恢复证明和容器清理后再继续：
install -m 644 /opt/blog-fullstack/current/deploy/docker/blog-backup.timer /etc/systemd/system/blog-backup.timer
systemctl daemon-reload
systemctl enable --now blog-backup.timer
systemctl list-timers blog-backup.timer
```

任务按服务器时区每日 03:30 加最多 15 分钟随机延迟执行。本机时区为 `Asia/Shanghai`；启用时观察到下一次为 2026-11-25 03:39:48 CST，以 `systemctl list-timers` 的实时结果为准。首份 Compose 备份恢复通过且新 timer 生效后，才停用旧 `vueblog-backup.timer`，并保留历史归档。新机实际验收时约 919MiB 内存可用、memory full avg10 为 0，未与候选构建并行。

oneshot 完成后 `inactive/dead` 是正常状态；systemd 回收再加载 unit 对象时，启动时间和 InvocationID 字段也可能为空。不能只凭 `is-active` 判断成功或失败，应结合本次 journal 中 worker 的 `_SYSTEMD_INVOCATION_ID`、manager 同 ID 的 `JOB_RESULT=done`、`backup/restore: passed` 以及归档恢复证明。不要因观测字段为空就重复启动备份。

## 独立检查已有备份

```bash
python3 /opt/blog-fullstack/current/deploy/scripts/restore_drill.py \
  /opt/blog-fullstack/backups/EXACT_BACKUP_NAME.dump
```

命令只能创建临时恢复库，不能指定生产恢复目标，失败不会覆盖正式数据。灾难恢复要先准备新项目、新密码和空 PostgreSQL，验证归档与摘要，再迁移应用配置和公开流量；`PostgresClient.restore_empty` 拒绝非空目标。不可对运行中的数据卷执行 `pg_restore --clean`。

数据库归档不包含 COS 对象、Redis AOF、主机证书或第三方配置。COS 对象须单独保护；Redis 丢失后验证码和限流记录会丢失，恢复服务时应生成新的 JWT_SECRET 使旧 Token 失效。不能将密钥放入数据库归档来代替独立凭据管理。异地加密备份仍需单独的受控存储和授权，本机备份不覆盖整机损坏。
