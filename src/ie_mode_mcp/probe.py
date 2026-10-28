import argparse
import json
import sys

from .browser import Browser, doctor


def main():
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    parser = argparse.ArgumentParser(description="Diagnose or interactively inspect Edge IE mode")
    parser.add_argument("url", nargs="?")
    args = parser.parse_args()
    print(json.dumps(doctor(), ensure_ascii=False, indent=2))
    if not args.url:
        return
    browser = Browser()
    try:
        print(json.dumps(browser.start(args.url), ensure_ascii=False, indent=2))
        while input("Log in manually. Enter = snapshot; q + Enter = close: ").strip().lower() != "q":
            try:
                print(json.dumps(browser.snapshot(), ensure_ascii=False, indent=2))
            except Exception as error:
                print(f"Snapshot failed ({type(error).__name__}). Session retained; retry or q to close.")
    finally:
        browser.close()


if __name__ == "__main__":
    main()
