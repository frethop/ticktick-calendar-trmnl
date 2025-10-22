import logging
import requests
import ticktickutils as tt
from datetime import datetime
from datetime import time
from datetime import timedelta
from datetime import timezone
import pytz
import os.path
import json
import re

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError

version = "0.81 (042525)"

logging.basicConfig(filename='ticktick-trml.log', encoding='utf-8', level=logging.DEBUG)
logger = logging.getLogger("TICKTICK-TRMNL")
logger.info("TickTick TRMNL started on "+str(datetime.now()))

SCOPES = ["https://www.googleapis.com/auth/calendar.readonly"]

lists = tt.get_user_project()
todaysTasks = []
today = datetime.now()

rticktickDateFormat = "%Y-%m-%dT%H:%M:%S"
#ticktickDateFormat = "yyyy-MM-dd'T'HH:mm:ssZ"
ticktickDateFormat = "%Y-%m-%d"

def isToday(dateString):
    global today
    dateString = dateString[:10]
    dt = datetime.strptime(dateString, ticktickDateFormat)
    return today.date() == dt.date()

creds = None
# The file token.json stores the user's access and refresh tokens, and is
# created automatically when the authorization flow completes for the first
# time.
#if os.path.exists("token.json"):
try:
    creds = Credentials.from_authorized_user_file("token.json", SCOPES)
except:
    logger.error("token.json does not exist.")
# If there are no (valid) credentials available, let the user log in.
if not creds or not creds.valid:
    if creds and creds.expired and creds.refresh_token:
        creds.refresh(Request())
    else:
        flow = InstalledAppFlow.from_client_secrets_file(
            "credentials.json", SCOPES
        )
        creds = flow.run_local_server(port=0)
# Save the credentials for the next run
with open("token.json", "w") as token:
    token.write(creds.to_json())

events = []
try:
    service = build("calendar", "v3", credentials=creds)

    # Call the Calendar API
    now = datetime.now(timezone.utc)
    #now = datetime.utcnow().isoformat() + "Z"  # 'Z' indicates UTC time
    now = now.replace(hour=0,minute=0)
    now = str(now).replace(" ","T")
    logger.info("Getting the upcoming 10 events")
    events_result = (
        service.events()
        .list(
            calendarId="primary",
            timeMin=now,
            maxResults=40,
            singleEvents=True,
            orderBy="startTime",
        )
        .execute()
    )
    events = events_result.get("items", [])

    if not events:
      logger.info("No upcoming events found.")

except HttpError as error:
    logger.error(f"An error occurred: {error}")

## Gather all the tasks for today
for list in lists:
    try:
        tasks = tt.get_project_with_data(project_id=list['id'])['tasks']
    except:
        logger.error("Too early for TickTick")
        exit() 

    for task in tasks:
        try: 
            #print(task['title']+":"+task['startDate']+" to "+task['dueDate'])
            if isToday(task['startDate']):
                logger.debug("Ticktick entry: "+str(task))
                todaysTasks.append(task)
        except:
            pass

## Gather the events for today -- package them in a dictionary structure like that from TickTick
for ev in events:
    start = ev["start"].get("dateTime", ev["start"].get("date"))
    if isToday(start):
        try:
            task = {}
            task['startDate'] = ev["start"].get("dateTime", ev["start"].get("date"))
            task['dueDate'] = ev["end"].get("dateTime", ev["start"].get("date"))
            task['title'] = ev['summary']
            task['timeZone'] = ev['start']['timeZone']
            task['status'] = -1
            logger.debug("Calendar event: "+str(task))
            todaysTasks.append(task)
        except:
            print("All day event!")
            print(ev) 

## ------------------------------------------------------------------------------------------
## Now we start the variable generation process.

#tzone = pytz.timezone(task['timeZone'])
def taskKey(task):
    return task['startDate']

todaysTasks.sort(key=taskKey)
print(todaysTasks)

payload_tasks = []

for task in todaysTasks:
    task['title'] = re.sub(r'\[.*\]', '', task['title'])
    print(task['title'])

    tzone = pytz.timezone(task['timeZone'])

    ## Start of the task/event
    t = task['startDate'][:19]
    start = datetime.strptime(t, rticktickDateFormat)
    if task['status'] == -1:
        start = start.replace(second=0, tzinfo=tzone)
    else:
        start = start.replace(second=0, tzinfo=pytz.UTC)
        start = start.astimezone(tzone)
    ## round to a 15 min boundary
    originalStart = None
    if start.time().minute % 15 != 0:
        originalStart = start
        newminute = int(start.time().minute / 15) * 15
        start = start.replace(minute=newminute)

    print(start)

    ## End of the task/event
    e = task['dueDate'][:19]
    end = datetime.strptime(e, rticktickDateFormat)
    if task['status'] == -1:
        end = end.replace(second=0, tzinfo=tzone)
    else:
        end = end.replace(second=0, tzinfo=pytz.UTC)
        end = end.astimezone(tzone)

    ## round to a 15 min boundary
    originalEnd = None
    if end.time().minute % 15 != 0:
        originalEnd = end
        newminute = (int(end.time().minute / 15)+1) * 15
        if newminute > 45:
            end = end.replace(minute=0)
            end = end + timedelta(hours=1)
        else:
            end = end.replace(minute=newminute)
    
    if start.time() == end.time():
        end = end + timedelta(minutes=15)
   
    print(end)

    ## add to the list
    startd = start if originalStart == None else originalStart
    endd = end if originalEnd == None else originalEnd

    ttype = "event" if task['status']==-1 else "task"
    startN = int(startd.strftime("%-H%M"))
    endN = int(endd.strftime("%-H%M"))

    payload_tasks.append(   
        {
            "type": "event" if task["status"] == -1 else "task",
            "text": task["title"],
            "start": startd.strftime("%I:%M").lstrip("0"),
            "end": endd.strftime("%I:%M").lstrip("0"),
            "startN": startN,
            "endN": endN,
        }
    )

# tjson = [json.dumps(taskjson)]
# print(taskjson)
# print("----")
# print(tjson)

todaystr = datetime.now().strftime("%m/%d/%Y %-I:%M")

url = "https://usetrmnl.com/api/custom_plugins/58ddda97-f6c6-4c45-a74c-5e83866b591b"
variables = {"merge_variables": {"tasks": payload_tasks, "date": todaystr }}
result = requests.post(url, json=variables)
if result.status_code != 200:
    logger.error(result.text)

