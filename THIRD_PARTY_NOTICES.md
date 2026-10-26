# 第三方组件

本项目自身代码采用 MIT 许可证；各第三方组件保留自己的许可证。

- audfprint：https://github.com/dpwe/audfprint，MIT。源码完整保留在 `vendor/audfprint`，包含上游 LICENSE。固定提交 `cb03ba99feafd41b8874307f0f4e808a6ce34362`，未修改上游算法。
- Streamlit：https://github.com/streamlit/streamlit，Apache-2.0。
- FFmpeg：https://ffmpeg.org/legal.html，LGPL / GPL，具体取决于本机发行包编译选项；安装脚本使用系统包管理器，不将 FFmpeg 二进制重新打包。
- NumPy / SciPy：BSD；SQLite：公有领域；filelock：Unlicense；psutil：BSD-3-Clause；pytest：MIT。
- 可选 ShazamIO：https://github.com/shazamio/ShazamIO，MIT（0.9.0）；客户端开源，所连接的 Shazam 服务并非开源。严格开源离线流程无需安装或启用此组件。

第三方源码中的版权头、许可证和 NOTICE 优先于本摘要。参考音乐及其版权和授权材料由使用者自行提供；软件许可证不会授予参考音乐的使用权。
