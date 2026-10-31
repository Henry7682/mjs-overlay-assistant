# Git 与 GitHub 工作流

## 开始前

先读 AGENTS、TODO、TESTING，以及存在的 WORKSPACE。确认当前 checkout、remote、HEAD、分支和工作树；维护者私人根历史与公开仓库历史不同，不做整库同步。只在公开 checkout 修改业务代码，私人素材不得提交。

```powershell
git status --short
git remote -v
git branch -vv
git fetch origin
git log -5 --oneline
git rev-list --left-right --count origin/main...HEAD
```

fetch 失败时 origin/main 只是缓存，不能当作已核验远端。推送前重新核对 GitHub 状态，不强推、不关闭 TLS 校验。保留用户未提交修改，不使用 reset --hard、clean 或整库暂存来清空工作区。

## 分支、测试、提交

从已核验主线建立 codex/* 主题分支。不同问题不混入同一 PR；确实依赖其他功能时写明基线。源码启动用 start.cmd，记录显示版本、完整提交、dirty 与数据目录；便携用户用 launch.cmd。原有 data 不作为迁移试验目录。

修改结束更新 TODO/TESTING；单元、截图回放、小程序组件和完整实战分别记录，缺少实战不能靠 CI 关闭。提交前检查 diff 和隐私，只 git add 本轮明确文件；不提交截图、日志、运行配置、令牌及未授权第三方数据库。已推送提交追加修复，不改写共享历史。

## PR 和 main 保护

流程：主题分支 → 提交推送 → PR → 当前提交 CI → 合并 → 本地 main 快进。

main 要求 PR（0 人强制审批）、GitHub Actions 的 syntax/windows 成功、与主线同步、评审讨论解决；禁止强推和删除，不设日常绕过账户。管理员同样受规则约束，但仍能修改规则本身。不得为一次操作临时解除保护；权限或接口失败时保留 PR，报告阻点。

CI 包含语法、锁定依赖与模型、测试、Windows 构建和冻结自检。必须核对当前 SHA 的检查，不以旧绿灯替代。合并前核对 head/base、差异和权限；用户仅要求推送时，不推定允许合并或发行。

合并后读取 GitHub 合并结果，核验提交，再 git switch main / git merge --ff-only origin/main。分歧先排查，不强制重置。删除分支前确认已合并、无开放 PR 和未知新提交；保留未发布实验。一般撤销使用新 revert 提交。

## 版本与发行

数字 VERSION 与显示标识分开。源码显示数字-dev、提交短号和受跟踪修改状态；无 Git 显示未知。新增源码要及时纳入 Git，未跟踪文件不影响日常 dirty 不等于它们可以未经审查发布。

源码提交/合并不等于安装包已发布。下一次发行预计1.0.3，不覆盖已发布1.0.2标签、资产或旧清单。签名更新清单也经 PR；不得为方便发布直接推 main。GitHub 与 Gitee 分别验证，不将 push 视为镜像资产已同步。

发布操作见 [RELEASING](RELEASING.md)。默认构建是开发包；正式构建必须显式开启发行模式并校验干净标签及包内提交。更新验收、签名和不可变资产规则继续有效。

## 收尾记录

分别报告：已提交、已推送、已合并、已发布。记录开发目录、分支与 SHA、CI 对应 SHA、测试类别、待验收条目、是否改变安装版/Gitee。状态不明写未核验。维护者本地目录变化只写私人导航，公开文档不携带机器路径。
