import requests
import json
res = requests.post(
    "http://127.0.0.1:8002/api/annotations/17g6am0v7r1dpj/pre-audit",
    json={"references": []},
    headers={"Cookie": "session_token=123"}
)
print(res.status_code)
print(res.text)
