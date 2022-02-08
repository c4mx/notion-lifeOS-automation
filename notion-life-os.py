#!/usr/bin/env python3

from __future__ import print_function

import datetime
import os.path
import os
from dotenv import load_dotenv

from google.auth.transport.requests import Request
from google.oauth2.credentials import Credentials
from google_auth_oauthlib.flow import InstalledAppFlow
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
import requests
import json
from pprint import pprint

# If modifying these scopes, delete the file token.json.
# SCOPES = ["https://www.googleapis.com/auth/calendar"]
SCOPES = ["https://www.googleapis.com/auth/tasks"]

load_dotenv(".env")


class NotionLifeOS:
    def __init__(self):
        self.gCal_service = self.init_gCal()

    def init_gCal(self, service_name="task"):
        """Shows basic usage of the Google Calendar API.
        Prints the start and name of the next 10 events on the user's calendar.
        """
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                creds.refresh(Request())
            else:
                flow = InstalledAppFlow.from_client_secrets_file(
                    "credentials.json", SCOPES
                )
                creds = flow.run_console()
            # Save the credentials for the next run
            with open("token.json", "w") as token:
                token.write(creds.to_json())

        if service_name == "calendar":
            service = build("calendar", "v3", credentials=creds)
        elif service_name == "task":
            service = build("tasks", "v1", credentials=creds)
        else:
            service = None

        return service

    def get_gCal_events(self):
        # Call the Calendar API
        print("Getting the upcoming 10 events")
        events_result = (
            self.gCal_service.events()
            .list(
                calendarId="primary",
                timeMin=f"{self.get_today_date()}T00:00:00+0100",
                maxResults=10,
                singleEvents=True,
                orderBy="startTime",
            )
            .execute()
        )
        events = events_result.get("items", [])

        pprint(events)

        if events:
            # Prints the start and name of the next 10 events
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                print(start, event["summary"])
        else:
            print("no upcoming events")

    def create_gCal_event(self, gCal_event):
        event = (
            self.gCal_service.events()
            .insert(calendarId="primary", body=gCal_event)
            .execute()
        )
        print("Event created: %s" % (event.get("htmlLink")))

    def get_gCal_notion_tasklist_id(self):
        tasks_result = self.gCal_service.tasklists().list(maxResults=10).execute()
        pprint(tasks_result)

    def get_gCal_tasks(self):
        print("[+] Getting all gcal tasks...")
        tasks = (
            self.gCal_service.tasks()
            .list(tasklist=os.getenv("GCAL_TASKLIST_ID"))
            .execute()
        )
        pprint(tasks)
        return tasks

    def delete_gCal_alltasks(self):
        task_list = self.get_gCal_tasks(self.gCal_service)
        if "items" in task_list:
            tasks = task_list["items"]
            print(f"[+] Deleting all {len(tasks)} tasks...")
            for task in tasks:
                self.gCal_service.tasks().delete(
                    tasklist=os.getenv("GCAL_TASKLIST_ID"), task=task["id"]
                ).execute()
        else:
            print("[+] No tasks deleted, task list empty")

    def create_gCal_task(self, task_name, due_date=None):
        if len(task_name) == 0:
            print("[-] Task name is required")
            return

        if due_date == None:
            due_date = self.now()

        task = {"title": task_name, "due": due_date}
        task = (
            self.create_gCal_task.tasks()
            .insert(tasklist=os.getenv("GCAL_TASKLIST_ID"), body=task)
            .execute()
        )
        print("Task created: %s" % (task))

    def get_notion_todo_actions(self):
        proxies = {"https": "http://127.0.0.1:8080"}
        api = f"https://api.notion.com/v1/databases/{os.getenv('NOTION_ACTION_DB_ID')}/query"
        headers = {
            "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
            "Content-Type": "application/json",
            "Notion-Version": "2021-08-16",
        }
        data = {
            "filter": {
                "and": [
                    {
                        "property": "Do Date",
                        "date": {"on_or_before": self.get_today_date()},
                    },
                    {"property": "Done", "checkbox": {"equals": False}},
                    {"property": "Status", "select": {"equals": "Active"}},
                ]
            }
        }
        # r = requests.post(api, headers=headers, json=data, proxies=proxies, verify=False)
        r = requests.post(api, headers=headers, json=data)

        return [
            {
                "title": r["properties"]["⭐Action⭐"]["title"][0]["plain_text"],
                "completed": r["properties"]["Done"]["checkbox"],
                "due": self.now(),
            }
            for r in json.loads(r.text)["results"]
        ]

    def notion_to_gCal_sync(self):
        notion_actions = self.get_notion_todo_actions()
        gCal_tasks = self.get_gCal_tasks()
        for action in notion_actions:
            for task in gCal_tasks:
                if action["title"] == task["title"]:
                    pass

    def sync_action2task(self):
        print("[+] Sync from Notion actions to gCal tasks...")
        actions = self.get_notion_todo_actions()
        self.delete_gCal_alltasks()
        for action in actions:
            self.create_gCal_task(action["title"])

    def mark_complete(self, task):
        self.gCal_service.tasks().update(
            tasklist=os.getenv("GCAL_TASKLIST_ID"),
            task=task["id"],
            body={"completed": self.now()},
        ).execute()

    def now(self):
        return datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

    def get_today_date(self):
        return datetime.datetime.today().strftime("%Y-%m-%d")

    def get_gCal_today_date(self):
        return self.get_today_date() + "T00:00:00+0100"


if __name__ == "__main__":
    life_os = NotionLifeOS()
    life_os.get_gCal_tasks()
