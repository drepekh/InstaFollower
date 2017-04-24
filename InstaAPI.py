# -*- coding: utf-8 -*-

import requests
import time
import random
import json


class InstaAPI:

    url = 'https://www.instagram.com/'
    url_user_info = 'https://www.instagram.com/%s/?__a=1'
    url_login = 'https://www.instagram.com/accounts/login/ajax/'
    url_logout = 'https://www.instagram.com/accounts/logout/'
    url_follow = 'https://www.instagram.com/web/friendships/%s/follow/'
    url_unfollow = 'https://www.instagram.com/web/friendships/%s/unfollow/'
    url_followers = 'https://www.instagram.com/query/'

    user_agent = ("Mozilla/5.0 (Windows NT 10.0; WOW64) AppleWebKit/537.36 "
                  "(KHTML, like Gecko) Chrome/48.0.2564.103 Safari/537.36")

    nodes = 'id,' \
            'username,' \
            'full_name,' \
            'biography,' \
            'requested_by_viewer,' \
            'has_requested_viewer,' \
            'followed_by_viewer,' \
            'follows_viewer,' \
            'blocked_by_viewer,' \
            'has_blocked_viewer,' \
            'is_verified,' \
            'is_private,' \
            'connected_fb_page,' \
            'external_url,' \
            'follows {count},' \
            'followed_by {count},' \
            'media {count}'

    followers_first = ("ig_user(%s) {"
                       "  followed_by.first(20) {"
                       "    count,"
                       "    page_info {"
                       "      end_cursor,"
                       "      has_next_page"
                       "    },"
                       "    nodes {"
                       "      %s"
                       "    }"
                       "  }"
                       "}") % ('%s', nodes)
    followers_after = ("ig_user(%s) {"
                       "  followed_by.after(%s, 20) {"
                       "    count,"
                       "    page_info {"
                       "      end_cursor,"
                       "      has_next_page"
                       "    },"
                       "    nodes {"
                       "      %s"
                       "    }"
                       "  }"
                       "}") % ('%s', '%s', nodes)
    user_info = ('ig_user(%s) {'
                 '  %s'
                 '}') % ('%s', nodes)

    follow_counter = 0
    unfollow_counter = 0

    def __init__(self, login, password):
        self.user_login = login
        self.user_password = password
        self.login_status = False
        self.s = requests.Session()

    def login(self):
        self.write_log('Trying to login as %s...' % self.user_login)
        self.s.cookies.update({
            'sessionid': '',
            'mid': '',
            'ig_pr': '1',
            'ig_vw': '1920',
            'csrftoken': '',
            's_network': '',
            'ds_user_id': ''
        })
        login_post = {
            'username': self.user_login,
            'password': self.user_password
        }
        self.s.headers.update({
            'Accept-Encoding': 'gzip, deflate',
            'Accept-Language': 'ru-RU,ru;q=0.8,en-US;q=0.6,en;q=0.4',
            'Connection': 'keep-alive',
            'Content-Length': '0',
            'Host': 'www.instagram.com',
            'Origin': 'https://www.instagram.com',
            'Referer': 'https://www.instagram.com/',
            'User-Agent': self.user_agent,
            'X-Instagram-AJAX': '1',
            'X-Requested-With': 'XMLHttpRequest'
        })

        r = self.s.get(self.url)
        self.s.headers.update({'X-CSRFToken': r.cookies['csrftoken']})
        time.sleep(1 + 5 * random.random())
        login = self.s.post(self.url_login,
                            data=login_post,
                            allow_redirects=True)
        self.s.headers.update({'X-CSRFToken': login.cookies['csrftoken']})
        self.csrftoken = login.cookies['csrftoken']

        if login.status_code == 200:
            try:
                r = json.loads(login.text)
                if r['authenticated']:
                    self.login_status = True
                    self.write_log('%s login success!' % self.user_login)
                    return
            except:
                pass
            self.login_status = False
            self.write_log('Login error! Check your login data!')
        else:
            self.write_log('Login error! Connection error! Code: ' + str(login.status_code))

    def logout(self):
        try:
            logout_post = {'csrfmiddlewaretoken': self.csrftoken}
            logout = self.s.post(self.url_logout, data=logout_post)
            self.write_log("Logout success!")
            self.login_status = False
        except Exception as e:
            self.write_log("Logout error!")
            self.write_log(str(e))

    def follow(self, user_id):
        if self.login_status:
            try:
                follow = self.s.post(self.url_follow % user_id)
                if follow.status_code == 200:
                    r = json.loads(follow.text)
                    if r['status'] == 'ok':
                        self.follow_counter += 1
                        return True
            except Exception as e:
                self.write_log("Except on follow!")
                self.write_log(str(e))
        return False

    def unfollow(self, user_id):
        """ Send http request to unfollow """
        if self.login_status:
            try:
                unfollow = self.s.post(self.url_unfollow % user_id)
                if unfollow.status_code == 200:
                    r = json.loads(unfollow.text)
                    if r['status'] == 'ok':
                        self.unfollow_counter += 1
                        return True
            except:
                self.write_log("Exept on unfollow!")
        return False

    def get_next_followers(self, user_id, end_cursor='', amount=20):
        res = []
        if self.login_status:
            try:
                if end_cursor == '':
                    followers = self.s.post(self.url_followers,
                                            data={'q': self.followers_first % user_id,
                                                  'ref': 'relationships::follow_list'})
                else:
                    followers = self.s.post(self.url_followers,
                                            data={'q': self.followers_after % (user_id, end_cursor),
                                                  'ref': 'relationships::follow_list'})
                if followers.status_code == 200:
                    followers = json.loads(followers.text)['followed_by']
                    res += followers['nodes']
                    if followers['page_info']['has_next_page']:
                        end_cursor = followers['page_info']['end_cursor']
                        return res, end_cursor
                    else:
                        return res, ''
                else:
                    self.write_log('Unexpected status code while getting followers')
            except:
                self.write_log('Except while getting followers')
        return None

    def get_followers(self, user_id, limit=-1):
        if limit == -1:
            self.write_log('Getting all followers of %s...' % user_id)
        else:
            self.write_log('Getting first %s followers of %s...' % (limit, user_id))
        res = []
        if self.login_status:
            end_cursor = ''
            while True:
                try:
                    if len(res) == 0:
                        followers = self.s.post(self.url_followers,
                                                data={'q': self.followers_first % user_id,
                                                      'ref': 'relationships::follow_list'})
                    else:
                        followers = self.s.post(self.url_followers,
                                                data={'q': self.followers_after % (user_id, end_cursor),
                                                      'ref': 'relationships::follow_list'})
                    time.sleep(3 + 3 * random.random())
                    if followers.status_code == 200:
                        followers = json.loads(followers.text)['followed_by']
                        res += followers['nodes']
                        if (followers['page_info']['has_next_page'] and
                           (limit < 0 or len(res) < limit)):
                            end_cursor = followers['page_info']['end_cursor']
                        else:
                            break
                    else:
                        self.write_log('Unexpected status code. Stopping...')
                        break
                except:
                    self.write_log('Except while getting followers. Stopping...')
                    break
        return res[:limit]

    def get_user(self, username=None, id=None):
        if username is None and id is None:
            return None
        if self.login_status:
            try:
                if username is not None:
                    user = self.s.get(self.url_user_info % username)
                    if user.status_code == 200:
                        r = json.loads(user.text)['user']
                        return r
                else:
                    user = self.s.post(self.url_followers,
                                       data={'q': self.user_info % id})
                    if user.status_code == 200:
                        r = json.loads(user.text)
                        if 'id' in r:
                            return r
            except:
                self.write_log('Except while getting user info')
        return None

    def write_log(self, log_text):
        print(log_text)