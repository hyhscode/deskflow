import pathlib
import sys

PROJECT_ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

import app.models  # noqa: F401,E402  导入后模型才登记进 metadata
from app.db.session import SessionLocal          # noqa: E402
from app.services.vector_search import build_index  # noqa: E402


def main() -> None:
    db = SessionLocal()
    try:
        count = build_index(db)
        print(f"索引重建完成：{count} 条知识")
    finally:
        db.close()


if __name__ == "__&#8203;main__":
    main()