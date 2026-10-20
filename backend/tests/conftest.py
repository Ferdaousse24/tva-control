import os, sys, tempfile
from pathlib import Path

TMP = tempfile.mkdtemp(prefix="tva-test-")
os.environ["DATA_DIR"] = TMP
# Pour tester sur PostgreSQL : définir DATABASE_URL avant de lancer pytest (sinon SQLite temporaire)
os.environ.setdefault("DATABASE_URL", f"sqlite:///{TMP}/test.db")
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import pytest
from fastapi.testclient import TestClient


@pytest.fixture()
def client():
    from app.main import app
    from app.db import Base, engine
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    return TestClient(app)
