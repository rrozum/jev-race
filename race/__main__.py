import argparse
import uvicorn

parser = argparse.ArgumentParser(description="Запуск Jev Race без базы данных")
parser.add_argument("--host", default="127.0.0.1")
parser.add_argument("--port", type=int, default=8080)
args = parser.parse_args()
uvicorn.run("race.app:create_app", factory=True, host=args.host, port=args.port,
            access_log=False, log_level="warning")
