"""
org_report.py

Builds an organization-level report (starting lineup + pitching staff + batting orders)
from the master Pistachio dataframe produced in main.py.

Design goals:
- Use the SAME projected offensive outputs already produced by Pistachio (wOBA splits + component rates).
- Build a one-player-per-position lineup with premium-position priority.
- Provide recommended batting orders vs RHP and vs LHP using a "The Book"-style top-heavy approach.
"""

from __future__ import annotations

from typing import Dict, List, Optional, Tuple

import pandas as pd
from config import (
    DH_PENALTY,
    RUNS_PER_GAME_HITTING_COEFF,
    RUNS_PER_GAME_HITTING_CONST,
    RUNS_PER_WIN,
    team_managed,
)

# Premium-position priority (earlier = more important).
DEFAULT_POSITION_PRIORITY: List[str] = [
    "SS",
    "CF",
    "2B",
    "C",
    "3B",
    "RF",
    "LF",
    "1B",
    "DH",
]

# Defensive positions that require explicit eligibility.
# (We treat 1B & DH as "always eligible" to avoid empty lineups.)
ELIGIBILITY_POSITIONS: set[str] = {"C", "SS", "2B", "3B", "LF", "CF", "RF"}


def _field_set(field_val: object) -> set[str]:
    """Parse the repo's 'field' column (e.g. 'SS, 2B, 3B') into a set."""
    if field_val is None or (isinstance(field_val, float) and pd.isna(field_val)):
        return set()
    s = str(field_val).strip()
    if not s:
        return set()
    return {p.strip() for p in s.split(",") if p.strip()}


def _eligible_for_position(row: pd.Series, pos: str) -> bool:
    """Eligibility gate for lineup assignment."""
    if pos in ("DH", "1B"):
        return True
    return pos in _field_set(row.get("field", ""))


def _war_from_woba(woba: pd.Series) -> pd.Series:
    """
    Convert wOBA to hitting WAR using the same linear conversion used in metrics_hitting.py.
    """
    return (
        (woba * RUNS_PER_GAME_HITTING_COEFF) - RUNS_PER_GAME_HITTING_CONST
    ) / RUNS_PER_WIN


def _build_side_columns(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """
    Add side-specific columns needed for lineup selection + batting order.
    side: 'R' (vs RHP) or 'L' (vs LHP)
    """
    if side not in ("R", "L"):
        raise ValueError("side must be 'R' or 'L'")

    woba_col = "wOBAR" if side == "R" else "wOBAL"
    bb_col = "bb_pctR" if side == "R" else "bb_pctL"
    hr_col = "hr_pctR" if side == "R" else "hr_pctL"
    k_col = "k_pctR" if side == "R" else "k_pctL"

    out = df.copy()

    out[f"wOBA_vs_{side}"] = out[woba_col]
    out[f"BBpct_vs_{side}"] = out.get(bb_col)
    out[f"HRpct_vs_{side}"] = out.get(hr_col)
    out[f"Kpct_vs_{side}"] = out.get(k_col)

    out[f"war_hitting_vs_{side}"] = _war_from_woba(out[f"wOBA_vs_{side}"])
    out[f"DH_hitting_vs_{side}"] = _war_from_woba(
        out[f"wOBA_vs_{side}"] * (1 - DH_PENALTY)
    )

    # Position scores for this side.
    for pos in ["C", "SS", "2B", "3B", "LF", "CF", "RF", "1B"]:
        out[f"{pos}_score_vs_{side}"] = (
            out.get(f"{pos}_def", 0) + out[f"war_hitting_vs_{side}"]
        )
    out[f"DH_score_vs_{side}"] = out[f"DH_hitting_vs_{side}"]

    return out


def build_starting_lineup(
    df: pd.DataFrame,
    org_abbr: Optional[str] = None,
    side: str = "R",
    position_priority: Optional[List[str]] = None,
) -> pd.DataFrame:
    """
    Build a one-player-per-position lineup for an org vs RHP or vs LHP.

    Returns a 9-row dataframe with starter at each position.
    """
    org = org_abbr or team_managed
    priority = position_priority or DEFAULT_POSITION_PRIORITY

    # Candidates: org hitters (exclude pitchers by sprp classification).
    pool = df[df["org"] == org].copy()
    if "sprp" in pool.columns:
        pool = pool[~pool["sprp"].isin(["sp", "rp"])].copy()

    pool = _build_side_columns(pool, side=side)

    lineup_rows: List[Dict[str, object]] = []
    used: set[int] = set()

    for pos in priority:
        score_col = f"{pos}_score_vs_{side}" if pos != "DH" else f"DH_score_vs_{side}"

        candidates = pool[~pool["player_id"].isin(used)].copy()
        eligible = candidates[
            candidates.apply(lambda r: _eligible_for_position(r, pos), axis=1)
        ]

        # If there are no eligible candidates for this position, fall back to "best available"
        # (prevents empty lineups if thresholds are strict or the org is thin at a spot).
        candidates = eligible if not eligible.empty else candidates

        # If we still have no candidates, emit blank row.
        if candidates.empty or score_col not in candidates.columns:
            lineup_rows.append(
                {
                    "pos": pos,
                    "name": "",
                    "age": pd.NA,
                    "minor": pd.NA,
                    "pa": pd.NA,
                    "wOBA_vs": pd.NA,
                    "wOBA": pd.NA,
                    "wRC+": pd.NA,
                    "BB%": pd.NA,
                    "HR%": pd.NA,
                    "K%": pd.NA,
                    "pos_WAR": pd.NA,
                    "field": "",
                    "player_id": pd.NA,
                }
            )
            continue

        pick = candidates.sort_values(score_col, ascending=False).iloc[0]
        used.add(int(pick["player_id"]))

        lineup_rows.append(
            {
                "pos": pos,
                "name": pick.get("name", ""),
                "age": pick.get("age", pd.NA),
                "minor": pick.get("minor", pd.NA),
                "pa": pick.get("pa", pd.NA),
                "wOBA_vs": pick.get(f"wOBA_vs_{side}", pd.NA),
                "wOBA": pick.get("wOBA", pd.NA),
                "wRC+": pick.get("wRC+", pd.NA),
                "BB%": pick.get(f"BBpct_vs_{side}", pd.NA),
                "HR%": pick.get(f"HRpct_vs_{side}", pd.NA),
                "K%": pick.get(f"Kpct_vs_{side}", pd.NA),
                "pos_WAR": pick.get(score_col, pd.NA),
                "field": pick.get("field", ""),
                "player_id": pick.get("player_id", pd.NA),
            }
        )

    lineup = pd.DataFrame(lineup_rows)

    # Make numeric columns numeric (for sorting/formatting).
    for c in [
        "age",
        "minor",
        "pa",
        "wOBA_vs",
        "wOBA",
        "wRC+",
        "BB%",
        "HR%",
        "K%",
        "pos_WAR",
    ]:
        if c in lineup.columns:
            lineup[c] = pd.to_numeric(lineup[c], errors="coerce")

    lineup.insert(0, "org", org)
    lineup.insert(1, "vs", f"vs {side}HP")
    return lineup.drop(columns=["player_id"], errors="ignore")


def build_batting_order(lineup: pd.DataFrame, side: str = "R") -> pd.DataFrame:
    """
    Create a recommended 1–9 batting order using a "The Book"-style approach:
      - Best hitter bats 2nd.
      - Best remaining power bat hits 4th.
      - Best remaining OBP/BB% bat hits 1st.
      - Next best hitters fill 3rd and 5th.
      - Remaining bats go 6–9 by descending wOBA.

    Uses the lineup dataframe produced by build_starting_lineup (expects wOBA_vs, BB%, HR% columns).
    """
    hitters = lineup.copy()
    hitters = hitters[hitters["name"].astype(str).str.len() > 0].copy()

    # If lineup isn't full, bail gracefully.
    if hitters.empty:
        return pd.DataFrame(
            columns=["slot", "pos", "name", "wOBA_vs", "wRC+", "BB%", "HR%"]
        )

    hitters["wOBA_vs"] = pd.to_numeric(hitters["wOBA_vs"], errors="coerce")
    hitters["BB%"] = pd.to_numeric(hitters["BB%"], errors="coerce")
    hitters["HR%"] = pd.to_numeric(hitters["HR%"], errors="coerce")
    hitters["wRC+"] = pd.to_numeric(hitters["wRC+"], errors="coerce")

    hitters = hitters.sort_values("wOBA_vs", ascending=False).reset_index(drop=True)

    def take_row(df_: pd.DataFrame, idx: int) -> Tuple[pd.Series, pd.DataFrame]:
        row = df_.iloc[idx]
        rest = df_.drop(df_.index[idx]).reset_index(drop=True)
        return row, rest

    # #2 = best by wOBA
    slot2, remaining = take_row(hitters, 0)

    # #4 = best power among top remaining wOBA hitters (top 2 remaining if possible)
    cand4 = remaining.head(2) if len(remaining) >= 2 else remaining
    if not cand4.empty:
        slot4 = cand4.sort_values(["HR%", "wOBA_vs"], ascending=[False, False]).iloc[0]
        remaining = remaining[remaining["name"] != slot4["name"]].reset_index(drop=True)
    else:
        slot4 = pd.Series(dtype=object)

    # #1 = best BB% among top remaining wOBA hitters (top 2 remaining if possible)
    cand1 = remaining.head(2) if len(remaining) >= 2 else remaining
    if not cand1.empty:
        slot1 = cand1.sort_values(["BB%", "wOBA_vs"], ascending=[False, False]).iloc[0]
        remaining = remaining[remaining["name"] != slot1["name"]].reset_index(drop=True)
    else:
        slot1 = pd.Series(dtype=object)

    # Remaining in wOBA order
    remaining = remaining.sort_values("wOBA_vs", ascending=False).reset_index(drop=True)

    # #3 and #5 are the next best
    slot3, remaining = (
        take_row(remaining, 0)
        if len(remaining) >= 1
        else (pd.Series(dtype=object), remaining)
    )
    slot5, remaining = (
        take_row(remaining, 0)
        if len(remaining) >= 1
        else (pd.Series(dtype=object), remaining)
    )

    order_rows: List[Tuple[int, pd.Series]] = [
        (1, slot1),
        (2, slot2),
        (3, slot3),
        (4, slot4),
        (5, slot5),
    ]

    # slots 6-9 by remaining wOBA
    slot_num = 6
    for _, r in remaining.iterrows():
        if slot_num > 9:
            break
        order_rows.append((slot_num, r))
        slot_num += 1

    # Build dataframe
    out_rows = []
    for slot, r in order_rows:
        out_rows.append(
            {
                "slot": slot,
                "pos": r.get("pos", ""),
                "name": r.get("name", ""),
                "wOBA_vs": r.get("wOBA_vs", pd.NA),
                "wRC+": r.get("wRC+", pd.NA),
                "BB%": r.get("BB%", pd.NA),
                "HR%": r.get("HR%", pd.NA),
            }
        )

    out = pd.DataFrame(out_rows).sort_values("slot")
    out.insert(0, "vs", f"vs {side}HP")
    return out


def build_pitching_staff(
    df: pd.DataFrame,
    org_abbr: Optional[str] = None,
    n_sp: int = 5,
    n_rp: int = 8,
) -> Tuple[pd.DataFrame, pd.DataFrame]:
    """
    Build a rotation (top n_sp SP) and bullpen (top n_rp RP) for the org.
    """
    org = org_abbr or team_managed
    pool = df[df["org"] == org].copy()

    # Rotation: sprp == 'sp'
    rotation = pool[pool.get("sprp", "").isin(["sp"])].copy()
    if not rotation.empty and "sp_war" in rotation.columns:
        rotation = rotation.sort_values("sp_war", ascending=False).head(n_sp)
    else:
        rotation = rotation.head(0)

    # Bullpen: sprp == 'rp'
    bullpen = pool[pool.get("sprp", "").isin(["rp"])].copy()
    if not bullpen.empty and "rp_war" in bullpen.columns:
        bullpen = bullpen.sort_values("rp_war", ascending=False).head(n_rp)
    else:
        bullpen = bullpen.head(0)

    # Columns for display
    rot_cols = ["name", "age", "minor", "ip", "sp_war", "pwOBA", "pwOBAR", "pwOBAL"]
    pen_cols = ["name", "age", "minor", "ip", "rp_war", "pwOBA", "pwOBAR", "pwOBAL"]

    rotation = rotation[[c for c in rot_cols if c in rotation.columns]].copy()
    bullpen = bullpen[[c for c in pen_cols if c in bullpen.columns]].copy()

    rotation.insert(0, "org", org)
    bullpen.insert(0, "org", org)
    return rotation, bullpen
