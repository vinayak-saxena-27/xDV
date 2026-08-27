"""Bulk-fetch StatsBomb open data (events + 360 frames) for every match.

Writes one parquet per match under data/raw/{events,frames}/ and tracks progress
in data/raw/_manifest.csv so the run is resumable.

Usage:
    python fetch_matches.py                # resume; build match index if missing
    python fetch_matches.py --refresh      # rebuild the match index first
    python fetch_matches.py --retry-360    # also re-attempt matches whose 360
                                           # frames previously failed ("partial")
"""
import sys
import time
from pathlib import Path
from datetime import datetime, timezone
import pandas as pd
from statsbombpy import sb

RAW = Path(__file__).parent / "data" / "raw"
EVENTS_DIR, FRAMES_DIR = RAW / "events", RAW / "frames"
MANIFEST = RAW / "_manifest.csv"
for d in (EVENTS_DIR, FRAMES_DIR):
    d.mkdir(parents = True, exist_ok = True)

MANIFEST_COLS = ["match_id", "competition_id", "season_id", "has_360",
                 "n_events", "n_frames", "status", "error", "fetched_at"]


#reads the manifest, keeping only the latest row per match_id
def load_manifest() -> pd.DataFrame:
    if not MANIFEST.exists():
        return pd.DataFrame(columns = MANIFEST_COLS)
    df = pd.read_csv(MANIFEST)
    return df.drop_duplicates(subset = "match_id", keep = "last").reset_index(drop = True)


#appends one row; load_manifest()/compact_manifest() collapse older rows per match_id
def append_manifest(row: dict) -> None:
    pd.DataFrame([row], columns = MANIFEST_COLS).to_csv(
        MANIFEST, mode = "a", header = not MANIFEST.exists(), index = False)


#rewrite the manifest with one row per match_id (call once at end of a run)
def compact_manifest() -> None:
    if MANIFEST.exists():
        load_manifest().to_csv(MANIFEST, index = False)


#builds the full list of matches across all comps/seasons
def build_match_index() -> pd.DataFrame:
    comps = sb.competitions()
    comps["season_has_360"] = comps["match_available_360"].notna()
    out = []
    for comp in comps.itertuples():
        try:
            match = sb.matches(competition_id = comp.competition_id, season_id = comp.season_id)
        except Exception as e:
            print(f" matches failed {comp.competition_id}/{comp.season_id}: {e}")
            continue
        match["season_has_360"] = comp.season_has_360
        out.append(match)
    if not out:
        raise SystemExit("no match lists could be fetched - check your connection")
    matches = pd.concat(out, ignore_index = True)
    print(f"match index: {len(matches)} matches from {len(out)}/{len(comps)} comp-seasons")
    # NB: cached even on partial success - use --refresh to rebuild if this run
    # only reached some comp-seasons
    matches.to_parquet(RAW / "matches.parquet", index = False)
    return matches


#fetches events and/or 360 frames for a match as needed and records the outcome
def fetch_match(match_id, competition_id, season_id, season_has_360, prev_status = None) -> None:
    event_path, frame_path = EVENTS_DIR / f"{match_id}.parquet", FRAMES_DIR / f"{match_id}.parquet"
    if event_path.exists() and prev_status == "ok":
        return  # already complete

    if event_path.exists():
        n_events = len(pd.read_parquet(event_path, columns = ["match_id"]))  # backfill count only
    else:
        events = sb.events(match_id = match_id)
        events["match_id"] = match_id
        events.to_parquet(event_path, index = False)
        n_events = len(events)

    has_360, n_frames, err = False, 0, ""
    if frame_path.exists():
        has_360, n_frames = True, len(pd.read_parquet(frame_path, columns = ["match_id"]))
    elif season_has_360:
        try:
            frames = sb.frames(match_id = match_id)
            if frames is not None and not frames.empty:
                frames["match_id"] = match_id
                frames.to_parquet(frame_path, index = False)
                has_360, n_frames = True, len(frames)
        except Exception as e:
            err = f"frames: {e}"

    append_manifest({"match_id": match_id, "competition_id": competition_id, "season_id": season_id,
        "has_360": has_360, "n_events": n_events, "n_frames": n_frames,
        "status": "partial" if err else "ok", "error": err,
        "fetched_at": datetime.now(timezone.utc).isoformat()})


#gets all the matches and loads all with error handling
def main() -> None:
    # reuse the cached match index on resume; pass --refresh to rebuild it
    index_path = RAW / "matches.parquet"
    if index_path.exists() and "--refresh" not in sys.argv:
        matches = pd.read_parquet(index_path)
    else:
        matches = build_match_index()

    status_by_id = load_manifest().set_index("match_id")["status"].to_dict()
    retry_360 = "--retry-360" in sys.argv

    # decide what still needs work from the manifest, not from disk, so a run
    # never re-loops matches that are already fully fetched
    def needs_fetch(mid) -> bool:
        st = status_by_id.get(mid)
        if st == "ok":
            return False
        if st == "partial":  # events done; frames failed last time
            return retry_360 and not (FRAMES_DIR / f"{mid}.parquet").exists()
        return True  # missing, "failed", or unrecognised status

    todo = matches[matches["match_id"].map(needs_fetch)]
    print(f"{len(todo)} to fetch, {len(matches) - len(todo)} already done")
    try:
        for i, row in enumerate(todo.itertuples(), 1):
            try:
                fetch_match(row.match_id, row.competition_id, row.season_id,
                            row.season_has_360, status_by_id.get(row.match_id))
            except Exception as e:
                append_manifest({
                    "match_id": row.match_id, "competition_id": row.competition_id,
                    "season_id": row.season_id, "has_360": False, "n_events": 0, "n_frames": 0,
                    "status": "failed", "error": str(e),
                    "fetched_at": datetime.now(timezone.utc).isoformat(),
                })
                print(f"  match {row.match_id} failed: {e}")
            time.sleep(0.1)  # be polite to the open-data host
            if i % 25 == 0:
                print(f"  {i} / {len(todo)}")
    finally:
        compact_manifest()


if __name__ == "__main__":
    main()
