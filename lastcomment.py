#!/usr/bin/env python

"""Print the last time a reviewer(bot) left a comment."""

import argparse
import copy
import json
import time

import requests


TIME_FORMAT = "%Y-%m-%d %H:%M:%S"


class Comment(object):
    date = None
    change_id = None
    subject = None

    def __init__(self, date, change_id, subject):
        super(Comment, self).__init__()
        self.date = date
        self.change_id = change_id
        self.subject = subject

    def __str__(self):
        return ("%s '%s' https://review.openstack.org/#q,%s,n,z" % (
            time.strftime(TIME_FORMAT, self.date),
            self.subject, self.change_id))

    def __le__(self, other):
        # self < other
        return self.date < other.date


def main():
    parser = argparse.ArgumentParser(description='list most recent comment by '
                                     'reviewer')
    parser.add_argument('-n', '--name',
                        default="Elastic Recheck",
                        help='unique gerrit name of the reviewer')
    # name = "VMware NSX CI"
    args = parser.parse_args()
    # Include review messages in query
    query = ("https://review.openstack.org/changes/?q=reviewer:\"%s\"&"
             "o=MESSAGES" % (args.name))
    r = requests.get(query)
    changes = json.loads(r.text[4:])

    comment = None
    for change in changes:
        date = last_comment(change, args.name)
        current_comment = Comment(date, change['change_id'],
                                  change['subject'])
        if not comment or comment < current_comment:
            comment = copy.copy(current_comment)
    print "last comment from '%s'" % args.name
    print comment


def last_comment(change, name):
    """Return most recent timestamp for comment by name."""
    last_date = None
    for message in change['messages']:
        if 'author' in message and message['author']['name'] == name:
            date = message['date']
            # https://review.openstack.org/Documentation/rest-api.html#timestamp
            # drop nanoseconds
            date = date.split('.')[0]
            date = time.strptime(date, TIME_FORMAT)
            if date > last_date:
                last_date = date
    return last_date


if __name__ == "__main__":
    main()
