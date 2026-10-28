# 第三方组件与模型

本项目独立实现；未复制 `CXH0920/mjs_agent_project` 的代码或训练数据。

依赖完整版本在 `requirements.lock.txt`。便携包使用 Python 3.11、PySide6 / Qt、OpenCV、NumPy、RapidOCR、ONNX Runtime、windows-capture、Pillow、httpx、BeautifulSoup 等。各分发包附带的许可、版权与通知文件保存在 `_internal/assets/licenses/`（源码为 `assets/licenses/`），请连同便携目录保留。

模型来自 RapidOCR 3.10.0 的官方默认模型注册表；上游为 PaddleOCR，权重归 Baidu / 相应 PaddleOCR 权利人。模型未经重新训练，仅重命名为固定本地文件：

| 本地文件 | RapidOCR 原名 |
| --- | --- |
| det.onnx | PP-OCRv6_det_small.onnx |
| rec.onnx | PP-OCRv6_rec_small.onnx |
| cls.onnx | ch_ppocr_mobile_v2.0_cls_mobile.onnx |

SHA-256 与大小记录在 `assets/models/manifest.json`。RapidOCR 的 `MODEL_LICENSES.md` 和 `LICENSE` 一同随包附带，包含上游地址与模型转换说明。

PySide6 / Qt 使用动态链接库，原有 DLL 保留独立文件；本项目未修改其源码。相应版本源码和许可可从 [Qt for Python](https://code.qt.io/cgit/pyside/pyside-setup.git/) 及 [Qt](https://code.qt.io/) 获取。

《名将杀》的名称、角色、榜单原图及相关素材归各自权利人。本助手不代表游戏官方。用户的实战截图不打入分发包。

0.2 的 Windows 界面自动化使用 pywinauto 0.6.9、comtypes 1.4.17、pywin32 312。仅操作“名将小助手”的公开界面；推荐内容属于小程序及相应作者，不是本助手自有数据库，也不代表合作或官方授权。推荐结果只保留于当前局内存，不随源码或便携包分发。
