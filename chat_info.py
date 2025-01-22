import json

url = "https://bot-open-api.bytedance.net/v3/chat/message/list"
method = "GET"
headers = {
    "Content-Type": "application/json",
    "Authorization": "Bearer pat_ph9Vf1uzPNUwwjNM0dVkpFDstDSanaelT1RKaxIzrrU9zORntvjoUyvkLDo2tTBM"
}

conversation_id = "7462385578504470565"
chat_id = "7462385578504486949"

import requests

response = requests.get(url, headers=headers, params={"conversation_id": conversation_id, "chat_id": chat_id})
print(json.dumps(response.json(), ensure_ascii=False))