import urllib.request
import urllib.error
import json

req = urllib.request.Request(
    "http://127.0.0.1:8000/api/annotations/4ile76x41d146v/pre-audit",
    data=b'{"references": []}',
    headers={"Content-Type": "application/json", "Cookie": "session_token=123"},
    method="POST"
)
try:
    with urllib.request.urlopen(req) as response:
        print(response.status)
        print(response.read().decode('utf-8'))
except urllib.error.HTTPError as e:
    print(e.code)
    print(e.read().decode('utf-8'))
