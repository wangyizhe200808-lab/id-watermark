# 证件双水印 · Local ID Watermark

一个本地运行的 Python 桌面工具，为身份证等照片添加可见用途声明和可校验的频域水印。
支持两种水印分别使用或同时使用，也提供命令行接口。运行软件时不联网、不上传照片。

默认内容已经设为：

- **可见水印：**`仅限办理供热入户手续使用`
- **频域水印：**`仅限办理供热入户手续使用，2026年10月`

**打印、扫描或复印后能否提取，必须用具体设备验证。本项目没有经过真实纸面链路测试，
不承诺复印后仍可恢复。** 可见水印承担纸面用途声明；频域水印是附加的可恢复标记。
文件 `docs/robustness_results.json` 只记录虚构样图的数字实验。

## 快速启动（Windows）

1. 安装 **64 位 Python，建议 3.12**（最低 3.10），安装时保留 Tcl/Tk 支持。
2. 解压后双击 `install_windows.bat`，首次安装依赖需要联网。
3. 之后双击 `start_windows.bat`，照片处理在本机完成，可以断网运行。

也可以在 PowerShell 中执行：

```powershell
py -3 -m venv .venv
.\.venv\Scripts\python.exe -m pip install .
.\.venv\Scripts\python.exe app.py
```

不需要激活 PowerShell 脚本，因此不涉及更改执行策略。
本次在 Linux / Python 3.12 上验证了算法和命令行；Windows 有启动脚本和 CI 配置，
仍需在实际 Windows 电脑运行确认。当前执行环境无法建立图形显示连接，
因此桌面界面尚未实际运行验收。

macOS / Linux：

```bash
python3 -m venv .venv
.venv/bin/python -m pip install .
.venv/bin/python app.py
```

Linux 可能需要安装系统的 `python3-tk` 和中文字体，例如 Noto Sans CJK。
如果界面提示未找到字体，点击「中文字体…」选择 `.ttf`、`.ttc` 或 `.otf` 文件。
Windows 默认识别微软雅黑 / 黑体，macOS 默认识别苹方。

## 添加水印

1. 选择照片。若准备以后从纸面恢复，建议先把原图裁成完整证件范围，再导入软件。
2. 分别勾选可见水印、频域水印，默认两者都开启。
3. 可见水印可选平铺或单处放置，调整字号、颜色、角度、透明度、水平 / 垂直间距。
   平铺时位置滑块移动整个图案；单处放置时移动文字所在位置。
   如需纸面溯源，建议勾选「附加可见副本编号」，即使频域信息丢失也可尝试人工核对编号。
   默认不勾选，因此默认可见文字仍严格为上面的用途声明。
4. 频域水印默认「增强」，需要纸面试验时可选更强的档位，但图像失真会增加。
5. **保存提取密码。** 软件启动时随机生成密码，也可自行修改，至少 8 位。
   密码不写入图片或提取凭据。
6. 按实际外发对象填写接收方备注，每次导出自动生成不同的 16 位十六进制副本编号。
7. 导出 PNG。软件先画可见水印，再写入频域水印，最后执行提取校验；
   若无法从实际量化后的像素恢复正确文字，则报告失败。

导出结果：

| 文件 | 用途 |
| --- | --- |
| `xxx.png` | 发给办理手续的接收方 |
| `xxx.png.receipt.json` | 本人保留的提取参数、编号、接收方备注、时间与文件 SHA-256 |
| 提取密码 | 另行保存在密码管理器等安全位置，软件不自动写入文件 |

只需外发 PNG。原图保持原样；软件拒绝覆盖所选原图。
导出的图片移除原始 EXIF / GPS / 缩略图等元数据，水印是直接写入像素的。
导出后的 `300 DPI` 是文件分辨率提示，不代表图像细节得到提高，也不保证打印比例。

预览只展示可见水印。频域水印可能带来细小纹理或亮度变化，导出后请放大检查，
确保人像、姓名和号码等办理所需内容清楚。过淡的可见水印在复印时也可能丢失。

## 提取与扫描件校正

进入「提取 / 扫描件校正」，选择待提取图片、对应的 `.receipt.json`，输入密码。

- 原始导出 PNG：直接提取，无需原始照片。
- 等比例缩放且没有裁切的完整图像：软件恢复到凭据记录的尺寸后尝试提取。
- 带纸张背景、旋转或透视的扫描 / 拍照图像：按左上、右上、右下、左下顺序点击
  **整张外发图像**的四个角，先透视校正再提取。
- 如果原始照片有背景，不能仅点击身份证四角而遗漏原来的背景；坐标系必须对应。
- 四角校正用于恢复坐标，不保证足够准确，也不能恢复复印丢失的频率细节。

提取成功时必须同时通过 Reed–Solomon 纠错、格式检查和 HMAC 完整性验证。
失败时不会把本地凭据里的备注或预设文字当成提取结果。
提取界面将「接收方备注」标明为来自本地凭据，它不是从照片解出的内容。

**必须保留对应凭据和密码。** 这里的「盲提取」指不需要原图，不是无参数识别。
目前没有提供丢失凭据后的自动全库搜索，也没有自动纠正任意裁切、旋转、平移的能力。

## 实际可达到的溯源范围

每次导出嵌入完整用途文字和随机副本编号。编号与本人保留的接收方记录对应，
可帮助识别某张恢复成功的图片来自哪次外发；对不同接收方请分别导出。
同一张已导出图片转发给多个人，则无法再区分这些接收方。
对打印 / 复印件，附加可见编号比仅依靠频域提取更容易核对；它仍可能被遮挡或去除。

水印不能防止复制、重拍、人工重绘或针对性去除。它不是照片加密，不能阻止读取证件内容。
HMAC 用于拒绝错误提取，不是公钥数字签名；持有密码的人可以制作新水印，
本地凭据和时间也可被修改，因此结果不是不可伪造的归属、身份或司法证据。

真实纸面验证建议按拟用流程做一次：导出 → 打印 → 扫描 → 提取，
再增加一次复印后重复检查；记录打印缩放、DPI、彩色 / 灰度模式和设备型号。
二值黑白复印、强阈值化、小尺寸证件图、低清重拍、局部裁切和数次复印很可能破坏水印。
手机拍摄还会引入透视、镜头畸变和照明不均。

## 频域方法与开源复用

本项目复用 [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark)
的 DWT-DCT-SVD 核心，而不是只在 FFT 图里写字。变换域量化和重复编码用于从像素恢复比特。

新增部分：

- 只在亮度通道写入，减少不必要的色偏；便于灰度图中尝试恢复。
- UTF-8 用途文字、独立副本编号组成版本化数据包。
- 每个 RS 码字附加 48 字节纠错，单个码字可纠正最多 24 个错误字节。
- PBKDF2-HMAC-SHA256 派生参数，使用随机 salt；另加 128 位 HMAC 标签检查恢复结果。
- 沿用上游 NumPy 置乱，其种子仍只有 32 位，**不能据此宣称频域水印具备密码学保密性**。
- 导出前回读像素自检、PNG 导出、EXIF 清除、凭据管理与四角透视恢复。

工程上优先保留高分辨率原图。容量不足会拒绝写入，至少要求每位信息重复 4 次；
重复更多也不代表纸面恢复一定成功。两种水印均可修改文字。

其他 GitHub 参考：

| 仓库 | 适用范围 | 与本需求的关系 |
| --- | --- | --- |
| [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) | Python 频域盲水印，MIT | 本项目直接复用的算法核心 |
| [mantoufan/id-watermark](https://github.com/mantoufan/id-watermark) | 网页本地证件可见水印，MIT | 可见水印功能参考，不包含本项目频域流程 |
| [joyqi/sfz](https://github.com/joyqi/sfz) | 网页本地可见水印，GPL-3.0 | 适合单独加可见水印，没有复制其代码 |
| [ShieldMnt/invisible-watermark](https://github.com/ShieldMnt/invisible-watermark) | Python DWT/DCT 等，MIT | 备选；作者明确提示缩放 / 裁切鲁棒性限制 |

没有核实到一个可直接保证「可调可见水印 + 完整中文频域文字 + 任意打印复印溯源」的现成项目。
完整第三方声明与保留的许可见 `THIRD_PARTY_NOTICES.md`、`licenses/`。

## 命令行

```bash
# 默认同时写入两种水印；不传密码时用 getpass 安全询问
python -m id_watermark embed private/id.jpg output/heat.png --recipient "供热办理接收方A"

# 只加可见水印，无需密码
python -m id_watermark embed private/id.jpg output/visible.png --mode visible --font-size 36 --gap-y 50

# 只加频域水印
python -m id_watermark embed private/id.jpg output/hidden.png --mode hidden --strength strong

# 提取完整中文文字和副本编号
python -m id_watermark extract output/heat.png output/heat.png.receipt.json

# 指定扫描图中的完整导出图像四角坐标
python -m id_watermark extract private/scan.jpg output/heat.png.receipt.json --corners 100 80 1699 80 1699 1079 100 1079
```

自动化调用可用 `--password-env IDWM_PASSWORD` 从进程环境变量读取密码，
不提供明文 `--password` 命令行参数，以免密码写入命令历史或暴露在进程列表。

公开演示材料位于 `examples/`，没有真实证件信息。其公开测试密码是
`DEMO-only-not-for-private-use`，配合 `examples/demo_receipt.json` 使用。

```bash
python -m id_watermark extract examples/sample_marked.png examples/demo_receipt.json
```

## 开发、验证和发布

```bash
python -m pip install -e ".[dev]"
python -m pytest -q
python -m ruff check .
python -m scripts.make_demo
python -m scripts.robustness_demo
```

测试覆盖完整中文提取、纠错、错误密码、未标记图片的否定结果、灰度、
原图保护、EXIF 清除、可见水印位置 / 密度以及四角恢复。
GitHub Actions 配置包含 Windows / Ubuntu 和 Python 3.10 / 3.12；配置不代表已经在远端跑过。

项目按 MIT 许可整理，可以作为后续 GitHub 仓库起点。
将真实照片放在 `private/`，输出放在 `output/`；两者以及提取凭据已被 `.gitignore` 排除。
图片默认忽略，仅放行包内虚构样图和软件示意截图。提交前检查 `git status`。
本次只提供源码，没有上传 GitHub，也没有打包或验证 Windows exe。
