#!/usr/bin/env python3

from __future__ import print_function
from asyncio import create_task

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
        self.headers = {
            "Authorization": f"Bearer {os.getenv('NOTION_API_KEY')}",
            "Content-Type": "application/json",
            "Notion-Version": "2021-08-16",
        }
        self.last_actions = {}
        self.last_tasks = {}
        self.sync_notion_gCal()

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
        result = (
            self.gCal_service.tasks()
            .list(tasklist=os.getenv("GCAL_TASKLIST_ID"), showCompleted=False)
            .execute()
        )
        if "items" in result:
            tasks = {r["notes"]: r for r in result["items"]}
        else:
            tasks = {}

        print(f"[+] Got all {len(tasks)} tasks")
        return tasks

    def delete_gCal_task(self, task_id):
        print(f"[+] Deleting task - {task_id} ...")
        self.gCal_service.tasks().delete(
            tasklist=os.getenv("GCAL_TASKLIST_ID"), task=task_id
        ).execute()

    def delete_gCal_alltasks(self):
        tasks = self.get_gCal_tasks()
        print(f"[+] Deleting all {len(tasks)} tasks...")
        for v in tasks.values():
            self.gCal_service.tasks().delete(
                tasklist=os.getenv("GCAL_TASKLIST_ID"), task=v["id"]
            ).execute()

    def create_gCal_task(self, task_name, action_id, due_date=None):
        if due_date == None:
            due_date = self.now()

        task = {"title": task_name, "due": due_date, "notes": f"{action_id}"}
        task = (
            self.gCal_service.tasks()
            .insert(tasklist=os.getenv("GCAL_TASKLIST_ID"), body=task)
            .execute()
        )
        print("[+] Task created: %s" % (task_name))
        return task

    def get_notion_actions(self):
        proxies = {"https": "http://127.0.0.1:8080"}
        api = f"https://api.notion.com/v1/databases/{os.getenv('NOTION_ACTION_DB_ID')}/query"
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
        r = requests.post(api, headers=self.headers, json=data)
        actions = {
            r["id"]: {
                "title": r["properties"]["⭐Action⭐"]["title"][0]["plain_text"],
                "completed": r["properties"]["Done"]["checkbox"],
                "do_date": r["properties"]["Do Date"]["date"],
            }
            for r in json.loads(r.text)["results"]
        }

        print(f"[+] Got all {len(actions)} actions from notion")
        return actions

    def mark_action_done(self, action_id):
        api = f"https://api.notion.com/v1/pages/{action_id}"
        r = requests.request(
            "PATCH",
            api,
            headers=self.headers,
            json={"properties": {"Done": {"checkbox": True}}},
        )

        print(f"[+] Marked action - {action_id} as Done")

    def mark_task_done(self, task_id):
        self.gCal_service.tasks().update(
            tasklist=os.getenv("GCAL_TASKLIST_ID"),
            task=task_id,
            body={"completed": self.now()},
        ).execute()

    def mark_task_uncompleted(self, task_id):
        self.gCal_service.tasks().update(
            tasklist=os.getenv("GCAL_TASKLIST_ID"),
            task=task_id,
            body={"completed": False},
        ).execute()

    def sync_notion_gCal(self):
        actions = self.get_notion_actions()
        tasks = self.get_gCal_tasks()
        a_changed = actions != self.last_actions
        t_changed = tasks != self.last_tasks

        # print(a_changed)
        # print(t_changed)
        if a_changed:
            # sync from notion to gcal

            to_add = actions.keys() - tasks.keys()
            for a_id in to_add:
                task = self.create_gCal_task(actions[a_id]["title"], a_id)
                tasks[task["notes"]] = task

            to_remove = tasks.keys() - actions.keys()
            for a_id in to_remove:
                self.delete_gCal_task(tasks[a_id]["id"])

            self.last_actions = actions
            self.last_tasks = tasks

        elif t_changed:
            # sync form gcal to notion
            removed = self.last_tasks.keys() - tasks.keys()
            print(removed)
            for t in removed:
                a_id = self.last_tasks[t]["notes"]
                self.mark_action_done(a_id)
                del self.last_actions[a_id]
            self.last_tasks = tasks

    def now(self):
        return datetime.datetime.now().astimezone().strftime("%Y-%m-%dT%H:%M:%S%z")

    def get_today_date(self):
        return datetime.datetime.today().strftime("%Y-%m-%d")

    def get_gCal_today_date(self):
        return self.get_today_date() + "T00:00:00+0100"


if __name__ == "__main__":
    life_os = NotionLifeOS()
    # tasks = life_os.get_gCal_tasks()
    # actions = life_os.get_notion_todo_actions()
