# Pistachio

**Pistachio** is a projection system for the computer game *Out of the Park Baseball 2026 (OOTP 26)*.

## What It Projects

- **Position players**:  
  - wOBA  
  - WAR (by position)

- **Pitchers**:  
  - "Pitching wOBA"  
  - WAR (for starters and relievers)

## Output

When run successfully, the system generates three HTML pages of projections:

- `pitchers.html`: Pitchers and pitching prospects  
- `hitters.html`: Hitters  
- `hit_prospects.html`: Hitter prospects

## Based on OOTP 26

These projections are built from the ground up for **OOTP 26**.  While not perfect, the testing method is intended to be rigorous.

The underlying testing data and methodology is set out in detail in this Google Sheet:
https://docs.google.com/spreadsheets/d/19f0pZUqyonjDa2AwHckd8Al9H-wmBC6nvM-Y0RzzhSs/edit?gid=202842399#gid=202842399

---

## Configuration Instructions

You need to update `config.py` to match your OOTP save in these areas and then save the file:

- `filepath`: Path to your CSV exports from OOTP  
- `export_filepath`: Folder for saving HTML outputs  
- `pistachio_filepath`: Folder containing `main.py` and other scripts  
- `ID = 3332`: Your scout’s `coach_id` from `coaches.csv`  
- `team_managed = 'CHC'`: Your in-game team abbreviation

⚠️ You **must** update these before running `main.py`, or it won’t work.

### Other optional Config Settings

- `club_lookup`: Maps team numbers to abbreviations (default set to MLB)
- `POSITION_THRESHOLDS`: Minimum fielding ratings by position
- Pitcher thresholds: Defines starter vs reliever status (default setting is that a starter has at least 3 pitches rated 45 or above and stamina at 40 or above; a reliever has at least two pitches rated 45 or above, with no stamina condition)

ℹ️ The code expects the game to output ratings on the **20–80 scale** in increments of **5**. It won't work well on other settings.

---

## Additional Info

- **Player IDs** saved in `flagged.txt` can be found in outputs by:
  - Typing `flag` in the search bar
  - Using the 'Custom Search Builder' in the HTML to search for 'flag equals flag'

This is useful for tracking:
- Draft prospects
- Free agents
- Waiver wire
- Any other custom shortlists created in-game

---

## Extras

- Examples of the html outputs are included in the `outputs` folder  
  (Note: these will be overwritten once you successfully run the code in main.py with your own stuff based on your OOTP save)

- Feedback and pull requests welcome

🧵 [OOTP Forum Post (by "Squirrel")](https://forums.ootpdevelopments.com/showthread.php?t=361580)

## org_report.html (Organisation report)

This project now generates an additional report: `org_report.html`. It is intended as a quick “who should I start?” view for the organisation set in `config.py`:

- `team_managed` (e.g. `"KC"`) determines which org is filtered into the report. :contentReference[oaicite:7]{index=7}

### What’s inside the report
The report contains:

1) **Starting lineup vs RHP** (one player per position)
2) **Batting order vs RHP**
3) **Starting lineup vs LHP**
4) **Batting order vs LHP**
5) **Rotation (Top 5 SP)**
6) **Bullpen (Top 8 RP)**

You’ll also see “summary cards” at the top showing total projected lineup WAR vs RHP/LHP and total WAR for the rotation and bullpen. :contentReference[oaicite:8]{index=8}

### How lineup WAR is calculated
Pistachio already computes positional WAR columns for hitters by combining defense + offense:

- Example: `3B = 3B_def + war_hitting` (and similarly for SS/2B/CF/etc)
- DH is special-cased: `DH = DH_hitting` (no defensive component) :contentReference[oaicite:9]{index=9}

`war_hitting` comes from the player’s projected overall wOBA:
- wOBA is computed from `wOBAR` and `wOBAL` and blended using `HANDEDNESS_WEIGHTS` (default 70% vs RHP, 30% vs LHP). 
- Hitting WAR is then computed from wOBA using a linear conversion to runs/game and then to wins using `RUNS_PER_WIN`. 

### How the org report chooses starters (and why players “move positions”)
The org report selects a single starter at each position under two constraints:
- A player can only be assigned to **one** starting position.
- Premium positions are filled first (e.g. SS/CF/2B), so a versatile player may be “used up” at a premium position even if they also grade well elsewhere.

### Why WAR differs vs RHP vs LHP in the org report
Unlike `hitters.html` (which shows season-average positional WAR columns), `org_report.html` displays matchup-specific results:
- The “vs RHP” view uses the player’s projected `wOBAR` as the offensive input.
- The “vs LHP” view uses the player’s projected `wOBAL` as the offensive input.
This produces different matchup-specific `pos_WAR` values for the same player across the two lineups. :contentReference[oaicite:12]{index=12}

### Pitching staff selection
Pitchers are projected via `pwOBAR`/`pwOBAL` (then blended to `pwOBA`), converted to WAR, and split into:
- `sp_war` for starters
- `rp_war` for relievers (scaled down due to fewer innings) 
Rotation picks the top 5 by `sp_war`; bullpen picks the top 8 by `rp_war`.