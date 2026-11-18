# 接通 kongqi-agent-1317119844

桶：kongqi-agent-1317119844，地域：ap-shanghai，访问权限：私有读写。

## 子账号与权限

在腾讯云访问管理 CAM 创建用于程序调用的子用户，创建自定义策略（使用策略语法），将本目录 `cos-policy.json` 内容粘贴进去，再把该策略关联至子用户。策略仅允许该桶 uploads/* 下的上传、元数据查询、下载和跨域预请求，不授权删除、改 ACL、修改桶配置或访问其他桶。

参考[腾讯云 COS API 授权策略](https://cloud.tencent.com/document/product/436/31923)：HEAD Object 对应 HeadObject，OPTIONS Object 对应 OptionsObject，需与 PutObject、GetObject 一起按实际请求范围授权。

为这个子用户创建 API 密钥，保存 SecretId 与 SecretKey，准备在本机遮罩窗口输入。不要把密钥粘贴到聊天、源码、截图或 GitHub。无需为应用提供主账号密钥。

## 浏览器跨域规则

由桶管理员在 COS 控制台为该桶新增 CORS 规则：

| 字段 | 本机联调值 |
|---|---|
| 来源 Origin | http://127.0.0.1:5173 |
| 方法 | PUT、GET、HEAD |
| 允许请求头 | Content-Type、Content-Length |
| 暴露响应头 | ETag |
| 缓存时间 | 600 秒 |

本目录 `cos-cors.json` 是 Python SDK 的 CORSConfiguration 示例，不是 CAM 权限策略。若控制台使用表单，按上表填写；不要用它覆盖已有的其他业务 CORS 规则。正式网站备案和 HTTPS 访问验收完成后，再增加实际网站 Origin。此规则不把桶改为公有读。

参考[腾讯云 CORS 配置](https://cloud.tencent.com/document/product/436/43811)。应用运行账号不需要修改桶 CORS 的权限，管理员在控制台设置即可。

## 配置到当前服务器

在项目根目录的本机终端运行：

```powershell
.\backend\.venv\Scripts\python.exe .\deploy\configure_cos.py
```

脚本核对 SSH 主机后，弹出 Blog COS configuration，隐藏输入 SecretId/SecretKey。它会通过服务器写入一个小私有测试图片，核对 HEAD 大小、签名读取和非签名读取拒绝，随后原子写入服务器环境配置、重启服务并检查健康，同时检测本机 CORS。凭据不在本机保存或输出。

测试对象会留在 uploads/verification/ 供管理员检查；应用账号不需要删除权限。认证或私有读取验证失败时不写入服务器凭据，CORS 未就绪则明确提示需要补规则。

## 最后验收

登录本机预览的写作页，上传图片和 PDF，保存文章，退出登录后仍可读取该文章的附件；未发布的附件不能匿名读取。删除文章后附件入口应返回 404（已发出的短时签名仍会在有效期内有效）。检查浏览器开发者工具确认没有 CORS 错误。

2026-11-18 已完成真实桶上传、HEAD、签名下载及匿名读取拒绝检查，当前本机 Origin 的 CORS 预请求也已通过。用户确认图片/PDF 上传、保存文章和打开附件成功；数据库中两类 ready 附件及文章关联各 1 条。本次验收不包含 CDN、STS、内容扫描或正式网站 Origin。未发布附件和删除文章后的访问限制已有自动化测试覆盖，尚未记录用户在真实桶中的逐项人工验收。
