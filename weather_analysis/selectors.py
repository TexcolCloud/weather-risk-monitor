"""Selection policies for high-priority equipment rooms in the report."""

from collections import defaultdict

from .warning_rules import risk_score


def select_top_rooms(
    rooms_data,
    focus_counties,
    total_limit=10,
    county_limit=6,
):
    focus_names = {county["name"] for county in focus_counties}
    selected = []
    selected_keys = set()
    seen_counties = defaultdict(int)
    sorted_rooms = sorted(rooms_data, key=risk_score, reverse=True)

    for room in sorted_rooms:
        county = room.get("county", "")
        if county not in focus_names or seen_counties[county] >= county_limit:
            continue
        selected.append(room)
        selected_keys.add((county, room.get("name", "")))
        seen_counties[county] += 1
        if len(selected) >= total_limit:
            return selected

    for room in sorted_rooms:
        county = room.get("county", "")
        key = (county, room.get("name", ""))
        if county not in focus_names or key in selected_keys:
            continue
        selected.append(room)
        if len(selected) >= total_limit:
            break
    return selected
