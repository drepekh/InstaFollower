# -*- coding: utf-8 -*-

from InstaAPI import InstaAPI
from tkinter import *
from tkinter import ttk
from idlelib.WidgetRedirector import WidgetRedirector
import queue
from threading import Thread, Event
import sqlite3
from datetime import datetime
import random
import time
from configparser import ConfigParser, NoSectionError
import os
import pickle

DEBUG = True

if not DEBUG:
    sys.stderr = open('error.log', 'a')


class InstaAPIMod(InstaAPI):
    def __init__(self, login, password, log):
        InstaAPI.__init__(self, login, password)
        self.log = log

    def write_log(self, text):
        self.log.write_log(text)


class DigitEntry(Entry):
    def __init__(self, master, *args, **kwargs):
        def validator(text):
            try:
                int(text)
                return True
            except:
                return False

        vcmd = (master.register(validator), '%S')

        Entry.__init__(self, master, *args, **kwargs)
        self['validate'] = 'key'
        self['validatecommand'] = vcmd


class App:
    LOG = 0
    LOGIN_SUCCESSFUL = 1
    LOGIN_FAILED = 3
    FINISHED = 4
    STARTED = 5

    RADIO_ALL = 1
    RADIO_TAG = 2
    RADIO_USER = 3

    GET_USERS = 1
    FOLLOW = 2
    UNFOLLOW = 3

    db_path = 'db/users.db'
    q = queue.Queue()
    settings_default = {'follow_time_const': 20,
                        'follow_time_rand': 10,
                        'unfollow_time_const': 20,
                        'unfollow_time_rand': 10,
                        'get_users_time_const': 4,
                        'get_users_time_rand': 3,
                        'limit_day': 970}
    settings = dict(settings_default)

    class UserManager:
        def __init__(self, login_wid, pass_wid, login_but, logout_but):
            self.follower = None
            self.login_in = login_wid
            self.password = pass_wid
            self.login_but = login_but
            self.logout_but = logout_but

        @property
        def login_status(self):
            if self.follower is None:
                return False
            return self.follower.login_status

        @property
        def user_login(self):
            return self.follower.user_login

        def num_of_actions(self):
            conn = sqlite3.connect(App.db_path)
            cur = conn.cursor()
            st = int(datetime.utcnow().timestamp()) - 60 * 60 * 24
            cur.execute('SELECT COUNT(*) FROM "%s" '
                        'WHERE follow_date>?;' % self.follower.user_login,
                        (st,))
            count = cur.fetchone()[0]

            cur.execute('SELECT COUNT(*) FROM "%s" '
                        'WHERE unfollow_date>?;' % self.follower.user_login,
                        (st,))
            count += cur.fetchone()[0]
            cur.close()
            conn.close()
            return count

        def write_log(self, text):
            pass

    class QueueWidget(Toplevel):
        def __init__(self, master, log_func, *args, **kwargs):
            self.actions = []
            self.write_log = log_func
            self.current_task = None

            Toplevel.__init__(self, master, *args, **kwargs)
            self.title('Task queue')
            self.protocol('WM_DELETE_WINDOW', self.withdraw)

            Label(self, text='Done:').pack(anchor=W)
            self.frame_done = Frame(self)
            self.frame_done.pack(anchor=W)
            Label(self, text='In progress:').pack(anchor=W)
            self.frame_current = Frame(self)
            self.frame_current.pack(anchor=W)
            Label(self, text='In queue:').pack(anchor=W)
            self.frame_queue = Frame(self)
            self.frame_queue.pack(anchor=W)

        def create_frame(self, master, name, opts, can_be_deleted=True):
            frame = Frame(master)
            frame.pack(anchor=W)
            if can_be_deleted:
                Button(frame, text='X', command=lambda: self.delete_item(frame)).pack(side=LEFT)
            Label(frame, text=name).pack(side=LEFT)
            Label(frame, text='User: ' + opts['user'].user_login).pack(side=LEFT, padx=5)
            for i in opts:
                if i != 'user':
                    Label(frame, text=i + ': ' + str(opts[i])).pack(side=LEFT, padx=5)
            return frame

        def add_item(self, name, func, opts):
            frame = self.create_frame(self.frame_queue, name, opts)
            self.actions.append((name, func, opts, frame))

        def delete_item(self, frame):
            for i in range(len(self.actions)):
                if self.actions[i][3] == frame:
                    frame.pack_forget()
                    frame.destroy()
                    del self.actions[i]
                    break

        def start_next_action(self):
            for wid in self.frame_current.winfo_children():
                wid.pack_forget()
                wid.destroy()
                self.create_frame(self.frame_done,
                                  self.current_task[0],
                                  self.current_task[2],
                                  False)
            if len(self.actions) > 0:
                self.current_task = self.actions[0]
                del self.actions[0]
                self.current_task[3].pack_forget()
                self.current_task[3].destroy()
                self.create_frame(self.frame_current,
                                  self.current_task[0],
                                  self.current_task[2],
                                  False)
                self.write_log('Starting next task: ' + self.current_task[0])
                thread = Thread(target=self.current_task[1],
                                kwargs=self.current_task[2])
                thread.start()
                return True
            return False

    def __init__(self, master):
        self.master = master
        self.top = False
        self.users = {}
        self.read_config()
        self.pause = Event()
        self.pause.set()
        master.protocol('WM_DELETE_WINDOW', self.on_close)
        master.title('InstaFollower')

        tabs = ttk.Notebook(master)
        tab1 = ttk.Frame(tabs)
        tab2 = ttk.Frame(tabs)
        tab3 = ttk.Frame(tabs)

        # -----Tab 1-----
        def create_input_frame(master):
            log_input_frame = Frame(master)
            log_input_frame.pack()
            log_input_frame_left = Frame(log_input_frame)
            log_input_frame_left.pack(side=LEFT)
            log_input_frame_right = Frame(log_input_frame)
            log_input_frame_right.pack(side=LEFT)
            log_buttons_frame = Frame(log_input_frame)
            log_buttons_frame.pack(padx=10)

            Label(log_input_frame_left, text="Login:").pack(anchor=E)
            login_in = Entry(log_input_frame_right)
            login_in.pack()

            Label(log_input_frame_left, text='Password:').pack(anchor=E)
            password = Entry(log_input_frame_right, show='*')
            password.pack()

            login_but = Button(log_buttons_frame, text='Login')
            login_but.pack(side=LEFT)
            logout_but = Button(log_buttons_frame, text='Logout', state=DISABLED)
            logout_but.pack(side=LEFT)

            user = self.UserManager(login_in, password, login_but, logout_but)

            login_but['command'] = lambda: self.login_click(user)
            logout_but['command'] = lambda: self.logout(user)
            return user

        if os.path.exists('session'):
            with open('session', 'rb') as file:
                ses = pickle.load(file)
                for user in ses:
                    us = create_input_frame(tab1)
                    us.login_in.insert(0, user)
                    self.enable(us.logout_but)
                    self.disable(us.login_but,
                                 us.login_in,
                                 us.password)
                    us.follower = InstaAPIMod(user, '', self)
                    us.follower.s.cookies = ses[user][0]
                    us.follower.s.headers = ses[user][1]
                    us.follower.csrftoken = us.follower.s.cookies.get('csrftoken', domain='www.instagram.com')
                    us.follower.login_status = True
                    self.users[user] = us

        if len(self.users) == 0:
            create_input_frame(tab1)

        add_user_but = Button(tab1, text='Add user')
        add_user_but.pack()

        def add_user_input():
            add_user_but.pack_forget()
            create_input_frame(tab1)
            add_user_but.pack()

        add_user_but['command'] = add_user_input

        # -----Tab 2-----
        self.selected_user = StringVar()
        self.user_box = ttk.Combobox(tab2, state='readonly', textvariable=self.selected_user)
        self.user_box.pack()
        self.user_box['values'] = list(self.users.keys())

        frame_interface = Frame(tab2)
        frame_interface.pack()

        frame_labels = Frame(frame_interface)
        frame_labels.pack(side=LEFT)
        frame_entries = Frame(frame_interface)
        frame_entries.pack(side=LEFT)

        Label(frame_labels, text="User:").pack(anchor=E)
        self.uid = Entry(frame_entries)
        self.uid.pack()

        Label(frame_labels, text='Amount:').pack(anchor=E)
        self.amount = DigitEntry(frame_entries)
        self.amount.pack()

        Label(frame_labels, text='Min followers:').pack(anchor=E)
        self.min_followers = DigitEntry(frame_entries)
        self.min_followers.pack()

        Label(frame_labels, text='Min posts:').pack(anchor=E)
        self.min_posts = DigitEntry(frame_entries)
        self.min_posts.pack()

        self.frame_options = Frame(frame_interface)
        self.frame_options.pack(side=LEFT, padx=10)

        self.random = IntVar()
        self.random.set(1)
        Checkbutton(self.frame_options, text='Random', variable=self.random)\
            .pack(anchor=W)

        self.follow_opt = IntVar()
        self.follow_opt.set(self.RADIO_ALL)
        Radiobutton(self.frame_options, text='All', variable=self.follow_opt, value=self.RADIO_ALL)\
            .pack(anchor=W)

        frame_tag = Frame(self.frame_options)
        frame_tag.pack()
        Radiobutton(frame_tag, text='By tags', variable=self.follow_opt, value=self.RADIO_TAG)\
            .pack(side=LEFT)
        self.tags = Entry(frame_tag)
        self.tags.pack(side=LEFT)

        Radiobutton(self.frame_options, text='By user', variable=self.follow_opt, value=self.RADIO_USER)\
            .pack(anchor=W)

        frame_buttons = Frame(tab2)
        frame_buttons.pack()
        self.get_users_but = Button(frame_buttons, text='Get users', command=self.get_followers_click)
        self.get_users_but.pack(side=LEFT)
        self.follow_but = Button(frame_buttons, text='Follow', command=self.follow_click)
        self.follow_but.pack(side=LEFT)
        self.unfollow_but = Button(frame_buttons, text='Unfollow', command=self.unfollow_click)
        self.unfollow_but.pack(side=LEFT)
        tags_but = Button(frame_buttons, text='Manage tags', command=self.tags_editor)
        tags_but.pack(side=LEFT, padx=5)
        queue_but = Button(frame_buttons, text='Queue')
        queue_but.pack(side=LEFT)
        self.start_but = Button(frame_buttons, text='Start', command=lambda: self.q.put((self.STARTED,)))
        self.start_but.pack(side=LEFT)

        # -----Tab 3-----
        tree = ttk.Treeview(tab3, height=6, columns=('value',))
        tree.pack(side=LEFT)
        tree.column('value', width=100)
        tree.heading('value', text='Value')
        tree.heading('#0', text='Name')
        for name in sorted(self.settings):
            tree.insert('', 'end', name, text=name, values=(self.settings[name],))

        frame_edit = Frame(tab3)
        frame_edit.pack(side=LEFT)
        Label(frame_edit, text='New value:').pack()
        new_value = DigitEntry(frame_edit)
        new_value.pack()

        def set_setting():
            selected = tree.selection()
            value = new_value.get()
            if selected and value:
                value = int(value)
                self.settings[selected[0]] = value
                tree.item(selected[0], values=(value,))
                self.save_config()

        def reset_setting():
            selected = tree.selection()
            if selected:
                self.settings[selected[0]] = self.settings_default[selected[0]]
                tree.item(selected[0], values=(self.settings_default[selected[0]],))
                self.save_config()

        frame_set_but = Frame(frame_edit)
        frame_set_but.pack(pady=5)
        Button(frame_set_but, text='Set', command=set_setting).pack(side=LEFT)
        Button(frame_set_but, text='Reset', command=reset_setting).pack(side=LEFT, padx=10)

        tabs.add(tab1, text='Login')
        tabs.add(tab2, text='Following options')
        tabs.add(tab3, text='Settings')
        tabs.pack()

        # -----Logging widget-----
        frame_logging = Frame(master)
        frame_logging.pack()
        self.log = Text(frame_logging, wrap=WORD)
        self.log.redirector = WidgetRedirector(self.log)
        self.log.insert = self.log.redirector.register("insert", lambda *args, **kw: "break")
        self.log.delete = self.log.redirector.register("delete", lambda *args, **kw: "break")
        self.log.pack(side=LEFT)

        scroll = Scrollbar(frame_logging, command=self.log.yview)
        scroll.pack(side=RIGHT, fill=Y)
        self.log.config(yscrollcommand=scroll.set)

        # -----Queue window-----
        self.queue_window = App.QueueWidget(master, self.write_log)
        queue_but['command'] = self.queue_window.deiconify
        self.queue_window.withdraw()

        if not os.path.exists('db/'):
            os.mkdir('db')

        self.conn = sqlite3.connect(self.db_path)
        cur = self.conn.cursor()
        cur.execute('CREATE TABLE IF NOT EXISTS users ('
                    'id INTEGER NOT NULL,'
                    'username TEXT NOT NULL,'
                    'full_name TEXT,'
                    'biography TEXT,'
                    'is_verified INTEGER,'
                    'is_private INTEGER,'
                    'connected_fb_page TEXT,'
                    'external_url TEXT,'
                    'follows INTEGER,'
                    'followed_by INTEGER,'
                    'media INTEGER,'
                    'last_checked INTEGER,'
                    'PRIMARY KEY(id));')

        cur.execute('CREATE TABLE IF NOT EXISTS followers ('
                    'uid INTEGER NOT NULL,'
                    'follows INTEGER NOT NULL,'
                    'PRIMARY KEY(uid, follows));')

        cur.execute('CREATE TABLE IF NOT EXISTS tags ('
                    'uid INTEGER NOT NULL,'
                    'tag TEXT,'
                    'PRIMARY KEY(uid, tag));')
        self.conn.commit()

        self.log_update()

    def on_close(self):
        res = {}
        for name in self.users:
            res[name] = (self.users[name].follower.s.cookies,
                         self.users[name].follower.s.headers)

        with open('session', 'wb') as file:
            pickle.dump(res, file)
        self.master.destroy()

    def disable(self, *args):
        for wid in args:
            if isinstance(wid, Frame):
                self.disable(*wid.winfo_children())
            else:
                wid['state'] = 'disabled'

    def enable(self, *args):
        for wid in args:
            if isinstance(wid, Frame):
                self.enable(*wid.winfo_children())
            else:
                wid['state'] = 'normal'

    def read_config(self):
        config = ConfigParser()
        config.read('settings.cfg')
        try:
            for name in config.options('config'):
                self.settings[name] = config.getint('config', name)
        except NoSectionError:
            pass

    def save_config(self):
        config = ConfigParser()
        config.add_section('config')
        for name in self.settings:
            config.set('config', name, str(self.settings[name]))

        with open('settings.cfg', 'w') as file:
            config.write(file)

    def tags_editor(self):
        if not self.top:
            self.top = True
            top = Toplevel(self.master)
            top.title('Tags')

            def on_close():
                self.top = False
                top.destroy()

            top.protocol('WM_DELETE_WINDOW', on_close)
            cur = self.conn.cursor()
            cur.execute('SELECT '
                        'DISTINCT(followers.follows) AS id,'
                        'users.username AS username,'
                        'tags.tag AS tag '
                        'FROM followers '
                        'JOIN users on followers.follows=users.id '
                        'LEFT JOIN tags on id=tags.uid '
                        'ORDER BY id;')
            tags = {}
            for row in cur:
                if row[0] in tags:
                    tags[row[0]]['tags'].append(row[2])
                else:
                    if row[2] is None:
                        tags[row[0]] = {'name': row[1], 'tags': []}
                    else:
                        tags[row[0]] = {'name': row[1], 'tags': [row[2]]}
            main = Frame(top)
            main.pack(fill=X)
            left = Frame(main)
            left.pack(side=LEFT)
            right = Frame(main)
            right.pack(side=LEFT, expand=True, fill=X)
            entries = {}
            for user in tags:
                Label(left, text=tags[user]['name']).pack(anchor=E)
                entries[user] = Entry(right)
                entries[user].pack(fill=X, expand=True)
                entries[user].insert(0, ' '.join(tags[user]['tags']))

            def save_changes():
                cur.execute('DELETE FROM tags;')
                for user in tags:
                    tgs = entries[user].get().strip().split()
                    for tag in tgs:
                        try:
                            cur.execute('INSERT INTO tags '
                                        'VALUES(?,?);', (user, tag))
                        except sqlite3.IntegrityError:
                            pass
                        except Exception as e:
                            self.write_log('Exception while saving tags')
                            self.write_log(str(e))
                self.conn.commit()

            Button(top, text='Save', command=save_changes).pack()

    def login_click(self, user):
        l = user.login_in.get()
        p = user.password.get()
        if l in self.users:
            self.write_log('User with this username already logged in')
            return
        if l != '' and p != '':
            self.disable(user.login_but,
                         user.login_in,
                         user.password)
            user.follower = InstaAPIMod(l, p, self)
            thread = Thread(target=self.login, args=(user,))
            thread.start()
        else:
            self.write_log('Invalid input')

    def login(self, user):
        try:
            user.follower.login()
        except Exception as e:
            self.write_log('Exception on login. Try again')
            print(str(e), file=sys.stderr)
            self.q.put((self.LOGIN_FAILED, user))
            return
        if user.follower.login_status:
            conn = sqlite3.connect(self.db_path)
            cur = conn.cursor()
            cur.execute('''CREATE TABLE IF NOT EXISTS "%s" (
                           uid INTEGER NOT NULL,
                           follow_date INTEGER NOT NULL,
                           unfollow_date INTEGER NOT NULL,
                           PRIMARY KEY(uid));''' % user.follower.user_login)
            conn.commit()
            conn.close()
            self.q.put((self.LOGIN_SUCCESSFUL, user))
        else:
            self.q.put((self.LOGIN_FAILED, user))

    def logout(self, user):
        user.follower.logout()
        if user.follower.login_status:
            pass
        else:
            self.disable(user.logout_but)
            self.enable(user.login_but,
                        user.login_in,
                        user.password)
            del self.users[user.follower.user_login]
            ls = list(self.user_box['values'])
            ls.remove(user.follower.user_login)
            self.user_box['values'] = ls
            if len(ls) == 0 or self.selected_user.get() == user.follower.user_login:
                self.selected_user.set('')

    @staticmethod
    def insert_user(cur, user):
        ts = int(datetime.utcnow().timestamp())
        cur.execute('INSERT OR REPLACE INTO users '
                    'VALUES(?,?,?,?,?,?,?,?,?,?,?,?);', (user['id'],
                                                         user['username'],
                                                         user['full_name'],
                                                         user['biography'],
                                                         user['is_verified'],
                                                         user['is_private'],
                                                         user['connected_fb_page'],
                                                         user['external_url'],
                                                         user['follows']['count'],
                                                         user['followed_by']['count'],
                                                         user['media']['count'],
                                                         ts))
        return cur

    def get_user_from_input(self, user):
        uid = self.uid.get().strip()
        try:
            uid = int(uid)
            us = user.follower.get_user(id=uid)
        except:
            us = user.follower.get_user(username=uid)

        if us is None:
            return None
        self.insert_user(self.conn.cursor(), us)
        self.conn.commit()
        return us['id']

    @staticmethod
    def get_int_from_input(wid):
        res = wid.get().strip()
        try:
            if res == '':
                return 0
            else:
                res = int(res)
                return res
        except:
            return None

    def get_followers_click(self):
        us = self.selected_user.get()
        if us is None or us == '':
            self.write_log('Account not selected')
            return
        uid = self.get_user_from_input(self.users[us])
        amount = self.get_int_from_input(self.amount)
        if None in [uid, amount]:
            self.write_log('Invalid input')
            return
        opts = {'uid': uid,
                'amount': amount,
                'user': self.users[us]}

        self.queue_window.add_item('Get users', self.get_followers, opts)

    def get_followers(self, user, uid, amount):
        self.write_log('Getting followers from ' + str(uid))
        end_cursor = ''
        total = 0
        new = 0
        conn = sqlite3.connect(self.db_path)
        while True:
            res = user.follower.get_next_followers(uid, end_cursor)
            if res is None:
                break
            fols = res[0]
            end_cursor = res[1]
            cur = conn.cursor()
            total += len(fols)
            for i in fols:
                try:
                    cur = self.insert_user(cur, i)

                    cur.execute('INSERT INTO followers '
                                'VALUES(?,?);', (i['id'], uid))
                    new += 1
                except sqlite3.IntegrityError:
                    pass
                except Exception as e:
                    self.write_log('Unexpected exception while getting followers')
                    self.write_log(str(e))
            conn.commit()
            cur.close()
            if end_cursor == '' or (amount != 0 and total >= amount):
                break
            self.write_log('Progress: ' + str(total))
            time.sleep(self.settings['get_users_time_const'] +
                       self.settings['get_users_time_rand'] * random.random())
            self.pause.wait()
        conn.close()

        self.write_log('Users got: ' + str(total))
        self.write_log('New users: ' + str(new))
        self.q.put((self.FINISHED,))

    def follow_click(self):
        us = self.selected_user.get()
        if us is None or us == '':
            self.write_log('Account not selected')
            return
        if self.follow_opt.get() == self.RADIO_USER:
            uid = self.get_user_from_input(self.users[us])
            if uid is None:
                self.write_log('Invalid input. User was not found')
                return
        else:
            uid = None
        amount = self.get_int_from_input(self.amount)
        min_fol = self.get_int_from_input(self.min_followers)
        min_posts = self.get_int_from_input(self.min_posts)
        if None in [amount, min_fol, min_posts, us]:
            self.write_log('Invalid input')
            return
        opts = {'uid': uid,
                'amount': amount,
                'min_fol': min_fol,
                'min_posts': min_posts,
                'radio': self.follow_opt.get(),
                'rand': self.random.get(),
                'tags': self.tags.get().strip().split(),
                'user': self.users[us]}

        self.queue_window.add_item('Follow', self.follow, opts)

    def follow(self, user, amount, radio, rand, uid=None, tags=None, min_fol=0, min_posts=0):
        conn = sqlite3.connect(self.db_path)
        if amount == 0:
            amount = 970
        num = 0
        str_tags = ''
        if radio == self.RADIO_TAG:
            for i in range(len(tags)):
                tags[i] = 'tag="%s"' % tags[i]
            str_tags = ' or '.join(tags)

        while num < amount and user.num_of_actions() < self.settings['limit_day']:
            cur = conn.cursor()
            cur.execute('SELECT '
                        'DISTINCT (users.id),'
                        'users.username '
                        'FROM users '
                        'JOIN followers ON followers.uid=users.id '
                        'LEFT JOIN "%s" ON users.id="%s".uid '
                        'WHERE '
                        '%s '
                        '%s '
                        '"%s".uid IS NULL AND '
                        'users.followed_by>%s AND '
                        'users.media>%s '
                        '%s '
                        'LIMIT 1;' % (user.follower.user_login,
                                      user.follower.user_login,
                                      ('followers.follows=%s AND' % uid) if radio == self.RADIO_USER else '',
                                      ('followers.follows IN '
                                       '(SELECT DISTINCT(uid) '
                                       'FROM tags WHERE %s) AND' % str_tags) if radio == self.RADIO_TAG else '',
                                      user.follower.user_login,
                                      min_fol,
                                      min_posts,
                                      'ORDER BY RANDOM()' if rand else ''))
            us = cur.fetchone()
            if us is None:
                self.write_log('No more users that match conditions in DB')
                break
            f = user.follower.follow(us[0])
            if f:
                cur.execute('INSERT INTO "%s"'
                            'VALUES(?,?,?)' % user.follower.user_login,
                            (us[0], int(datetime.utcnow().timestamp()), 0))
                conn.commit()
                num += 1
                self.write_log('Followed: %s #%i' % (us[1], user.follower.follow_counter))
            cur.close()
            if num >= amount:
                break
            if user.num_of_actions() >= self.settings['limit_day']:
                self.write_log('Limit is reached')
                break
            time.sleep(self.settings['follow_time_const'] +
                       self.settings['follow_time_rand'] * random.random())
            self.pause.wait()
        conn.close()
        self.write_log('Following finished')
        self.q.put((self.FINISHED,))

    def unfollow_click(self):
        us = self.selected_user.get()
        if us is None or us == '':
            self.write_log('Account not selected')
            return
        if self.follow_opt.get() == self.RADIO_USER:
            uid = self.get_user_from_input(self.users[us])
            if uid is None:
                self.write_log('Invalid input. User was not found')
                return
        else:
            uid = None
        amount = self.get_int_from_input(self.amount)
        if amount is None:
            self.write_log('Invalid input')
            return
        opts = {'uid': uid,
                'amount': amount,
                'radio': self.follow_opt.get(),
                'tags': self.tags.get().strip().split(),
                'user': self.users[us]}

        self.queue_window.add_item('Unfollow', self.unfollow, opts)

    def unfollow(self, user, amount, radio, uid=None, tags=None):
        conn = sqlite3.connect(self.db_path)
        if amount == 0:
            amount = 970
        num = 0
        str_tags = ''
        if radio == self.RADIO_TAG:
            for i in range(len(tags)):
                tags[i] = 'tag="%s"' % tags[i]
            str_tags = ' or '.join(tags)

        while num < amount and user.num_of_actions() < self.settings['limit_day']:
            cur = conn.cursor()

            cur.execute('SELECT '
                        'DISTINCT(t.uid),'
                        'users.username '
                        'FROM "%s" AS t '
                        'JOIN users ON t.uid=users.id '
                        'JOIN followers ON t.uid=followers.uid '
                        'WHERE '
                        '%s '
                        '%s '
                        'unfollow_date=0 '
                        'ORDER BY follow_date '
                        'LIMIT 1;' % (user.follower.user_login,
                                      ('followers.follows=%s AND' % uid) if radio == self.RADIO_USER else '',
                                      ('followers.follows IN '
                                       '(SELECT DISTINCT(uid)'
                                       'FROM tags WHERE %s) AND' % str_tags) if radio == self.RADIO_TAG else ''))
            us = cur.fetchone()
            if us is None:
                self.write_log('No more users that match conditions')
                break
            f = user.follower.unfollow(us[0])
            if f:
                cur.execute('UPDATE "%s" '
                            'SET unfollow_date=? '
                            'WHERE uid=?;' % user.follower.user_login,
                            (int(datetime.utcnow().timestamp()), us[0]))

                conn.commit()
                num += 1
                self.write_log("Unfollow: %s #%i" % (us[1], user.follower.unfollow_counter))
            cur.close()
            if num >= amount:
                break
            if user.num_of_actions() >= self.settings['limit_day']:
                self.write_log('Limit is reached')
                break
            time.sleep(self.settings['unfollow_time_const'] +
                       self.settings['unfollow_time_rand'] * random.random())
            self.pause.wait()
        conn.close()
        self.write_log('Unfollowing finished')
        self.q.put((self.FINISHED,))

    def write_log(self, text):
        self.q.put((self.LOG, text))

    def log_update(self):
        while not self.q.empty():
            ev = self.q.get()

            if ev[0] == self.LOG:
                self.log.insert(END, datetime.now().strftime('%H:%M:%S ') + str(ev[1]) + '\n')

            elif ev[0] == self.LOGIN_SUCCESSFUL:
                self.users[ev[1].follower.user_login] = ev[1]
                self.enable(ev[1].logout_but)
                ls = list(self.user_box['values'])
                ls.append(ev[1].follower.user_login)
                self.user_box['values'] = ls

            elif ev[0] == self.LOGIN_FAILED:
                self.enable(ev[1].login_but,
                            ev[1].login_in,
                            ev[1].password)

            elif ev[0] == self.FINISHED:
                if not self.queue_window.start_next_action():
                    for us in self.users:
                        self.enable(self.users[us].logout_but)
                    self.enable(self.start_but)
                    self.write_log('No more tasks in queue')

            elif ev[0] == self.STARTED:
                if self.queue_window.start_next_action():
                    for us in self.users:
                        self.disable(self.users[us].logout_but)
                    self.disable(self.start_but)
                else:
                    self.write_log('Queue is empty')

        self.log.after(100, self.log_update)

root = Tk()
app = App(root)
root.mainloop()