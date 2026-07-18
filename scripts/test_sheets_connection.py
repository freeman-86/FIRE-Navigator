import gspread
from google.oauth2.service_account import Credentials

# 鍵ファイルを使って認証する
SCOPES = ["https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive.readonly"]
creds = Credentials.from_service_account_file("secrets/gsheets_credentials.json", scopes=SCOPES)
client = gspread.authorize(creds)

# テスト用スプレッドシートを開く
sheet = client.open("FIRE-Navigator-test").sheet1

# A1セルを読み込む
value = sheet.acell("A1").value
print(f"A1の現在の値: {value}")

# 2倍にしてA2セルに書き込む
doubled = float(value) * 2
sheet.update_acell("A2", doubled)
print(f"A2に書き込みました: {doubled}")