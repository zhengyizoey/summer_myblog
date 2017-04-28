# coding=utf8
import datetime, time, hashlib
from config import configs
from models import User, session


# f:time.time()
def f2time(f):
    d = int(time.time() - f)
    if d < 60:
        return u'刚刚'
    if d < 60*60:
        return u'%s分钟前'% (d/60)
    if d < 60*60*24:
        return u'%s小时前'%(d/3600)
    dt = datetime.datetime.fromtimestamp(f)
    return u'%s年%s月%s日'%(dt.year, dt.month, dt.day)


def translate_time(objectlist):
    if isinstance(objectlist, list):
        for object_ in objectlist:
            # object_.created_at = f2time(object_.created_at)
            object_['created_at'] = f2time(object_['created_at'])

    else:
        # objectlist.created_at = f2time(objectlist.created_at)
        objectlist['created_at'] = f2time(objectlist['created_at'])
    return objectlist


# _COOKIE_NAME = 'awesession'
_COOKIE_NAME = configs.cookies.cookieawesome
_COOKIE_KEY = configs.session.secret


# cookie: id-expires-md5(id-password-KEY)
def make_signed_cookie(id, password, max_age):
    expires = str(int(time.time()) + (max_age or 86400))  # 一天+现在时间=过期的时间点
    L = [id, expires, hashlib.md5('%s-%s-%s-%s' % (id, password, expires, _COOKIE_KEY)).hexdigest()]
    return '-'.join(L)


def parse_cookie(cookie):
    try:
        L = cookie.split('-')
        id_, expires, md5 = L
        if int(expires) > time.time():
            #user = User.get(id_)
            user = session.query(User).filter(User.id == id_).first()
            if md5 == hashlib.md5('%s-%s-%s-%s' % (id_, user.password, expires, _COOKIE_KEY)).hexdigest():
                return user
    except Exception as e:
        return None


class Paginator(object):
    def __init__(self, page, object_, count): # 传入页码，被分页的list，每页条数
        self.page = page
        self.object_ = object_
        self.count = count
        self.pagenums = 0 if not object_ else self.pagenums()
        self.hasprevious = self.page > 1
        self.hasnext = self.page < self.pagenums
        self.object_list = self.object_list() if object_ else []

    def pagenums(self):
        return len(self.object_)/self.count + (1 if len(self.object_)%self.count else 0)

    def object_list(self):
        if self.page == self.pagenums:
            return self.object_[(self.page-1)*self.count:]
        return self.object_[(self.page-1)*self.count:self.page*self.count]
