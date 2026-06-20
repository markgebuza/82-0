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


def empty_slots(page):
    """Court slots still showing a position label (PG/SG/…) are unfilled."""
    return page.evaluate(
        """(sel) => [...document.querySelectorAll(sel)]
            .map(b => (b.textContent || '').trim())
            .filter(t => /^(PG|SG|SF|PF|C)$/.test(t))""",
        SLOT_SEL,
    )


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

def best_fit(page, era, team, empties):

    connection = sqlite3.connect("players_scores.db")

    c = connection.cursor()

    c.execute("SELECT player from scores where")

    

def _slot_button(page, slot):
    """Locate the court slot button whose label is exactly `slot` (exact match so
    the single-letter 'C' doesn't substring-match other slots)."""
    return page.locator(SLOT_SEL).filter(has_text=re.compile(rf"^{slot}$")).first


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


def play_one_game(page):
    """Build a full lineup by taking the first player each round. Returns lineup dict."""
    lineup = {}
    while True:
        rnd = round_number(page)
        if rnd is None:
            break
        _spin(page)
        time.sleep(2.3)

        empties = empty_slots(page)
        if not empties:
            return lineup
        picked = first_eligible_card(page, empties)
        if picked is None:
            raise RuntimeError(f"round {rnd}: no player on screen can fill {empties}")
        index, name, team, era, eligible = picked

        # A click occasionally misses, leaving the round unchanged (and no SPIN).
        # Retry across every slot the player is eligible for until one advances
        # the round — a single slot's click can silently miss.
        placed = False
        for slot in eligible:
            for _ in range(3):
                try:
                    player_card(page, index)[0].click()
                    time.sleep(0.6)
                    _slot_button(page, slot).click(timeout=ACTION_TIMEOUT)
                    time.sleep(1.0)
                    if round_number(page) != rnd:   # advanced to next round / result screen
                        lineup[slot] = f"{name} ({team},{era})"
                        placed = True
                        break
                except Exception:
                    time.sleep(1)
            if placed:
                break
        if not placed:
            raise RuntimeError(f"round {rnd}: could not place {name} in {eligible}")
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
