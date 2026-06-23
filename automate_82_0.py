"""
82-0.com Automation Script (Classic mode)

Each round the game hands you a RANDOM team + decade and a list of players from
that team/era. You can't pick from a predefined roster because the team/decade
combos are chosen randomly. For a test run we scan the player list each round
and select the FIRST player that can fill one of the still-empty court slots,
drop them into that slot, then read each player's per-game stats and the final
score. Scanning for the first *eligible* player (rather than blindly taking the
first one) means every round is winnable, so no runs fail.

Requirements:
    pip install playwright
    python -m playwright install chromium

Usage:
    python automate_82_0.py

Output:
    results_82_0.json — two parallel lists, one entry per game:
        per_game_stats : list of 5 [PPG, RPG, APG, SPG, BPG] lists (one per player)
        final_scores   : the overall points rating
"""
import sqlite3
import json
import re
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

# ── Config ─────────────────────────────────────────────────────────────────────
OUTPUT_FILE    = "results_82_0.json"
NUM_RUNS       = 100
HEADLESS       = False   # set True to run without a visible browser window
SLOW_MO        = 100     # ms between actions
NAV_TIMEOUT    = 30_000  # ms to wait for page load
ACTION_TIMEOUT = 8_000   # ms to wait for UI elements

POSITIONS = ("PG", "SG", "SF", "PF", "C")
CARD_SEL  = "div[draggable='true'].cursor-pointer"   # a player card in the list
SLOT_SEL  = "button.w-16.h-16"                        # a court position slot

# ── Helpers ────────────────────────────────────────────────────────────────────

def _click_if_present(page, label, timeout=400):
    try:
        btn = page.get_by_role("button", name=label, exact=False).first
        if btn.is_visible(timeout=timeout):
            btn.click()
            time.sleep(0.4)
            return True
    except Exception:
        pass
    return False


def wait_for_board(page, timeout=25):
    """Clear the promo popup, cookie banner, mode modal and onboarding until the
    game board is live. Readiness is the 'Round x/5' label — the SPIN element
    exists in the DOM behind the modals, so it can't be used as the signal."""
    deadline = time.time() + timeout
    while time.time() < deadline:
        # Order matters: dismiss the promo + cookie first, then enter Classic mode.
        # "Close" is intentionally omitted — it's ambiguous and can dismiss the
        # mode modal without starting a game.
        for label in ("Don't Show Again", "Accept", "Play Classic",
                      "Got it", "Continue", "Next", "Done"):
            _click_if_present(page, label, timeout=300)
        if round_number(page) is not None:
            return True
        time.sleep(0.4)
    return False


def enter_game(page):
    """Load the site and get to a live Round 1/5 board."""
    page.goto("https://www.82-0.com/", timeout=NAV_TIMEOUT)
    time.sleep(3)
    wait_for_board(page)


def round_number(page):
    m = re.search(r'Round\s+(\d)\s*/\s*5', page.inner_text("body"))
    return int(m.group(1)) if m else None


def _arrange(occupant, forbid):
    """Assign every already-placed player to a distinct eligible position other than
    `forbid`, freeing that slot. `occupant` maps a player key (its current slot, or
    just an index) to that player's eligible positions. Returns {key: position} or
    None if impossible. Bipartite matching via Kuhn's algorithm."""
    allowed = [p for p in POSITIONS if p != forbid]
    match = {}  # position -> player key

    def assign(key, seen):
        for pos in sorted(occupant[key], key=POSITIONS.index):   # guards before centers
            if pos in allowed and pos not in seen:
                seen.add(pos)
                if pos not in match or assign(match[pos], seen):
                    match[pos] = key
                    return True
        return False

    for key in occupant:
        if not assign(key, set()):
            return None
    return {key: pos for pos, key in match.items()}


def empty_slots(placed):
    """A slot is empty unless it's genuinely full: it counts as open whenever the
    already-placed players (`placed` = list of each player's eligible positions)
    can be rearranged among their other positions to free it."""
    occupant = dict(enumerate(placed))
    return [p for p in POSITIONS if _arrange(occupant, p) is not None]


def player_card(page, index=0):
    """Wait for the player list and return (locator, name, positions, team, era)
    for the card at `index`."""
    page.locator(CARD_SEL).first.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    card = page.locator(CARD_SEL).nth(index)
    lines = [l for l in card.inner_text(timeout=2000).split("\n") if l.strip()]
    name     = lines[0]
    posline  = card.locator("p").nth(1).inner_text()
    positions = [x for x in re.split(r"[^A-Z]+", posline) if x in POSITIONS]
    team, era = "?", "?"
    teamline = card.locator("p").nth(2).inner_text()
    parts = [x.strip() for x in re.split(r"[^A-Za-z0-9']+", teamline) if x.strip()]
    if len(parts) >= 2:
        team, era = parts[0], parts[1]
    return card, name, positions, team, era


def first_eligible_card(page, empties):
    """Return (index, name, team, era, eligible_slots) for the first player card
    on screen that can fill one of the still-empty slots, or None. eligible_slots
    is every empty slot the player can occupy, in the card's position order."""
    page.locator(CARD_SEL).first.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    count = page.locator(CARD_SEL).count()
    for i in range(count):
        _card, name, positions, team, era = player_card(page, i)
        eligible = [p for p in positions if p in empties]
        if eligible:
            return i, name, team, era, eligible
    return None

def best_fit(page, team, era, empties):

    page.locator(CARD_SEL).first.wait_for(state="visible", timeout=ACTION_TIMEOUT)

    connection = sqlite3.connect("players_scores.db")

    c = connection.cursor()

    count = page.locator(CARD_SEL).count()

    # Map each on-screen player name to its card index so we can return the index
    # the game actually uses for clicking, not the DB query offset.
    card_index_by_name = {player_card(page, i)[1]: i for i in range(count)}

    offset = 0

    while True:

        c.execute("SELECT player, positions from scores where team = ? and era = ? limit 1 offset ?", (team, era, offset))

        player_pos = c.fetchone()

        if player_pos is None:
            break

        positions = json.loads(player_pos[1])
        # Prefer high-priority slots: guards, then forwards, then centers.
        eligible = sorted((p for p in positions if p in empties), key=POSITIONS.index)

        card_index = card_index_by_name.get(player_pos[0])

        if eligible and card_index is not None:
            connection.close()
            return card_index, player_pos[0], team, era, eligible, positions

        offset += 1
    connection.close()
    return None


    

def _slot_index_map(page):
    """Map each court position to its slot-button DOM index, read from the empty
    board. Captured while all slots show their position label so it stays valid once
    they fill with players (a filled slot's button no longer shows the label)."""
    page.locator(SLOT_SEL).first.wait_for(state="visible", timeout=ACTION_TIMEOUT)
    labels = page.evaluate(
        "(sel)=>[...document.querySelectorAll(sel)].map(b=>(b.textContent||'').trim())",
        SLOT_SEL,
    )
    return {lab: i for i, lab in enumerate(labels) if lab in POSITIONS}


def _click_slot(page, slots, pos):
    page.locator(SLOT_SEL).nth(slots[pos]).click(timeout=ACTION_TIMEOUT)


def _drag_slot(page, slots, src, dst):
    """Drag the player in slot `src` onto the empty slot `dst`. The board uses native
    HTML5 drag-and-drop (draggable='true'), which Chromium does not fire from synthetic
    mouse moves, so dispatch the drag events directly with a shared DataTransfer."""
    source = page.locator(SLOT_SEL).nth(slots[src])
    target = page.locator(SLOT_SEL).nth(slots[dst])
    source.scroll_into_view_if_needed()
    dt = page.evaluate_handle("() => new DataTransfer()")
    source.dispatch_event("dragstart", {"dataTransfer": dt})
    target.dispatch_event("dragenter", {"dataTransfer": dt})
    target.dispatch_event("dragover", {"dataTransfer": dt})
    target.dispatch_event("drop", {"dataTransfer": dt})
    source.dispatch_event("dragend", {"dataTransfer": dt})


def _plan_moves(arrangement):
    """Turn a target {current_slot: target_slot} mapping into an ordered list of
    (from, to) single-player moves, each dropping a player onto an empty slot. Empty
    slots act as buffers to resolve cycles (15-puzzle style)."""
    cur = {k: k for k in arrangement}   # player id (starting slot) -> current slot
    moves = []
    occupied = lambda: set(cur.values())
    while any(cur[k] != arrangement[k] for k in arrangement):
        for k in arrangement:                       # a player whose target is open
            if cur[k] != arrangement[k] and arrangement[k] not in occupied():
                moves.append((cur[k], arrangement[k]))
                cur[k] = arrangement[k]
                break
        else:                                        # cycle: park one player in a buffer
            buf = next(p for p in POSITIONS if p not in occupied())
            for k in arrangement:
                if cur[k] != arrangement[k]:
                    moves.append((cur[k], buf))
                    cur[k] = buf
                    break
    return moves


def _slot_is_empty(page, slots, pos):
    """An empty slot shows its position label; a filled one shows the player."""
    return page.locator(SLOT_SEL).nth(slots[pos]).inner_text(timeout=2000).strip() == pos


def _free_slot(page, slots, occupant, lineup, target):
    """Rearrange the already-placed players so `target` becomes empty by dragging each
    player from its slot onto an empty one. Mutates occupant/lineup to track the new
    board. False if target can't be freed or a drag won't land."""
    if target not in occupant:
        return True
    arrangement = _arrange(occupant, target)
    if arrangement is None:
        return False
    for src, dst in _plan_moves(arrangement):
        for _ in range(3):
            _drag_slot(page, slots, src, dst)
            time.sleep(0.6)
            if _slot_is_empty(page, slots, src):   # drag landed: src vacated
                break
        else:
            return False   # drag never landed — don't desync occupant from the board
        occupant[dst] = occupant.pop(src)
        if src in lineup:
            lineup[dst] = lineup.pop(src)
    return True


def _spin(page):
    """Click SPIN, retrying while the button renders after a round transition or a
    brief ad clears. Waits between attempts so it isn't just hammering an empty DOM."""
    last = None
    for _ in range(6):
        try:
            page.get_by_text("SPIN", exact=False).first.click(timeout=4_000)
            return
        except Exception as e:
            last = e
            for label in ("Got it", "Continue", "Next", "Done"):
                _click_if_present(page, label, timeout=200)
            time.sleep(2)
    raise last


def _best_eligible_score(c, team, era, empties):
    """Highest OVR among players for (team, era) that can fill one of the open slots,
    read straight from the DB. 0 if none fits."""
    c.execute("SELECT positions, score FROM scores WHERE team=? AND era=? ORDER BY score DESC",
              (team, era))
    for positions_json, score in c.fetchall():
        if any(p in empties for p in json.loads(positions_json)):
            return score
    return 0.0


def _axis_reroll_value(c, axis, team, era, empties):
    """Average best-eligible OVR over every other valid value on `axis`: other teams in
    the same era, or other eras for the same team. Combos that never existed simply
    aren't in the DB, so they drop out of the average."""
    if axis == "team":
        c.execute("SELECT DISTINCT team FROM scores WHERE era=? AND team!=?", (era, team))
        cands = [(r[0], era) for r in c.fetchall()]
    else:
        c.execute("SELECT DISTINCT era FROM scores WHERE team=? AND era!=?", (team, era))
        cands = [(team, r[0]) for r in c.fetchall()]
    scores = [_best_eligible_score(c, t, e, empties) for t, e in cands]
    return sum(scores) / len(scores) if scores else 0.0


def _reroll(page, axis):
    """Click the refresh icon button sitting beside the 'team'/'era' label. Only the
    label's own button or an adjacent sibling counts — never a page-wide search, which
    would wander back to the restart-game button."""
    label = page.get_by_text(re.compile(rf"^{axis}$", re.I)).first
    for xp in ("xpath=ancestor-or-self::button[1]",    # refresh icon + word share one button
               "xpath=preceding-sibling::button[1]",   # <button/> <span>team</span>
               "xpath=following-sibling::button[1]",
               "xpath=../button[1]"):                   # button is a sibling under the same row
        btn = label.locator(xp)
        if btn.count():
            btn.first.click(timeout=ACTION_TIMEOUT)
            return
    raise RuntimeError(f"could not find reroll control for {axis}")


def consider_rerolls(page, team, era, empties, rerolls):
    """Spend remaining team/era rerolls while a reroll's expected OVR beats the current
    draw. Rerolls land on a random other value, so the decision is made on the average
    OVR across possible outcomes. Returns the (possibly new) team/era."""
    connection = sqlite3.connect("players_scores.db")
    c = connection.cursor()
    try:
        while True:
            current = _best_eligible_score(c, team, era, empties)
            options = [(axis, _axis_reroll_value(c, axis, team, era, empties))
                       for axis in ("team", "era") if rerolls[axis]]
            axis, value = max(options, key=lambda o: o[1], default=(None, 0.0))
            if axis is None or value <= current:
                break
            _reroll(page, axis)
            rerolls[axis] = False
            time.sleep(2.3)
            p = player_card(page, 0)
            team, era = p[3], p[4]
    finally:
        connection.close()
    return team, era


def play_one_game(page):
    """Build a full lineup by taking the first player each round. Returns lineup dict."""
    lineup = {}
    occupant = {}   # court slot -> the occupying player's eligible positions
    slots = None
    rerolls = {"team": True, "era": True}   # one reroll per axis for the whole game
    while True:
        rnd = round_number(page)
        if rnd is None:
            break
        _spin(page)
        time.sleep(2.3)
        if slots is None:   # capture the slot layout on the still-empty round-1 board
            slots = _slot_index_map(page)

        empties = empty_slots(list(occupant.values()))
        if not empties:
            return lineup

        p = player_card(page, 0)

        team = p[3]
        era = p[4]

        team, era = consider_rerolls(page, team, era, empties, rerolls)

        picked = best_fit(page, team, era, empties)
        if picked is None:
            raise RuntimeError(f"round {rnd}: no player on screen can fill {empties}")
        index, name, team, era, eligible, positions = picked

        # An eligible slot may be physically occupied but freeable: rearrange the
        # placed players to vacate it, then click the card in. A click occasionally
        # misses (round unchanged, no SPIN), so retry the placement.
        placed_ok = False
        for slot in eligible:
            if not _free_slot(page, slots, occupant, lineup, slot):
                continue
            for _ in range(3):
                try:
                    player_card(page, index)[0].click()
                    time.sleep(0.6)
                    _click_slot(page, slots, slot)
                    time.sleep(1.0)
                    if round_number(page) != rnd:   # advanced to next round / result screen
                        lineup[slot] = f"{name} ({team},{era})"
                        occupant[slot] = positions
                        placed_ok = True
                        break
                except Exception:
                    time.sleep(1)
            if placed_ok:
                break
        if not placed_ok:
            raise RuntimeError(f"round {rnd}: could not place {name} in {eligible}")
    time.sleep(5)
    return lineup


_PLAYER_STATS_RE = re.compile(
    r'([0-9.]+)\s+PPG\s+([0-9.]+)\s+RPG\s+([0-9.]+)\s+APG\s+([0-9.]+)\s+SPG\s+([0-9.]+)\s+BPG'
)


def parse_result(page):
    """Read the result screen and return:
        players — list of 5 [PPG, RPG, APG, SPG, BPG] lists, in lineup order
        score   — the overall points rating (the 'X.X pts' value)
    """
    page.wait_for_selector("text=/PROJECTED RECORD/i", timeout=15_000)
    time.sleep(0.5)
    body = page.inner_text("body")
    rows = [[float(x) for x in m.groups()] for m in _PLAYER_STATS_RE.finditer(body)]

    # The result screen appends a team-total row (column sums of the 5 players);
    # drop it so only the per-player stats remain.
    for i, r in enumerate(rows):
        others = rows[:i] + rows[i + 1:]
        if others and all(abs(r[c] - sum(o[c] for o in others)) < 0.5 for c in range(5)):
            rows.pop(i)
            break

    pts = re.search(r'([0-9]+(?:\.[0-9]+)?)\s*pts', body)
    score = float(pts.group(1)) if pts else None
    return rows, score


def build_another(page):
    """Start the next run from a clean page load — deterministic, avoids the
    interstitial ads that can follow the in-game 'Build Another' button."""
    enter_game(page)


# ── Main ───────────────────────────────────────────────────────────────────────

def run_automation():
    per_game_stats = []   # one entry per game: list of 5 [PPG, RPG, APG, SPG, BPG]
    final_scores   = []   # one entry per game: the overall points rating

    def save():
        Path(OUTPUT_FILE).write_text(json.dumps(
            {"per_game_stats": per_game_stats, "final_scores": final_scores}, indent=2))

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=HEADLESS, slow_mo=SLOW_MO)
        context = browser.new_context(viewport={"width": 1280, "height": 900})
        page    = context.new_page()

        print("Loading 82-0.com ...")
        enter_game(page)
        print("Game ready.\n")

        for run in range(1, NUM_RUNS + 1):
            try:
                play_one_game(page)
                players, score = parse_result(page)
                per_game_stats.append(players)
                final_scores.append(score)
                save()
                print(f"Run {run:02d} | score {score} | {len(players)} players")
            except Exception as e:
                print(f"Run {run:02d} | skipped: {e}")
            build_another(page)

        browser.close()

    print(f"\nDone. {len(final_scores)}/{NUM_RUNS} games saved to {OUTPUT_FILE}")


if __name__ == "__main__":
    run_automation()
