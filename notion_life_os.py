#!/usr/bin/env python3

from __future__ import print_function
from asyncio import create_task

import datetime
import os.path
import os
from dotenv import load_dotenv
import sched, time
import logging

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
        self.today = self.get_today_date()
        self.new_logfile(self.today)
        self.scheduler = sched.scheduler(time.time, time.sleep)

    def new_logfile(self, date):
        Log_Format = "%(levelname)s %(asctime)s - %(message)s"

        logging.basicConfig(
            filename=f"log/{date}.log",
            filemode="a",
            format=Log_Format,
            level=logging.INFO,
        )

        self.logger = logging.getLogger()

    def run(self):
        self.logger.info("[+] Life OS automation is running ...")
        self.scheduler.enter(60, 1, self.sync_notion_gCal)
        self.scheduler.run()

    def init_gCal(self, service_name="task"):
        creds = None
        # The file token.json stores the user's access and refresh tokens, and is
        # created automatically when the authorization flow completes for the first
        # time.
        if os.path.exists("token.json"):
            creds = Credentials.from_authorized_user_file("token.json", SCOPES)
        # If there are no (valid) credentials available, let the user log in.
        if not creds or not creds.valid:
            if creds and creds.expired and creds.refresh_token:
                try:
                    creds.refresh(Request())
                except Exception as e:
                    self.logger.error(e)
                    exit(-1)
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
        self.logger.info("Getting the upcoming 10 events")
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

        self.logger.info(pprint(events))

        if events:
            # self.logger.infos the start and name of the next 10 events
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                self.logger.info(start, event["summary"])
        else:
            self.logger.info("no upcoming events")

    def create_gCal_event(self, gCal_event):
        event = (
            self.gCal_service.events()
            .insert(calendarId="primary", body=gCal_event)
            .execute()
        )
        self.logger.info("Event created: %s" % (event.get("htmlLink")))

    def get_gCal_notion_tasklist_id(self):
        tasks_result = self.gCal_service.tasklists().list(maxResults=10).execute()
        self.logger.info(tasks_result)

    def get_gCal_tasks(self):
        try:
            result = (
                self.gCal_service.tasks()
                .list(tasklist=os.getenv("GCAL_TASKLIST_ID"), showCompleted=False)
                .execute()
            )

            self.logger.debug(pprint(result))

            if "items" in result:
                tasks = {r["notes"]: r for r in result["items"]}
            else:
                tasks = {}
        except Exception as e:
            self.logger.error(e)
            return {}

        self.logger.info(f"[+] Got all {len(tasks)} tasks")
        return tasks

    def delete_gCal_task(self, task_id):
        self.logger.info(f"[+] Deleting task - {task_id} ...")
        self.gCal_service.tasks().delete(
            tasklist=os.getenv("GCAL_TASKLIST_ID"), task=task_id
        ).execute()

    def delete_gCal_alltasks(self):
        tasks = self.get_gCal_tasks()
        self.logger.info(f"[+] Deleting all {len(tasks)} tasks...")
        for v in tasks.values():
            try:
                self.gCal_service.tasks().delete(
                    tasklist=os.getenv("GCAL_TASKLIST_ID"), task=v["id"]
                ).execute()
            except Exception as e:
                self.logger.error(e)

    def create_gCal_task(self, task_name, action_id, due_date=None):
        if due_date == None:
            due_date = self.get_gCal_today_date()

        task = {"title": task_name, "due": due_date, "notes": f"{action_id}"}
        self.logger.debug(pprint(task))

        task = (
            self.gCal_service.tasks()
            .insert(tasklist=os.getenv("GCAL_TASKLIST_ID"), body=task)
            .execute()
        )
        self.logger.info("[+] Task created: %s" % (task_name))
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
        try:
            r = requests.post(api, headers=self.headers, json=data)
            actions = {
                r["id"]: {
                    "title": r["properties"]["⭐Action⭐"]["title"][0]["plain_text"],
                    "completed": r["properties"]["Done"]["checkbox"],
                    "do_date": r["properties"]["Do Date"]["date"],
                }
                for r in json.loads(r.text)["results"]
            }
            self.logger.info(f"[+] Got all {len(actions)} actions from notion")
            return actions
        except Exception as e:
            self.logger.error(e)
            return self.last_actions

    def mark_action_done(self, action_id):
        api = f"https://api.notion.com/v1/pages/{action_id}"
        try:
            requests.request(
                "PATCH",
                api,
                headers=self.headers,
                json={"properties": {"Done": {"checkbox": True}}},
            )
            self.logger.info(f"[+] Marked action - {action_id} as Done")
        except Exception as e:
            self.logger.error(e)
            self.logger.error(f"[-] Error when marked action - {action_id} as Done")

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

    def is_first_req_today(self):
        real_today = self.get_today_date()
        if real_today != self.today:
            self.today = real_today
            return True
        else:
            return False

    def sync_notion_gCal(self):
        self.logger.info("[+] Sync notion and gCal ...")

        if datetime.datetime.now().strftime("%H:%M") == "23:59":
            time.sleep(300)

        actions = self.get_notion_actions()

        if self.is_first_req_today():
            self.new_logfile(self.today)
            self.delete_gCal_alltasks()
            tasks = {}
        else:
            tasks = self.get_gCal_tasks()

        a_changed = actions != self.last_actions
        t_changed = tasks != self.last_tasks

        # self.logger.info(a_changed)
        # self.logger.info(t_changed)
        if a_changed:
            # sync from notion to gcal
            self.notion2gcal(actions, tasks)

        elif t_changed:
            # sync form gcal to notion
            self.gcal2notion(tasks)

        self.scheduler.enter(60, 1, self.sync_notion_gCal)

    def notion2gcal(self, actions, tasks):
        to_add = actions.keys() - tasks.keys()
        for a_id in to_add:
            task = self.create_gCal_task(actions[a_id]["title"], a_id)
            tasks[task["notes"]] = task

        to_remove = tasks.keys() - actions.keys()
        for a_id in to_remove:
            self.delete_gCal_task(tasks[a_id]["id"])
            del tasks[a_id]

        self.last_actions = actions
        self.last_tasks = tasks

    def gcal2notion(self, tasks):
        # Only remove operations on gCal tasks
        removed = self.last_tasks.keys() - tasks.keys()
        self.logger.info(removed)
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
        return self.get_today_date() + "T00:00:00.000Z"


if __name__ == "__main__":
    life_os = NotionLifeOS()
    life_os.run()
