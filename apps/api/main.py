import argparse

import uvicorn

from lawcopilot_api import create_app

app = create_app()


def main() -> None:
    parser = argparse.ArgumentParser(description="LawCopilot API")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", default=18731, type=int)
    args = parser.parse_args()
    uvicorn.run(app, host=args.host, port=args.port, reload=False)


if __name__ == "__main__":
    main()
