# 任务卡协议

仅在自然人用户明确启用总控面后的建卡、交接或格式维护时读取。

## 目录与唯一记录

```text
_control/
├── OVERVIEW.md                 # 自动生成的全局进度
├── CURRENT.md                  # 按需：重点和约定
├── tasks/<id>.md               # 首次登记即跨项目的工作
└── projects/<project-key>/
    ├── OVERVIEW.md             # 自动生成，包含涉及该项目的跨仓卡片
    ├── CURRENT.md              # 按需：项目重点和约定
    └── tasks/<id>.md           # 首次登记为单项目的工作
```

需要时再建目录。单项目事项后来跨仓，保留原 ID 和路径，只更新 repos。
通过实际仓库和 Git common-dir 判断 worktree 的项目身份，不将每个 worktree 当成新项目。

ID 使用稳定短名，可带时间戳，必须与文件名（不含 .md）一致且全局唯一。
ID 和项目键使用字母、数字、点、下划线、连字符，以字母或数字开头；不能使用路径。
卡片限定为根 tasks/ 或 projects/<key>/tasks/ 下的直接 .md 文件，不使用符号链接。

## 卡片示例

以下为未启动事项的格式示例，不代表已登记、实施或授权：

```markdown
---
id: "20260915-field-change"
title: "统一某字段的存储和消费"
status: deferred
owner: null
repos: [filedb_dev, filedb_datac, prefect, data-health-dashboard]
updated_at: "2026-09-15T14:30:00+08:00"
next_step: "确定字段含义与消费范围"
depends_on: []
parent: null
---

# 统一某字段的存储和消费

## 接手摘要
当前状态、已完成和尚未验证的内容，控制在少量段落。

## 目标与验收
本项工作的独立结果，以及足以证明完成的验证。

## 范围与工作副本
实际仓库、checkout/worktree、分支或起始提交、负责范围。
需要集成时记录承接集成的任务；共享数据、缓存和部署目标另行说明。

## 已确认决定与依据
采用的接口文档及版本、决定理由、必要的确认来源。
交接确有需要时记录自然人用户的已有授权范围与条件。

## 进展与证据
变化、验证命令及结果、对应代码版本、产物路径。
未提交内容注明所在工作副本；生产运行变更单独记录。

## 阻塞与下一步
具体依赖、解除条件、可直接执行的下一步。

## 后续发现
未拆卡的想法或关联工作项链接。
```

头部必填：id、title、status、owner（可为 null）、repos（非空项目键列表）、
updated_at（带时区的 ISO 时间）。next_step、depends_on、parent 可省略。
时间和可能含特殊字符的文本用引号；不要在字段内放长日志。

owner 默认填真实独立任务链接，例如 `codex://threads/实际ID`。
无法取得 ID 时用可识别的任务名称和工作位置，不能编造链接。
null 表示尚未分配；换模型无需更改 owner，换独立任务接手时更新。
parent 和 depends_on 填卡片 ID；尚未建卡的外部条件在正文中说明。

| status | 含义 |
| --- | --- |
| ready | 可接手，但尚未开始 |
| doing | 工作任务正在推进 |
| blocked | 受具体条件阻塞，需写解除条件 |
| deferred | 明确暂缓或尚未选入执行 |
| done | 本卡验收已满足且有证据 |
| cancelled | 取消或被替代，正文说明原因 |

需要独立审查时写入本卡验收，不给所有卡片增加统一审批流程。
一张卡可以涵盖多个仓库；多个独立任务并行时各自写子卡，父卡记录共同目标和集成验收。
脚本只展示状态，不自动判定验收、解除依赖或完成父卡。

## 总览、触发和交接

- 使用 apply_patch 写卡后，coordination_after_edit hook 刷新 OVERVIEW；它只识别上述卡片路径。
  普通代码、TODO、CURRENT 和生成总览的编辑不会触发汇总。
- hook 不分析自然人用户的提示语、不启用任务、不调用模型、不读取历史对话。
  启用意图由全局规则与 skill 处理，生效范围是当前工作。
- Python、shell 或编辑器等其他方式写卡后，执行主 skill 给出的刷新入口。
  hook 不覆盖所有文件写入方式；新 hook 需要宿主加载并信任后才会自动执行。
- 全局和项目 OVERVIEW 都由同一批卡片生成，显示活跃项和结束项数量。
  结束项详情留在原卡，按需检索；不存在第二份需人工维护的进度表。
- 刷新加锁串行执行并逐文件原子替换；自然人用户只改任务卡和必要的 CURRENT。
  CURRENT 是重点与约定，不是实时状态。
- 卡片格式不完整或重复 ID 会阻止本次生成，报告问题而不输出不完整的绿色结果。
  修改期间另一个任务可能触发生成失败，完成卡片写入后再次刷新即可。
- 交接时更新 owner、接手摘要、代码版本、未提交状态、依据和下一步。
  子卡进展自动进入总览，不需要自然人用户回协调任务发一次「汇总」指令。

## 维护与验证

Codex hook 入口统一放在 ~/.codex/hooks/，本技能的汇总脚本保留在 scripts/。
hook 通过绝对路径加载汇总脚本，不依赖工作任务的当前目录。
脚本使用本机 Conda base 的 Python 和 PyYAML；路径以主 skill 的刷新入口为准。
root 在 refresh_overview.py 顶部统一配置。主 skill、全局入口和 hook 命令需随根目录迁移一并调整。

维护脚本后运行：

```bash
cd ~/.codex/skills/coordination/scripts
/opt/miniconda3/bin/python -m unittest discover -s tests -v
```

测试使用独立临时目录及合成卡片，不创建真实业务工作项。
