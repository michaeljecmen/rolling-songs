#!/usr/bin/python3

import json
import sys
import shutil

from helpers.config import read_config, get_absolute_rolling_songs_dir
from helpers.lastfm import get_lastfm_network
from helpers.log import append_to_log

# takes the current tracklist and appends
# the relevant information to the logfile
# also re-parses and pretty prints the logfile, 
# which has probably been pretty ugly up until now
def finalize(outfilename):
    config = read_config()
    lastfm = get_lastfm_network(config).get_authenticated_user()

    trackfilename = config["DATA_DIR"] + config["STORAGE_FILENAME"]
    with open(get_absolute_rolling_songs_dir() + trackfilename, "r") as trackfile:
        tracklist = json.load(trackfile)
    
    for track in tracklist:
        # update playcounts to be as up-to-date as possible
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs) - track["playcount"]
    
    # cheekily rewrite the config so we don't touch the old logfile
    shutil.copy(config["DATA_DIR"] + config["LOG_FILENAME"], config["DATA_DIR"] + outfilename)
    config["LOG_FILENAME"] = outfilename
    append_to_log(config, tracklist, [])

    # write log to new file prettily
    with open(get_absolute_rolling_songs_dir() + config["DATA_DIR"] + outfilename, "r") as outfile:
        unformatted = json.load(outfile)
    
    with open(get_absolute_rolling_songs_dir() + config["DATA_DIR"] + outfilename, "w") as outfile:
        json.dump(unformatted, outfile, indent=4)

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("usage: python3 finalize.py {OUTPUT_FILENAME}")
        print("this will overwrite that file if it does not exist, dumping the json contents of the log into it.")
        print("this file will be stored in the {DATA_DIR} folder.")
        exit(1)
    finalize(sys.argv[1])