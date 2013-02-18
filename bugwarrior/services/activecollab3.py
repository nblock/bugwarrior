from twiggy import log

from bugwarrior.services import IssueService
from bugwarrior.config import die
from bugwarrior.db import MARKUP

import urllib2
import time
import json
import datetime
import pprint

api_count = 0
task_count = 0

class ActiveCollabApi():
    def call_api(self, uri, key, url):
        global api_count
        api_count += 1
        url = url.rstrip("/") + "?auth_api_token=" + key + "&path_info=" + uri + "&format=json"
        req = urllib2.Request(url)
        res = urllib2.urlopen(req)
        return json.loads(res.read())

class Client(object):
    def __init__(self, url, key, user_id, projects):
        self.url = url
        self.key = key
        self.user_id = user_id
        self.projects = projects

    # Return a UNIX timestamp from an ActiveCollab date
    def format_date(self, date):
        if date is None:
            return
        d = datetime.datetime.fromtimestamp(time.mktime(time.strptime(
                    date, "%Y-%m-%d")))
        timestamp = int(time.mktime(d.timetuple()))
        return timestamp

    # Return a priority of L, M, or H based on AC's priority index of -2 to 2
    def format_priority(self, priority):
        priority = str(priority)
        priority_map = {'-2': 'L', '-1': 'L', '0': 'M', '1': 'H', '2': 'H'}
        return priority_map[priority]

    def find_issues(self, user_id=None, project_id=None, project_name=None):
        """
        Approach:

        1. Get user ID from .bugwarriorrc file
        2. Get list of tickets from /user-tasks for a given project
        3. For each ticket/task returned from #2, get ticket/task info and check
           if logged-in user is primary (look at `is_owner` and `user_id`)
        """
        ac = ActiveCollabApi()
        user_tasks_data = ac.call_api("/projects/" + str(project_id) + "/tasks", self.key, self.url)
        user_subtasks_data = ac.call_api("/projects/" + str(project_id) + "/subtasks", self.key, self.url)
        global task_count
        assigned_tasks = []

        try:
            for key, task in enumerate(user_tasks_data):
                task_count += 1
                assigned_task = dict()
                # Load Task data
                # @todo Implement threading here.
                if ((task[u'assignee_id'] == int(self.user_id)) and (task[u'completed_on'] is None)):
                    assigned_task['permalink'] = task[u'permalink']
                    assigned_task['task_id'] = task[u'task_id']
                    assigned_task['id'] = task[u'id']
                    assigned_task['project_id'] = task[u'project_id']
                    assigned_task['project'] = project_name
                    assigned_task['description'] = task[u'name']
                    assigned_task['type'] = "task"
                    assigned_task['created_on'] = task[u'created_on'][u'mysql']
                    assigned_task['created_by_id'] = task[u'created_by_id']
                    if 'priority' in task:
                        assigned_task['priority'] = self.format_priority(task[u'priority'])
                    else:
                        assigned_task['priority'] = self.default_priority
                    if task[u'due_on'] is not None:
                        assigned_task['due'] = self.format_date(task[u'due_on'][u'mysql'])
                if assigned_task:
                    # log.name(self.target).debug(" Adding '" + assigned_task['description'] + "' to task list.")
                    print ' Adding %s to task list' % assigned_task['description']
                    assigned_tasks.append(assigned_task)
        except:
            print ' No user tasks loaded for "%s"' % project_name
            # log.name(self.target).debug(' No user tasks loaded for "%s".' % project_id)

        # Subtasks
        if user_subtasks_data:
            for key, subtask in enumerate(user_subtasks_data):
                task_count += 1
                assigned_task = dict()
                if ((subtask[u'assignee_id'] == int(self.user_id)) and (subtask[u'completed_on'] is None)):
                    # Get permalink
                    assigned_task['permalink'] = (self.url).rstrip('api.php') + 'projects/' + str(project_id) + '/tasks'
                    for k, t in enumerate(assigned_tasks):
                        if 'id' in t:
                            if subtask[u'parent_id'] == t[u'id']:
                                assigned_task['permalink'] = t[u'permalink']
                    assigned_task['task_id'] = subtask[u'id']
                    assigned_task['project'] = project_name
                    assigned_task['project_id'] = project_id
                    assigned_task['description'] = subtask['body']
                    assigned_task['type'] = 'subtask'
                    assigned_task['created_on'] = subtask[u'created_on']
                    assigned_task['created_by_id'] = subtask[u'created_by_id']
                    if 'priority' in subtask:
                        assigned_task['priority'] = self.format_priority(subtask[u'priority'])
                    else:
                        assigned_task['priority'] = self.default_priority
                    if subtask[u'due_on'] is not None:
                        assigned_task['due'] = self.format_date(subtask[u'due_on'])
                if assigned_task:
                    # log.name(self.target).debug(" Adding '" + assigned_task['description'] + "' to task list.")
                    print ' Adding subtask %s to task list' % assigned_task['description']
                    assigned_tasks.append(assigned_task)

        return assigned_tasks

class ActiveCollab3Service(IssueService):
    def __init__(self, *args, **kw):
        super(ActiveCollab3Service, self).__init__(*args, **kw)

        self.url = self.config.get(self.target, 'url').rstrip("/")
        self.key = self.config.get(self.target, 'key')
        self.user_id = self.config.get(self.target, 'user_id')

        # Get a list of favorite projects
        projects = []
        ac = ActiveCollabApi()
        data = ac.call_api("/projects", self.key, self.url)
        for item in data:
            if item[u'is_favorite'] == 1:
                projects.append(dict([(item[u'id'], item[u'name'])]))

        self.projects = projects

        self.client = Client(self.url, self.key, self.user_id, self.projects)

    @classmethod
    def validate_config(cls, config, target):
        for k in ('url', 'key', 'user_id'):
            if not config.has_option(target, k):
                die("[%s] has no '%s'" % (target, k))

        IssueService.validate_config(config, target)

    def get_issue_url(self, issue):
        return issue['permalink']

    def get_project_name(self, issue):
        return issue['project']

    def description(self, title, project_id, task_id="", cls="task"):

        cls_markup = {
            'task': '#',
            'subtask': 'Subtask #',
        }

        return "%s%s%s - %s" % (
            MARKUP, cls_markup[cls], str(task_id),
            title[:45],
        )

    def format_annotation(self, created, permalink):
        return (
            "annotation_%i" % time.mktime(created.timetuple()),
            "%s" % (permalink),
        )

    def annotations(self, issue):
        return dict([
            self.format_annotation(
                datetime.datetime.fromtimestamp(time.mktime(time.strptime(
                    issue['created_on'], "%Y-%m-%d %H:%M:%S"))),
                issue['permalink'],
            )])

    def issues(self):
        # Loop through each project
        start = time.time()
        issues = []
        projects = self.projects
        # @todo Implement threading here.
        log.name(self.target).debug(" {0} projects in favorites list.", len(projects))
        for project in projects:
            for project_id, project_name in project.iteritems():
                log.name(self.target).debug(" Getting tasks for #" + str(project_id) + " " + str(project_name) + '"')
                issues += self.client.find_issues(self.user_id, project_id, project_name)

        log.name(self.target).debug(" Found {0} total.", len(issues))
        global api_count
        log.name(self.target).debug(" {0} API calls", api_count)
        log.name(self.target).debug(" {0} tasks and subtasks analyzed", task_count)
        log.name(self.target).debug(" Elapsed Time: %s" % (time.time() - start))

        formatted_issues = []

        for issue in issues:
            formatted_issue = dict(
                description=self.description(
                issue["description"],
                issue["project_id"], issue["task_id"], issue["type"],
                ),
                project=self.get_project_name(issue),
                priority=issue["priority"],
                **self.annotations(issue)
            )
            if "due" in issue:
                formatted_issue["due"] = issue["due"]
            formatted_issues.append(formatted_issue)
        log.name(self.target).debug(" {0} tasks assigned to you", len(formatted_issues))
        return formatted_issues
