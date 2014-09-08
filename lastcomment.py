#!/usr/bin/env python

"""Print the last time a reviewer(bot) left a comment."""

import argparse
import datetime
import json

import requests


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Comment(object):
    date = None
    number = None
    subject = None
    now = None

    def __init__(self, date, number, subject):
        super(Comment, self).__init__()
        self.date = date
        self.number = number
        self.subject = subject
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


def last_comment(change, name):
    """Return most recent timestamp for comment by name."""
    last_date = None
    for message in change['messages']:
        if 'author' in message and message['author']['name'] == name:
            date = message['date']
            # https://review.openstack.org/Documentation/rest-api.html#timestamp
            # drop nanoseconds
            date = date.split('.')[0]
            date = datetime.datetime.strptime(date, TIME_FORMAT)
            if not last_date or date > last_date:
                last_date = date
    return last_date


def print_last_comments(name):
    # Include review messages in query
    query = ("https://review.openstack.org/changes/?q=reviewer:\"%s\"&"
             "o=MESSAGES" % (name))
    r = requests.get(query)
    changes = json.loads(r.text[4:])

    comments = []
    for change in changes:
        date = last_comment(change, name)
        comments.append(Comment(date, change['_number'],
                                change['subject']))

    COUNT = 5
    print "last %s comments from '%s'" % (COUNT, name)
    for i, comment in enumerate(sorted(comments,
                                       key=lambda comment: comment.date,
                                       reverse=True)[0:COUNT]):
        print "[%d] %s" % (i, comment)


def main():
    parser = argparse.ArgumentParser(description='list most recent comment by '
                                     'reviewer')
    parser.add_argument('-n', '--name',
                        default="Elastic Recheck",
                        help='unique gerrit name of the reviewer')
    # name = "VMware NSX CI"
    args = parser.parse_args()
    print_last_comments(args.name)


if __name__ == "__main__":
    main()
