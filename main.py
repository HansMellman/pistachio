# from exporter import export_hitters
from exporter import export_html_pages, export_org_report
from metrics_fielding import calc_fielding_metrics
from metrics_hitting import calc_hitting_metrics, calc_potential_hitting_metrics
from metrics_pitching import calc_pitching_metrics, calc_potential_pitching_metrics
from metrics_war import calc_war
from reader import (
    add_hitting_career_stats,
    add_pitching_career_stats,
    add_scouted_ratings,
    can_field,
    count_pitches,
    is_flagged,
    load_players,
)


def main():
    df = load_players()
    df = add_pitching_career_stats(df)
    df = add_hitting_career_stats(df)
    df = add_scouted_ratings(df)
    df = count_pitches(df)
    df = can_field(df)
    df = is_flagged(df)
    df = calc_pitching_metrics(df)
    df = calc_potential_pitching_metrics(df)
    df = calc_hitting_metrics(df)
    df = calc_potential_hitting_metrics(df)
    df = calc_fielding_metrics(df)
    df = calc_war(df)
    df = df.sort_values(by="best", ascending=False)
    print(df.head(10))  # Preview in terminal
    # export_hitters(df)
    export_html_pages(df)
    export_org_report(df)


if __name__ == "__main__":
    main()
