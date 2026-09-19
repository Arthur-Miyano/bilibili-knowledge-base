---
name: B站知识库
description: 安静的本地 Google 风格双栏工作台，把 B 站内容安全地整理进 Obsidian Vault。
colors:
  page: "#f8fafd"
  surface: "#ffffff"
  text: "#202124"
  muted: "#5f6368"
  subtle: "#80868b"
  line: "#dadce0"
  line-soft: "#e8eaed"
  blue: "#1a73e8"
  blue-dark: "#185abc"
  blue-soft: "#e8f0fe"
  green: "#188038"
  green-soft: "#e6f4ea"
  green-line: "#b7dfc2"
  yellow: "#c58a00"
  yellow-soft: "#fff8e1"
  yellow-text: "#614a00"
  red: "#d93025"
  red-soft: "#fce8e6"
  red-line: "#f1b8b3"
  input-line: "#c7c9cc"
  placeholder: "#8a8f94"
  selection-text: "#174ea6"
typography:
  display:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "clamp(30px, 4vw, 42px)"
    fontWeight: 600
    lineHeight: 1.16
    letterSpacing: "-.035em"
  headline:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "18px"
    fontWeight: 600
    lineHeight: 1.3
  title:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "15px"
    fontWeight: 600
    lineHeight: 1.3
  body:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "15px"
    fontWeight: 400
    lineHeight: 1.7
  label:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "13px"
    fontWeight: 600
    lineHeight: 1.4
  mono:
    fontFamily: "ui-monospace, SFMono-Regular, Consolas, monospace"
    fontSize: "11px"
    fontWeight: 400
    lineHeight: 1.4
  meta:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "12px"
    fontWeight: 400
    lineHeight: 1.4
  control:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "14px"
    fontWeight: 400
    lineHeight: 1.4
  display-mobile:
    fontFamily: "Microsoft YaHei UI, Microsoft YaHei, Segoe UI, Noto Sans CJK SC, sans-serif"
    fontSize: "31px"
    fontWeight: 600
    lineHeight: 1.16
rounded:
  compact: "6px"
  field: "7px"
  button: "8px"
  panel: "12px"
  narrow-panel: "10px"
  circle: "50%"
spacing:
  xs: "6px"
  sm: "8px"
  md: "12px"
  lg: "18px"
  xl: "24px"
  2xl: "32px"
  workbench-top: "58px"
components:
  button-primary:
    backgroundColor: "{colors.blue}"
    textColor: "{colors.surface}"
    rounded: "{rounded.button}"
    padding: "0 20px"
    height: "48px"
  button-secondary:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.blue-dark}"
    rounded: "{rounded.compact}"
    padding: "7px 12px"
  input-text:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.field}"
    padding: "0 14px"
    height: "48px"
  panel:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.text}"
    rounded: "{rounded.panel}"
    padding: "22px"
  nav-topbar:
    backgroundColor: "rgb(255 255 255 / 86%)"
    textColor: "{colors.text}"
    padding: "0 32px"
    height: "64px"
  pipeline-step:
    backgroundColor: "{colors.surface}"
    textColor: "{colors.muted}"
---

# Design System: B站知识库

## Overview

**Creative North Star: “安静的 Google 工作台”**

这是一个带常驻功能侧栏的雾白工作台：层级清楚、留白充足，Google 蓝只承担主动作和当前焦点，四色状态标记帮助用户快速读懂本机依赖与运行反馈。整体保持熟悉、直接、克制的 Google 美学，不把页面堆成仪表盘卡片墙。

字体使用系统中文无衬线栈，配合轻边线、很浅的表面差异和低强度阴影，让本地工具保持安静但不失可操作性。页面的具体发布路径是本页的签名表达；它不是所有未来页面都必须复用的全局结构。

**Key Characteristics:**
- 雾白画布上的单一白色工作面
- 克制的 Google 蓝主动作与四色语义状态
- 248px 功能侧栏与左对齐宽工作区，窄屏下转为顶部标签导航
- 语义化文字与图标并用，不依赖颜色传达状态

## Colors

Palette character: cool paper neutrals keep the tool quiet, while one Google blue carries action and focus; green, amber, and red are reserved for operational status.

### Primary
- **Google Blue** (#1a73e8): primary submit action, active pipeline state, links, and focus treatment.
- **Google Blue Dark** (#185abc): action hover, active labels, and privacy icon emphasis.
- **Google Blue Soft** (#e8f0fe): selected/active tonal fill behind blue states and secondary-button hover.

### Secondary
- **Ready Green** (#188038): available dependencies, completed steps, and successful result state.
- **Ready Green Soft** (#e6f4ea): completed-step and successful-result fill.
- **Ready Green Line** (#b7dfc2): successful result-panel border.
- **Error Red** (#d93025): validation, failed dependency, and error state.
- **Error Red Soft** (#fce8e6): failed-step and error-result fill.
- **Error Red Line** (#f1b8b3): failed result-panel border.

### Tertiary
- **Warning Amber** (#c58a00): missing dependency state.
- **Warning Amber Soft** (#fff8e1): recovery/advice surface.
- **Warning Amber Text** (#614a00): readable copy on the warning recovery surface.

### Neutral
- **Cool Paper** (#f8fafd): page canvas and scrollbar track context.
- **White Work Surface** (#ffffff): top bar, panels, fields, and result rows.
- **Google Text** (#202124): headings, labels, and primary content.
- **Muted Text** (#5f6368): supporting copy, status values, and secondary descriptions.
- **Subtle Text** (#80868b): quiet metadata and idle icon color.
- **Structural Line** (#dadce0): connectors, secondary button borders, and light controls.
- **Soft Line** (#e8eaed): panel borders and result-file borders.

**The One Blue Action Rule.** Use the primary blue for the main action, active/focus states, and their immediate feedback; status colors stay semantic and are not decorative accents.

## Typography

**Display Font:** Microsoft YaHei UI, with Microsoft YaHei, Segoe UI, and Noto Sans CJK SC fallbacks
**Body Font:** Microsoft YaHei UI, with Microsoft YaHei, Segoe UI, and Noto Sans CJK SC fallbacks
**Label/Mono Font:** System sans for labels; ui-monospace, SFMono-Regular, and Consolas for generated file paths

**Character:** The pairing is native, calm, and utilitarian. Tight display tracking gives the Chinese hero a confident entry point; smaller labels and generous body leading keep operational details easy to scan.

### Hierarchy
- **Display** (600, `clamp(30px, 4vw, 42px)`, `1.16`): page title and primary orientation.
- **Headline** (600, `18px`, `1.3`): form section title.
- **Title** (600, `15px`, `1.3`): panel headings, step names, and compact labels.
- **Body** (400, `15px`, `1.7`): explanatory lead copy and longer privacy guidance.
- **Label** (600, `13px`, `1.4`): form labels and control-facing text.
- **Mono** (400, `11px`, `1.4`): generated Vault file paths where character differentiation matters.
- **Meta** (400, `12px`, `1.4`): compact status values, badges, and utility copy.
- **Control** (400, `14px`, `1.4`): text inside inputs and primary controls.
- **Display on narrow screens** (600, `31px`, `1.16`): the mobile override for the page title.

## Layout

The desktop app shell uses a `248px` sticky feature sidebar and a left-aligned content area capped at `1180px`. Navigation separates three tasks: create a knowledge base, choose models and credentials, and inspect runtime status. The create view owns source, Vault, execution and result; the settings view pairs knowledge-organization and speech-recognition choices before a shared credential surface; the status view owns dependencies and privacy. Settings controls remain associated with the create form through the native `form` attribute. Panels use white work surfaces over the cool-paper canvas and dividers rather than a dashboard card wall.

At `900px` and below, the sidebar becomes a sticky top bar with horizontal feature tabs. At `700px` and below, settings and readiness grids become one column, the pipeline compresses its connectors, and form actions stack. At `430px`, navigation reduces to its consistent SVG icon set while retaining accessible labels. The layout remains keyboard- and 390px-friendly without horizontal overflow.

## Elevation & Depth

Depth is a restrained hybrid: white surfaces sit on the cool-paper page with one shared ambient panel shadow, while borders and tonal fills do most of the separation work. The page does not rely on floating cards or layered dashboard chrome.

### Shadow Vocabulary
- **Panel ambient** (`0 1px 2px rgb(60 64 67 / 12%), 0 2px 6px rgb(60 64 67 / 8%)`): shared by readiness, form, and result panels.
- **Primary action lift** (`0 1px 2px rgb(26 115 232 / 30%)`, rising to `0 2px 5px rgb(26 115 232 / 28%)`): subtle affordance for the primary button and its hover state.

**The Flat Workbench Rule.** Let surface tone and quiet borders establish structure; reserve stronger lift for an actionable control or a stateful result.

## Shapes

The form language uses gently rounded rectangles, not pills: fields use `7px`, primary controls `8px`, and desktop panels `12px` (reduced to `10px` on narrow screens). Step icons and status dots are circular (`50%`). Borders stay one pixel and low contrast, while state-specific borders become visible only for success and error results.

## Components

### Buttons
- **Character:** direct and confident, with one full-width primary action and a restrained secondary utility.
- **Primary:** Google Blue fill, white label, `48px` height, `8px` radius, and full-width form placement. Hover deepens the blue and raises the shadow; active nudges down `1px`; focus-visible uses a blue outline; loading disables the control and shows a spinner.
- **Secondary:** white surface, muted structural border, Google Blue Dark text, `6px` radius, and `7px 12px` padding. Hover adds a blue border and blue-soft fill; focus-visible uses the same accessible outline language.

### Cards / Containers
- **Corner Style:** readiness, form, and result panels use `12px` on desktop and `10px` on narrow screens.
- **Background:** white work surface against the cool-paper page.
- **Shadow Strategy:** shared panel ambient shadow; result state may replace the neutral border with green or red.
- **Border:** soft line at rest; success and error result panels use their semantic border tones.
- **Internal Padding:** readiness/result panels center on `22px`; the form panel uses `25px 25px 26px` on desktop and `21px 17px 20px` on narrow screens.

### Inputs / Fields
- **Style:** white `48px` field, `7px` radius, one-pixel neutral border, `14px` horizontal inset, and `14px` text.
- **Focus:** Google Blue border plus a `3px` blue focus halo; invalid fields switch to the red border and red halo.
- **Error / Disabled:** validation copy sits directly below the field; errors are announced with `role="alert"`. No disabled field style is introduced beyond native behavior.

### Navigation
- **Style:** a quiet `248px` sticky left rail with the four-color square mark, three labeled feature tabs, and a bottom local-only status. The selected item uses blue-soft fill and blue-dark text. At `900px`, it becomes a sticky horizontal top navigation; at phone width labels visually collapse while their accessible names remain.

### Pipeline Step
- **Style:** the page-specific source → cloud → Vault path uses circular line icons, compact two-line labels, and one-pixel connectors. Idle steps are neutral; active, complete, and error states switch both icon treatment and label color. The state is always expressed with icon treatment plus text, not color alone.

## Do's and Don'ts

### Do:
- **Do** keep the main work surface left aligned beside the feature rail and separate creation, configuration, and status by task.
- **Do** use Google Blue for the primary action and active/focus feedback, with semantic green/amber/red for operational state.
- **Do** pair status color with a written label or icon so the state remains understandable without color perception.
- **Do** preserve visible focus rings, semantic form labels, explicit credential state copy, and the single-column narrow-screen fallback.
- **Do** keep the page calm with white surfaces, soft borders, and restrained ambient elevation.

### Don't:
- **Don't** turn this surface into a dashboard card wall or introduce a second competing accent color.
- **Don't** use status colors as decoration or as the only explanation of readiness, success, or failure.
- **Don't** replace the system font stack with a decorative display face without a confirmed brand need.
- **Don't** promote this page's three-step publish path into a universal layout rule for unrelated screens.
