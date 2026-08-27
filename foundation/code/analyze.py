import pandas as pd

#importing dataframes
events = pd.read_csv("data/raw/events.csv")
frames = pd.read_csv("data/raw/frames.csv")

#printing details for dataframes to find common columns
print(events.shape, events.columns.tolist(), events.head(3))
print(frames.shape, frames.columns.tolist(), frames.head(3))

#verifying if all event ids are covered in frames
print(frames['id'].isin(events['id']).mean())

#checking specific event types in dataframes to decide next steps
covered_ids = frames['id'].unique()
covered_events = events[events['id'].isin(covered_ids)]
print(covered_events["type"].value_counts())