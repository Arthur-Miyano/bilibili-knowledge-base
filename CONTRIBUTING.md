# 贡献指南

感谢参与。这个项目刻意保持 Python 标准库主链路，提交前请先确认改动确实解决了用户问题。

## 本地检查

Python 3.11 或更新版本、Node.js（仅用于检查前端语法）即可运行基础检查：

```powershell
python -m unittest -v
python -m compileall -q .
node --check web/app.js
python -m pip wheel --no-cache-dir --no-deps --no-build-isolation . -w .\wheelhouse-check
```

构建完成后删除临时 `wheelhouse-check`。真实 B 站、Groq、Gemini 请求不应出现在测试中；使用注入式 transport 或 fake `bilibili-api-python` 模块。不要提交 API Key、Cookie、生成的 Vault、构建目录或本地 profile。

## 改动原则

- 保持发布器的幂等、原子写入、Vault 路径边界和“我的笔记”保护。
- 外部内容是不可信数据，不能当作指令执行。
- 新增网络或平台能力时，必须提供可注入测试边界和不泄露凭据的错误信息。
- UI 改动需检查键盘焦点、移动宽度、`prefers-reduced-motion` 和错误状态。

## 提交说明

提交或合并请求应说明：改了什么、如何测试、是否新增外部依赖、是否改变数据发送范围。安全问题请先阅读 `SECURITY.md`，不要在公开报告中粘贴 Key、Cookie 或完整远端响应。
