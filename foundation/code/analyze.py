import pandas as pd
import ast
from shapely.geometry import Polygon

#importing dataframes
events = pd.read_csv("data/raw/events.csv")
frames = pd.read_csv("data/raw/frames.csv")

#printing details for dataframes to find common columns
print(events.shape, events.columns.tolist(), events.head(3))
print(frames.shape, frames.columns.tolist(), frames.head(3))

#verifying if all event ids are covered in frames
print(frames['id'].isin(events['id']).mean())

#checking specific event types in frames to decide next steps
covered_ids = frames['id'].unique()
covered_events = events[events['id'].isin(covered_ids)]
print(covered_events["type"].value_counts())

#calculate the visible_area column in frames
def parse_visible_area(visible_area_str):
    try:
        flat = ast.literal_eval(visible_area_str)
        return list(zip(flat[0::2], flat[1::2]))
    except:
        return []

def compute_area(raw):
    try:
        coords = parse_visible_area(raw)
        return  Polygon(coords).area
    except:
        return 0
    
frames["visible_area_coords"] = frames["visible_area"].apply(parse_visible_area)
frames["visible_area_size"] = frames["visible_area"].apply(compute_area)
print(frames["visible_area_size"].describe())