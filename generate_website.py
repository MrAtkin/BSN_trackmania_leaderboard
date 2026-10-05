import sqlite3
import os
import subprocess
import csv

DB_FILE = 'trackmania_times.db'
PENALTY_MS = 5 * 60 * 1000

def ms_to_time(ms):
    minutes = ms // 60000
    ms %= 60000
    seconds = ms // 1000
    milliseconds = ms % 1000
    return f"{minutes:02d}:{seconds:02d}.{milliseconds:03d}"

def is_teacher(name):
    # Detects standard title prefixes to universally filter staff members
    return name.lower().startswith(('mr.', 'ms.', 'mrs.', 'miss', 'mr ', 'ms ', 'mrs '))

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

def generate_static_website():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    db_path = os.path.join(script_dir, DB_FILE)
    csv_path = os.path.join(script_dir, 'student_stats.csv')
    
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()
    cursor.execute("SELECT DISTINCT season FROM times")
    
    raw_seasons = [row[0] for row in cursor.fetchall() if row[0]]
    seasons = sort_seasons_chronologically(raw_seasons)

    if not seasons:
        print("No times recorded yet!")
        conn.close()
        return
        
    terms = []
    years = []
    for s in seasons:
        parts = s.split(' ')
        if len(parts) == 2:
            if parts[0] not in terms: terms.append(parts[0])
            if parts[1] not in years: years.append(parts[1])
        else:
            if s not in terms: terms.append(s)

    term_order = {"Winter": 1, "Spring": 2, "Summer": 3, "Fall": 4}
    terms = sorted(terms, key=lambda x: term_order.get(x, 99))
    years = sorted(years, reverse=True)
    
    # Initialize the yearly aggregator dictionary
    yearly_data = {y: {} for y in years}
    
    default_season_parts = seasons[0].split(' ')
    default_term = default_season_parts[0] if len(default_season_parts) > 0 else ""
    default_year = default_season_parts[1] if len(default_season_parts) == 2 else ""

    csv_file = open(csv_path, 'w', newline='', encoding='utf-8')
    csv_writer = csv.writer(csv_file)
    
    csv_header = ['Season', 'Name', 'Total Score']
    for i in range(1, 11):
        csv_header.extend([f'T{i} Score', f'T{i} Time'])
    csv_writer.writerow(csv_header)

    html_content = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>Trackmania Leaderboards</title>
    <style>
        :root {
            --bg-color: #f4f7f6;
            --text-color: #333;
            --container-bg: white;
            --th-bg: #2c3e50;
            --th-text: white;
            --border-color: #ddd;
            --row-hover: #f1f1f1;
            --input-bg: white;
            
            --atkin-text: #27ae60;
            --gold-text: #b58500; 
            --silver-text: #7f8c8d; 
            --bronze-text: #a05a2c; 
        }
        .dark-mode {
            --bg-color: #121212;
            --text-color: #e0e0e0;
            --container-bg: #1e1e1e;
            --th-bg: #111;
            --th-text: #e0e0e0;
            --border-color: #333;
            --row-hover: #2a2a2a;
            --input-bg: #333;
            
            --atkin-text: #2ecc71;
            --gold-text: #d4af37; 
            --silver-text: #bdc3c7; 
            --bronze-text: #cd7f32; 
        }
        
        body { font-family: Arial, sans-serif; background-color: var(--bg-color); color: var(--text-color); margin: 0; padding: 20px; transition: background-color 0.3s, color 0.3s; }
        .container { max-width: 1200px; margin: 0 auto; background: var(--container-bg); padding: 30px; border-radius: 8px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); transition: background-color 0.3s; }
        h1 { text-align: center; color: var(--text-color); }
        .controls { display: flex; justify-content: space-between; align-items: center; margin-bottom: 20px; padding: 0 10px; }
        .control-group { display: flex; align-items: center; }
        select, button { padding: 8px 12px; font-size: 16px; margin-left: 10px; border-radius: 4px; border: 1px solid var(--border-color); background-color: var(--input-bg); color: var(--text-color); cursor: pointer; }
        .dark-mode-btn { font-size: 18px; padding: 8px 12px; }
        .dark-mode-btn:hover { opacity: 0.8; }
        
        table { width: 100%; border-collapse: collapse; margin-top: 20px; }
        th, td { padding: 6px 4px; text-align: center; border-bottom: 1px solid var(--border-color); white-space: nowrap; font-size: 14px; }
        th { background-color: var(--th-bg); color: var(--th-text); }
        tr:hover { background-color: var(--row-hover); }
        .data-table { display: none; overflow-x: auto; width: 100%; -webkit-overflow-scrolling: touch; }
        .data-table.active { display: block; }
        
        #no-data-msg { display: none; text-align: center; margin-top: 40px; font-size: 18px; color: #7f8c8d; font-style: italic; }
        
        .fastest-time { color: var(--atkin-text); font-weight: 800; }
        .atkin-time { color: var(--atkin-text); font-weight: 800; }
        .gold-time { color: var(--gold-text); font-weight: 900; }
        .silver-time { color: var(--silver-text); font-weight: 800; }
        .bronze-time { color: var(--bronze-text); font-weight: 800; }
        
        th.sortable { cursor: pointer; position: relative; padding-right: 18px; user-select: none; }
        th.sortable:hover { opacity: 0.9; }
        th.sortable::after { content: '↕'; position: absolute; right: 4px; color: #7f8c8d; font-size: 11px; top: 50%; transform: translateY(-50%); }
        th.sort-asc::after { content: '↑'; color: #2ecc71; font-weight: bold; font-size: 14px; }
        th.sort-desc::after { content: '↓'; color: #e74c3c; font-weight: bold; font-size: 14px; }

        .bracket-container { display: grid; grid-template-columns: repeat(5, 200px); gap: 15px 25px; padding: 25px; background-color: #161616; border-radius: 8px; overflow-x: auto; margin-top: 20px; min-width: 1100px; }
        .grid-cell { display: flex; flex-direction: column; gap: 8px; }
        .grid-cell h2 { text-align: center; color: #aaa; font-size: 12px; margin: 0; text-transform: uppercase; letter-spacing: 1px; }
        
        .cell-uba  { grid-column: 1; grid-row: 1; }
        .cell-ubb  { grid-column: 1; grid-row: 3; }
        .cell-lb1  { grid-column: 1; grid-row: 5; }
        .cell-ubf  { grid-column: 2; grid-row: 2; }
        .cell-lb2  { grid-column: 2; grid-row: 4; }
        .cell-lb3  { grid-column: 3; grid-row: 4; }
        .cell-lf   { grid-column: 4; grid-row: 3; }
        .cell-gf   { grid-column: 5; grid-row: 2 / 4; align-self: center; }

        .bracket-container-legacy { display: grid; grid-template-columns: repeat(3, 200px); gap: 15px 25px; padding: 25px; background-color: #161616; border-radius: 8px; overflow-x: auto; margin-top: 20px; min-width: 700px; }
        .cell-ma { grid-column: 1; grid-row: 1; }
        .cell-mb { grid-column: 1; grid-row: 3; }
        .cell-lb { grid-column: 2; grid-row: 2; }
        .cell-gf-legacy { grid-column: 3; grid-row: 1 / 3; align-self: center; } 
        
        .bracket-match { background-color: #242424; border: 1px solid #333; border-radius: 4px; overflow: hidden; color: white; box-shadow: 0 4px 8px rgba(0,0,0,0.5); }
        .bracket-match.golden { border: 1px solid #d4af37; box-shadow: 0 0 12px rgba(212, 175, 55, 0.3); }
        
        .match-player { display: flex; justify-content: space-between; align-items: center; padding: 6px 12px; border-bottom: 1px solid #333; font-size: 14px; height: 20px; }
        .match-player:last-child { border-bottom: none; }
        .match-player.advancing { font-weight: bold; background-color: #2c3e50; }
        .bracket-match.golden .match-player.advancing { background-color: #4a3b0e; }
        
        .player-score { background-color: #111; padding: 2px 6px; border-radius: 4px; font-family: monospace; color: #fff; }
        .narrow-table { max-width: 750px; margin: 0 auto; }
    </style>
    <script>
        function updateView() {
            var term = document.getElementById('termSelect').value;
            var year = document.getElementById('yearSelect') ? document.getElementById('yearSelect').value : "";
            var mode = document.getElementById('modeSelect').value;
            
            var seasonId = year ? term + "_" + year : term;
            
            // Route 'Overall' selection in the Season dropdown to the Yearly table
            var targetId = term === 'Overall' ? 'overall-' + year : mode + '-' + seasonId;
            
            var tables = document.getElementsByClassName('data-table');
            for (var i = 0; i < tables.length; i++) { 
                tables[i].classList.remove('active'); 
            }
            
            var targetElement = document.getElementById(targetId);
            var noDataMsg = document.getElementById('no-data-msg');
            
            if(targetElement) { 
                targetElement.classList.add('active'); 
                if(noDataMsg) noDataMsg.style.display = 'none';
            } else {
                if(noDataMsg) noDataMsg.style.display = 'block';
            }
        }

        function toggleDarkMode() {
            document.body.classList.toggle('dark-mode');
            localStorage.setItem('darkMode', document.body.classList.contains('dark-mode'));
        }

        window.onload = function() {
            if (localStorage.getItem('darkMode') === 'true') {
                document.body.classList.add('dark-mode');
            }
            updateView();
        }

        function sortTable(thElement, colIndex) {
            var table = thElement.closest('table');
            var tbody = table.querySelector('tbody');
            var rows = Array.from(tbody.querySelectorAll('tr'));
            
            var isAsc = thElement.classList.contains('sort-asc');
            var direction = isAsc ? -1 : 1;
            
            var ths = table.querySelectorAll('th');
            ths.forEach(function(th) { th.classList.remove('sort-asc', 'sort-desc'); });
            
            thElement.classList.add(isAsc ? 'sort-desc' : 'sort-asc');
            
            rows.sort(function(a, b) {
                var cellA = a.cells[colIndex].textContent.trim();
                var cellB = b.cells[colIndex].textContent.trim();
                
                if (cellA === "-") cellA = "99:99.999";
                if (cellB === "-") cellB = "99:99.999";
                
                var valA = isNaN(Number(cellA)) ? cellA.toLowerCase() : Number(cellA);
                var valB = isNaN(Number(cellB)) ? cellB.toLowerCase() : Number(cellB);
                
                if (valA < valB) return -1 * direction;
                if (valA > valB) return 1 * direction;
                return 0;
            });
            
            rows.forEach(function(row) { tbody.appendChild(row); });
        }
    </script>
</head>
<body>
<div class="container">
    <h1>Trackmania Leaderboards</h1>
    <div class="controls">
        <div class="control-group">
            <label style="font-size: 16px; font-weight: bold;">Season:</label>
            <select id="termSelect" onchange="updateView()">
"""
    for t in terms:
        selected = ' selected' if t == default_term else ''
        html_content += f'                <option value="{t}"{selected}>{t}</option>\n'
        
    html_content += """                <option value="Overall">Overall</option>
            </select>
"""
    if years:
        html_content += """            <label style="font-size: 16px; font-weight: bold; margin-left: 15px;">Year:</label>
            <select id="yearSelect" onchange="updateView()">
"""
        for y in years:
            selected = ' selected' if y == default_year else ''
            html_content += f'                <option value="{y}"{selected}>{y}</option>\n'
            
        html_content += """            </select>
"""
        
    html_content += """        </div>
        <div class="control-group">
            <label style="font-size: 16px; font-weight: bold;">Display Mode:</label>
            <select id="modeSelect" onchange="updateView()">
                <option value="times">Times</option>
                <option value="scores">Scores</option>
                <option value="records">Student Records</option>
                <option value="playoffs">Playoffs Bracket</option>
            </select>
            <button class="dark-mode-btn" onclick="toggleDarkMode()" title="Toggle Dark Mode">🌙</button>
        </div>
    </div>
    
    <div id="no-data-msg">
        No tournament data available for the selected season and year.
    </div>
"""

    for index, season in enumerate(seasons):
        safe_season_id = season.replace(" ", "_")
        cursor.execute("SELECT DISTINCT student_id FROM times WHERE season = ?", (season,))
        active_students = [row[0] for row in cursor.fetchall()]
        
        student_times_pool = {i: [] for i in range(1, 11)}
        student_data = {}
        
        for student_id in active_students:
            cursor.execute("SELECT name FROM students WHERE id = ?", (student_id,))
            name = cursor.fetchone()[0]
            cursor.execute("SELECT track_number, time_ms FROM times WHERE student_id = ? AND season = ?", (student_id, season))
            times_dict = dict(cursor.fetchall())
            
            student_data[student_id] = {'name': name, 'track_times': [], 'track_scores': [], 'total_score': 0}
            
            for i in range(1, 11):
                t_ms = times_dict.get(i, PENALTY_MS)
                student_data[student_id]['track_times'].append(t_ms)
                
                # ONLY genuine students are used for scoring and the student medal pool
                if not is_teacher(name):
                    student_times_pool[i].append(t_ms)

        top_student_times = {}
        atkin_times = {}
        for i in range(1, 11):
            valid_times = [t for t in student_times_pool[i] if t < PENALTY_MS]
            unique_sorted = sorted(list(set(valid_times)))
            top_student_times[i] = unique_sorted[:3] 
            
            atkin_t = PENALTY_MS
            for s_id in active_students:
                if student_data[s_id]['name'].strip().lower() in ["mr. atkin", "mr atkin"]:
                    atkin_t = student_data[s_id]['track_times'][i-1]
                    break
            atkin_times[i] = atkin_t

        for student_id in active_students:
            name = student_data[student_id]['name']
            if not is_teacher(name):
                csv_row = [
                    season, 
                    name, 
                    student_data[student_id]['total_score']
                ]
                
            for i in range(1, 11):
                my_time = student_data[student_id]['track_times'][i-1]
                if my_time == PENALTY_MS:
                    score = 0
                else:
                    actual = sum(1 for t in student_times_pool[i] if t < PENALTY_MS)
                    faster = sum(1 for t in student_times_pool[i] if t < my_time)
                    if actual > 1: 
                        dynamic_floor = 1 if actual >= 10 else 100 - ((actual - 2) * (99 / 8))
                        score_range = 150 - dynamic_floor
                        score = round(150 - (faster * (score_range / (actual - 1))))
                    else: 
                        score = 150
                        
                student_data[student_id]['track_scores'].append(score)
                student_data[student_id]['total_score'] += score
                
                if not is_teacher(name):
                    csv_row.extend([score, "-" if my_time == PENALTY_MS else ms_to_time(my_time)])
                    
            if not is_teacher(name):
                csv_row[2] = student_data[student_id]['total_score']
                csv_writer.writerow(csv_row)
                
                # --- NEW YEARLY AGGREGATION LOGIC ---
                term = season.split(' ')[0] if len(season.split(' ')) == 2 else season
                year = season.split(' ')[1] if len(season.split(' ')) == 2 else "Unknown"
                
                if year in yearly_data:
                    if student_id not in yearly_data[year]:
                        yearly_data[year][student_id] = {'name': name, 'total_score': 0, 'seasons': {}}
                    yearly_data[year][student_id]['seasons'][term] = student_data[student_id]['total_score']
                    yearly_data[year][student_id]['total_score'] += student_data[student_id]['total_score']

        cursor.execute('''
            SELECT p.match_id, s.name, p.score 
            FROM playoff_matches p 
            JOIN students s ON p.student_id = s.id 
            WHERE p.season = ? 
            ORDER BY p.match_id, p.score DESC
        ''', (season,))
        
        bracket_data = {}
        for match_id, name, score in cursor.fetchall():
            if match_id not in bracket_data: bracket_data[match_id] = []
            bracket_data[match_id].append({'name': name, 'score': score})

        def render_match(match_id, b_data, is_golden=False, is_elimination=False):
            players = b_data.get(match_id, [])
            golden_class = ' golden' if is_golden else ''
            html = '<div class="bracket-match' + golden_class + '">\n'
            
            match_played = sum([p["score"] for p in players]) > 0 if len(players) == 4 else False
            
            for idx in range(4):
                if idx < len(players):
                    p = players[idx]
                    adv_class = ""
                    name_style = ""
                    
                    if match_played:
                        if match_id == 'GF':
                            if idx == 0: adv_class = "advancing"
                            elif idx >= 2 and is_elimination: name_style = "color: #e74c3c;" 
                        else:
                            if idx < 2: adv_class = "advancing"
                            elif is_elimination: name_style = "color: #e74c3c;" 
                                
                    html += f'<div class="match-player {adv_class}"><span style="{name_style}">{p["name"]}</span><span class="player-score">{p["score"]}</span></div>\n'
                else:
                    html += '<div class="match-player"><span style="color: #666; font-style: italic;">TBD</span></div>\n'
            html += '</div>\n'
            return html

        is_active = "active" if index == 0 else ""
        
        # TIME TABLE (Sorted with Countback Tiebreaker Rule)
        html_content += f'    <div id="times-{safe_season_id}" class="data-table {is_active}"><table><thead><tr><th class="sortable" onclick="sortTable(this, 0)">Rank</th><th class="sortable" onclick="sortTable(this, 1)">Name</th>'
        for i in range(1, 11): html_content += f'<th class="sortable" onclick="sortTable(this, {i+1})">T{i} Time</th>'
        html_content += '</tr></thead><tbody>'
        
        for rank, data in enumerate(sorted(student_data.values(), key=lambda x: (x['total_score'], sorted(x['track_scores'], reverse=True)), reverse=True), 1):
            html_content += f'<tr><td><strong>{rank}</strong></td><td style="text-align: left;">{data["name"]}</td>'
            
            for idx, t_ms in enumerate(data['track_times']):
                track_idx = idx + 1
                if t_ms == PENALTY_MS: 
                    html_content += '<td><span style="color: #e74c3c;">-</span></td>'
                    continue
                
                is_mr_atkin = data["name"].strip().lower() in ["mr. atkin", "mr atkin"]
                student_top_3 = top_student_times[track_idx]
                atkin_t = atkin_times[track_idx]
                
                fastest_student_time = student_top_3[0] if len(student_top_3) > 0 else None
                student_stole_green = (atkin_t < PENALTY_MS and fastest_student_time is not None and fastest_student_time < atkin_t)
                
                if is_mr_atkin:
                    # Stays bold green unless a student beat this specific track time
                    if not student_stole_green:
                        html_content += f'<td class="atkin-time">{ms_to_time(t_ms)}</td>' 
                    else:
                        html_content += f'<td>{ms_to_time(t_ms)}</td>' 
                else:
                    if t_ms in student_top_3:
                        medal_rank = student_top_3.index(t_ms)
                        if medal_rank == 0:
                            html_content += f'<td class="gold-time">{ms_to_time(t_ms)}</td>'
                        elif medal_rank == 1:
                            html_content += f'<td class="silver-time">{ms_to_time(t_ms)}</td>'
                        elif medal_rank == 2:
                            html_content += f'<td class="bronze-time">{ms_to_time(t_ms)}</td>'
                    else:
                        html_content += f'<td>{ms_to_time(t_ms)}</td>'
                        
            html_content += '</tr>'
        html_content += '</tbody></table></div>\n'

        # SCORE TABLE (Sorted with Countback Tiebreaker Rule)
        html_content += f'    <div id="scores-{safe_season_id}" class="data-table"><table><thead><tr><th class="sortable" onclick="sortTable(this, 0)">Rank</th><th class="sortable" onclick="sortTable(this, 1)">Name</th>'
        for i in range(1, 11): html_content += f'<th class="sortable" onclick="sortTable(this, {i+1})">T{i} Score</th>'
        html_content += '<th class="sortable" onclick="sortTable(this, 12)">Total Score</th></tr></thead><tbody>'
        
        students_for_scores = [d for d in student_data.values() if not is_teacher(d['name'])]
        for rank, data in enumerate(sorted(students_for_scores, key=lambda x: (x['total_score'], sorted(x['track_scores'], reverse=True)), reverse=True), 1):
            html_content += f'<tr><td><strong>{rank}</strong></td><td style="text-align: left;">{data["name"]}</td>'
            for score in data['track_scores']: html_content += f'<td>{score}</td>'
            html_content += f'<td><strong>{data["total_score"]}</strong></td></tr>'
        html_content += '</tbody></table></div>\n'
        
        # STUDENT RECORDS TABLE
        html_content += f'    <div id="records-{safe_season_id}" class="data-table"><table><thead><tr><th style="width: 20%;">Track</th><th style="text-align: left;">Student Record Holder</th><th class="sortable" onclick="sortTable(this, 2)">Record Time</th></tr></thead><tbody>'
        for i in range(1, 11):
            valid_times = [(student_data[s_id]['name'], student_data[s_id]['track_times'][i-1]) 
                           for s_id in active_students 
                           if student_data[s_id]['track_times'][i-1] < PENALTY_MS and not is_teacher(student_data[s_id]['name'])]
                           
            if valid_times:
                best_t = min(valid_times, key=lambda x: x[1])[1]
                holders = [name for name, t in valid_times if t == best_t]
                holder_str = ", ".join(holders)
                
                atkin_t = atkin_times[i]
                time_class = "fastest-time"
                
                if atkin_t < PENALTY_MS and best_t < atkin_t:
                    time_class = "gold-time"
                    
                html_content += f'<tr><td><strong>Track {i}</strong></td><td style="text-align: left;">{holder_str}</td><td class="{time_class}">{ms_to_time(best_t)}</td></tr>'
            else:
                html_content += f'<tr><td><strong>Track {i}</strong></td><td style="text-align: left;">-</td><td>-</td></tr>'
        html_content += '</tbody></table></div>\n'

        # DYNAMIC PLAYOFF BRACKET RENDERER
        html_content += '    <div id="playoffs-' + safe_season_id + '" class="data-table">'
        
        if season == "Spring 2026":
            html_content += '      <div class="bracket-container-legacy">'
            html_content += '        <div class="grid-cell cell-ma"><h2 style="color: #d4af37;">Match A (Top 4)</h2>' + render_match("MA", bracket_data, is_golden=True, is_elimination=False) + '</div>'
            html_content += '        <div class="grid-cell cell-mb"><h2>Match B (Bottom 4)</h2>' + render_match("MB", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-lb"><h2>Lower Bracket</h2>' + render_match("LB", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-gf-legacy"><h2 style="color: #d4af37;">Grand Final</h2>' + render_match("GF", bracket_data, is_golden=True, is_elimination=True) + '</div>'
            html_content += '      </div>'
        else:
            html_content += '      <div class="bracket-container">'
            html_content += '        <div class="grid-cell cell-uba"><h2 style="color: #d4af37;">Upper Bracket A</h2>' + render_match("UBA", bracket_data, is_golden=True, is_elimination=False) + '</div>'
            html_content += '        <div class="grid-cell cell-ubf"><h2 style="color: #d4af37;">UB Final</h2>' + render_match("UBF", bracket_data, is_golden=True, is_elimination=False) + '</div>'
            html_content += '        <div class="grid-cell cell-gf"><h2 style="color: #d4af37;">Grand Final</h2>' + render_match("GF", bracket_data, is_golden=True, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-ubb"><h2 style="color: #d4af37;">Upper Bracket B</h2>' + render_match("UBB", bracket_data, is_golden=True, is_elimination=False) + '</div>'
            html_content += '        <div class="grid-cell cell-lf"><h2>Lower Final</h2>' + render_match("LF", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-lb2"><h2>Lower Bracket 2</h2>' + render_match("LB2", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-lb3"><h2>Lower Bracket 3</h2>' + render_match("LB3", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '        <div class="grid-cell cell-lb1"><h2>Lower Bracket 1</h2>' + render_match("LB1", bracket_data, is_golden=False, is_elimination=True) + '</div>'
            html_content += '      </div>'

        html_content += '    </div>\n'
        
    # --- NEW YEARLY OVERALL STANDINGS TABLES RENDERER ---
    for year in years:
        if year in yearly_data and yearly_data[year]:
            html_content += f'    <div id="overall-{year}" class="data-table narrow-table"><table><thead><tr><th class="sortable" onclick="sortTable(this, 0)">Rank</th><th class="sortable" onclick="sortTable(this, 1)">Name</th>'
            for t in ["Winter", "Spring", "Summer", "Fall"]:
                html_content += f'<th class="sortable" onclick="sortTable(this, {["Winter", "Spring", "Summer", "Fall"].index(t) + 2})">{t} Score</th>'
            html_content += '<th class="sortable" onclick="sortTable(this, 6)">Yearly Total</th></tr></thead><tbody>'
            
            # Tiebreaker applied to yearly totals too (compares total score, then falls back to highest individual season)
            ranked_students = sorted(yearly_data[year].values(), key=lambda x: (x['total_score'], sorted(x['seasons'].values(), reverse=True)), reverse=True)
            for rank, data in enumerate(ranked_students, 1):
                html_content += f'<tr><td><strong>{rank}</strong></td><td style="text-align: left;">{data["name"]}</td>'
                for t in ["Winter", "Spring", "Summer", "Fall"]:
                    score = data['seasons'].get(t, "-")
                    html_content += f'<td>{score}</td>'
                html_content += f'<td><strong>{data["total_score"]}</strong></td></tr>'
            html_content += '</tbody></table></div>\n'

    html_content += """</div></body></html>"""
    conn.close()
    csv_file.close()

    file_path = os.path.join(script_dir, 'leaderboard.html')
    with open(file_path, 'w', encoding='utf-8') as f:
        f.write(html_content)
    
    try:
        subprocess.run(['git', 'add', 'leaderboard.html', 'student_stats.csv', DB_FILE], cwd=script_dir, check=True, capture_output=True, text=True)
        subprocess.run(['git', 'commit', '-m', 'Add Yearly Overall Standings'], cwd=script_dir, capture_output=True, text=True)
        subprocess.run(['git', 'push'], cwd=script_dir, check=True, capture_output=True, text=True)
    except subprocess.CalledProcessError:
        pass

if __name__ == '__main__':
    generate_static_website()