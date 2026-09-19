# 安全策略

## 当前支持范围

本程序默认只监听本机回环地址，并把生成内容写入用户明确指定的 Obsidian Vault。API Key 可以从环境变量读取，也可以由本地 Web 面板仅为当前请求显式提供；请求后不落盘、不回显。B 站适配器是用户明确安装的 `bilibili-api-python` 库，只接受用户显式提供的 `BILIBILI_COOKIE`（环境变量或当前 Web 请求）。程序不会读取浏览器 Cookie、二维码登录状态、用户目录 credential 或其他隐式凭据。

适配器只把 Cookie 交给 `*.bilibili.com` 的 API 请求；字幕和音频 CDN 下载不携带会话 Cookie。远端错误会转换为不包含响应正文、Cookie 或 API Key 的服务专属提示。

## 不要提交的内容

请不要把以下内容放进 issue、日志或补丁：

- `GROQ_API_KEY`、`GEMINI_API_KEY` 或 B 站 Cookie；
- 浏览器导出的完整 Cookie、二维码登录文件或其他 credential 文件；
- 私人课程字幕、音频或 Vault 内容；
- 未脱敏的远端响应正文。

## 报告问题

发现可能导致凭据泄露、跨站写入 Vault、路径越界或远端数据外泄的问题时，请优先使用代码托管平台提供的私密安全报告渠道；如果当前仓库尚未配置该渠道，请先提交不含敏感材料的最小公开 issue，并注明“security”，等待维护者提供私密联系方式。不要为复现问题上传真实 Key、Cookie 或课程材料。

当前项目尚未声明公开仓库 URL，因此文档不提供虚构的安全邮箱或链接。
