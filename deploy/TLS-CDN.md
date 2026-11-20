# 域名、证书、缓存操作

2026-11-20：当前实际使用原生部署，站点 `kongqi.xyz` 的证书已存在，但 HTTP-01 续期演练曾因公网 403 失败。附件 CDN 尚未开通；最新准备步骤见 [腾讯云私有 COS CDN 接入](<G:/Full Stack/agent full stack project/deploy/CDN-SETUP.md>)。以下 `example.com` 命令是通用模板，不能当作现网操作结果。

将 `example.com` 替换为自己的域名。网站域名 A 记录指向部署主机，CDN 资源域名 CNAME 指向云厂商给出的加速域名，资源源站选择 COS 桶。业务 `/api/*` 不走资源 CDN。

先安装 Nginx 和 certbot，开放 80/443，创建 `/var/www/certbot`。首次签证书时只启用 HTTP 配置中的 ACME location 和站点代理，不要加载尚不存在的证书文件。运行：

```bash
sudo certbot certonly --webroot -w /var/www/certbot -d example.com -d www.example.com
# 将 nginx-ssl.conf.example 配置中的域名替换后放入 conf.d
sudo nginx -t
sudo systemctl reload nginx
sudo certbot renew --dry-run
```

certbot 安装提供的定时任务负责续期；将部署钩子保存为 `/etc/letsencrypt/renewal-hooks/deploy/reload-nginx.sh`，内容为 `#!/bin/sh` 和 `nginx -t && systemctl reload nginx`，赋可执行权限。通过证书监控验证续期生效。

Nginx 配置含邮箱接口和统计写入接口的 IP 限流。若入口接了负载均衡，必须只信任实际 LB 网段的 real_ip_header，不能直接信任公网客户端提供的 X-Forwarded-For。

内层 frontend/nginx.conf 为带 hash 的 assets 设置一年 immutable 缓存，HTML 与 API 使用 no-store。CDN 同步规则：HTML TTL 0，assets TTL 31536000，API 不缓存；发布时刷新 HTML 缓存，hash 资源由新路径发布，不覆盖旧文件。注意容器切换时旧资源的保留策略，正式 CDN 发布应至少保留前一版本资源。

COS：桶 CORS 允许网站 HTTPS Origin、PUT/GET/HEAD 方法和 Content-Type/Content-Length 请求头；暴露 ETag，禁止把管理密钥放入前端。附件 CDN 准备使用独立域名、HTTPS 私有回源及 Type D 访客鉴权。应用本地已增加 Type D 签名支持，配置默认关闭，尚未发布或通过真实 CDN 验收；不能只填写一个 CDN 域名就启用下载。

上线验收：HTTP 返回 301；HTTPS 证书主机名、链和有效期正确；deep link 如 /posts/1 可访问；assets 命中缓存；登录与 API 没有 CDN 缓存；证书续期演练成功；COS PUT 与后续 CDN GET 都成功。
