import streamlit as st
import json
import os
import datetime
import calendar
import pandas as pd
import plotly.graph_objects as go

# Data storage path
DATA_FILE = "gym_records.json"

# Default Body Parts and Exercise Master (Cool English)
DEFAULT_EXERCISE_MASTER = {
    "Chest": ["Bench Press", "Dumbbell Fly", "Incline Dumbbell Press", "Cable Crossover", "Chest Press"],
    "Back": ["Deadlift", "Lat Pulldown", "Pull-up (Chinning)", "Bent Over Row", "One-Arm Dumbbell Row"],
    "Legs": ["Barbell Squat", "Leg Press", "Leg Extension", "Leg Curl", "Calf Raise"],
    "Shoulders": ["Shoulder Press", "Lateral Raise", "Front Raise", "Rear Delt Fly", "Upright Row"],
    "Arms": ["Bicep Curl", "Hammer Curl", "Skull Crusher", "Tricep Pushdown"],
    "Core": ["Crunch", "Leg Raise", "Plank", "Ab Roller"]
}

def load_records():
    if os.path.exists(DATA_FILE):
        try:
            with open(DATA_FILE, "r") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_records(records):
    with open(DATA_FILE, "w") as f:
        json.dump(records, f, indent=2, ensure_ascii=False)

# Dynamically populate exercise master with custom inputs from records
def get_extended_exercise_master(records):
    master = {k: list(v) for k, v in DEFAULT_EXERCISE_MASTER.items()}
    for date_str, day_data in records.items():
        for ex in day_data.get("exercises", []):
            part = ex.get("body_part")
            name = ex.get("name")
            if part in master and name not in master[part]:
                master[part].append(name)
    return master

# 1RM Calculation (Epley formula)
def calculate_1rm(weight, reps):
    if reps == 1:
        return weight
    return round(weight * (1 + reps / 30.0), 1)

# Retrieve previous session's total volume
def get_previous_session_weight(records):
    sorted_dates = sorted(records.keys())
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    previous_weight = 0.0
    for d_str in reversed(sorted_dates):
        if d_str < today_str:
            previous_weight = records[d_str].get("total_weight", 0.0)
            break
    return previous_weight

# Calculate elapsed days since the last workout session
def get_days_since_last_session(records):
    if not records:
        return None
    sorted_dates = sorted(records.keys())
    today_str = datetime.date.today().strftime("%Y-%m-%d")
    today = datetime.date.today()
    
    if today_str in records:
        # If session exists today, search for the most recent one before today
        prev_date_str = None
        for d_str in reversed(sorted_dates):
            if d_str < today_str:
                prev_date_str = d_str
                break
        if prev_date_str:
            prev_date = datetime.datetime.strptime(prev_date_str, "%Y-%m-%d").date()
            return (today - prev_date).days
        return None
    else:
        # If no session today, find the absolute latest session
        last_date_str = sorted_dates[-1]
        last_date = datetime.datetime.strptime(last_date_str, "%Y-%m-%d").date()
        return (today - last_date).days

# Streamlit Configuration
st.set_page_config(page_title="Antigravity Gym Sync", page_icon="🏋️‍♂️", layout="centered")

# Session State Management
if "page" not in st.session_state:
    st.session_state.page = "dashboard"
if "workout_date" not in st.session_state:
    st.session_state.workout_date = datetime.date.today()
if "temp_exercises" not in st.session_state:
    st.session_state.temp_exercises = []
# Calendar display state variables
if "cal_year" not in st.session_state:
    st.session_state.cal_year = datetime.date.today().year
if "cal_month" not in st.session_state:
    st.session_state.cal_month = datetime.date.today().month

# Sync date state from URL query parameters
query_params = st.query_params
if "date" in query_params:
    try:
        param_date = datetime.datetime.strptime(query_params["date"], "%Y-%m-%d").date()
        st.session_state.workout_date = param_date
        st.session_state.cal_year = param_date.year
        st.session_state.cal_month = param_date.month
        st.session_state.page = "calendar"
        st.query_params.clear()
        st.rerun() # Rerun immediately with clean URL parameters
    except ValueError:
        pass

# UI Styles (Shadcn/Tailwind style light & clean theme)
st.markdown("""
<style>
    /* Prevent horizontal scrolling and force responsive width */
    html, body, [data-testid="stAppViewContainer"], [data-testid="stApp"] {
        max-width: 100vw !important;
        overflow-x: hidden !important;
    }
    
    /* Primary buttons (Positive major actions) */
    .stButton>button[kind="primary"] {
        background-color: #22c55e !important;
        color: white !important;
        border-radius: 8px !important;
        border: none !important;
        padding: 0.5rem 1rem;
        font-weight: bold !important;
        transition: background-color 0.2s;
    }
    .stButton>button[kind="primary"]:hover {
        background-color: #16a34a !important;
    }
    
    /* Danger/Destructive buttons (Delete, Clear) */
    .stButton>button[id^="del_"], 
    .stButton>button[id*="clear"],
    .stButton>button[id*="delete"] {
        background-color: #ef4444 !important;
        color: white !important;
        border: none !important;
        border-radius: 8px !important;
        font-weight: bold !important;
        padding: 0.5rem 1rem;
        transition: background-color 0.2s;
    }
    .stButton>button[id^="del_"]:hover, 
    .stButton>button[id*="clear"]:hover,
    .stButton>button[id*="delete"]:hover {
        background-color: #dc2626 !important;
    }
    
    /* Secondary buttons (Nav, Back) */
    .stButton>button[kind="secondary"] {
        background-color: #ffffff !important;
        color: #1f2937 !important;
        border: 1px solid #e5e7eb !important;
        border-radius: 8px !important;
        padding: 0.5rem 1rem;
        transition: border-color 0.2s, background-color 0.2s;
    }
    .stButton>button[kind="secondary"]:hover {
        border-color: #d1d5db !important;
        background-color: #f9fafb !important;
    }
    
    /* Calendar control month navigation buttons */
    .stButton>button[id*="prev_month"], 
    .stButton>button[id*="next_month"] {
        background-color: #f3f4f6 !important;
        color: #1f2937 !important;
        border: 1px solid #d1d5db !important;
    }
    .stButton>button[id*="prev_month"]:hover, 
    .stButton>button[id*="next_month"]:hover {
        background-color: #e5e7eb !important;
        border-color: #9ca3af !important;
    }
    
    /* Centered dark theme metrics card */
    .metric-card {
        background: #161b22 !important;
        border: 1px solid #30363d !important;
        border-radius: 12px !important;
        padding: 1.5rem !important;
        text-align: center !important;
        box-shadow: 0 4px 6px -1px rgba(0, 0, 0, 0.1), 0 2px 4px -1px rgba(0, 0, 0, 0.06);
    }
    .metric-card h3 {
        color: #8b949e !important;
        font-size: 0.875rem !important;
        font-weight: 600 !important;
        margin: 0 0 6px 0 !important;
    }
    .metric-card h1 {
        color: #ffffff !important;
        font-size: 2.0rem !important;
        font-weight: 750 !important;
        margin: 10px 0 !important;
    }
    .metric-card p {
        color: #8b949e !important;
        font-size: 0.85rem !important;
        margin: 0 !important;
    }
    
    /* Clean white background card container for HTML Calendar */
    .html-cal-container {
        background-color: #ffffff !important;
        border-radius: 12px;
        padding: 1rem;
        border: 1px solid #e5e7eb;
        box-shadow: 0 1px 3px rgba(0,0,0,0.1);
        margin-bottom: 20px;
    }
    
    /* Calendar styling rules inside card container */
    .html-cal-table {
        width: 100%;
        border-collapse: collapse;
    }
    .html-cal-table th {
        color: #4b5563;
        font-weight: bold;
        text-align: center;
        padding: 8px 4px;
        font-size: 0.85rem;
        width: 14.28%;
    }
    .html-cal-table td {
        text-align: center;
        padding: 6px 2px;
        width: 14.28%;
    }
    .html-cal-day-link {
        display: inline-block;
        width: 38px;
        height: 38px;
        line-height: 36px;
        border-radius: 8px;
        text-decoration: none !important;
        color: #1f2937 !important; /* Cool dark links instead of default browser blue */
        font-size: 0.9rem;
        font-weight: 600;
        border: 1px solid transparent;
        background-color: transparent;
        transition: all 0.15s ease;
        box-sizing: border-box;
    }
    .html-cal-day-link:hover {
        background-color: #f3f4f6;
        color: #000000 !important;
    }
    /* Workout days (Clean green background with bold white text) */
    .html-cal-has-record {
        background-color: #22c55e !important;
        color: #ffffff !important;
        border-color: #16a34a !important;
    }
    .html-cal-has-record:hover {
        background-color: #16a34a !important;
    }
    /* Active selected day (Strong dark border ring) */
    .html-cal-selected {
        border: 2px solid #111827 !important;
        font-weight: bold;
    }
    .html-cal-has-record.html-cal-selected {
        border: 2px solid #111827 !important;
    }
    .html-cal-empty-td {
        height: 38px;
    }
    
    /* Responsive overrides for smaller phone viewports */
    @media (max-width: 768px) {
        h1 { font-size: 1.4rem !important; }
        h2 { font-size: 1.2rem !important; }
        h3 { font-size: 1.0rem !important; }
        
        .html-cal-day-link {
            width: 32px;
            height: 32px;
            line-height: 30px;
            font-size: 0.8rem;
        }
        
        .metric-card {
            padding: 0.7rem !important;
            margin-bottom: 8px;
        }
        .metric-card h1 { font-size: 1.6rem !important; }
        .metric-card h3 { font-size: 0.75rem !important; }
        
        .stButton>button {
            padding: 0.4rem 0.6rem !important;
            font-size: 0.8rem !important;
        }
        
        div[data-testid="stTable"] {
            width: 100% !important;
            overflow-x: auto !important;
            -webkit-overflow-scrolling: touch;
        }
        div[data-testid="stTable"] table {
            font-size: 0.75rem !important;
            min-width: 300px !important;
        }
        div[data-testid="stTable"] th, div[data-testid="stTable"] td {
            padding: 4px 6px !important;
        }
        
        div[data-testid="stPlotlyChart"] {
            width: 100% !important;
            max-width: 100% !important;
            overflow-x: hidden !important;
        }
    }
</style>
""", unsafe_allow_html=True)

records = load_records()
exercise_master = get_extended_exercise_master(records)

# --- Global Navigation Tabs (Hidden in Log/Edit page) ---
if st.session_state.page != "create_record":
    nav_options = ["🏠 Dashboard", "📅 History Calendar"]
    selected_nav = st.segmented_control(
        "Navigation", 
        nav_options, 
        default=nav_options[0] if st.session_state.page == "dashboard" else nav_options[1],
        label_visibility="collapsed"
    )

    if selected_nav == "🏠 Dashboard":
        st.session_state.page = "dashboard"
    elif selected_nav == "📅 History Calendar":
        st.session_state.page = "calendar"

st.write("")

# --- Page 1: Dashboard ---
if st.session_state.page == "dashboard":
    st.title("🏋️‍♂️ Antigravity Gym Dashboard")
    
    # Dashboard summary and charts tabs
    tab_summary, tab_charts = st.tabs(["📊 Summary", "📈 Volume Trend"])
    
    with tab_summary:
        col1, col2, col3 = st.columns(3)
        
        total_all_weight = sum(data.get("total_weight", 0) for data in records.values())
        total_days = len(records)
        today_str = datetime.date.today().strftime("%Y-%m-%d")
        today_weight = records.get(today_str, {}).get("total_weight", 0)
        previous_weight = get_previous_session_weight(records)
        days_since_last = get_days_since_last_session(records)
        
        # Friendly interval progression status messages
        if days_since_last is None:
            days_text = "No previous sessions"
        elif days_since_last == 0:
            days_text = "Next session: Let's go!"
        else:
            days_text = f"Last: {days_since_last} days ago"
            
        with col1:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Total Weight Lifted</h3>
                <h1>{total_all_weight:,.1f} kg</h1>
            </div>
            """, unsafe_allow_html=True)
        with col2:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Today's Volume</h3>
                <h1>{today_weight:,.1f} kg</h1>
                <p>Previous: {previous_weight:,.1f} kg</p>
            </div>
            """, unsafe_allow_html=True)
        with col3:
            st.markdown(f"""
            <div class="metric-card">
                <h3>Active Days</h3>
                <h1>{total_days} Days</h1>
                <p>{days_text}</p>
            </div>
            """, unsafe_allow_html=True)
            
        st.write("")
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("➕ Create Training Record (Today)", key="btn_go_create", type="primary", use_container_width=True):
                st.session_state.workout_date = datetime.date.today()
                st.session_state.page = "create_record"
                st.rerun()
        with col_act2:
            if st.button("📅 View History Calendar", key="btn_go_cal", use_container_width=True):
                st.session_state.page = "calendar"
                st.rerun()

    with tab_charts:
        st.subheader("📈 Exercise Volume Over Time")
        st.write("Track your progressive overload session-by-session.")
        
        all_recorded_exercises = set()
        for day_data in records.values():
            for ex in day_data.get("exercises", []):
                all_recorded_exercises.add(ex.get("name"))
                
        if all_recorded_exercises:
            chart_ex = st.selectbox("Select exercise to analyze", sorted(list(all_recorded_exercises)))
            
            chart_data = []
            for date_str, day_data in records.items():
                for ex in day_data.get("exercises", []):
                    if ex.get("name") == chart_ex:
                        volume = sum(s.get("weight", 0.0) * s.get("reps", 0) for s in ex.get("sets", []))
                        chart_data.append({
                            "date": datetime.datetime.strptime(date_str, "%Y-%m-%d").date(),
                            "Volume": volume
                        })
            
            if chart_data:
                df_chart = pd.DataFrame(chart_data).sort_values("date")
                
                fig_trend = go.Figure()
                fig_trend.add_trace(go.Scatter(
                    x=df_chart["date"],
                    y=df_chart["Volume"],
                    mode='lines+markers',
                    name='Total Volume',
                    line=dict(color='#22c55e', width=3),
                    marker=dict(size=8, color='#111827')
                ))
                
                fig_trend.update_layout(
                    xaxis_title="Date",
                    yaxis_title="Total Volume (kg)",
                    margin=dict(t=20, b=20, l=20, r=20),
                    plot_bgcolor='rgba(0,0,0,0)',
                    paper_bgcolor='rgba(0,0,0,0)',
                    yaxis=dict(gridcolor='#e5e7eb'),
                    xaxis=dict(gridcolor='#e5e7eb')
                )
                st.plotly_chart(fig_trend, width="stretch")
                
                if len(df_chart) >= 2:
                    latest = df_chart.iloc[-1]
                    previous = df_chart.iloc[-2]
                    diff = latest["Volume"] - previous["Volume"]
                    
                    if diff > 0:
                        st.success(f"🔥 Volume is up by **+{diff:.1f} kg** compared to previous session ({previous['date']}: {previous['Volume']:.1f}kg)! You surpassed your limits!")
                    elif diff < 0:
                        st.info(f"💪 Volume is down by **{diff:.1f} kg** from previous session ({previous['date']}: {previous['Volume']:.1f}kg). Stay focused, hit it harder next time!")
                    else:
                        st.warning(f"🏋️‍♂️ Volume matched previous session. Aim for progressive overload on your next run!")
                else:
                    st.info("Only 1 session recorded. Complete another workout to unlock progression metrics.")
            else:
                st.info("Failed to retrieve timeseries data.")
        else:
            st.info("No workout history available to plot trend.")

# --- Page 2: History Calendar ---
elif st.session_state.page == "calendar":
    st.title("📅 Workout History Calendar")
    
    col_cal_nav1, col_cal_nav2, col_cal_nav3 = st.columns([1, 2, 1])
    with col_cal_nav1:
        if st.button("◀ Prev", key="btn_prev_month", use_container_width=True):
            if st.session_state.cal_month == 1:
                st.session_state.cal_month = 12
                st.session_state.cal_year -= 1
            else:
                st.session_state.cal_month -= 1
            st.rerun()
            
    with col_cal_nav2:
        month_name = calendar.month_name[st.session_state.cal_month]
        st.markdown(f"<h3 style='text-align: center; margin-top: 5px; color:#1f2937;'>{month_name} {st.session_state.cal_year}</h3>", unsafe_allow_html=True)
        
    with col_cal_nav3:
        if st.button("Next ▶", key="btn_next_month", use_container_width=True):
            if st.session_state.cal_month == 12:
                st.session_state.cal_month = 1
                st.session_state.cal_year += 1
            else:
                st.session_state.cal_month += 1
            st.rerun()
            
    st.write("")
    
    # White background calendar card block
    st.markdown('<div class="html-cal-container">', unsafe_allow_html=True)
    
    # Weekday Headers
    st.markdown("""
    <div style='display: flex; justify-content: space-around; width: 100%; margin-bottom: 8px;'>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Mon</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Tue</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Wed</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Thu</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Fri</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Sat</div>
        <div style='width:14.28%; text-align:center; font-weight:bold; color:#4b5563; font-size:0.8rem;'>Sun</div>
    </div>
    """, unsafe_allow_html=True)
    
    cal = calendar.Calendar(firstweekday=0)
    month_days = cal.monthdayscalendar(st.session_state.cal_year, st.session_state.cal_month)
    
    selected_date_str = st.session_state.workout_date.strftime("%Y-%m-%d")
    
    # Build HTML Calendar Grid
    html_code = '<table class="html-cal-table">'
    for week in month_days:
        html_code += '<tr>'
        for day in week:
            if day == 0:
                html_code += '<td class="html-cal-empty-td"></td>'
            else:
                this_date_str = f"{st.session_state.cal_year:04d}-{st.session_state.cal_month:02d}-{day:02d}"
                has_record = this_date_str in records
                is_selected = selected_date_str == this_date_str
                
                classes = ['html-cal-day-link']
                if has_record:
                    classes.append('html-cal-has-record')
                if is_selected:
                    classes.append('html-cal-selected')
                    
                class_str = ' '.join(classes)
                html_code += f'<td><a class="{class_str}" href="?date={this_date_str}" target="_self">{day}</a></td>'
        html_code += '</tr>'
    html_code += '</table>'
    
    st.markdown(html_code, unsafe_allow_html=True)
    st.markdown('</div>', unsafe_allow_html=True)
    
    st.write("---")
    st.subheader(f"🔍 Selected Date: {selected_date_str}")
    
    if selected_date_str in records:
        day_data = records[selected_date_str]
        st.success(f"Total Volume: {day_data.get('total_weight', 0):,.1f} kg")
        
        col_edit, col_space = st.columns([1, 2])
        with col_edit:
            if st.button("✏️ Edit This Record", key="btn_edit_cal_date", type="primary", use_container_width=True):
                st.session_state.page = "create_record"
                st.rerun()
            
        st.write("")
        
        for ex in day_data.get("exercises", []):
            st.markdown(f"##### **{ex['body_part']} - {ex['name']}**")
            df_preview_sets = pd.DataFrame(ex["sets"])
            df_preview_sets.columns = ["Set", "Weight (kg)", "Reps", "Est. 1RM (kg)"]
            st.table(df_preview_sets.style.format({"Weight (kg)": "{:.1f}", "Est. 1RM (kg)": "{:.1f}"}))

        # Relocation section
        with st.expander("🔄 Move Record to Another Date"):
            new_date = st.date_input("Select target date", st.session_state.workout_date, key="move_date_picker")
            new_date_key = new_date.strftime("%Y-%m-%d")
            
            if new_date_key != selected_date_str:
                if st.button("🚀 Move Date", key="btn_move_record", type="primary", use_container_width=True):
                    target_data = records.pop(selected_date_str)
                    
                    if new_date_key in records:
                        records[new_date_key]["exercises"].extend(target_data["exercises"])
                        new_total = sum(
                            sum(s.get("weight", 0.0) * s.get("reps", 0) for s in ex.get("sets", []))
                            for ex in records[new_date_key]["exercises"]
                        )
                        records[new_date_key]["total_weight"] = round(new_total, 1)
                    else:
                        records[new_date_key] = target_data
                        
                    save_records(records)
                    st.success(f"Moved successfully to {new_date_key}!")
                    st.session_state.workout_date = new_date
                    st.session_state.cal_year = new_date.year
                    st.session_state.cal_month = new_date.month
                    st.rerun()
    else:
        st.info("No records found for this date.")
        if st.button("➕ Create New Record", key="btn_create_cal_date", type="primary", use_container_width=True):
            st.session_state.page = "create_record"
            st.rerun()

# --- Page 3: Create & Edit Record ---
elif st.session_state.page == "create_record":
    st.title("📝 Edit Workout Record")
    
    if st.button("⬅️ Back to Calendar", key="btn_go_cal_page", use_container_width=True):
        st.session_state.page = "calendar"
        st.rerun()
        
    st.write("---")
    
    if "sync_result" in st.session_state:
        st.subheader("💾 Workout Sync Status")
        
        # Local save result
        st.success("✅ Workout details saved locally!")
        
        # Google Health sync result
        res = st.session_state.sync_result
        if res["status"] == "success":
            st.info(res["message"])
        else:
            st.error(res["message"])
            
        st.write("")
        if st.button("⬅️ Back to Calendar", type="primary", use_container_width=True):
            if "temp_exercises" in st.session_state:
                del st.session_state.temp_exercises
            del st.session_state.sync_result
            st.session_state.page = "calendar"
            st.rerun()
        st.stop()
    
    col1, col2 = st.columns(2)
    with col1:
        workout_date = st.date_input("Workout Date", st.session_state.workout_date)
        st.session_state.workout_date = workout_date
    date_key = workout_date.strftime("%Y-%m-%d")
    
    existing_data = records.get(date_key, {})
    
    if "last_loaded_date" not in st.session_state or st.session_state.last_loaded_date != date_key:
        st.session_state.last_loaded_date = date_key
        if existing_data and "exercises" in existing_data:
            st.session_state.temp_exercises = existing_data["exercises"]
        else:
            st.session_state.temp_exercises = []
            
    st.subheader(f"💪 Log Workout for {date_key}")
    
    with st.expander("🆕 Add Exercise", expanded=True):
        col_part, col_ex = st.columns(2)
        with col_part:
            selected_part = st.selectbox("Body Part", list(exercise_master.keys()))
        with col_ex:
            exercise_options = exercise_master[selected_part]
            selected_ex = st.selectbox("Exercise", exercise_options + ["Other (Custom)"])
            
            if selected_ex == "Other (Custom)":
                selected_ex = st.text_input("Enter custom exercise name", "")
                
        st.markdown("##### Set Details")
        num_sets = st.number_input("Sets", min_value=1, max_value=10, value=3)
        
        sets_data = []
        for s in range(num_sets):
            cw, cr, crm = st.columns([2, 2, 1])
            with cw:
                w = st.number_input(f"Set {s+1} Weight", min_value=0.0, max_value=300.0, value=60.0, step=5.0, format="%.1f", key=f"w_{s}")
            with cr:
                r = st.number_input(f"Set {s+1} Reps", min_value=1, max_value=100, value=10, step=1, key=f"r_{s}")
            with crm:
                rm = calculate_1rm(w, r)
                st.markdown(f"<p style='margin-top:28px; font-weight:bold; color:#22c55e;'>RM: {rm:.1f}</p>", unsafe_allow_html=True)
            sets_data.append({"set_num": s+1, "weight": round(w, 1), "reps": r, "rm": round(rm, 1)})
            
        if st.button("Add Exercise to Log", key="btn_add_ex", type="primary", use_container_width=True):
            if selected_ex:
                st.session_state.temp_exercises.append({
                    "body_part": selected_part,
                    "name": selected_ex.strip(),
                    "sets": sets_data
                })
                st.success(f"Added {selected_ex}!")
                st.rerun()
            else:
                st.error("Please enter an exercise name.")

    if st.session_state.temp_exercises:
        st.write("---")
        st.subheader("📋 Workout Draft")
        
        total_lifted = 0
        for i, ex in enumerate(st.session_state.temp_exercises):
            st.markdown(f"#### {ex['body_part']} - {ex['name']}")
            
            df_sets = pd.DataFrame(ex["sets"])
            df_sets.columns = ["Set", "Weight (kg)", "Reps", "Est. 1RM (kg)"]
            st.table(df_sets.style.format({"Weight (kg)": "{:.1f}", "Est. 1RM (kg)": "{:.1f}"}))
            
            ex_total = sum(s["weight"] * s["reps"] for s in ex["sets"])
            total_lifted += ex_total
            st.write(f"Exercise Volume: {ex_total:,.1f} kg")
            
            if st.button(f"Delete", key=f"del_{i}", use_container_width=True):
                st.session_state.temp_exercises.pop(i)
                st.rerun()
            st.write("---")
            
        st.markdown(f"### 🔥 Total Workout Volume: {total_lifted:,.1f} kg")
        
        col_act1, col_act2 = st.columns(2)
        with col_act1:
            if st.button("💾 Save Workout", key="btn_save", type="primary", use_container_width=True):
                records[date_key] = {
                    "total_weight": round(total_lifted, 1),
                    "exercises": st.session_state.temp_exercises
                }
                save_records(records)
                st.success("Workout saved successfully!")
                
                # Automatically sync workout details to Google Fit via API
                try:
                    import google_health_sync
                    ex_summary = ", ".join([ex["name"] for ex in st.session_state.temp_exercises])
                    sync_success = google_health_sync.write_workout_session(date_key, total_lifted, ex_summary)
                    if sync_success:
                        st.session_state.sync_result = {
                            "status": "success",
                            "message": f"🏋️‍♂️ Successfully synced workout to Google Health v4! ({total_lifted:.1f} kg)"
                        }
                    else:
                        st.session_state.sync_result = {
                            "status": "failed",
                            "message": "⚠️ Google Health Sync failed. Please check your Secrets configuration."
                        }
                except Exception as e:
                    import traceback
                    traceback.print_exc()
                    st.session_state.sync_result = {
                        "status": "error",
                        "message": f"⚠️ Google Health Sync error: {str(e)}"
                    }
                
                st.rerun()
        with col_act2:
            if st.button("🗑️ Clear All Draft", key="btn_clear_all", use_container_width=True):
                if "temp_exercises" in st.session_state:
                    del st.session_state.temp_exercises
                st.rerun()
    else:
        st.info("Added exercises will appear here.")
