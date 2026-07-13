import os
import sys
import json
import datetime
import webbrowser
import http.server
import urllib.parse
import requests

CREDENTIALS_PATH = "/Users/kanri/Documents/ClaudeCode/credentials.json"
TOKEN_PATH = "/Users/kanri/Documents/ClaudeCode/google_health_token.json"
REDIRECT_PORT = 8080
REDIRECT_URI = f"http://localhost:{REDIRECT_PORT}"
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly"
]

authorization_code = None

class OAuthHandler(http.server.BaseHTTPRequestHandler):
    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        query = urllib.parse.parse_qs(parsed.query)
        if 'code' in query:
            global authorization_code
            authorization_code = query['code'][0]
            self.send_response(200)
            self.send_header('Content-Type', 'text/html; charset=utf-8')
            self.end_headers()
            self.wfile.write("認証が完了しました。このブラウザタブを閉じて、ターミナルに戻ってください。".encode('utf-8'))
        else:
            self.send_response(400)
            self.end_headers()

    def log_message(self, format, *args):
        pass

def run_local_server():
    server = http.server.HTTPServer(('localhost', REDIRECT_PORT), OAuthHandler)
    server.handle_request()

def do_oauth_flow():
    if not os.path.exists(CREDENTIALS_PATH):
        print(f"Error: {CREDENTIALS_PATH} が見つかりません。")
        print("Google Cloud ConsoleからダウンロードしたOAuthクライアントのJSONファイルを、上記パスに配置してください。")
        sys.exit(1)

    with open(CREDENTIALS_PATH, 'r') as f:
        creds = json.load(f)
    
    client_key = 'installed' if 'installed' in creds else 'web'
    client_id = creds[client_key]['client_id']
    client_secret = creds[client_key]['client_secret']
    auth_uri = creds[client_key].get('auth_uri', 'https://accounts.google.com/o/oauth2/v2/auth')
    token_uri = creds[client_key].get('token_uri', 'https://oauth2.googleapis.com/token')

    params = {
        'client_id': client_id,
        'redirect_uri': REDIRECT_URI,
        'response_type': 'code',
        'scope': ' '.join(SCOPES),
        'access_type': 'offline',
        'prompt': 'consent'
    }
    url = f"{auth_uri}?{urllib.parse.urlencode(params)}"

    print("ブラウザを開いてGoogle Health API認証を行います...")
    print(f"URL: {url}")
    webbrowser.open(url)

    run_local_server()

    if not authorization_code:
        print("Error: 認可コードの取得に失敗しました。")
        sys.exit(1)

    token_data = {
        'code': authorization_code,
        'client_id': client_id,
        'client_secret': client_secret,
        'redirect_uri': REDIRECT_URI,
        'grant_type': 'authorization_code'
    }
    
    response = requests.post(token_uri, data=token_data)
    if response.status_code != 200:
        print(f"Error swapping token: {response.text}")
        sys.exit(1)
    
    tokens = response.json()
    tokens['client_id'] = client_id
    tokens['client_secret'] = client_secret
    tokens['token_uri'] = token_uri

    os.makedirs(os.path.dirname(TOKEN_PATH), exist_ok=True)
    with open(TOKEN_PATH, 'w') as f:
        json.dump(tokens, f, indent=2)
    
    print(f"✅ Google Health API の認証情報が保存されました: {TOKEN_PATH}")

def get_access_token():
    if not os.path.exists(TOKEN_PATH):
        print(f"Error: {TOKEN_PATH} が存在しません。まず --auth を実行して認証を行ってください。")
        sys.exit(1)

    with open(TOKEN_PATH, 'r') as f:
        tokens = json.load(f)

    refresh_data = {
        'client_id': tokens['client_id'],
        'client_secret': tokens['client_secret'],
        'refresh_token': tokens['refresh_token'],
        'grant_type': 'refresh_token'
    }

    response = requests.post(tokens.get('token_uri', 'https://oauth2.googleapis.com/token'), data=refresh_data)
    if response.status_code != 200:
        print(f"Error refreshing token: {response.text}")
        sys.exit(1)

    new_tokens = response.json()
    tokens['access_token'] = new_tokens['access_token']
    if 'refresh_token' in new_tokens:
        tokens['refresh_token'] = new_tokens['refresh_token']
    
    with open(TOKEN_PATH, 'w') as f:
        json.dump(tokens, f, indent=2)

    return tokens['access_token']

def get_health_data(target_date_str):
    access_token = get_access_token()
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # 1. 体重データの取得
    weight_url = "https://health.googleapis.com/v4/users/me/dataTypes/weight/dataPoints"
    weight = None
    try:
        weight_response = requests.get(weight_url, headers=headers)
        if weight_response.status_code == 200:
            weight_data = weight_response.json()
            if "dataPoints" in weight_data:
                for dp in weight_data["dataPoints"]:
                    w_obj = dp.get("weight", {})
                    sample_time = w_obj.get("sampleTime", {})
                    civil_date = sample_time.get("civilTime", {}).get("date", {})
                    if civil_date:
                        dp_date_str = f"{civil_date.get('year'):04d}-{civil_date.get('month'):02d}-{civil_date.get('day'):02d}"
                        if dp_date_str == target_date_str:
                            grams = w_obj.get("weightGrams")
                            if grams:
                                weight = round(grams / 1000, 2)
    except Exception as e:
        print(f"Warning: 体重データの取得・解析中にエラーが発生しました: {e}", file=sys.stderr)

    # 2. 睡眠データの取得
    sleep_url = "https://health.googleapis.com/v4/users/me/dataTypes/sleep/dataPoints"
    sleep_minutes = None
    sleep_start_str = None
    sleep_end_str = None
    try:
        sleep_response = requests.get(sleep_url, headers=headers)
        if sleep_response.status_code == 200:
            sleep_data = sleep_response.json()
            if "dataPoints" in sleep_data:
                longest_session = None
                max_duration = 0
                for dp in sleep_data["dataPoints"]:
                    s_obj = dp.get("sleep", {})
                    interval = s_obj.get("interval", {})
                    start_t = interval.get("startTime")
                    end_t = interval.get("endTime")
                    if start_t and end_t:
                        try:
                            s_dt = datetime.datetime.fromisoformat(start_t.replace("Z", "+00:00"))
                            e_dt = datetime.datetime.fromisoformat(end_t.replace("Z", "+00:00"))
                            
                            e_dt_jst = e_dt + datetime.timedelta(hours=9)
                            if e_dt_jst.strftime("%Y-%m-%d") == target_date_str:
                                duration = (e_dt - s_dt).total_seconds()
                                if duration > max_duration:
                                    max_duration = duration
                                    longest_session = (s_dt, e_dt)
                        except Exception:
                            pass
                
                if longest_session:
                    s_dt, e_dt = longest_session
                    s_dt_jst = s_dt + datetime.timedelta(hours=9)
                    e_dt_jst = e_dt + datetime.timedelta(hours=9)
                    
                    sleep_minutes = round(max_duration / 60)
                    sleep_start_str = s_dt_jst.strftime("%H:%M")
                    sleep_end_str = e_dt_jst.strftime("%H:%M")
    except Exception as e:
        print(f"Warning: 睡眠データの取得・解析中にエラーが発生しました: {e}", file=sys.stderr)

    result = {
        "date": target_date_str,
        "weight_kg": weight,
        "sleep_minutes": sleep_minutes,
        "sleep_start": sleep_start_str,
        "sleep_end": sleep_end_str
    }
    
    print(json.dumps(result, indent=2, ensure_ascii=False))

if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "--auth":
        do_oauth_flow()
    else:
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")
        if len(sys.argv) > 1:
            target_date = sys.argv[1]
        get_health_data(target_date)
