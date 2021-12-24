#!/usr/bin/python3

import sys
import os
import spotipy
import pylast
import json
import datetime
from pathlib import Path

from gmail import send_gmail

# debug flag
debug = False

# constants
DATE_FORMAT = "%Y-%m-%d"

def debug_print(*args, **kwargs):
    if debug:
        print(*args, **kwargs)

def get_config(): # TODO add functionality for leaving things blank
    # IMPORTANT: config.json is the only thing that's .gitignore'd
    # don't put your details in example.json, or a file with any other name
    with open("config.json", "r") as cfile:
        config = json.load(cfile)

    # get required fields from the example file
    with open("example.json", "r") as example_conf:
        required_fields = json.load(example_conf).keys()

    error = False
    error_msg = ''
    for field in required_fields:
        if field not in config.keys():
            error = True
            error_msg += f'\"{field}\", '
    
    if error:
        print('ERROR: your config.json is missing the following required fields:')
        print('\t[ ', end='')
        error_msg = error_msg[:-2] # pop trailing comma and space
        print(error_msg, end='')
        print(' ]')
        exit(1)

    return config

def authenticate_services(config):
    # will require you to sign in via a browser the first time you launch this
    token = spotipy.util.prompt_for_user_token(
        config["SPOTIFY_USERNAME"],
        "user-library-read",
        config["SPOTIFY_CLIENT_ID"],
        config["SPOTIFY_CLIENT_SECRET"],
        config["SPOTIFY_REDIRECT_URI"]
    )
    spotify = spotipy.Spotify(auth=token)

    network = pylast.LastFMNetwork(
        api_key=config["LASTFM_API_KEY"],
        api_secret=config["LASTFM_SECRET"],
        username=config["LASTFM_USERNAME"],
        password_hash=pylast.md5(config["LASTFM_PASSWORD"])
    )
    
    return spotify, network.get_authenticated_user()

# returns list of { "name": trackname, "artists": [artists], "album": album }
# containing each song in the spotify playlist provided
def get_rolling_tracklist(config, spotify):
    spotify_username = config["SPOTIFY_USERNAME"]
    playlists = spotify.user_playlists(spotify_username)
    tracklist = []
    for playlist in playlists['items']:

        if playlist['owner']['id'] != spotify_username:
            continue

        if playlist['name'] != config["SPOTIFY_PLAYLIST"]:
            continue
        
        # found the rolling playlist
        results = spotify.playlist(playlist['id'], fields="tracks,next")
        spotify_tracks = results['tracks']
        while spotify_tracks:
            # not quite sure why the for loop is needed here
            for item in spotify_tracks['items']:
                spotify_track = item['track']
                track = {
                    "name": spotify_track['name'],
                    "artists": [ artist['name'] for artist in spotify_track['artists'] ],
                    "album": spotify_track['album']['name']
                }
                tracklist.append(track)
                
            spotify_tracks = spotify.next(spotify_tracks)
        
        # can only be one rolling playlist
        break

    return tracklist

def file_exists(filename):
    return Path(filename).exists()

# load previous tracklist from json file in config
def load_previous_tracklist(config):
    if not file_exists(config["STORAGE_FILENAME"]):
        debug_print("first time running this program, previous tracklist not stored yet")
        return {}

    with open(config["STORAGE_FILENAME"], "r") as trackfile:
        return json.load(trackfile)

def are_tracks_same(new, old):
    # new have "name", "artists", and "album" fields
    # old have "name", "artists", "album", and "playcount" fields
    if new["name"] != old["name"]:
        return False
    if new["artists"] != old["artists"]:
        return False
    if new["album"] != old["album"]:
        return False

    return True

# linear, who cares. returns track or None if not found
def get_corresponding_track(tracklist, track):
    for corresponding_track in tracklist:
        if are_tracks_same(corresponding_track, track):
            return corresponding_track
    return None

# for each new track, get number of plays at present and store.
# for each track which was removed from tracklist, get number of plays
# at present and deduct plays when added to get plays since added.
# returns updated tracklist, removed tracks as a pair
def update_tracklist(new_tracklist, tracklist, lastfm):
    # separate new tracks and kept tracks
    news = []
    kept = []
    for new_track in new_tracklist:
        existing_track = get_corresponding_track(tracklist, new_track)
        if existing_track is None:
            news.append(new_track)
        else:
            kept.append(existing_track)

    # now repeat in reverse to find removed tracks
    removed = []
    for existing_track in tracklist:
        if get_corresponding_track(new_tracklist, existing_track) is None:
            # this track must have been removed since we last checked
            removed.append(existing_track)

    # prepare simple log message to email user
    message = ""

    # go through olds, update playcounts and timestamp out
    for track in removed:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs) - track["playcount"]
        message += "[-] " + track["name"] + " by " + str(track["artists"]) + ", " + track["playcount"] + " plays since added\n"
      
    # go through news, set playcounts and timestamp in, and append to kept
    for track in news:
        scrobs = lastfm.get_track_scrobbles(track["artists"][0], track["name"])
        track["playcount"] = len(scrobs)
        kept.append(track)
        message += "[+] " + track["name"] + " by " + str(track["artists"]) + '\n'

    # kept is now the updated current tracklist
    return kept, removed, news, message

def truncate_utf8_chars(filename, count, ignore_newlines=True):
    """
    Yoinked from Stack Overflow. - MJ

    Truncates last `count` characters of a text file encoded in UTF-8.
    :param filename: The path to the text file to read
    :param count: Number of UTF-8 characters to remove from the end of the file
    :param ignore_newlines: Set to true, if the newline character at the end of the file should be ignored
    """
    with open(filename, 'rb+') as f:
        size = os.fstat(f.fileno()).st_size

        offset = 1
        chars = 0
        while offset <= size:
            f.seek(-offset, os.SEEK_END)
            b = ord(f.read(1))

            if ignore_newlines:
                if b == 0x0D or b == 0x0A:
                    offset += 1
                    continue

            if b & 0b10000000 == 0 or b & 0b11000000 == 0b11000000:
                # This is the first byte of a UTF8 character
                chars += 1
                if chars == count:
                    # When `count` number of characters have been found, move current position back
                    # with one byte (to include the byte just checked) and truncate the file
                    f.seek(-1, os.SEEK_CUR)
                    f.truncate()
                    return
            offset += 1

# if it does not already exist, create logfile
def create_logfile(config, tracklist, date):
    if file_exists(config["LOG_FILENAME"]):
        return

    # create logfile and store current 25 tracks in it
    with open(config["LOG_FILENAME"], "w") as logfile:
        # playcount is redundant in logfile
        for track in tracklist:
            track.pop("playcount")

        # init must be a list so changelog can be appended to it later
        init = [{
            "date": date,
            "starting_tracks": tracklist
        }]
        
        logfile.write(json.dumps(init, indent=4))

def append_to_log(config, removed, added, date):
    # no appending needed if no tracks were removed
    # also, skip the day altogether if there wasn't an equal exchange
    if len(removed) == 0 or len(removed) != len(added):
        return False

    # add diff to logfile
    with open(config["LOG_FILENAME"], "a") as logfile:
        # remove the trailing ] character first
        truncate_utf8_chars(config["LOG_FILENAME"], 1)

        changelog = {
            "date": date,
            "in": [],
            "out": []
        }
        for rtrack in removed:
            changelog["out"].append(rtrack)
        for atrack in added:
            # playcounts are not necessary for new tracks in log
            # this is what the updated data store is for
            atrack.pop("playcount")
            changelog["in"].append(atrack)
        logfile.write(',\n' + json.dumps(changelog, indent=4))

        # aaaaand now re-add the trailing ] to ensure valid json list
        logfile.write('\n]')

    return True

def write_tracklist_file(config, tracklist):
    with open(config["STORAGE_FILENAME"], "w") as tfile:
        json.dump(tracklist, tfile, indent=4)
    
def debug_print_and_email_message(config, subject, content):
    if content != "":
        send_gmail(config["SENDER_EMAIL"], config["SENDER_PASSWORD"], config["RECEIVER_EMAIL"], subject, content)
        debug_print(content)

def main():
    config = get_config()
    spotify, lastfm = authenticate_services(config)

    # get current tracks and compare to previously stored tracks
    tracklist = get_rolling_tracklist(config, spotify)

    # read previous tracklist from storage file
    previous_tracklist = load_previous_tracklist(config)

    # get diff and update playcounts for new and removed songs
    date = datetime.datetime.today().strftime(DATE_FORMAT)
    tracklist, removed, added, message = update_tracklist(tracklist, previous_tracklist, lastfm)

    # write the tracklist file to be checked next time
    write_tracklist_file(config, tracklist)

    # ...and update logfile, creating it if dne
    create_logfile(config, tracklist, date)
    append_to_log(config, removed, added, date)

    # finally, log the message and email it to the user
    debug_print_and_email_message(config, "your rolling playlist was updated!", message)
    
if __name__ == '__main__':
    # debug printing on for any invocation with more than the required args
    if len(sys.argv) > 1:
        debug = True
    main()