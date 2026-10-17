# 第三方代码与许可

本项目自身代码采用 MIT 许可，详见 `LICENSE`。

| 项目 | 用途 | 使用方式 / 许可 |
| --- | --- | --- |
| [guofei9987/blind_watermark](https://github.com/guofei9987/blind_watermark) | DWT-DCT-SVD、量化、分块置乱与重复嵌入 | 固定依赖 0.4.4；MIT |
| [tomerfiliba-org/reedsolomon](https://github.com/tomerfiliba-org/reedsolomon) | Reed–Solomon 纠错 | 依赖 reedsolo 1.7.0；分发附带许可见 `licenses/reedsolo-LICENSE.txt` |
| [python-pillow/Pillow](https://github.com/python-pillow/Pillow) | 文字绘制、照片读写、EXIF 处理 | 依赖；HPND |
| [numpy/numpy](https://github.com/numpy/numpy) | 数组处理 | 依赖；BSD-3-Clause |
| [opencv/opencv](https://github.com/opencv/opencv) | DCT、色彩转换和透视校正 | 依赖 opencv-python；OpenCV 4.5+ 核心为 Apache-2.0；wheel 的附带组件以其许可为准 |
| [PyWavelets/pywt](https://github.com/PyWavelets/pywt) | 小波变换 | 依赖；MIT |

`id_watermark/frequency.py` 中 `LumaCore.embed()` 和 `extract_raw()` 是对
`blind_watermark/bwm_core.py` 的改编，只写入和读取亮度通道。
保留上游版权 `Copyright (c) 2019 郭飞`，其完整 MIT 许可已放入
`licenses/blind-watermark-MIT.txt`。本项目采用其已有频域实现，没有将该算法作为原创。

可见水印使用 Pillow 直接实现。下列项目作为需求与功能调研参考，没有复制其源码：

- [mantoufan/id-watermark](https://github.com/mantoufan/id-watermark)：网页本地可见水印，MIT。
- [joyqi/sfz](https://github.com/joyqi/sfz)：网页本地可见水印，GPL-3.0。
- [ShieldMnt/invisible-watermark](https://github.com/ShieldMnt/invisible-watermark)：另一种频域水印实现，MIT。

本源码包不分发字体或第三方二进制程序；运行时使用系统字体或用户指定的字体。
若以后制作包含依赖的 exe 安装包，应同时带上实际打包版本及其组件的许可证。
