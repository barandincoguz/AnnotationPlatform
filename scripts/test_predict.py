import requests
res = requests.get("http://127.0.0.1:8002/api/internal/predictions/pending?limit=4")
print(res.text)
