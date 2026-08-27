from statsbombpy import sb
import pandas as pd

#loading data
complist = sb.competitions()
print(complist.head())

MATCH_ID = 38
events = sb.events(match_id = MATCH_ID)
frames = sb.frames(match_id = MATCH_ID)

#checking shape and columns in dataframes
print(events.shape, events.columns.tolist())
print(frames.shape, frames.columns.tolist())

#writing to csvs
events.to_csv("events.csv", index = False)
frames.to_csv("frames.csv", index = False)
