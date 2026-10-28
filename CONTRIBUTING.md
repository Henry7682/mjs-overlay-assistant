# 参与开发与测试

当前为 1.0.0 发布准备阶段，发布状态见 [docs/RELEASE_STATUS.md](docs/RELEASE_STATUS.md)。

1. 修改前阅读 `AGENTS.md`、`TODO.md` 和相关 `TESTING.md` 记录。
2. 使用独立分支与 Python 3.11 x64 虚拟环境，避免污染系统 Python。
3. 提交时说明问题、实现、测试证据和仍未验证的场景。
4. 修改结束更新 TODO；单元测试、截图回放、小程序组件测试和完整实战分别记录。
5. 不提交私人截图、日志、配置、账号信息或第三方攻略数据库。脱敏裁片也须人工检查。

先运行 `powershell -NoProfile -ExecutionPolicy Bypass -File .\setup.ps1 -Development`，再运行 `.venv\Scripts\python.exe -X utf8 -m pytest -q`。该入口使用开发哈希锁、独立虚拟环境和模型校验。部分测试需要本地 OCR 模型；公开仓库不包含私人实战素材，不能以缺样本为由宣称实战通过。发布流程见 [发布维护](docs/RELEASING.md)。

代码采用 GPL-3.0-only。提交贡献前请确认你有权按该许可提供相关代码；第三方素材必须注明来源及其独立许可。
