# 资源更新工作流（后续维护 agent 入口）

业务源码仅在公开 checkout 内维护。先读 AGENTS、TODO、TESTING、GIT-WORKFLOW；读取本地 WORKSPACE 查找私人证据。默认维护机没有 VPN：必须独立验证 Gitee，GitHub失败不能被解释为两端均失败。

## 一次手动更新

在项目根目录使用独立环境执行：

```powershell
.\.venv\Scripts\python.exe -X utf8 tools/maintain_data.py --publish --force
```

这是会发布签名数据的维护命令，不是玩家命令。发布前确认用户已授权资源更新、SSH凭据有效、签名私钥在仓库外且可用。不得打印私钥或令牌。

工具按模式检查官方榜单、全量归档组合网页，验证后分别推送两端数据分支；原始材料在 `.research/maintenance/official-state`、`.research/jiangce/日期`。先查看 `.research/maintenance/status.json`，已有任务时等待；禁止同时运行两个发布者。任务锁冲突不是数据更新成功。

逐项核对报告的 official、guides、boards-GitHub/Gitee、guides-GitHub/Gitee；success的含义是该检查执行成功，仍需检查 pending_count、真实数据周期、条数。确认 finished 存在，记录最后成功及失败原因。网络失败保留有效旧数据，再按失败渠道重试。

## 榜单待复核

1. 找到 `official-state/boards/<模式>/pending.json` 和其中 image_path 原图，核验原图 SHA256、官方出处、模式和周期。
2. 不修改 pending 原件；复制到本轮证据目录。核对 raw_win_rows/raw_pick_rows 的缺号、重复、疑点姓名、分数及真实表格底边。两侧同时漏行时不能用最大排名自证完整。
3. 只依据原图更正；保留修正前后记录与局部证据，使用 `assemble_rows` 重建英雄字段。姓名和数值不能按邻行猜。未知姓名须有独立双榜证据；待确认模式不得强行归类。
4. `validate_board` 必须返回空；自动完整性失败后，人工核对确实完整方可写入明确标记为 `manual-image-review` 的完整性证据，不能伪造 OCR 置信度或称其为自动核验成功。
5. 通过 `BoardStore.install` 安装到维护目录，保留previous；把已验证各模式快照放入独立输入目录，再执行：

```powershell
.\.venv\Scripts\python.exe tools/prepare_boards.py <已核验JSON目录> <候选通道目录>
.\.venv\Scripts\python.exe tools/publish_jiangce.py <候选通道目录> Gitee --kind boards
.\.venv\Scripts\python.exe tools/publish_jiangce.py <候选通道目录> GitHub --kind boards
```

只编辑私人候选，不能覆盖已发布不可变文件。相同周期修订必须注明所替换的原图哈希和官方修订依据。排名合法增减不以历史人数拒绝，仍须两榜完整证据。

## 只更新组合库

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File tools/sync-jiangce.ps1 -Publish
```

核对分页两遍一致、唯一详情数等于入库数、未知姓名清单、站位与评分对应。内容未变保留版本号。原始HTML只在维护端；用户个人编辑不进入签名库，也不上传。发布者不得收集用户 custom-guides.json。

## 验收与回退

- 两端匿名下载 channel.json、channel.sig 和不可变数据文件；分别验RSA、大小、SHA256、SQLite/榜单结构。SSH推送成功不等于匿名客户端可用。
- 用隔离目录运行 `jiangce_update.DailyCheck` / `board_channel.discover`，模拟GitHub不可达并关闭测试进程代理，确认Gitee可独立获取。不要修改系统代理或真实用户data用于故障注入。
- 记录维护版数据与客户端实际装载版本；组合库下一局生效，不能因当前缓存尚旧判定更新失败。
- 若发布后发现内容错误，不覆盖旧文件或强推历史。生成新版本，记录更正原因；在客户端验证前继续保留可用旧数据。
- 数据更新无需软件Release。业务解析器/模式算法修改必须PR和测试，下一次软件发行才能送达玩家。
- 软件发行另见 RELEASING.md。普通玩家入口为 launch.cmd；源码版只提示软件更新，不覆盖Git目录。

## 定时任务

`tools/install-data-task.ps1 -CheckOnly` 检查本机任务。注册需维护者明确授权；默认05:00、登录补跑、不唤醒。电脑离线/账号未登录/源站限制都可能导致维护延迟。保留每次 run-*.json，区分因同日成功跳过、锁冲突、部分发布和完整成功。

结束更新TODO/TESTING和私人WORKSPACE；原图/日志不提交。后续agent务必读取最近的失败证据，不因为本次人工补齐而关闭自动解析缺口。
