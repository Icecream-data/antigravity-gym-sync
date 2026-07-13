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

# Scopes verified for Google Health get and Google Fit write
SCOPES = [
    "https://www.googleapis.com/auth/googlehealth.health_metrics_and_measurements.readonly",
    "https://www.googleapis.com/auth/googlehealth.sleep.readonly",
    "https://www.googleapis.com/auth/fitness.activity.write",
    "https://www.googleapis.com/auth/fitness.activity.read"
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
            self.wfile.write("Authentication completed. You can close this tab and return to the terminal.".encode('utf-8'))
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
        print(f"Error: {CREDENTIALS_PATH} not found.")
        print("Please place your OAuth client JSON credentials file downloaded from Google Cloud Console into the path above.")
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

    print("Opening browser for Google Fit & Health authentication...")
    print(f"URL: {url}")
    webbrowser.open(url)

    run_local_server()

    if not authorization_code:
        print("Error: Failed to retrieve authorization code.")
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
    
    print(f"✅ Auth tokens successfully saved to: {TOKEN_PATH}")

def load_tokens():
    try:
        import streamlit as st
        if hasattr(st, "secrets") and "google_health_token" in st.secrets:
            return dict(st.secrets["google_health_token"])
    except Exception:
        pass

    if os.path.exists(TOKEN_PATH):
        with open(TOKEN_PATH, 'r') as f:
            return json.load(f)
    return None

def save_tokens(tokens):
    if os.path.exists(TOKEN_PATH) or os.path.exists(os.path.dirname(TOKEN_PATH)):
        with open(TOKEN_PATH, 'w') as f:
            json.dump(tokens, f, indent=2)

def get_access_token():
    tokens = load_tokens()
    if not tokens:
        print(f"Error: Token configuration not found. Run auth setup first.")
        sys.exit(1)

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
    
    save_tokens(tokens)
    return tokens['access_token']

# Create a Fitness Data Source for Activity Segments if it doesn't exist
def get_or_create_data_source(access_token):
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    data_source_payload = {
        "dataStreamName": "ActivitySegment",
        "type": "raw",
        "application": {
            "name": "Antigravity Gym Sync"
        },
        "dataType": {
            "name": "com.google.activity.segment",
            "field": [
                {
                    "name": "activity",
                    "format": "integer"
                }
            ]
        }
    }
    
    url = "https://www.googleapis.com/fitness/v1/users/me/dataSources"
    
    try:
        response = requests.post(url, headers=headers, json=data_source_payload)
        if response.status_code in [200, 201]:
            ds_info = response.json()
            return ds_info.get("dataStreamId")
        elif response.status_code == 409:
            get_response = requests.get(url, headers=headers)
            if get_response.status_code == 200:
                sources = get_response.json().get("dataSource", [])
                for src in sources:
                    if src.get("dataStreamName") == "ActivitySegment" and src.get("application", {}).get("name") == "Antigravity Gym Sync":
                        return src.get("dataStreamId")
            return "raw:com.google.activity.segment:486610225594:Antigravity Gym Sync:ActivitySegment"
        else:
            print(f"Warning: Failed to create fitness data source. Status: {response.status_code}", file=sys.stderr)
            return None
    except Exception as e:
        print(f"Exception during data source creation: {e}", file=sys.stderr)
        return None

# Write Workout Session to Google Fit Jurnal (Legacy but standard compatible Google Fit API v1)
# Writes both the Activity Segment Datapoint (so it shows in Fit App) and the Session wrapper.
def write_workout_session(date_str, total_volume, exercises_summary=""):
    access_token = get_access_token()
    
    # 1. Get or Create the Activity Segment Data Source
    data_stream_id = get_or_create_data_source(access_token)
    if not data_stream_id:
        print("Error: Could not retrieve or create Google Fit Data Source.", file=sys.stderr)
        return False
        
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }
    
    # Define Default Session Time (18:00 - 19:00 JST)
    start_time_str = f"{date_str}T18:00:00+09:00"
    end_time_str = f"{date_str}T19:00:00+09:00"
    s_dt = datetime.datetime.fromisoformat(start_time_str)
    e_dt = datetime.datetime.fromisoformat(end_time_str)
    start_millis = int(s_dt.timestamp() * 1000)
    end_millis = int(e_dt.timestamp() * 1000)
    start_nanos = start_millis * 1000000
    end_nanos = end_millis * 1000000
    
    # 2. Write Datapoint to the Activity Segment Dataset
    # This guarantees that the session has exercise duration content, forcing Google Fit to display it.
    dataset_url = f"https://www.googleapis.com/fitness/v1/users/me/dataSources/{data_stream_id}/datasets/{start_nanos}-{end_nanos}"
    dataset_payload = {
        "dataSourceId": data_stream_id,
        "minStartTimeNs": start_nanos,
        "maxEndTimeNs": end_nanos,
        "point": [
            {
                "startTimeNanos": start_nanos,
                "endTimeNanos": end_nanos,
                "dataTypeName": "com.google.activity.segment",
                "value": [
                    {
                        "intVal": 97 # 97 represents Strength Training
                    }
                ]
            }
        ]
    }
    
    try:
        ds_response = requests.patch(dataset_url, headers=headers, json=dataset_payload)
        if ds_response.status_code not in [200, 201]:
            print(f"Warning: Failed to write activity segment datapoint: {ds_response.status_code} - {ds_response.text}", file=sys.stderr)
    except Exception as e:
        print(f"Exception during datapoint write: {e}", file=sys.stderr)

    # 3. Write Workout Session
    session_id = f"antigravity-gym-session-{date_str}"
    session_payload = {
        "id": session_id,
        "name": f"Gym Workout ({date_str})",
        "description": f"Logged via Antigravity Gym. Total Volume: {total_volume:.1f} kg. Details: {exercises_summary}",
        "startTimeMillis": start_millis,
        "endTimeMillis": end_millis,
        "version": 1,
        "activityType": 97 # 97 represents Strength Training
    }
    
    session_url = f"https://www.googleapis.com/fitness/v1/users/me/sessions/{session_id}"
    
    try:
        response = requests.put(session_url, headers=headers, json=session_payload)
        if response.status_code in [200, 201]:
            print(f"✅ Successfully wrote workout session to Google Fit Jurnal: {session_id}")
            return True
        else:
            print(f"Error writing workout session: {response.status_code} - {response.text}", file=sys.stderr)
            return False
    except Exception as e:
        print(f"Exception during workout session write: {e}", file=sys.stderr)
        return False

def get_health_data(target_date_str):
    access_token = get_access_token()
    
    headers = {
        "Authorization": f"Bearer {access_token}",
        "Content-Type": "application/json"
    }

    # Retrieve Weight Data
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
        print(f"Warning: Error parsing weight data: {e}", file=sys.stderr)

    # Retrieve Sleep Data
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
        print(f"Warning: Error parsing sleep data: {e}", file=sys.stderr)

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
    elif len(sys.argv) > 3 and sys.argv[1] == "--write-workout":
        date_param = sys.argv[2]
        volume_param = float(sys.argv[3])
        summary_param = sys.argv[4] if len(sys.argv) > 4 else ""
        write_workout_session(date_param, volume_param, summary_param)
    else:
        yesterday = datetime.date.today() - datetime.timedelta(days=1)
        target_date = yesterday.strftime("%Y-%m-%d")
        if len(sys.argv) > 1:
            target_date = sys.argv[1]
        get_health_data(target_date)
