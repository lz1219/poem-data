"""核对目录、原卷题及固定维基修订。"""
from wikisource_source import main
import argparse
from pathlib import Path

if __name__ == '__main__':
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--cache', type=Path)
    main(p.parse_args().cache)
