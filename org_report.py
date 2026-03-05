"""
org_report.py

Builds an organization-level report (starting lineup + pitching staff + batting orders)
from the master Pistachio dataframe produced in main.py.

Key additions vs the original Pistachio exports:
- Roster-aware platoon construction: we cap the union of players across vs RHP and vs LHP lineups
  to a maximum number of active MLB batters (default: 13).
- We treat the vs RHP lineup as the "core 9" (you face more RHPs) and then choose up to 4
  additional bench bats to improve the vs LHP lineup while still respecting common roster needs:
    * Backup catcher (coverage requirement)
    * Utility infielder
    * Backup outfielder
    * 4th bat = best available (flex)
- Optional "runs per game" estimates for each lineup, based on split wOBA and league constants.
- Batting floor flags (The creator’s infographic concept):
    * DH/1B/LF should generally be stronger bats (higher wRC+ floor)
    * CF/SS/C can be weaker bats if defense is premium (lower wRC+ floor)
  We do NOT use this to override the WAR-based selection; it is a transparency / sanity-check flag.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Dict, List, Optional, Set, Tuple

import pandas as pd

from config import (
    DH_PENALTY,
    LEAGUE_RUNS_PER_PA,
    LEAGUE_WOBA,
    RUNS_PER_GAME_HITTING_COEFF,
    RUNS_PER_GAME_HITTING_CONST,
    RUNS_PER_WIN,
    WOBA_SCALE,
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
ELIGIBILITY_POSITIONS: Set[str] = {"C", "SS", "2B", "3B", "LF", "CF", "RF"}

# Batting floors (wRC+) by position (based on the creator’s infographic tiers).
BAT_FLOOR_WRC_PLUS: Dict[str, int] = {
    # Bat-first tier
    "DH": 115,
    "1B": 115,
    "LF": 115,
    # Mixed tier
    "RF": 105,
    "3B": 105,
    "2B": 105,
    # Premium defense tier
    "CF": 95,
    "SS": 95,
    "C": 95,
}

# Approximate plate appearances per game by lineup slot (1..9).
# These sum to ~39.47 PA/G, which is a reasonable MLB team average.
PA_WEIGHTS_BY_SLOT: Dict[int, float] = {
    1: 4.76,
    2: 4.65,
    3: 4.56,
    4: 4.47,
    5: 4.38,
    6: 4.29,
    7: 4.20,
    8: 4.12,
    9: 4.04,
}

INFIELD_POS: Set[str] = {"SS", "2B", "3B", "1B"}
OF_POS: Set[str] = {"LF", "CF", "RF"}

# Catcher-capable detection (coverage requirement)
CATCH_RATING_COLS: Tuple[str, str, str] = ("Cfram", "Cabil", "Carm")
MIN_CATCH_RATING_FLOOR: float = (
    30.0  # low floor: "emergency/backup catcher" eligibility
)


def _field_set(field_val: object) -> Set[str]:
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


def _filter_org_hitters(df: pd.DataFrame, org: str) -> pd.DataFrame:
    """Org-only, hitters-only view of the master dataframe."""
    pool = df[df["org"] == org].copy()
    if "sprp" in pool.columns:
        pool = pool[~pool["sprp"].isin(["sp", "rp"])].copy()
    if "player_id" in pool.columns:
        pool["player_id"] = pd.to_numeric(pool["player_id"], errors="coerce")
    return pool


def _war_from_woba(woba: pd.Series) -> pd.Series:
    """Convert wOBA to hitting WAR using the same linear conversion used in metrics_hitting.py."""
    return (
        (woba * RUNS_PER_GAME_HITTING_COEFF) - RUNS_PER_GAME_HITTING_CONST
    ) / RUNS_PER_WIN


def _wrc_plus_from_woba(woba: object) -> object:
    """
    Compute a wRC+-style value from wOBA using the project’s league constants.
    This is an approximation for splits (since we only have overall league constants).
    """
    try:
        if woba is None or (isinstance(woba, float) and pd.isna(woba)):
            return pd.NA
        woba_f = float(woba)
        r_per_pa = ((woba_f - LEAGUE_WOBA) / WOBA_SCALE) + LEAGUE_RUNS_PER_PA
        if LEAGUE_RUNS_PER_PA == 0:
            return pd.NA
        return round((r_per_pa / LEAGUE_RUNS_PER_PA) * 100, 0)
    except Exception:
        return pd.NA


def _bat_floor_note(pos: str, wrc_vs: object) -> str:
    floor = BAT_FLOOR_WRC_PLUS.get(pos)
    if floor is None:
        return ""
    try:
        if wrc_vs is None or (isinstance(wrc_vs, float) and pd.isna(wrc_vs)):
            return ""
        wrc_val = float(wrc_vs)
        return "OK" if wrc_val >= float(floor) else f"Below floor (needs {floor})"
    except Exception:
        return ""


def _build_side_columns(df: pd.DataFrame, side: str) -> pd.DataFrame:
    """Add side-specific columns needed for lineup selection + batting order."""
    if side not in ("R", "L"):
        raise ValueError("side must be 'R' or 'L'")

    woba_col = "wOBAR" if side == "R" else "wOBAL"
    bb_col = "bb_pctR" if side == "R" else "bb_pctL"
    hr_col = "hr_pctR" if side == "R" else "hr_pctL"
    k_col = "k_pctR" if side == "R" else "k_pctL"

    out = df.copy()
    out[f"wOBA_vs_{side}"] = out.get(woba_col)
    out[f"BBpct_vs_{side}"] = out.get(bb_col)
    out[f"HRpct_vs_{side}"] = out.get(hr_col)
    out[f"Kpct_vs_{side}"] = out.get(k_col)

    out[f"war_hitting_vs_{side}"] = _war_from_woba(out[f"wOBA_vs_{side}"])
    out[f"DH_hitting_vs_{side}"] = _war_from_woba(
        out[f"wOBA_vs_{side}"] * (1 - DH_PENALTY)
    )

    for pos in ["C", "SS", "2B", "3B", "LF", "CF", "RF", "1B"]:
        out[f"{pos}_score_vs_{side}"] = (
            out.get(f"{pos}_def", 0) + out[f"war_hitting_vs_{side}"]
        )
    out[f"DH_score_vs_{side}"] = out[f"DH_hitting_vs_{side}"]

    score_cols = [
        f"{p}_score_vs_{side}" for p in ["C", "SS", "2B", "3B", "LF", "CF", "RF", "1B"]
    ] + [f"DH_score_vs_{side}"]
    existing = [c for c in score_cols if c in out.columns]
    out[f"best_score_vs_{side}"] = out[existing].max(axis=1) if existing else pd.NA

    return out


def build_starting_lineup(
    df: pd.DataFrame,
    org_abbr: Optional[str] = None,
    side: str = "R",
    position_priority: Optional[List[str]] = None,
    restrict_ids: Optional[Set[int]] = None,
    drop_player_id: bool = True,
) -> pd.DataFrame:
    """
    Build a one-player-per-position lineup for an org vs RHP or vs LHP.

    If restrict_ids is provided, only those player_ids are eligible to be selected.
    """
    org = org_abbr or team_managed
    priority = position_priority or DEFAULT_POSITION_PRIORITY

    pool = _filter_org_hitters(df, org)
    if restrict_ids is not None and "player_id" in pool.columns:
        restrict_ids_int = {int(x) for x in restrict_ids if pd.notna(x)}
        pool = pool[pool["player_id"].isin(restrict_ids_int)].copy()

    pool = _build_side_columns(pool, side=side)

    lineup_rows: List[Dict[str, object]] = []
    used: Set[int] = set()

    for pos in priority:
        score_col = f"{pos}_score_vs_{side}" if pos != "DH" else f"DH_score_vs_{side}"

        candidates = pool[~pool["player_id"].isin(used)].copy()
        eligible = candidates[
            candidates.apply(lambda r: _eligible_for_position(r, pos), axis=1)
        ]

        forced = bool(
            pos in ELIGIBILITY_POSITIONS and eligible.empty and not candidates.empty
        )
        forced_note = f"FORCED (no qualified {pos})" if forced else ""

        candidates2 = eligible if not eligible.empty else candidates

        if candidates2.empty or score_col not in candidates2.columns:
            lineup_rows.append(
                {
                    "pos": pos,
                    "note": "",
                    "bat_note": "",
                    "name": "",
                    "age": pd.NA,
                    "minor": pd.NA,
                    "pa": pd.NA,
                    "wOBA_vs": pd.NA,
                    "wRC+_vs": pd.NA,
                    "wOBA": pd.NA,
                    "wRC+": pd.NA,
                    "pos_WAR": pd.NA,
                    "field": "",
                    "player_id": pd.NA,
                }
            )
            continue

        pick = candidates2.sort_values(score_col, ascending=False).iloc[0]
        if pd.notna(pick.get("player_id")):
            used.add(int(pick["player_id"]))

        woba_vs = pick.get(f"wOBA_vs_{side}", pd.NA)
        wrc_vs = _wrc_plus_from_woba(woba_vs)
        bat_note = _bat_floor_note(pos, wrc_vs)

        lineup_rows.append(
            {
                "pos": pos,
                "note": forced_note,
                "bat_note": bat_note,
                "name": pick.get("name", ""),
                "age": pick.get("age", pd.NA),
                "minor": pick.get("minor", pd.NA),
                "pa": pick.get("pa", pd.NA),
                "wOBA_vs": woba_vs,
                "wRC+_vs": wrc_vs,
                "wOBA": pick.get("wOBA", pd.NA),
                "wRC+": pick.get("wRC+", pd.NA),
                "pos_WAR": pick.get(score_col, pd.NA),
                "field": pick.get("field", ""),
                "player_id": pick.get("player_id", pd.NA),
            }
        )

    lineup = pd.DataFrame(lineup_rows)

    for c in ["age", "minor", "pa", "wOBA_vs", "wOBA", "wRC+", "wRC+_vs", "pos_WAR"]:
        if c in lineup.columns:
            lineup[c] = pd.to_numeric(lineup[c], errors="coerce")

    lineup.insert(0, "org", org)
    lineup.insert(1, "vs", f"vs {side}HP")

    if drop_player_id:
        return lineup.drop(columns=["player_id"], errors="ignore")
    return lineup


def build_batting_order(lineup: pd.DataFrame, side: str = "R") -> pd.DataFrame:
    """
    Recommended 1–9 batting order using a "The Book"-style approach:
      - Best hitter bats 2nd.
      - Best remaining power bat hits 4th.
      - Best remaining OBP/BB% bat hits 1st.
      - Next best hitters fill 3rd and 5th.
      - Remaining bats go 6–9 by descending wOBA.
    """
    hitters = lineup.copy()
    hitters = hitters[hitters["name"].astype(str).str.len() > 0].copy()

    if hitters.empty:
        return pd.DataFrame(columns=["slot", "pos", "name", "wOBA_vs", "wRC+_vs"])

    hitters["wOBA_vs"] = pd.to_numeric(hitters["wOBA_vs"], errors="coerce")
    hitters["BB%"] = pd.to_numeric(
        hitters.get("BB%", pd.Series([pd.NA] * len(hitters))), errors="coerce"
    )
    hitters["HR%"] = pd.to_numeric(
        hitters.get("HR%", pd.Series([pd.NA] * len(hitters))), errors="coerce"
    )

    hitters = hitters.sort_values("wOBA_vs", ascending=False).reset_index(drop=True)

    def take_row(df_: pd.DataFrame, idx: int) -> Tuple[pd.Series, pd.DataFrame]:
        row = df_.iloc[idx]
        rest = df_.drop(df_.index[idx]).reset_index(drop=True)
        return row, rest

    slot2, remaining = take_row(hitters, 0)

    cand4 = remaining.head(2) if len(remaining) >= 2 else remaining
    if not cand4.empty:
        slot4 = cand4.sort_values(["HR%", "wOBA_vs"], ascending=[False, False]).iloc[0]
        remaining = remaining[remaining["name"] != slot4["name"]].reset_index(drop=True)
    else:
        slot4 = pd.Series(dtype=object)

    cand1 = remaining.head(2) if len(remaining) >= 2 else remaining
    if not cand1.empty:
        slot1 = cand1.sort_values(["BB%", "wOBA_vs"], ascending=[False, False]).iloc[0]
        remaining = remaining[remaining["name"] != slot1["name"]].reset_index(drop=True)
    else:
        slot1 = pd.Series(dtype=object)

    remaining = remaining.sort_values("wOBA_vs", ascending=False).reset_index(drop=True)
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
    slot_num = 6
    for _, r in remaining.iterrows():
        if slot_num > 9:
            break
        order_rows.append((slot_num, r))
        slot_num += 1

    out_rows = []
    for slot, r in order_rows:
        woba_vs = r.get("wOBA_vs", pd.NA)
        out_rows.append(
            {
                "slot": slot,
                "pos": r.get("pos", ""),
                "name": r.get("name", ""),
                "wOBA_vs": woba_vs,
                "wRC+_vs": _wrc_plus_from_woba(woba_vs),
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
    """Build a rotation (top n_sp SP) and bullpen (top n_rp RP) for the org."""
    org = org_abbr or team_managed
    pool = df[df["org"] == org].copy()

    rotation = pool[pool.get("sprp", "").isin(["sp"])].copy()
    rotation = (
        rotation.sort_values("sp_war", ascending=False).head(n_sp)
        if "sp_war" in rotation.columns
        else rotation.head(0)
    )

    bullpen = pool[pool.get("sprp", "").isin(["rp"])].copy()
    bullpen = (
        bullpen.sort_values("rp_war", ascending=False).head(n_rp)
        if "rp_war" in bullpen.columns
        else bullpen.head(0)
    )

    rot_cols = ["name", "age", "minor", "ip", "sp_war", "pwOBA", "pwOBAR", "pwOBAL"]
    pen_cols = ["name", "age", "minor", "ip", "rp_war", "pwOBA", "pwOBAR", "pwOBAL"]

    rotation = rotation[[c for c in rot_cols if c in rotation.columns]].copy()
    bullpen = bullpen[[c for c in pen_cols if c in bullpen.columns]].copy()

    rotation.insert(0, "org", org)
    bullpen.insert(0, "org", org)
    return rotation, bullpen


def estimate_runs_per_game(order: pd.DataFrame) -> float:
    """
    Estimate lineup runs per game from a batting order table.

    R/PA = ((wOBA - lg_wOBA) / wOBA_scale) + lg_R/PA
    Then weight by approximate PA/G by lineup slot and sum.
    """
    if order is None or order.empty:
        return float("nan")

    tmp = order[["slot", "wOBA_vs"]].copy()
    tmp["slot"] = pd.to_numeric(tmp["slot"], errors="coerce")
    tmp["wOBA_vs"] = pd.to_numeric(tmp["wOBA_vs"], errors="coerce")

    tmp["pa_w"] = tmp["slot"].map(PA_WEIGHTS_BY_SLOT).fillna(PA_WEIGHTS_BY_SLOT[9])
    tmp["r_per_pa"] = ((tmp["wOBA_vs"] - LEAGUE_WOBA) / WOBA_SCALE) + LEAGUE_RUNS_PER_PA
    tmp["r_per_pa"] = tmp["r_per_pa"].fillna(LEAGUE_RUNS_PER_PA)

    return float((tmp["r_per_pa"] * tmp["pa_w"]).sum())


def _lineup_total_war(lineup: pd.DataFrame) -> float:
    if lineup is None or lineup.empty or "pos_WAR" not in lineup.columns:
        return 0.0
    return float(pd.to_numeric(lineup["pos_WAR"], errors="coerce").fillna(0).sum())


def _is_catcher_capable(row: pd.Series) -> bool:
    """Loose catcher coverage check (different from 'field' quality thresholds)."""
    if "C" in _field_set(row.get("field", "")):
        return True
    for c in CATCH_RATING_COLS:
        v = row.get(c)
        if v is not None and pd.notna(v):
            try:
                if float(v) >= MIN_CATCH_RATING_FLOOR:
                    return True
            except Exception:
                continue
    return False


def _is_backup_c(row: pd.Series) -> bool:
    return _is_catcher_capable(row)


def _is_utility_inf(row: pd.Series) -> bool:
    fs = _field_set(row.get("field", ""))
    return len(fs.intersection(INFIELD_POS)) > 0


def _is_backup_of(row: pd.Series) -> bool:
    fs = _field_set(row.get("field", ""))
    return len(fs.intersection(OF_POS)) > 0


def _versatility_score(row: pd.Series) -> int:
    fs = _field_set(row.get("field", ""))
    return len(fs.intersection(INFIELD_POS.union(OF_POS).union({"C"})))


@dataclass
class OrgReportPlan:
    org: str
    max_batters: int
    roster: pd.DataFrame
    lineup_r: pd.DataFrame
    lineup_l: pd.DataFrame
    order_r: pd.DataFrame
    order_l: pd.DataFrame
    lineup_war_r: float
    lineup_war_l: float
    runs_pg_r: float
    runs_pg_l: float


def build_roster_constrained_plan(
    df: pd.DataFrame,
    org_abbr: Optional[str] = None,
    max_batters: int = 13,
    position_priority: Optional[List[str]] = None,
    bench_profile: str = "standard",
    candidate_eval_cap: int = 60,
) -> OrgReportPlan:
    """
    Build:
      - Core lineup vs RHP (9 starters)
      - A 13-batter roster (core 9 + up to 4 bench bats)
      - Best lineup vs LHP restricted to that 13-batter roster
      - Batting orders vs both sides
      - Runs/game estimates vs both sides
    """
    org = org_abbr or team_managed
    priority = position_priority or DEFAULT_POSITION_PRIORITY

    pool = _filter_org_hitters(df, org)
    if pool.empty:
        empty = pd.DataFrame()
        return OrgReportPlan(
            org,
            max_batters,
            empty,
            empty,
            empty,
            empty,
            empty,
            0.0,
            0.0,
            float("nan"),
            float("nan"),
        )

    lineup_r = build_starting_lineup(
        df,
        org_abbr=org,
        side="R",
        position_priority=priority,
        restrict_ids=None,
        drop_player_id=False,
    )
    core_ids = set(
        pd.to_numeric(lineup_r["player_id"], errors="coerce")
        .dropna()
        .astype(int)
        .tolist()
    )

    roster_ids: Set[int] = set(core_ids)
    role_map: Dict[int, str] = {pid: "Core (vs RHP)" for pid in core_ids}

    lineup_l_base = build_starting_lineup(
        df,
        org_abbr=org,
        side="L",
        position_priority=priority,
        restrict_ids=roster_ids,
        drop_player_id=False,
    )
    best_total = _lineup_total_war(lineup_l_base)

    pool_by_id = pool.dropna(subset=["player_id"]).copy()
    pool_by_id["player_id"] = pd.to_numeric(pool_by_id["player_id"], errors="coerce")
    pool_by_id = pool_by_id.dropna(subset=["player_id"]).copy()
    pool_by_id["player_id"] = pool_by_id["player_id"].astype(int)
    pool_by_id = pool_by_id.set_index("player_id", drop=False)

    def catcher_capable_pid(pid: int) -> bool:
        if pid not in pool_by_id.index:
            return False
        row = pool_by_id.loc[pid]
        if isinstance(row, pd.DataFrame):
            row = row.iloc[0]
        return _is_catcher_capable(row)

    def catcher_capable_count(ids: Set[int]) -> int:
        return sum(1 for pid in ids if catcher_capable_pid(pid))

    need_backup_c_pick = catcher_capable_count(roster_ids) < 2

    bench_slots: List[Tuple[str, Optional[callable]]]
    if bench_profile == "standard":
        if need_backup_c_pick:
            bench_slots = [
                ("Bench: Backup C", _is_backup_c),
                ("Bench: Utility IF", _is_utility_inf),
                ("Bench: Backup OF", _is_backup_of),
                ("Bench: Flex", None),
            ]
        else:
            bench_slots = [
                ("Bench: Utility IF", _is_utility_inf),
                ("Bench: Backup OF", _is_backup_of),
                ("Bench: Flex", None),
                ("Bench: Flex", None),
            ]
    else:
        bench_slots = [("Bench: Flex", None)] * max(0, max_batters - len(roster_ids))

    pool_l = _build_side_columns(pool, side="L")
    if "best_score_vs_L" not in pool_l.columns:
        pool_l["best_score_vs_L"] = pd.NA

    def choose_bench_candidate(slot_label: str, predicate) -> Tuple[Optional[int], str]:
        nonlocal best_total, roster_ids

        remaining = pool_l[~pool_l["player_id"].isin(roster_ids)].copy()
        note = ""

        if predicate is not None:
            candidates = remaining[remaining.apply(predicate, axis=1)].copy()
            if candidates.empty:
                candidates = remaining.copy()
                note = " (no eligible found; best available)"
        else:
            candidates = remaining.copy()

        if candidates.empty:
            return None, note

        candidates["vers"] = candidates.apply(_versatility_score, axis=1)
        candidates = candidates.sort_values(
            ["best_score_vs_L", "vers"], ascending=[False, False]
        ).head(candidate_eval_cap)

        best_pid: Optional[int] = None
        best_impr = -1e9
        best_cand_score = -1e9
        best_vers = -1

        for _, cand in candidates.iterrows():
            pid = int(cand["player_id"])
            test_ids = set(roster_ids)
            test_ids.add(pid)

            test_lineup_l = build_starting_lineup(
                df,
                org_abbr=org,
                side="L",
                position_priority=priority,
                restrict_ids=test_ids,
                drop_player_id=False,
            )
            total = _lineup_total_war(test_lineup_l)
            impr = total - best_total

            cand_score = float(
                pd.to_numeric(cand.get("best_score_vs_L"), errors="coerce") or 0.0
            )
            vers = int(cand.get("vers") or 0)

            if (impr > best_impr) or (
                impr == best_impr and (cand_score, vers) > (best_cand_score, best_vers)
            ):
                best_pid = pid
                best_impr = impr
                best_cand_score = cand_score
                best_vers = vers

        if best_pid is None:
            return None, note

        roster_ids.add(best_pid)
        best_total = _lineup_total_war(
            build_starting_lineup(
                df,
                org_abbr=org,
                side="L",
                position_priority=priority,
                restrict_ids=roster_ids,
                drop_player_id=False,
            )
        )
        return best_pid, note

    for label, pred in bench_slots:
        if len(roster_ids) >= max_batters:
            break
        pid, note = choose_bench_candidate(label, pred)
        if pid is None:
            continue
        role_map[pid] = label + note

    while len(roster_ids) < max_batters:
        remaining = pool_l[~pool_l["player_id"].isin(roster_ids)].copy()
        if remaining.empty:
            break
        remaining["vers"] = remaining.apply(_versatility_score, axis=1)
        pick = remaining.sort_values(
            ["best_score_vs_L", "vers"], ascending=[False, False]
        ).iloc[0]
        pid = int(pick["player_id"])
        roster_ids.add(pid)
        role_map[pid] = "Bench: Flex"

    lineup_l = build_starting_lineup(
        df,
        org_abbr=org,
        side="L",
        position_priority=priority,
        restrict_ids=roster_ids,
        drop_player_id=False,
    )

    order_r = build_batting_order(lineup_r, side="R")
    order_l = build_batting_order(lineup_l, side="L")

    runs_pg_r = estimate_runs_per_game(order_r)
    runs_pg_l = estimate_runs_per_game(order_l)

    lineup_war_r = _lineup_total_war(lineup_r)
    lineup_war_l = _lineup_total_war(lineup_l)

    if not need_backup_c_pick:
        catcher_pids = [pid for pid in roster_ids if catcher_capable_pid(pid)]
        starter_c_pid: Optional[int] = None
        for pid_val, pos in zip(
            pd.to_numeric(lineup_r["player_id"], errors="coerce")
            .dropna()
            .astype(int)
            .tolist(),
            lineup_r["pos"].tolist(),
        ):
            if pos == "C" and catcher_capable_pid(pid_val):
                starter_c_pid = pid_val
                break

        backup_candidates = [pid for pid in catcher_pids if pid != starter_c_pid]
        if backup_candidates:
            backup_pid = backup_candidates[0]
            cur_role = role_map.get(backup_pid, "Bench")
            if "Backup C" not in cur_role:
                role_map[backup_pid] = f"{cur_role} + Backup C coverage"

    # Aggregate forced-notes by player_id from both lineups
    forced_notes: Dict[int, List[str]] = {}

    def _ingest_forced(lineup_df: pd.DataFrame, side_label: str) -> None:
        if lineup_df is None or lineup_df.empty:
            return
        for _, r in lineup_df.iterrows():
            note_val = str(r.get("note") or "").strip()
            pid_val = r.get("player_id")
            if not note_val or pd.isna(pid_val):
                continue
            forced_notes.setdefault(int(pid_val), []).append(
                f"{note_val} (vs {side_label})"
            )

    _ingest_forced(lineup_r, "RHP")
    _ingest_forced(lineup_l, "LHP")

    roster = pool[pool["player_id"].isin(roster_ids)].copy()
    roster["role"] = roster["player_id"].apply(
        lambda x: role_map.get(int(x), "Bench") if pd.notna(x) else "Bench"
    )
    roster["note"] = roster["player_id"].apply(
        lambda x: "; ".join(forced_notes.get(int(x), [])) if pd.notna(x) else ""
    )

    start_r = {
        int(pid): pos
        for pid, pos in zip(
            pd.to_numeric(lineup_r["player_id"], errors="coerce")
            .dropna()
            .astype(int)
            .tolist(),
            lineup_r["pos"].tolist(),
        )
    }
    start_l = {
        int(pid): pos
        for pid, pos in zip(
            pd.to_numeric(lineup_l["player_id"], errors="coerce")
            .dropna()
            .astype(int)
            .tolist(),
            lineup_l["pos"].tolist(),
        )
    }

    roster["starts_vs_R"] = roster["player_id"].apply(
        lambda x: "Yes" if int(x) in start_r else ""
    )
    roster["starts_vs_L"] = roster["player_id"].apply(
        lambda x: "Yes" if int(x) in start_l else ""
    )
    roster["pos_vs_R"] = roster["player_id"].apply(lambda x: start_r.get(int(x), ""))
    roster["pos_vs_L"] = roster["player_id"].apply(lambda x: start_l.get(int(x), ""))

    roster_cols = [
        "role",
        "note",
        "name",
        "age",
        "pa",
        "wOBAR",
        "wOBAL",
        "wOBA",
        "wRC+",
        "starts_vs_R",
        "pos_vs_R",
        "starts_vs_L",
        "pos_vs_L",
        "field",
    ]
    roster = roster[[c for c in roster_cols if c in roster.columns]].copy()

    def _role_rank(r: str) -> int:
        if r.startswith("Core"):
            return 0
        if "Backup C" in r:
            return 1
        if "Utility IF" in r:
            return 2
        if "Backup OF" in r:
            return 3
        return 4

    roster["_rank"] = roster["role"].astype(str).apply(_role_rank)
    roster = roster.sort_values(["_rank", "name"]).drop(columns=["_rank"])

    return OrgReportPlan(
        org=org,
        max_batters=max_batters,
        roster=roster,
        lineup_r=lineup_r,
        lineup_l=lineup_l,
        order_r=order_r,
        order_l=order_l,
        lineup_war_r=lineup_war_r,
        lineup_war_l=lineup_war_l,
        runs_pg_r=runs_pg_r,
        runs_pg_l=runs_pg_l,
    )
