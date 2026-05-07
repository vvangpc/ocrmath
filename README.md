# ocrmath

> 自制 Mathpix Snipping Tool 替代品 — 调用 Mathpix API 实现截屏公式识别 + PDF 转 Markdown / DOCX。
> 用 pay-as-you-go 套餐替代月度订阅，按 100 张截图 / 月计算约 $0.20，比订阅档（$4.99-$19/月）便宜 90% 以上。

![Python](https://img.shields.io/badge/python-3.10%2B-blue) ![PyQt6](https://img.shields.io/badge/GUI-PyQt6-green) ![License](https://img.shields.io/badge/license-MIT-orange)

---

## 功能

| | |
|---|---|
| **截屏公式识别** | 全局快捷键唤起 → 鼠标拖选公式区域 → 自动识别 → 一键复制 LaTeX |
| **LaTeX 实时预览** | 结果窗口内置 MathJax 矢量渲染，所见即所得，支持中文混排 |
| **本地缓存** | SHA256 去重，相同区域第二次识别零成本零网络 |
| **历史记录** | 主窗口"历史记录"标签页：搜索 / 复制 / 重新打开 / 删除 |
| **PDF 转换** | 拖拽 PDF → 选输出格式（MMD/MD/DOCX/TeX/HTML/带文字层 PDF）→ 异步进度条 |
| **托盘常驻** | 关闭主窗口最小化到托盘；识别中托盘图标闪烁状态指示 |
| **可自定义快捷键** | 设置对话框中按下任意组合键即可记录 |
| **加密凭证存储** | Windows DPAPI 与当前用户绑定，明文不落盘 |

## 成本（来源：[Mathpix Pricing](https://mathpix.com/pricing/api)）

| 操作 | 单价 | 100 次/月 |
|---|---|---|
| 截屏识别 (`/v3/text`) | **$0.002 / 张** | $0.20 |
| PDF 转换 (`/v3/pdf`) | **$0.005 / 页** | $0.50（按 100 页） |

PAYG 一次性 $19.99 启动费。含 12 行以上文本的图像按 PDF 单价计费。

## 安装

### 方式 A：使用安装包（推荐普通用户）

1. 到 [Releases](https://github.com/vvangpc/ocrmath/releases) 下载最新 `ocrmath-setup-x.y.z.exe`
2. 双击安装，按提示完成
3. 启动菜单或桌面打开 **ocrmath**

### 方式 B：从源码运行（开发者）

需要 Python 3.10+（推荐 3.13）。

```powershell
git clone https://github.com/vvangpc/ocrmath.git
cd ocrmath
pip install -r requirements.txt
python main.py
```

## 申请 Mathpix API Key

1. 注册 [accounts.mathpix.com](https://accounts.mathpix.com/)
2. Console → API Keys 创建一组 `app_id` 和 `app_key`
3. Console → Billing 切换到 **Pay-as-you-go** 套餐
4. 启动 ocrmath，首次运行会弹窗让你填入凭证

## 使用

### 截屏识别

1. 按全局快捷键（默认 `Ctrl+Alt+M`）或点击托盘图标
2. 屏幕变暗后用鼠标拖选公式区域，松开
3. 等待 1-2 秒，结果窗口弹出
4. 点击行内 / 独立 LaTeX 旁的「复制」按钮即可粘贴
5. 复制后窗口自动关闭

### PDF 转换

1. 主窗口切到"PDF 转换"标签
2. 拖入 PDF 或点"选择 PDF…"
3. 勾选所需输出格式：
   - **MMD** — Mathpix Markdown，公式用 `$...$` 保留 LaTeX，适合 Typora / Obsidian
   - **MD** — 标准 Markdown，适合 GitHub / 通用编辑器
   - **DOCX** — Microsoft Word
   - **TeX zip** — LaTeX 源文件
   - **HTML** — 网页
   - **带文字层 PDF** — 原 PDF 但可选中复制文字
4. 输出目录默认与所选 PDF 同目录
5. 点"开始转换"，进度条流畅推进，完成后自动打开输出文件夹

### 历史记录

切到"历史记录"标签页，可：
- 搜索（300ms 节流）
- 单击双击行 → 重新打开结果窗口
- 复制 LaTeX
- 删除单条 / 清空整库

## 数据目录

```
%APPDATA%\ocrmath\
├── config.dat      # DPAPI 加密的凭证 + 快捷键
├── ocrmath.db      # SQLite：识别结果缓存与历史索引
└── cache\          # 截屏 PNG 文件（按 SHA256 前两位分桶）
    ├── ab\
    │   └── ab12...ef.png
    └── cd\...
```

## 项目结构

```
main.py            # 入口：托盘 + 全局热键 + 缓存查找 + 信号串联
main_window.py     # 主窗口（QTabWidget：截屏 / PDF / 历史）
snipper.py         # 全屏半透明截图 widget
result_window.py   # 截图结果展示窗（含 LaTeX 预览 + 缓存徽章）
pdf_panel.py       # PDF 转换 UI
history_panel.py   # 历史记录面板
image_client.py    # /v3/text 调用 + QThread worker
pdf_client.py      # /v3/pdf 提交/轮询/下载 + QThread worker
storage.py         # SQLite 缓存 + 历史 + PNG 文件管理
mathjax_view.py    # MathJax 3 + QWebEngineView 矢量渲染（首次启动从 jsdelivr 下载 ~1MB）
config.py          # DPAPI 加密读写 + 快捷键存储
settings_dialog.py # API key + 快捷键设置对话框
styles.py          # 全局 QSS 主题
```

## 自行打包

机器需安装 [Inno Setup 6](https://jrsoftware.org/isdl.php)。

```powershell
pip install pyinstaller
python -m PyInstaller build.spec
& "C:\Users\$env:USERNAME\AppData\Local\Programs\Inno Setup 6\ISCC.exe" installer.iss
```

输出在 `dist\installer\ocrmath-setup-x.y.z.exe`。

## API 烟雾测试（不打开 GUI）

```powershell
$env:MATHPIX_APP_ID = "your_app_id"
$env:MATHPIX_APP_KEY = "your_app_key"

python test_image_api.py path\to\equation.png
python test_pdf_api.py path\to\small.pdf
```

## 故障排查

| 现象 | 处理 |
|---|---|
| 启动报缺少 PyQt6 | `pip install -r requirements.txt` |
| 全局热键不生效 | `keyboard` 库被杀软拦截，可用主窗口按钮替代；或在设置中改其他组合键 |
| 401 / 403 | API Key 错，从托盘菜单 → 设置… 重填 |
| PDF 进度条卡 0% | 网络问题；查看 PDF 标签页底部日志 |
| LaTeX 预览空白 | 首次需联网下载 MathJax (~1MB) 至 `%APPDATA%\ocrmath\mathjax\`；如长时间空白请检查网络代理 |
| 多显示器截图错位 | 已按 `QGuiApplication.screens()` 多屏拼接，仍有问题请提 issue |

## 隐私说明

- 所有图像和 PDF **直接发送到 Mathpix**（HTTPS），ocrmath 不上传到其他服务器
- API 凭证用 Windows DPAPI 加密，与当前 Windows 用户账户绑定，他人复制走也解不开
- 识别结果缓存在本地 `%APPDATA%\ocrmath\ocrmath.db`
- Mathpix 会保留你提交的源 PDF 30 天，输出文件 90 天，详见 [Mathpix Privacy](https://mathpix.com/privacy)

## 贡献

欢迎 issue / PR。建议优先方向：
- 跨平台支持（macOS / Linux）— 目前 DPAPI 仅 Windows 可用，其他系统使用明文存储
- 自动粘贴到上一焦点窗口（参考 Mathpix Snip）
- 深色模式 QSS

## 许可

[MIT License](LICENSE)

## 致谢

- [Mathpix](https://mathpix.com/) — 提供出色的 OCR API
- [PyQt6](https://pypi.org/project/PyQt6/)
- [MathJax](https://www.mathjax.org/) — 矢量公式渲染
- [keyboard](https://github.com/boppreh/keyboard)
- [Inno Setup](https://jrsoftware.org/isinfo.php)

---

> 本工具与 Mathpix Inc. 无任何官方关联，仅为第三方 API 客户端。
