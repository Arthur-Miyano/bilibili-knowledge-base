# B站知识库

一个不依赖前端框架的本地知识库工具：把 B 站视频的标题、字幕或音频整理成结构稳定的 Obsidian Markdown，并安全写入用户指定的 Vault。离线 JSON → Obsidian 主链路只使用 Python 标准库；云端语音识别使用 Groq Whisper，内容整理可选择 Gemini、DeepSeek 或 Kimi。 知识内容先进入带证据绑定的规范 Knowledge IR，再确定性投影为 Course View/Markdown；课程视图不是规范知识层。

## 能做什么

- 本地 JSON 知识库发布：索引页、分 P 笔记、目录、前后笔记链接和时间轴。
- Knowledge IR 由本地来源、证据和知识项组成；模型只提取并引用证据，Course View/Markdown 由本地渲染。
- 重复发布幂等，保留 `## 我的笔记`；自动区被人工修改时拒绝覆盖。
- 文件名清洗、Vault 路径边界、同目录临时文件原子替换。
- B 站来源使用可选的 `bilibili-api-python==17.4.2` 进程内适配器，逐个分 P 读取字幕或音频地址，优先字幕。
- 本地 Web 面板只监听回环地址，不保存 API Key；状态页会显示 FFmpeg、B 站适配器和云端 Key 是否就绪。

## Windows / PowerShell 快速开始

先安装 Python 3.11 或更新版本和 FFmpeg，并确认：

```powershell
python --version
ffmpeg -version
```

在项目目录创建环境并安装 B 站适配器：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -e ".[bilibili]"
```

这会安装本项目和固定版本 `bilibili-api-python==17.4.2`。适配器在当前 Python 进程内读取 B 站公开元数据、逐个分 P 请求字幕或音频地址；不会读取浏览器或用户目录凭据。Web 面板可使用 B 站官方二维码登录，登录凭据仅保存在当前 Python 进程内存，服务重启即失效；也可在当前会话显式设置 `BILIBILI_COOKIE` 作为备用方案。

配置云端 Key（只在当前 PowerShell 会话生效）：

```powershell
$env:GROQ_API_KEY = "你的 Groq Key"
$env:GEMINI_API_KEY = "你的 Gemini Key"
$env:DEEPSEEK_API_KEY = "你的 DeepSeek Key"   # 与 Gemini、Kimi 三选一
$env:MOONSHOT_API_KEY = "你的 Kimi Key"       # 与 Gemini、DeepSeek 三选一
# 只有 B 站需要登录时设置；不要把真实 Cookie 提交到仓库或日志
$env:BILIBILI_COOKIE = "SESSDATA=...; bili_jct=..."
```

先做只读 B 站适配器烟测（只读取元数据、字幕和音频地址，不下载完整媒体，也不调用 Groq/Gemini）：

```powershell
python -c "from cloud_pipeline import BilibiliSource; print(BilibiliSource().lessons('BV17x411w7KC'))"
```

如果返回 HTTP 412、401 或 403，程序会明确提示 B 站风控/登录或权限问题；请按提示配置自己的 Cookie，或稍后重试。程序不会替用户绕过访问控制。

然后发布：

```powershell
python cloud_pipeline.py "https://www.bilibili.com/video/BV17x411w7KC" --vault "C:\Users\你\Documents\学习库"
```

## macOS / Linux 快速开始

```bash
python3 -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[bilibili]'
ffmpeg -version
export GROQ_API_KEY='你的 Groq Key'
export GEMINI_API_KEY='你的 Gemini Key'
export BILIBILI_COOKIE='SESSDATA=...; bili_jct=...'
python -c 'from cloud_pipeline import BilibiliSource; print(BilibiliSource().lessons("BV17x411w7KC"))'
python cloud_pipeline.py 'https://www.bilibili.com/video/BV17x411w7KC' --vault "$HOME/Documents/学习库"
```

如果不需要 B 站云端入口，可以只运行 `python -m pip install -e .`，离线 JSON 发布器不需要额外依赖。

## 离线演示

无需网络、Key 或 B 站适配器：

```powershell
python course_publisher.py sample_course.json --vault .\demo-vault
```

随后打开 `demo-vault\Courses\Python 入门示例`。重复运行不会生成重复文件。

## 本地 Web 面板

```powershell
python web_app.py --no-open
```

Windows 用户也可以双击项目根目录的 `启动B站知识库.cmd`：服务已运行时直接打开面板，否则启动本地 Web 面板。

然后打开终端显示的 `127.0.0.1` 地址。面板只接受本机回环 Host/Origin；非回环 `--host` 会被拒绝，不提供局域网公开或账户系统。页面中的适配器缺失提示只给安装命令，不会在浏览器里自动安装。

页面左侧可在“创建知识库”“模型与凭据”“运行状态”之间切换。内容整理可选择 Gemini、DeepSeek 或 Kimi，并继续选择具体模型；语音识别可选择 Groq Whisper Large V3 Turbo 或 Large V3。仅 Vault 路径保存在当前浏览器；B站链接、Key 和手动 Cookie 不保存。B站登录可使用官方二维码，凭据只保存在当前 Python 服务进程内存，重启即失效；Key/Cookie 使用密码框，空值回退对应服务端环境变量，凭据只随本次请求发送给本机服务，服务端也不落盘。B站 Cookie 只用于官方 API 请求，CDN 请求不会携带会话 Cookie。

## B 站适配器与故障恢复

默认 `BilibiliSource` 使用 `bilibili-api-python` 的公开 API：先读取视频信息和全部分 P，再为每个 `cid` 请求字幕；没有字幕时按对应 `page_index` 请求该分 P 的音频地址。因此单 P 和多 P 都走同一条适配器路径，字幕优先。

适配器失败会区分缺少库、需要登录、B 站风控/412、网络超时、限流和无效视频，不回显远端响应、Cookie 或 API Key。遇到 412/401/403 时，可在 Web 面板使用官方二维码登录，也可按错误提示设置自己提供的 `BILIBILI_COOKIE`；Cookie 只用于 `*.bilibili.com` 的 API 请求，下载字幕或音频 CDN 时不会携带会话 Cookie。程序不会读取浏览器 Cookie、不会把扫码凭据写入文件，也不绕过访问控制。

## 数据、隐私与费用

- `GROQ_API_KEY` 以及当前选择的 `GEMINI_API_KEY`、`DEEPSEEK_API_KEY` 或 `MOONSHOT_API_KEY` 可从环境变量读取，也可由 Web 页面仅为当前请求显式提供；服务端和响应不会回显它们。
- B 站 BV 号、公开元数据和按需的字幕/音频地址由本机 `bilibili-api-python` 适配器处理；字幕与知识库材料会发送给当前选择的 Gemini、DeepSeek 或 Kimi；无字幕时，本机 FFmpeg 处理后的音频会发送给 Groq。
- 云端免费额度、模型和数据保留政策会变化，不能承诺永久免费；请在发送课程材料前阅读对应服务商条款。
- 本地临时音频处理后自动清理；发布结果只写入用户指定 Vault。

## 测试与构建

```powershell
python -m unittest -v
python -m compileall -q .
node --check web/app.js
python -m pip wheel --no-cache-dir --no-deps --no-build-isolation . -w .\wheelhouse-check
```

Node.js 只属于贡献者前端语法检查，不是普通用户运行程序的前置条件。测试使用 mock，不消费 B 站、Groq 或 Gemini 配额，也不需要真实 Key。构建目录可在检查后删除。CI 覆盖 Ubuntu/Windows 与 Python 3.11/3.14，并有独立 job 安装 wheel 的 `[bilibili]` extra 后检查适配器导入和两个入口。

## 当前边界

完整媒体准备、ASR、视觉理解仍依赖 FFmpeg、B 站适配器和外部云服务；没有 Key、FFmpeg、适配器库、登录权限或网络时，程序会给出可操作错误，不伪造成功。识别出的远端文本只作为数据处理，不执行其中指令。提交规范和本地检查见 `CONTRIBUTING.md`，安全问题见 `SECURITY.md`。
