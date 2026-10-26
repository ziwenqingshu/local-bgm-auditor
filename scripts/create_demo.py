"""生成原创合成参考曲和双曲视频；不会联网或自动导入用户曲库。"""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from bgm_audit.config import Paths
from bgm_audit.demo import create_demo

if __name__ == "__main__":
    output = create_demo(Paths().root)
    print(f"演示文件：{output}")
    print("导入两首 WAV 后，审核 MP4。预期：2–12 秒星河，12–22 秒远山（识别支持区间略短）。")
    print("这些文件由本脚本合成，可自由用于本项目测试，不代表真实商业音乐识别率。")
