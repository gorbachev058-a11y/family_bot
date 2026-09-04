import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pytest
from fastapi.testclient import TestClient
from web_api import app

client = TestClient(app)

def test_chat_endpoint():
    response = client.post("/chat", json={
        "message": "привет",
        "role": "Мужчина",
        "user_id": "test_user_123"
    })
    assert response.status_code == 200
    assert "response" in response.json()
    print("✅ Тест чата пройден")