import datetime

DATE_FORMAT = "%Y-%m-%d"

# returns current date as a formatted string
def get_date():
    return datetime.datetime.today().strftime(DATE_FORMAT)