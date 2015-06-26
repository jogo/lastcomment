#!/usr/bin/env python

"""Print the last time a reviewer(bot) left a comment."""

import argparse
import collections
import datetime
import json
import sys

import requests


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Comment(object):
    date = None
    number = None
    subject = None
    now = None

    def __init__(self, date, number, subject, message):
        super(Comment, self).__init__()
        self.date = date
        self.number = number
        self.subject = subject
        self.message = message
        self.now = datetime.datetime.utcnow().replace(microsecond=0)

    def __str__(self):
        return ("%s (%s old) https://review.openstack.org/%s '%s' " % (
            self.date.strftime(TIME_FORMAT),
            (self.now - self.date),
            self.number, self.subject))

    def __le__(self, other):
        # self < other
        return self.date < other.date

    def __repr__(self):
        # for sorting
        return repr((self.date, self.number))


def get_comments(change, name):
    """Generator that returns all comments by name on a given change."""
    body = None
    for message in change['messages']:
        if 'author' in message and message['author']['name'] == name:
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


def print_last_comments(name, count, print_message, project, votes):
    success = collections.defaultdict(int)
    failure = collections.defaultdict(int)

    # Include review messages in query
    search = "reviewer:\"%s\"" % name
    if project:
        search = search + (" AND project:\"%s\"" % project)
    query = ("https://review.openstack.org/changes/?q=%s&"
             "o=MESSAGES" % search)
    r = requests.get(query)
    try:
        changes = json.loads(r.text[4:])
    except ValueError:
        print "query: '%s' failed with:\n%s" % (query, r.text)
        sys.exit(1)

    comments = []
    for change in changes:
        for date, message in get_comments(change, name):
            if date is None:
                # no comments from reviewer yet. This can happen since
                # 'Uploaded patch set X.' is considered a comment.
                continue
            comments.append(Comment(date, change['_number'],
                                    change['subject'], message))

    message = "last %s comments from '%s'" % (count, name)
    if project:
        message += " on project '%s'" % project
    print message
    # sort by time
    for i, comment in enumerate(sorted(comments,
                                       key=lambda comment: comment.date,
                                       reverse=True)[0:count]):
        print "[%d] %s" % (i, comment)
        if print_message:
            print "message: \"%s\"" % comment.message
            print
        if votes:
            for line in comment.message.splitlines():
                if line.startswith("* ") or line.startswith("- "):
                    job = line.split(' ')[1]
                    if " : SUCCESS" in line:
                        print line
                        success[job] += 1
                    if " : FAILURE" in line:
                        print line
                        failure[job] += 1

    if votes:
        print "success count by job:"
        for job in success.iterkeys():
            print "* %s: %d" % (job, success[job])
        print "failure count by job:"
        for job in failure.iterkeys():
            print "* %s: %d" % (job, failure[job])


def main():
    parser = argparse.ArgumentParser(description='list most recent comment by '
                                     'reviewer')
    parser.add_argument('-n', '--name',
                        default="Elastic Recheck",
                        help='unique gerrit name of the reviewer')
    parser.add_argument('-c', '--count',
                        default=10,
                        help='unique gerrit name of the reviewer')
    parser.add_argument('-f', '--file',
                        default=None,
                        help='file containing list of names to search on, '
                             'single name per line (overwrites -n)')
    parser.add_argument('-m', '--message',
                        action='store_true',
                        help='print comment message')
    parser.add_argument('-v', '--votes',
                        action='store_true',
                        help=('Look in comments for CI Jobs and detect '
                              'SUCCESS/FAILURE'))
    parser.add_argument('-p', '--project',
                        help='only list hits for a specific project')

    args = parser.parse_args()
    names = [args.name]
    if args.file:
        with open(args.file) as f:
            names = [l.rstrip() for l in f]

    for n in names:
        print 'Checking name: %s' % n
        try:
            print_last_comments(n, int(args.count), args.message,
                                args.project, args.votes)
        except Exception as e:
            print e
            pass


if __name__ == "__main__":
    main()
