from ml_practice import linear_reg
import json
import sqlite3

features = [[],[],[],[],[]]
output = []

with open("results_82_0.json") as file:
    data = json.load(file)
    for entry in range(len(data["per_game_stats"])):
        for i in range(len(features)):
            sums = [0] * 5
            for player in data["per_game_stats"][entry]:
                sums[i] += player[i]
            features[i].append(round(sums[i],1))  
        output.append(data["final_scores"][entry])

l = linear_reg(features, output)

l.stochastic_gd(alpha=0.005, max_iters=100)

out_file = open("train_output.txt", "a", encoding="utf-8")
def log(msg):
    out_file.write(f"{msg}\n")

log(l.params)

viable_scores = []
viable_player_team_era = []

connection = sqlite3.connect("players_scores.db")

with open("players_flat.json") as file:
    players = json.load(file)
    
for p in players:
    if p["era"] == "1950s":
        continue
    if p["rpg"] is None:
        p["rpg"] = 0
    if p["spg"] is None:
        p["spg"] = 0
    if p["bpg"] is None:
        p["bpg"] = 0
    pred = round(l.pred_new_data([[p["ppg"]], [p["rpg"]], [p["apg"]], [p["spg"]], [p["bpg"]]])[0], 2)
    if pred > 10:
        viable_player_team_era.append((p["player"], p["team"], p["era"], json.dumps(p["positions"]), pred))
viable_player_team_era = sorted(viable_player_team_era, key= lambda n: n[4], reverse=True)

cursor = connection.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS scores (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    player TEXT,
    team TEXT,
    era TEXT,
    positions TEXT,
    score FLOAT
)""")

for s in range(len(viable_player_team_era)):
    cursor.execute("INSERT INTO scores (player, team, era, positions, score) VALUES (?, ?, ?, ?, ?)", viable_player_team_era[s])

connection.commit()

connection.close()

out_file.close()



