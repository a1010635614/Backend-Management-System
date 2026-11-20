# 主站 Let's Encrypt 自动续期准备

当前主站和附件证书是两套配置：主站 `kongqi.xyz` 使用 Certbot/Let's Encrypt，附件 `cdn.kongqi.xyz` 使用腾讯云证书。已验收附件 HTTPS 不代表主站续期通过。此前主站 HTTP-01 演练收到平台 403；ICP备案仍按用户要求暂缓。

拟改为自动 DNS-01：创建 `_acme-challenge.kongqi.xyz` TXT，验证后仅删除本次创建的记录。它不需要通过主站 HTTP 路径。单纯手工添加 TXT 无法自动续期，必须有 DNS 插件或认证/清理 hook。[Certbot 官方说明](https://eff-certbot.readthedocs.io/en/stable/using.html#manual)

## 独立 RAM 程序身份

1. 阿里云控制台进入 RAM 访问控制，创建专门用于证书 DNS 验证的程序用户；与人工登录身份分开。
2. 使用 [alidns-policy.template.json](alidns-policy.template.json)，把 `<ALIYUN_ACCOUNT_ID>` 替换为域名所属阿里云主账号 UID，保存为自定义策略并关联到该程序身份。
3. 策略只包含读取、添加和删除记录，不授予全账号 DNS 或其他云产品权限。
4. 创建此身份的 AccessKey，后续通过遮罩配置工具写入服务器 root 0600 专用配置，不发到聊天、不提交 Git、不复用 COS 或主账号密钥。

**实际权限边界：** 上述策略授权到 `kongqi.xyz` 整个 DNS 域，不是单条 TXT。阿里云文档说明，若需限制到某个子域，应将其作为独立子域管理，再按该子域授权；不能声称只靠这份策略就限制为 `_acme-challenge`。[自定义权限策略](https://help.aliyun.com/zh/dns/alibaba-cloud-dns-custom-permission-policy-reference-dns)、[资源 ARN](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-ram)

RAM 身份创建完成后仍应先核对域名读取权限，再用 ACME 测试环境验证添加、权威 DNS 可见、校验与精确清理。记录 API 的域名资源格式已核对官方 [AddDomainRecord](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-adddomainrecord) 和 [DescribeDomainRecordInfo](https://help.aliyun.com/zh/dns/api-alidns-2015-01-09-describedomainrecordinfo)。

## 实施与验收门槛

- [ ] 实现或安装已审阅的 DNS-01 认证/清理程序，固定阿里云 HTTPS API，日志不得记录密钥或完整签名 URL。
- [ ] 配置文件/临时状态 root 0600；只处理授权域名与验证 TXT；清理前核对记录 ID、域名、类型和值，不删除其他记录。
- [ ] 等待实际权威 DNS 可见；测试错误凭据、传播超时、API 异常和清理失败。
- [ ] 通过独立测试证书的 ACME staging 演练，保留当前正式证书。
- [ ] 将现有主站续期配置改为 DNS-01；再执行对应证书 `renew --dry-run`，核对成功日志与清理结果。
- [ ] 成功续期后的部署 hook 执行 `nginx -t` 并 reload，核对定时器、证书新到期日和 HTTPS。

此文件是准备清单；目前未收集 AliDNS 凭据、未部署 DNS hook、未更改主站续期配置。`certbot.timer active` 不能替代续期演练成功的证据。
