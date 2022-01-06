import json
from os.path import dirname, abspath

def get_absolute_rolling_songs_dir():
    return dirname(dirname(abspath(__file__))) + "/"

def read_config(): # TODO add functionality for leaving out the lastfm info
    # IMPORTANT: config.json is the only thing that's .gitignore'd
    # don't put your details in example.json, or a file with any other name
    with open(get_absolute_rolling_songs_dir() + "config/config.json", "r") as cfile:
        config = json.load(cfile)

    # get required fields from the example file
    with open(get_absolute_rolling_songs_dir() + "config/example.json", "r") as example_conf:
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

def write_config(config):
    with open(get_absolute_rolling_songs_dir() + "config/config.json", "w") as cfile:
        json.dump(config, cfile, indent=4)