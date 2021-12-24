import json

def get_config(): # TODO add functionality for leaving things blank
    # IMPORTANT: config.json is the only thing that's .gitignore'd
    # don't put your details in example.json, or a file with any other name
    with open("config/config.json", "r") as cfile:
        config = json.load(cfile)

    # get required fields from the example file
    with open("config/example.json", "r") as example_conf:
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