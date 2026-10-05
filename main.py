import sqlite3
import re
import os
import shutil
from datetime import datetime
from generate_website import generate_static_website

# ==========================================
# CHANGE THIS WHEN A NEW TRACKMANIA CAMPAIGN BEGINS
# ==========================================
ACTIVE_TRACK_SEASON = "Fall 2026" # <------------------------------------ CHECK / UPDATE

DB_FILE = 'trackmania_times.db'
PENALTY_MS = 5 * 60 * 1000  

def init_db():
    conn = sqlite3.connect(DB_FILE)
    cursor = conn.cursor()
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            name TEXT UNIQUE NOT NULL
        )
    ''')
    
    try:
        cursor.execute("ALTER TABLE students ADD COLUMN tm_account_id TEXT")
    except sqlite3.OperationalError:
        pass 
        
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS times (
            student_id INTEGER,
            season TEXT,
            track_number INTEGER,
            time_ms INTEGER,
            PRIMARY KEY (student_id, season, track_number),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS playoff_matches (
            season TEXT,
            match_id TEXT, 
            student_id INTEGER,
            score INTEGER DEFAULT 0,
            PRIMARY KEY (season, match_id, student_id),
            FOREIGN KEY (student_id) REFERENCES students(id)
        )
    ''')
    conn.commit()
    return conn

def time_to_ms(time_str):
    parts = time_str.replace('.', ':').split(':')
    if len(parts) == 3:
        minutes = int(parts[0])
        seconds = int(parts[1])
        milliseconds = int(parts[2].ljust(3, '0'))
    elif len(parts) == 2:
        minutes = 0
        seconds = int(parts[0])
        milliseconds = int(parts[1].ljust(3, '0'))
    else:
        return 0
    return (minutes * 60 * 1000) + (seconds * 1000) + milliseconds

def ms_to_time(ms):
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def sort_seasons_chronologically(seasons_list):
    order = {'Winter': 1, 'Spring': 2, 'Summer': 3, 'Fall': 4}
    def sorter(season_str):
        try:
            parts = season_str.split()
            season = parts[0]
            year = int(parts[1])
            return (year, order.get(season, 0))
        except:
            return (0, 0)
    return sorted(seasons_list, key=sorter, reverse=True)

def select_playoff_season(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT season FROM playoff_matches UNION SELECT season FROM times")
    seasons = [row[0] for row in cursor.fetchall() if row[0]]
    seasons = sort_seasons_chronologically(seasons)

    print("\n--- Select Season for Playoffs ---")
    if seasons:
        for index, season in enumerate(seasons, 1):
            print(f"[{index}] {season}")
    else:
        print("No seasons found in the database yet.")
        return ACTIVE_TRACK_SEASON

    user_input = ""
    while not user_input:
        user_input = input("\nEnter a season's number from the list: ").strip()

    if user_input.isdigit():
        selection = int(user_input)
        if 1 <= selection <= len(seasons):
            return seasons[selection - 1]
    
    return user_input.title()

def get_or_create_student(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students ORDER BY name")
    students = cursor.fetchall()

    print("\n--- Student Selection ---")
    if students:
        for index, student in enumerate(students, 1):
            print(f"[{index}] {student[1]}")
    else:
        print("No students found in the database yet.")

    user_input = ""
    while not user_input:
        user_input = input("\nEnter a student's number from the list, or type a new name: ").strip()

    if user_input.isdigit():
        selection = int(user_input)
        if 1 <= selection <= len(students):
            return students[selection - 1][0]
        else:
            name = user_input
    else:
        name = user_input

    cursor.execute("SELECT id FROM students WHERE name COLLATE NOCASE = ?", (name,))
    row = cursor.fetchone()
    
    if row:
        return row[0]
    else:
        cursor.execute("INSERT INTO students (name) VALUES (?)", (name,))
        conn.commit()
        return cursor.lastrowid

def link_account(conn):
    cursor = conn.cursor()
    student_id = get_or_create_student(conn)
    cursor.execute("SELECT name, tm_account_id FROM students WHERE id = ?", (student_id,))
    name, current_id = cursor.fetchone()
    
    print(f"\n--- Linking Account for {name} ---")
    if current_id:
        print(f"Current Account ID: {current_id}")
    
    new_id = input("Enter new Account ID (or press Enter to cancel): ").strip()
    if new_id:
        cursor.execute("UPDATE students SET tm_account_id = ? WHERE id = ?", (new_id, student_id))
        conn.commit()
        print(f"Successfully linked {name} to {new_id}!")

def auto_pull_times(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name, tm_account_id FROM students WHERE tm_account_id IS NOT NULL")
    players = cursor.fetchall()
    
    if not players:
        print("\nNo students have a linked Trackmania Account ID yet. Use Menu Option 2 first!")
        return
        
    print(f"\n--- Scraping Seytaek for {ACTIVE_TRACK_SEASON} ---")
    
    try:
        from playwright.sync_api import sync_playwright
    except ImportError:
        print("\nERROR: Playwright is not installed.")
        return
        
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        
        for s_id, name, tm_id in players:
            print(f"Pulling times for {name}... (ID: {tm_id})")
            url = f"https://seytaek.com/seasons/active/{tm_id}"
            
            context = browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'
            )
            page = context.new_page()
            
            try:
                page.goto(url, wait_until='domcontentloaded', timeout=30000)
                page.wait_for_selector('.map', timeout=10000)
                
                for _ in range(3):
                    page.evaluate("window.scrollBy(0, 400)")
                    page.wait_for_timeout(400)
                page.evaluate("window.scrollTo(0, 0)")
                
                try:
                    page.wait_for_function("""
                        () => {
                            const records = document.querySelectorAll('.mapPersonalRecord');
                            for (let r of records) {
                                const text = r.textContent || "";
                                if (/[0-9]/.test(text) || text.includes('No time set')) return true;
                            }
                            return false;
                        }
                    """, timeout=15000)
                except Exception:
                    safe_name = name.replace(' ', '_').replace('.', '')
                    debug_img = f"debug_{safe_name}.png"
                    page.screenshot(path=debug_img)
                    print(f"  -> API Blocked! Saved a screenshot to '{debug_img}'.")
                    context.close()
                    continue
                
                page.wait_for_timeout(1000)
                
                data = page.evaluate("""
                    Array.from(document.querySelectorAll('.map')).map(mapEl => {
                        let nameEl = mapEl.querySelector('.mapName');
                        let pbEl = mapEl.querySelector('.mapPersonalRecord');
                        if (nameEl && pbEl) {
                            return { track: nameEl.textContent.trim(), pb: pbEl.textContent.trim() };
                        }
                        return null;
                    }).filter(item => item !== null);
                """)
                
                updates = 0
                valid_tracks = 0
                
                for item in data:
                    track_str = item['track']
                    time_str = item['pb']
                    
                    track_match = re.search(r"(\d+)", track_str)
                    if not track_match:
                        continue
                    track_number = int(track_match.group(1))
                    if track_number < 1 or track_number > 10:
                        continue
                        
                    time_match = re.search(r"((?:\d{1,2}:)?\d{1,2}[\.,]\d{1,3})", time_str)
                    if not time_match:
                        continue
                        
                    clean_time = time_match.group(1).replace(',', '.')
                    new_ms = time_to_ms(clean_time)
                    valid_tracks += 1
                    
                    cursor.execute('''SELECT time_ms FROM times WHERE student_id = ? AND season = ? AND track_number = ?''', (s_id, ACTIVE_TRACK_SEASON, track_number))
                    row = cursor.fetchone()
                    
                    if row is None:
                        cursor.execute('''INSERT INTO times (student_id, season, track_number, time_ms) VALUES (?, ?, ?, ?)''', (s_id, ACTIVE_TRACK_SEASON, track_number, new_ms))
                        updates += 1
                    elif new_ms < row[0]:
                        cursor.execute('''UPDATE times SET time_ms = ? WHERE student_id = ? AND season = ? AND track_number = ?''', (new_ms, s_id, ACTIVE_TRACK_SEASON, track_number))
                        updates += 1
                        
                if valid_tracks == 0:
                    print("  -> Player has not set any times for Tracks 1-10.")
                    print("")
                else:
                    print(f"  -> Successfully updated {updates} PBs! (Found {valid_tracks}/10 tracks)")
                    print("")
                    
            except Exception as e:
                print(f"  -> Error parsing data for {name}: {e}")
            finally:
                context.close()
        browser.close()
    conn.commit()
    print("\nAuto-pull complete!")

def record_time(conn):
    student_id = get_or_create_student(conn)
    print(f"\n--- Recording Times for {ACTIVE_TRACK_SEASON} ---")
    cursor = conn.cursor()
    
    while True:
        track_input = input("\nEnter Track Number (1-10): ").strip()
        if not track_input.isdigit() or not (1 <= int(track_input) <= 10):
            print("  -> Invalid track number. Please enter a number between 1 and 10.")
            continue
        track_number = int(track_input)
        
        while True:
            time_str = input(f"Track {track_number} time (MM:SS.mmm) or leave blank to cancel: ").strip()
            if not time_str:
                print(f"  -> Cancelled entry for Track {track_number}")
                break
                
            if re.match(r"^(?:\d{1,2}:)?\d{1,2}\.\d{1,3}$", time_str):
                new_ms = time_to_ms(time_str)
                cursor.execute('''SELECT time_ms FROM times WHERE student_id = ? AND season = ? AND track_number = ?''', (student_id, ACTIVE_TRACK_SEASON, track_number))
                row = cursor.fetchone()
                
                if row is None:
                    cursor.execute('''INSERT INTO times (student_id, season, track_number, time_ms) VALUES (?, ?, ?, ?)''', (student_id, ACTIVE_TRACK_SEASON, track_number, new_ms))
                    print("  -> Recorded!")
                elif new_ms < row[0]:
                    cursor.execute('''UPDATE times SET time_ms = ? WHERE student_id = ? AND season = ? AND track_number = ?''', (new_ms, student_id, ACTIVE_TRACK_SEASON, track_number))
                    print("  -> Personal Best!")
                else:
                    print("  -> Slower run kept.")
                break
            else:
                print("  -> Invalid format (MM:SS.mmm or SS.mmm).")
        conn.commit()
        another = input("\nEnter another track for this student? (Y/N): ").strip().upper()
        if another != 'Y':
            break

def get_season_standings(conn, season):
    cursor = conn.cursor()
    cursor.execute('''
        SELECT DISTINCT t.student_id, s.name 
        FROM times t
        JOIN students s ON t.student_id = s.id
        WHERE t.season = ?
    ''', (season,))
    
    teacher_prefixes = ('mr.', 'ms.', 'mrs.', 'miss', 'mr ', 'ms ', 'mrs ')
    active = [r[0] for r in cursor.fetchall() if not r[1].lower().startswith(teacher_prefixes)]
    
    season_times = {i: [] for i in range(1, 11)}
    student_times = {s_id: [] for s_id in active}
    student_track_scores = {s_id: [] for s_id in active}
    
    for s_id in active:
        cursor.execute("SELECT track_number, time_ms FROM times WHERE student_id = ? AND season = ?", (s_id, season))
        t_dict = dict(cursor.fetchall())
        for i in range(1, 11):
            t = t_dict.get(i, PENALTY_MS)
            student_times[s_id].append(t)
            season_times[i].append(t)
            
    for s_id in active:
        for i in range(1, 11):
            my_time = student_times[s_id][i-1]
            if my_time < PENALTY_MS:
                actual = sum(1 for t in season_times[i] if t < PENALTY_MS)
                faster = sum(1 for t in season_times[i] if t < my_time)
                if actual > 1:
                    dynamic_floor = 1 if actual >= 10 else 100 - ((actual - 2) * (99 / 8))
                    score_range = 150 - dynamic_floor
                    score = round(150 - (faster * (score_range / (actual - 1))))
                else:
                    score = 150
            else:
                score = 0
            student_track_scores[s_id].append(score)
            
    # Apply countback tiebreaker: Sorts by total score, then falls back to descending individual track scores
    ranked = sorted(
        active, 
        key=lambda s_id: (sum(student_track_scores[s_id]), sorted(student_track_scores[s_id], reverse=True)), 
        reverse=True
    )
    return ranked

def seed_playoffs(conn, season):
    standings = get_season_standings(conn, season)
    
    if season == "Spring 2026":
        top_8 = standings[:8]
        top_8 += [None] * (8 - len(top_8))
        groups = {'MA': top_8[0:4], 'MB': top_8[4:8]}
        format_name = "Legacy 8-Player Bracket"
    else:
        top_12 = standings[:12]
        top_12 += [None] * (12 - len(top_12))
        groups = {
            'UBA': [top_12[0], top_12[3], top_12[4], top_12[7]],
            'UBB': [top_12[1], top_12[2], top_12[5], top_12[6]],
            'LB1': [top_12[8], top_12[9], top_12[10], top_12[11]]
        }
        format_name = "12-Player Fast Double Elimination Bracket"
    
    cursor = conn.cursor()
    cursor.execute("DELETE FROM playoff_matches WHERE season = ?", (season,))
    for match_id, players in groups.items():
        for s_id in players:
            if s_id is not None:
                cursor.execute("INSERT INTO playoff_matches (season, match_id, student_id) VALUES (?, ?, ?)", (season, match_id, s_id))
    conn.commit()
    print(f"\n{format_name} successfully seeded for {season}!")

def enter_match_scores(conn, season):
    cursor = conn.cursor()
    if season == "Spring 2026":
        match_id = input("Enter Match ID to update (MA, MB, LB, GF): ").strip().upper()
    else:
        match_id = input("Enter Match ID to update (UBA, UBB, LB1, LB2, LB3, UBF, LF, GF): ").strip().upper()
    
    cursor.execute('''
        SELECT p.student_id, s.name, p.score 
        FROM playoff_matches p 
        JOIN students s ON p.student_id = s.id 
        WHERE p.season = ? AND p.match_id = ?
    ''', (season, match_id))
    
    players = cursor.fetchall()
    if not players:
        print("\nNo players found in that match. Ensure earlier rounds are completed.")
        return
        
    print(f"\n--- Entering Scores for {match_id} ---")
    for s_id, name, current_score in players:
        val = input(f"{name} (Current: {current_score}): ").strip()
        if val.isdigit():
            cursor.execute("UPDATE playoff_matches SET score = ? WHERE season = ? AND match_id = ? AND student_id = ?", (int(val), season, match_id, s_id))
    conn.commit()
    print("Scores updated.")

def auto_advance_playoffs(conn, season):
    cursor = conn.cursor()
    
    def get_match_data(m_id):
        cursor.execute("SELECT student_id, score FROM playoff_matches WHERE season = ? AND match_id = ? ORDER BY score DESC", (season, m_id))
        rows = cursor.fetchall()
        if len(rows) != 4 or sum(r[1] for r in rows) == 0: return []
        return rows

    def get_match_players(m_id):
        return [r[0] for r in get_match_data(m_id)]

    def push_to_match(target, s_ids):
        if len(s_ids) == 4:
            cursor.execute("SELECT student_id FROM playoff_matches WHERE season = ? AND match_id = ?", (season, target))
            if set([r[0] for r in cursor.fetchall()]) == set(s_ids): return 
            cursor.execute("DELETE FROM playoff_matches WHERE season = ? AND match_id = ?", (season, target))
            for s_id in s_ids:
                cursor.execute("INSERT INTO playoff_matches (season, match_id, student_id) VALUES (?, ?, ?)", (season, target, s_id))

    if season == "Spring 2026":
        ma, mb = get_match_players('MA'), get_match_players('MB')
        if ma and mb: push_to_match('LB', [ma[2], mb[2], mb[1], mb[0]])
        lb = get_match_players('LB')
        if ma and lb: push_to_match('GF', ma[:2] + lb[:2]) 
    else:
        uba, ubb, lb1 = get_match_players('UBA'), get_match_players('UBB'), get_match_players('LB1')
        if uba and ubb: push_to_match('UBF', uba[:2] + ubb[:2])
        if uba and ubb and lb1: push_to_match('LB2', [uba[3], ubb[3]] + lb1[:2])
        lb2 = get_match_players('LB2')
        if uba and ubb and lb2: push_to_match('LB3', [uba[2], ubb[2]] + lb2[:2])
        ubf, lb3 = get_match_players('UBF'), get_match_players('LB3')
        if ubf and lb3: push_to_match('LF', ubf[2:4] + lb3[:2])
        lf = get_match_players('LF')
        if ubf and lf: push_to_match('GF', ubf[:2] + lf[:2])

    conn.commit()
    print("\nMatches advanced based on current scores!")

def manage_playoffs(conn):
    season = select_playoff_season(conn)
    while True:
        print(f"\n--- {season} Playoff Management ---")
        print("1. Seed Bracket (Overwrites current bracket)")
        print("2. Enter Match Scores")
        print("3. Auto-Advance Completed Matches")
        print("4. Return to Main Menu")
        choice = input("Select: ").strip()
        
        if choice == '1': seed_playoffs(conn, season)
        elif choice == '2': enter_match_scores(conn, season)
        elif choice == '3': auto_advance_playoffs(conn, season)
        elif choice == '4': break

def remove_data(conn):
    cursor = conn.cursor()
    cursor.execute("SELECT id, name FROM students ORDER BY name")
    students = cursor.fetchall()
    
    if not students:
        print("No students found in the database.")
        return

    print("\n--- Remove Data: Select Player ---")
    for index, student in enumerate(students, 1):
        print(f"[{index}] {student[1]}")
        
    user_input = input("\nEnter the student's number (or press Enter to cancel): ").strip()
    if not user_input or not user_input.isdigit() or not (1 <= int(user_input) <= len(students)):
        return
        
    student_id = students[int(user_input) - 1][0]
    student_name = students[int(user_input) - 1][1]
    
    cursor.execute("SELECT season FROM times WHERE student_id = ? UNION SELECT season FROM playoff_matches WHERE student_id = ?", (student_id, student_id))
    seasons = sort_seasons_chronologically([row[0] for row in cursor.fetchall() if row[0]])
    
    season_filter = 'ALL'
    if seasons:
        print(f"\n--- Select Season for {student_name} ---")
        print("[0] All Seasons")
        for index, season in enumerate(seasons, 1):
            print(f"[{index}] {season}")
        
        s_input = input("\nEnter season number (0 for All): ").strip()
        if s_input.isdigit() and 1 <= int(s_input) <= len(seasons):
            season_filter = seasons[int(s_input) - 1]
        elif s_input != '0':
            return
    else:
        print(f"No existing data found for '{student_name}'.")
        return

    track_filter = 'ALL'
    print(f"\n--- Select Track for {student_name} ---")
    t_input = input("Enter track number (1-10), or press Enter for ALL tracks: ").strip()
    if t_input.isdigit() and 1 <= int(t_input) <= 10:
        track_filter = int(t_input)
    elif t_input != "":
        return

    if season_filter == 'ALL' and track_filter == 'ALL':
        cursor.execute("DELETE FROM times WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM playoff_matches WHERE student_id = ?", (student_id,))
        cursor.execute("DELETE FROM students WHERE id = ?", (student_id,))
        print(f"\nSuccessfully deleted '{student_name}' entirely.")
    elif season_filter != 'ALL' and track_filter == 'ALL':
        cursor.execute("DELETE FROM times WHERE student_id = ? AND season = ?", (student_id, season_filter))
        cursor.execute("DELETE FROM playoff_matches WHERE student_id = ? AND season = ?", (student_id, season_filter))
        print(f"\nSuccessfully deleted all {season_filter} data for '{student_name}'.")
    elif season_filter == 'ALL' and track_filter != 'ALL':
        cursor.execute("DELETE FROM times WHERE student_id = ? AND track_number = ?", (student_id, track_filter))
        print(f"\nSuccessfully deleted Track {track_filter} data across all seasons for '{student_name}'.")
    else:
        cursor.execute("DELETE FROM times WHERE student_id = ? AND season = ? AND track_number = ?", (student_id, season_filter, track_filter))
        print(f"\nSuccessfully deleted Track {track_filter} for '{student_name}' in {season_filter}.")
        
    conn.commit()

def backup_database():
    if not os.path.exists('backups'):
        os.makedirs('backups')
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    backup_path = os.path.join('backups', f'trackmania_times_{timestamp}.db')
    shutil.copy2(DB_FILE, backup_path)

def main():
    conn = init_db()
    while True:
        print(f"\n=== Trackmania Tracker (Active: {ACTIVE_TRACK_SEASON}) ===")
        print("1. Record a Time (Manual)")
        print("2. Link Trackmania Account ID")
        print("3. Auto-Pull Times from Web")
        print("4. Manage Playoffs")
        print("5. Remove Data")
        print("6. Update Website (Keep Running)")
        print("7. Exit & Update Website")
        
        choice = input("Select an option (1-7): ").strip()
        
        if choice == '1': record_time(conn)
        elif choice == '2': link_account(conn)
        elif choice == '3': auto_pull_times(conn)
        elif choice == '4': manage_playoffs(conn)
        elif choice == '5': remove_data(conn)
        elif choice == '6':
            generate_static_website()
            print("Website successfully updated!")
        elif choice == '7':
            backup_database()
            conn.close()
            generate_static_website()
            break

if __name__ == "__main__":
    main()