# Product

<!-- impeccable:product-schema 1 -->

## Platform

web

## Stack

delegated：静态 HTML、CSS、JavaScript 与 Python 标准库本地服务；不引入前端框架。

## Users

主要用户是希望把 B 站视频与分 P 内容整理进 Obsidian 的个人学习者和开源自部署用户。

## Product Purpose

把 B 站视频或分 P 内容经过云端识别与结构化整理，安全、幂等地发布为 Obsidian 知识库笔记。成功意味着用户在一个本地页面中填写来源、Vault、模型和按需凭据，即可完成进程内 B 站适配器、云端识别和发布主流程，并看懂结果或错误。

## Positioning

产品保留原始时间戳证据，由本地程序控制课次顺序和 Obsidian 写入安全；云端模型只负责识别和内容整理。

## Operating Context

用户在 Windows 电脑上运行本地服务，已有 Obsidian Vault；无字幕视频需要本机 FFmpeg 预处理，并使用用户自行配置的 Groq 与 Gemini、DeepSeek 或 Kimi 环境变量。

## Capabilities and Constraints

- 支持 B 站 BV/URL、多 P、字幕优先、无字幕云端 ASR，以及 Gemini、DeepSeek、Kimi 三选一结构化整理和 Obsidian 发布。
- 前端仅监听本机；可选择供应商与具体模型；Key/Cookie 只随当前请求提交，不写入浏览器存储或本地文件，空值回退对应服务端环境变量。
- 免费模型额度与外部平台接口可能变化；页面不能承诺永久免费。
- 当前请求采用最少依赖实现；更换框架属于后续明确需求。

## Brand Commitments

用户明确要求简洁、符合 Google 美学：宽屏双栏工作台、清晰的信息层级、适中的密度、克制的 Google 蓝强调色、熟悉而直接的表单反馈。

## Evidence on Hand

- 已实现并测试的云端管线：`cloud_pipeline.py`。
- 已实现并测试的安全发布器：`course_publisher.py`。
- 项目没有现成 Logo、客户证明或商业数据，不得虚构。

## Product Principles

- 一次只呈现完成任务所需的信息；桌面左侧常驻功能导航，创建、模型与凭据、运行状态分别进入独立界面。
- 明确显示本机依赖和云端配置状态。
- 不隐藏数据将发送到 Groq 与 Gemini 的事实。
- 错误可操作，成功结果可定位。

## Accessibility & Inclusion

使用语义化表单、键盘可操作控件、清晰焦点和不依赖颜色的状态反馈；支持窄屏。
