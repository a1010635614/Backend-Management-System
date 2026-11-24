# 主站 Let's Encrypt 自动续期准备

当前主站和附件证书是两套配置：主站`kongqi.xyz`使用Certbot/Let's Encrypt，附件`cdn.kongqi.xyz`使用腾讯云证书。此前HTTP-01演练收到平台403；2026-11-24晚间只读复核时公网HTTP已返回301、HTTPS200和有效证书，但没有因此重新执行ACME或推断ICP备案状态。用户本轮再次明确“继续暂缓证书，先做其他收尾”，续期配置仍是webroot，新DNS-01验收继续暂缓。

拟改为自动 DNS-01：创建 `_acme-challenge.kongqi.xyz` TXT，验证后仅删除本次创建的记录。它不需要通过主站 HTTP 路径。单纯手工添加 TXT 无法自动续期，必须有 DNS 插件或认证/清理 hook。[Certbot 官方说明](https://eff-certbot.readthedocs.io/en/stable/using.html#manual)

## 独立 RAM 程序身份

1. 阿里云控制台进入 RAM 访问控制，创建专门用于证书 DNS 验证的程序用户；与人工登录身份分开。
2. 使用 [alidns-policy.template.json](alidns-policy.template.json)，把 `<ALIYUN_ACCOUNT_ID>` 替换为域名所属阿里云主账号 UID，保存为自定义策略并关联到该程序身份。
3. 策略只包含读取、添加和删除记录，不授予全账号 DNS 或其他云产品权限。
4. 创建此身份的 AccessKey，后续通过遮罩配置工具写入服务器 root 0600 专用配置，不发到聊天、不提交 Git、不复用 COS 或主账号密钥。

**实际权限边界：** 上述策略授权到 `kongqi.xyz` 整个 DNS 域，不是单条 TXT。阿里云文档说明，若需限制到某个子域，应将其作为独立子域管理，再按该子域授权；不能声称只靠这份策略就限制为 `_acme-challenge`。[自定义权限策略](https://help.aliyun.com/zh/dns/alibaba-cloud-dns-custom-permission-policy-reference-dns)、[资源 ARN](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-ram)

RAM 身份创建完成后仍应先核对域名读取权限，再用 ACME 测试环境验证添加、权威 DNS 可见、校验与精确清理。记录 API 的域名资源格式已核对官方 [AddDomainRecord](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-adddomainrecord) 和 [DescribeDomainRecordInfo](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-describedomainrecordinfo)。

## 已实现的程序与配置入口（2026-11-24）

新机 `121.40.113.185` 已有 `/usr/bin/dig` 和 Certbot 2.9.0。源码中的 [alidns_hook.py](../scripts/alidns_hook.py) 是独立的标准库程序，不加载博客的 `.env`，也不需要把 DNS 密钥放进应用容器。

- 固定 `https://alidns.aliyuncs.com/`，校验 CA/主机名、拒绝重定向和环境代理；签名参数仅在 POST 正文中传输，异常只报告经过筛选的错误码。
- 只接受 `kongqi.xyz`，兼容 Certbot 的 `CERTBOT_IDENTIFIER` 与旧 `CERTBOT_DOMAIN`；主站验证不会处理 CDN 子域名或其他域名。
- 新增 `_acme-challenge` TXT、默认线路、TTL 600；保留其他 TXT。等待每个已发现的权威 NS 通过直接 TCP DNS 查询返回正确的权威应答。
- 状态目录 root 0700、文件 0600，先记录创建意图再请求 API。创建响应丢失时不盲目重试，也不接管已有的同值记录。
- 清理前核对记录 ID、域名、RR、类型、值和线路，只删除本次拥有的 ID；身份不符或删除结果不确定时保留状态供检查。

新机隔离 Linux 环境的 **69 项部署单元检查通过、零跳过**，其中 19 项覆盖 DNS hook、5 项覆盖只读预检和安全安装。测试使用替身 API 与合成凭据，**不等于真实 AliDNS/ACME 验收通过**。

本机先查看不读密钥、不联网的安装计划：

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 deploy\configure_alidns.py
```

专用 RAM 用户和策略准备好后，通过两个遮罩输入框配置：

```powershell
.\backend\.venv\Scripts\python.exe -X utf8 deploy\configure_alidns.py --apply
```

该命令先只读检查 DNS 权限与 NS，成功后安装：

| 路径 | 用途与权限 |
| --- | --- |
| `/etc/letsencrypt/alidns-hook.json` | 两项 AliDNS 凭据，root 0600，不包含在发布制品中 |
| `/usr/local/lib/blog-acme/alidns_hook.py` | 经过本地 SHA-256 核对的 hook 源码，root 0755 |
| `/usr/local/lib/blog-acme/reload-nginx.sh` | `nginx -t` 通过后 reload，root 0755 |
| `/var/lib/blog-acme` | 本次挑战的独立状态，root 0700 |

已有不同配置或不安全权限会阻止覆盖；取消输入不会发送凭据。安装本身不会修改 DNS、执行续期或改变现有证书。

## 安装后分阶段验收

以下为尚未执行的实际服务器操作，不能用单元测试结果代替。操作在新机上以 root 执行，不含明文密钥。

1. 只读复核：

   ```bash
   /usr/bin/python3 /usr/local/lib/blog-acme/alidns_hook.py check
   ```

2. 使用现有证书名称做 DNS-01 staging 测试；`--dry-run` 不保存测试证书，不替换正式证书：

   ```bash
   certbot renew --cert-name kongqi.xyz --dry-run --non-interactive \
     --authenticator manual --preferred-challenges dns \
     --manual-auth-hook '/usr/bin/python3 /usr/local/lib/blog-acme/alidns_hook.py auth' \
     --manual-cleanup-hook '/usr/bin/python3 /usr/local/lib/blog-acme/alidns_hook.py cleanup'
   ```

3. 核对 Certbot 成功、挑战状态均 cleaned、测试 TXT 清理，正式 fullchain 哈希保持不变。先保存当前续期配置备份，再使用 Certbot 2.9 支持的 `reconfigure`；它先进行 staging 测试，成功后才保存续期选项。[Certbot 配置修改说明](https://eff-certbot.readthedocs.io/en/stable/using.html#modifying-the-renewal-configuration-of-existing-certificates)

   ```bash
   certbot reconfigure --cert-name kongqi.xyz --non-interactive \
     --authenticator manual --preferred-challenges dns \
     --manual-auth-hook '/usr/bin/python3 /usr/local/lib/blog-acme/alidns_hook.py auth' \
     --manual-cleanup-hook '/usr/bin/python3 /usr/local/lib/blog-acme/alidns_hook.py cleanup' \
     --deploy-hook /usr/local/lib/blog-acme/reload-nginx.sh --run-deploy-hooks
   ```

4. 不再从命令行覆盖认证参数，验证已持久保存的配置：

   ```bash
   certbot renew --cert-name kongqi.xyz --dry-run --run-deploy-hooks --non-interactive
   systemctl is-enabled certbot.timer
   systemctl is-active certbot.timer nginx
   ```

5. 再核对有效 HTTPS、当前证书到期日、DNS 清理和配置中的 hook 路径。dry-run/reconfigure 使用当前正式证书运行部署 hook；这两项测试不会延长现有证书的到期日。[Certbot 部署 hook 说明](https://eff-certbot.readthedocs.io/en/stable/using.html#pre-and-post-validation-hooks)

传播超时会尝试精确清理已取得 ID 的记录；不确定创建、身份变化或清理失败则保留受保护的状态并报错。不要直接删除整个状态目录或批量清空 `_acme-challenge`，应先核对该次状态及具体记录。

## 实施与验收门槛

- [x] 实现已审阅的 DNS-01 认证/清理程序，固定阿里云 HTTPS API，错误不记录密钥或签名请求。
- [x] 权限、域名/记录身份与不确定结果的失败边界通过 Linux 合成检查。
- [x] 错误凭据、传播超时、API 异常、清理失败及所有权变化的替身检查通过。
- [x] 使用真实专用凭据安装 root 0600 配置，实际 AliDNS 读取权限与 NS 发现通过。
- [ ] 实际验证本次 TXT 的增删、权威 DNS 可见和精确清理。
- [ ] 通过独立测试证书的 ACME staging 演练，保留当前正式证书。
- [ ] 将现有主站续期配置改为 DNS-01；再执行对应证书 `renew --dry-run`，核对成功日志与清理结果。
- [ ] 成功续期后的部署 hook 执行 `nginx -t` 并 reload，核对定时器、证书新到期日和 HTTPS。

## 用户要求暂停后的实际状态

2026-11-24 已通过遮罩工具安装真实专用凭据与 hook，读取权限与 `dns7.hichina.com` / `dns8.hichina.com` 发现成功；密钥未进入聊天记录、源码或本机文件。

首次 DNS staging 在执行任何挑战之前被另一项 Certbot 操作占锁阻止，未创建 TXT。根据真实内核锁与进程信息，占锁者为手动终端中的 PID 2897：`certonly --dry-run --debug-challenges --webroot`，不是本次测试或系统定时任务。用户明确要求取消并暂不继续申请证书；仅核对该 PID 的启动时间及参数类别后发送 SIGINT，进程正常退出并释放锁，没有删除锁文件。

取消前后的正式 fullchain 与续期配置 SHA-256 均一致，vueblog/Nginx/PostgreSQL active，健康 HTTP 200/UP。原证书有效期至 2027-02-15；现有定时器保持原状，新 DNS hook **尚未写入正式续期配置**。证书测试/配置部分按用户要求暂停；恢复时先读取现状，再继续 staging 与 reconfigure，不因锁已释放就自动重跑。

代码与 69 项合成检查完成，但 AliDNS 写入/清理、ACME DNS-01 staging 与持久续期 dry-run 均不能标记通过。`certbot.timer active` 不能替代这些验收。
