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
    python admin.py create-user <username> [--stdin]
    python admin.py reset-password <username> [--stdin]
    python admin.py delete-user <username> [--force]

Passwords are never taken as command-line arguments, because arguments are
visible to other processes and land in shell history. The commands that need
one prompt for it, which needs a terminal. Where there is no terminal, such as
a hosting shell or a one-off job, pipe the password in and pass --stdin:

    echo "the-new-password" | python admin.py create-user alice --stdin
    echo "the-new-password" | python admin.py reset-password alice --stdin

create-user lets you add an account while registration is closed, which is how
the operator's own account should be made.

Promote your own account before opening registration, otherwise no one can
lock or remove anything. To run this against a deployed service, see the
Render Shell, or the one-off job examples in the README.
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


def read_password(name, argv, command):
    """Read a new password from the terminal, or from stdin with --stdin."""
    if '--stdin' in argv:
        return sys.stdin.readline().rstrip('\r\n')
    if sys.stdin.isatty():
        first = getpass.getpass(f'New password for {name}: ')
        if first != getpass.getpass('Repeat password: '):
            print('error: passwords did not match.', file=sys.stderr)
            return None
        return first
    # getpass reads the console directly on Windows, so without a terminal it
    # would block forever rather than fail fast. Refuse instead.
    print('error: no terminal available to prompt for a password.\n'
          f'       Pipe it in instead: echo "the-new-password" | '
          f'python admin.py {command} {name} --stdin', file=sys.stderr)
    return None


def check_password(password):
    if password is None:
        return False
    if not 12 <= len(password) <= 128:
        print('error: password must be 12-128 characters.', file=sys.stderr)
        return False
    return True


def main(argv):
    if not argv or argv[0] in ('-h', '--help', 'help'):
        return usage()
    command = argv[0]
    commands = ('list', 'promote', 'demote', 'create-user', 'reset-password',
                'delete-user')
    if command not in commands:
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

        if command == 'create-user':
            if row:
                print(f'error: {name!r} already exists.', file=sys.stderr)
                return 1
            if not 3 <= len(name) <= 30 or not all(
                    c.isascii() and (c.isalnum() or c == '_') for c in name):
                print('error: username must be 3-30 characters, letters, '
                      'numbers or underscores.', file=sys.stderr)
                return 1
            password = read_password(name, argv, command)
            if not check_password(password):
                return 1
            connection.execute(
                'INSERT INTO users(name,password,admin) VALUES(?,?,0)',
                (name, server.password(password)))
            connection.commit()
            print(f'Created {name}. It is an ordinary member; the first account '
                  'is never made a moderator automatically. Run '
                  f'"admin.py promote {name}" to grant that.')
            return 0

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

        if command == 'reset-password':
            password = read_password(name, argv, command)
            if not check_password(password):
                return 1
            connection.execute('UPDATE users SET password=? WHERE id=?',
                               (server.password(password), row['id']))
            connection.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
            connection.commit()
            print(f'Password updated for {describe(row)}. '
                  'All of their active sessions were signed out.')
            return 0

        # delete-user
        topics = connection.execute(
            'SELECT count(*) FROM topics WHERE user_id=?', (row['id'],)).fetchone()[0]
        replies = connection.execute(
            'SELECT count(*) FROM replies WHERE user_id=?', (row['id'],)).fetchone()[0]
        topics_word = 'topic' if topics == 1 else 'topics'
        replies_word = 'reply' if replies == 1 else 'replies'
        if (topics or replies) and '--force' not in argv[2:]:
            print(f'error: {name} has {topics} {topics_word} and {replies} '
                  f'{replies_word}. Deleting the account would remove them, '
                  'along with any replies other people left on their topics. '
                  'Re-run with --force if that is intended.', file=sys.stderr)
            return 1
        if topics or replies:
            connection.execute('DELETE FROM topics WHERE user_id=?', (row['id'],))
            connection.execute('DELETE FROM replies WHERE user_id=?', (row['id'],))
        connection.execute('DELETE FROM sessions WHERE user_id=?', (row['id'],))
        connection.execute('DELETE FROM users WHERE id=?', (row['id'],))
        connection.commit()
        print(f'Deleted {name}, along with {topics} {topics_word} '
              f'and {replies} {replies_word}.')
        return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1:]))
