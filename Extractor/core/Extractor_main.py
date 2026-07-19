import os
import sys
from pathlib import Path
import yaml

PROJECT_ROOT = Path(__file__).resolve().parents[2]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from project_config import EXTRACTOR_CONFIG_FILE, EXTRACTOR_OUTPUT_ROOT, EXTRACTOR_REPORT_ROOT, EXTRACTOR_RUNTIME_ROOT

BASE_DIR = EXTRACTOR_RUNTIME_ROOT
os.chdir(BASE_DIR)
if str(BASE_DIR) not in sys.path:
    sys.path.insert(0, str(BASE_DIR))

from rich.console import Console
from rich.panel import Panel
from extractor.extract_processor import ExtractProcessor

console = Console()

# 酷炫的 ASCII 字符画 Logo
# FORGE_LOGO = """
# [bold cyan]
#  ██╗  ██╗ █████╗  ██████╗██╗  ██╗███████╗██████╗
#  ██║  ██║██╔══██╗██╔════╝██║ ██╔╝██╔════╝██╔══██╗
#  ███████║███████║██║     █████╔╝ █████╗  ██████╔╝
#  ██╔══██║██╔══██║██║     ██╔═██╗ ██╔══╝  ██╔══██╗
#  ██║  ██║██║  ██║╚██████╗██║  ██╗███████╗██║  ██║
#  ╚═╝  ╚═╝╚═╝  ╚═╝ ╚═════╝╚═╝  ╚═╝╚══════╝╚═╝  ╚═╝
# [/bold cyan]"""
TAGLINE = "[green]PDF Hacker Attack & Incident Extractor[/green]"


def display_header():
    console.print(Panel(f"{TAGLINE}", border_style="cyan", expand=False))


if __name__ == "__main__":
    display_header()

    with EXTRACTOR_CONFIG_FILE.open("r", encoding="utf-8") as file:
        runtime_config = yaml.safe_load(file) or {}
    EVENT_NAME = os.getenv("RISKTAGGER_EVENT_NAME") or runtime_config.get("runtime", {}).get("event_name", "Bybit")

    if not EVENT_NAME:
        console.print("[bold red]❌ 事件名称不能为空，程序退出。[/bold red]")
        sys.exit(1)

    # 基础报告存放目录
    BASE_REPORT_DIR = EXTRACTOR_REPORT_ROOT

    # 自动拼接 PDF 绝对路径：例如 report/bybit/bybit_report.pdf
    #TARGET_PDF = os.path.join(BASE_REPORT_DIR, EVENT_NAME, f"{EVENT_NAME}_report.pdf")
    report_dir = BASE_REPORT_DIR / EVENT_NAME
    if not report_dir.exists():
        report_dir = BASE_REPORT_DIR / EVENT_NAME.lower()
    TARGET_PDF = report_dir / f"{report_dir.name}_report.pdf"
    # 自动拼接输出目录：例如 ./output/bybit/
    OUTPUT_DIR = EXTRACTOR_OUTPUT_ROOT / EVENT_NAME
    CONFIG_PATH = EXTRACTOR_CONFIG_FILE

    # 检查目标文件是否存在
    if not os.path.exists(TARGET_PDF):
        console.print(f"[bold red]❌ 找不到指定的 PDF 文件: {TARGET_PDF}[/bold red]")
        console.print(f"[yellow]请确保文件已重命名为 '{EVENT_NAME}_report.pdf' 并放入了对应文件夹。[/yellow]")
        sys.exit(1)

    console.print(f"\n[bold green]🚀 当前指定事件:[/bold green] {EVENT_NAME}")
    console.print(f"[bold green]📄 正在读取文件:[/bold green] {TARGET_PDF}")
    console.print(f"[bold green]📁 输出至目录:[/bold green] {OUTPUT_DIR}\n")

    # 初始化并运行提取器
    try:
        processor = ExtractProcessor(TARGET_PDF, OUTPUT_DIR, CONFIG_PATH)
        processor.run()
    except Exception as e:
        console.print(f"[bold red]运行出错: {str(e)}[/bold red]")
