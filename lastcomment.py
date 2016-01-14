#!/usr/bin/env python

"""Print the last time a reviewer(bot) left a comment."""

import argparse
import calendar
import collections
import datetime
import json
import sys
import urllib
import yaml

import requests

try:
    # Disable InsecurePlatformWarning warnings as documented here
    # https://github.com/kennethreitz/requests/issues/2214
    from requests.packages.urllib3.exceptions import InsecurePlatformWarning
    from requests.packages.urllib3.exceptions import InsecureRequestWarning
    requests.packages.urllib3.disable_warnings(InsecurePlatformWarning)
    requests.packages.urllib3.disable_warnings(InsecureRequestWarning)
except ImportError:
    # If there's an import error, then urllib3 may be packaged
    # separately, so apply it there too
    import urllib3
    from urllib3.exceptions import InsecurePlatformWarning
    from urllib3.exceptions import InsecureRequestWarning
    urllib3.disable_warnings(InsecurePlatformWarning)
    urllib3.disable_warnings(InsecureRequestWarning)

TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Account(object):
    _account_id = None
    name = None
    email = None
    username = None

    def __init__(self, account_info={}):
        super(Account, self).__init__()
        self._account_id = account_info.get('_account_id', 0)
        self.name = account_info.get('name', None)
        self.email = account_info.get('email', None)
        self.username = account_info.get('username', None)

    def __str__(self):
        a = []
        if self.name:
            a.append("'%s'" % self.name)
        if self.username:
            a.append(self.username)
        if self.email:
            a.append("<%s>" % self.email)
        if a:
            return "ID %s (%s)" % (self._account_id, ", ".join(a))
        else:
            return "ID %s" % self._account_id

    def __le__(self, other):
        # self < other
        return self._account_id < other._account_id


class Comment(object):
    date = None
    number = None
    subject = None
    now = None
    gerrit_url = None

    def __init__(self, date, number, subject, message):
        super(Comment, self).__init__()
        self.date = date
        self.number = number
        self.subject = subject
        self.message = message
        self.now = datetime.datetime.utcnow().replace(microsecond=0)

    def __str__(self):
        return ("%s (%s old) %s/%s '%s' " % (
            self.date.strftime(TIME_FORMAT),
            self.age(),
            self.gerrit_url,
            self.number, self.subject))

    def age(self):
        return self.now - self.date

    def __le__(self, other):
        # self < other
        return self.date < other.date

    def __repr__(self):
        # for sorting
        return repr((self.date, self.number))


def get_comments(change, account):
    """Generator that returns all comments by account on a given change."""
    body = None
    for message in change['messages']:
        if ('author' in message and
            '_account_id' in message['author'] and
            message['author']['_account_id'] == account._account_id):

            if (message['message'].startswith("Uploaded patch set") and
                len(message['message'].split()) is 4):
                # comment is auto created from posting a new patch
                continue
            date = message['date']
            body = message['message']
            # https://review.openstack.org/Documentation/rest-api.html#timestamp
            # drop nanoseconds
            date = date.split('.')[0]
            date = datetime.datetime.strptime(date, TIME_FORMAT)
            yield date, body


def query_gerrit(gerrit_url, account, count, project, verify=True):
    # Include review messages in query
    search = "reviewer:{%s}" % account._account_id
    if project:
        search = search + (" AND project:{%s}" % project)
    query = ("%s/changes/?q=%s&"
             "o=MESSAGES&pp=0" % (gerrit_url, urllib.quote_plus(search)))
    r = requests.get(query, verify=verify)
    try:
        changes = json.loads(r.text[4:])
    except ValueError:
        print "query: '%s' failed with:\n%s" % (query, r.text)
        sys.exit(1)

    comments = []
    for change in changes:
        for date, message in get_comments(change, account):
            if date is None:
                # no comments from reviewer yet. This can happen since
                # 'Uploaded patch set X.' is considered a comment.
                continue
            comments.append(Comment(date, change['_number'],
                                    change['subject'], message))

    return sorted(comments, key=lambda comment: comment.date,
                  reverse=True)[0:count]


def lookup_account(gerrit_url, account_id, verify=True):
    """Look up account information.

    An account "ID" can be any uniquely identifying account information. See the
    API documentation for more information:

    https://review.openstack.org/Documentation/rest-api-accounts.html#account-id
    """

    query = "%s/accounts/%s?pp=0" % (gerrit_url, urllib.quote_plus(account_id))
    r = requests.get(query, verify=verify)
    try:
        return Account(json.loads(r.text[4:]))
    except ValueError:
        print "account lookup for '%s' failed with:\n%s" % (account_id, r.text)
        sys.exit(1)


def vote(comment, success, failure, log=False):
    for line in comment.message.splitlines():
        if line.startswith("* ") or line.startswith("- "):
            job = line.split(' ')[1]
            if " : SUCCESS" in line:
                success[job] += 1
                if log:
                    print line
            if " : FAILURE" in line:
                failure[job] += 1
                if log:
                    print line


def generate_report(gerrit_url, account, count, project, verify):
    result = {'account': account.__dict__, 'project': project}
    success = collections.defaultdict(int)
    failure = collections.defaultdict(int)

    comments = query_gerrit(gerrit_url, account, count, project, verify)

    if len(comments) == 0:
        print "didn't find anything"
        return None

    print "last seen: %s (%s old)" % (comments[0].date, comments[0].age())
    result['last'] = epoch(comments[0].date)

    for comment in comments:
        vote(comment, success, failure)

    total = sum(success.values()) + sum(failure.values())
    if total > 0:
        success_rate = str(int(sum(success.values()) /
                               float(total) * 100)) + "%"
        result['rate'] = success_rate
        print "success rate: %s" % success_rate
    return result


def print_last_comments(gerrit_url, account, count, print_message, project,
                        votes, verify):
    success = collections.defaultdict(int)
    failure = collections.defaultdict(int)

    comments = query_gerrit(gerrit_url, account, count, project, verify)

    message = "last %s comments from '%s'" % (count, account.name)
    if project:
        message += " on project '%s'" % project
    print message
    # sort by time
    for i, comment in enumerate(comments):
        print "[%d] %s" % (i, comment)
        if print_message:
            print "message: \"%s\"" % comment.message
            print
        if votes:
            vote(comment, success, failure, log=True)

    if votes:
        print "success count by job:"
        for job in success.iterkeys():
            print "* %s: %d" % (job, success[job])
        print "failure count by job:"
        for job in failure.iterkeys():
            print "* %s: %d" % (job, failure[job])


def epoch(timestamp):
    return int(calendar.timegm(timestamp.timetuple()))


def main():
    parser = argparse.ArgumentParser(description='list most recent comment by '
                                     'reviewer')
    parser.add_argument('-n', '--name',
                        default="Elastic Recheck",
                        help='unique gerrit name of the reviewer')
    parser.add_argument('-c', '--count',
                        default=10,
                        type=int,
                        help='Max number of results to return')
    parser.add_argument('-f', '--file',
                        default=None,
                        help='yaml file containing list of names to search on'
                             'project: name'
                             ' (overwrites -p and -n)')
    parser.add_argument('-m', '--message',
                        action='store_true',
                        help='print comment message')
    parser.add_argument('-v', '--votes',
                        action='store_true',
                        help=('Look in comments for CI Jobs and detect '
                              'SUCCESS/FAILURE'))
    parser.add_argument('--json',
                        nargs='?',
                        const='lastcomment.json',
                        help=("Generate report to be stored in the json file "
                              "specified here. Ignores -v and -m "
                              "(default: 'lastcomment.json')"))
    parser.add_argument('-p', '--project',
                        help='only list hits for a specific project')
    parser.add_argument('-g', '--gerrit-url',
                        default='https://review.openstack.org/',
                        help='Gerrit server http/https url')
    parser.add_argument('--no-verify',
                        action='store_false',
                        help='Ignore gerrit server certificate validity')

    args = parser.parse_args()
    names = {args.project: [args.name]}
    accounts = {}
    if args.file:
        with open(args.file) as f:
            names = yaml.load(f)

    for project in names:
        for id in names[project]:
            if id in accounts:
                continue
            accounts[id] = lookup_account(args.gerrit_url, id, args.no_verify)

    if args.json:
        print "generating report %s" % args.json
        print "report is over last %s comments" % args.count
        report = {}
        timestamp = epoch(datetime.datetime.utcnow())
        report['timestamp'] = timestamp
        report['rows'] = []

    for project in names:
        print 'Checking project: %s' % project
        for name in names[project]:
            account = accounts[name]
            print 'Checking account: %s' % account
            try:
                if args.json:
                    report['rows'].append(generate_report(args.gerrit_url,
                        account, args.count, project, args.no_verify))
                else:
                    print_last_comments(args.gerrit_url, account, args.count,
                                        args.message, project, args.votes,
                                        args.no_verify)
            except Exception as e:
                print e
                pass

    if args.json:
        with open(args.json, 'w') as f:
            json.dump(report, f)


if __name__ == "__main__":
    main()
