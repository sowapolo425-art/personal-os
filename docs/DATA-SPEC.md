# 数据规范 v0.1

当前记录的权威数据为 UTF-8 Markdown。头部用 `---` 分隔，中间采用 JSON 对象；JSON 是 YAML 的合法子集，便于一般 Markdown 工具阅读。不依赖数据库或外部检索服务。

| 字段 | 含义 |
|---|---|
| id | 32 位十六进制 UUID，文件名相同 |
| title / kind | 标题与固定类型，kind 决定目录 |
| created_at / updated_at | UTC ISO 时间 |
| revision | 从 1 开始的版本号 |
| source | 来源说明，不声称已验证来源真实性 |
| source_ids | 草稿结论关联的本地证据 ID |
| status | self_report：自我报告；confirmed：本地已审核；imported_source：导入原始资料，不代表确认其中的说法 |
| sensitivity | private：可被当前 Agent 读取；restricted：默认隐藏 |
| tags | 用户或 Agent 提供的标签 |

导入记录另有 import_hash 和 imported_at；v0.4.1 增加 import_key 和 import_locator，按来源及会话/页码/片段位置去重，兼容旧记录。带可靠时区/时间戳的对话保留 source_created_at，并将原始时间用于时间线。七天积累图使用导入时间，体现实际新增到资料库的时间。未知原始日期使用本次保存时间，不猜测日期。

草稿的 record 字段是候选内容，其 status 只有在草稿 state=approved 并写入正式目录后才有效。待确认内容只存在 `.personal-os/proposals`，不出现在正式检索结果中。Agent 不能通过 MCP 批准草稿。

v0.4.1 草稿另存 source_revisions（来源 ID 到版本号），审核拒绝来源被删除或变更。旧草稿没有此字段仍可读取，审批时继承来源的受限级别。文件和聊天原文不能通过结论提案更新覆盖，提取结果创建独立记录并引用原文。

## 类型

record / thought / event / profile / goal / project / decision / knowledge。
profile 必须先提案；其余类型可记录用户原文。任何已有记录的更新都必须提案。
工具不限制 Agent 误选其他类型，因此档案语义仍需遵守交互协议。

## 并发与历史

库级操作系统文件锁串行化 MCP 进程读写；单文件临时写入、刷新后替换。
更新先写历史快照，再更新当前 Markdown。草稿审批检查版本冲突。
多个文件间没有数据库级原子事务：突然断电可能留下额外快照，或已更新记录而审批状态未落盘。请检查最新记录与草稿状态后处理，勿盲目重试覆盖。

每次写入、读取、检索、提案、审核、删除、恢复产生最少审计事件，仅有时间、动作、ID，没有正文。审计可编辑，不是防篡改的安全日志。

手工修改不自动生成版本，不保证并发一致性。普通自建 Markdown 不自动导入，工具仅检索合法 ID 文件。初版搜索按包含关系匹配正文、标题和标签，返回最近更新优先，未使用向量检索。
