#!/usr/bin/env python3
"""Operator CLI for the Cybercab Forum.

Moderator access is assigned explicitly by the operator (see /guidelines) and
never granted automatically, so this is the only way to create a moderator and
the only way to recover an account when a password is lost.

Reads the same FORUM_DB environment variable as server.py.

Usage:
    python admin.py list
    python admin.py promote <username>
    python admin.py demote <username>
    python admin.py reset-password <username>
    python admin.py reset-password <username> --stdin

reset-password prompts for the new password, which requires a terminal. When
there is no terminal, such as a hosting shell or a scheduled job, pipe the
password in and pass --stdin instead:

    echo "the-new-password" | python admin.py reset-password alice --stdin

Promote your own account before opening registration, otherwise no one can
lock or remove anything.
"""
import getpass
import os
import sys

import server


def usage():
    print(__doc__.strip())
    return 2


def describe(row):
    return f'{row["name"]} (id {row["id"]})'


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        return usage()
    command = argv[0]
    if command not in ('list', 'promote', 'demote', 'reset-password'):
        print(f'error: unknown command {command!r}\n', file=sys.stderr)
        return usage()

    server.init()
    with server.connect() as connection:
        if command == 'list':
            rows = connection.execute(
                'SELECT users.*,'
                ' (SELECT count(*) FROM topics WHERE user_id=users.id) AS topics,'
                ' (SELECT count(*) FROM replies WHERE user_id=users.id) AS replies'
                ' FROM users ORDER BY users.id').fetchall()
            if not rows:
                print(f'No accounts yet in {server.DB}')
                return 0
            print(f'{"id":>4}  {"moderator":<9} {"topics":>6} {"replies":>7}  username')
            for row in rows:
                print(f'{row["id"]:>4}  {"yes" if row["admin"] else "-":<9}'
                      f' {row["topics"]:>6} {row["replies"]:>7}  {row["name"]}')
            return 0

        if len(argv) < 2:
            print(f'error: {command} needs a username', file=sys.stderr)
            return 2
        name = argv[1]
        row = connection.execute('SELECT * FROM users WHERE name=?', (name,)).fetchone()
        if not row:
            print(f'error: no account named {name!r}', file=sys.stderr)
            return 1

        if command == 'promote':
            if row['admin']:
                print(f'{describe(row)} is already a moderator.')
                return 0
            connection.execute('UPDATE users SET admin=1 WHERE id=?', (row['id'],))
            connection.commit()
            print(f'{describe(row)} is now a moderator.')
            return 0

        if command == 'demote':
            if not row['admin']:
                print(f'{describe(row)} is not a moderator.')
                return 0
            remaining = connection.execute(
                'SELECT count(*) FROM users WHERE admin=1').fetchone()[0]
            if remaining <= 1:
                print('error: refusing to remove the last moderator. '
                      'Promote another account first, or you will be locked out '
                      'of locking and deleting.', file=sys.stderr)
                return 1
            connection.execute('UPDATE users SET admin=0 WHERE id=?', (row['id'],))
            connection.commit()
            print(f'{describe(row)} is no longer a moderator.')
            return 0

        # reset-password
        if '--stdin' in argv[2:]:
            password = sys.stdin.readline().rstrip('\r\n')
        elif sys.stdin.isatty():
            password = getpass.getpass(f'New password for {name}: ')
            if password != getpass.getpass('Repeat password: '):
                print('error: passwords did not match.', file=sys.stderr)
                return 1
        else:
            # getpass reads the console directly on Windows, so without a
            # terminal it would block forever rather than fail. Refuse instead.
            print('error: no terminal available to prompt for a password.\n'
                  f'       Pipe it in instead: '
                  f'echo "the-new-password" | python admin.py reset-password {name} --stdin',
                  file=sys.stderr)
            return 1
        if not 12 <= len(password) <= 128:
            print('error: password must be 12-128 characters.', file=sys.stderr)
            return 1
        connection.execute('UPDATE users SET password=? WHERE id=?',
                           (server.password(password), row['id']))
        connection.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
        connection.commit()
        print(f'Password updated for {describe(row)}. '
              'All of their active sessions were signed out.')
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
