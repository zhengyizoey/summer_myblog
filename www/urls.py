# coding=utf-8
import re, hashlib, time, datetime, os
from models import User, Blog, Comment
from transwrap.web import get, post, view, ctx, HttpError, interceptor
from transwrap.db import select, select_one, insert, update
from api import api, APIError
from config import configs


@view('admin.html')
@get('/admin')
def get_admin():
    if ctx.request.user and ctx.request.manager:
        return dict()
    raise HttpError.seeother('/login')

@api
@post('/api/admin/deleteblog')
def deleteblog():
    if ctx.request.user and ctx.request.manager:
        i = ctx.request.input()
        blogid = i.blogid
        blog = select_one('select * from blogs where id=?', blogid)
        update('delete from blogs where id=?', blogid)
        return blog
    raise APIError('not admin')


# f:time.time()
def f2time(f):
    d = int(time.time() - f)
    if d < 60:
        return u'刚刚'
    if d < 60*60:
        return u'%s分钟前'% (d/60)
    if d < 60*60*30:
        return u'%s天前'%(d/3600)
    dt = datetime.datetime.fromtimestamp(f)
    return u'%s年%s月%s日'%(dt.year, dt.month, dt.day)


def translate_time(objectlist):
    if isinstance(objectlist, list):
        for object_ in objectlist:
            object_.created_at = f2time(object_.created_at)
    else:
        objectlist.created_at = f2time(objectlist.created_at)
    return objectlist


@api
@get('/api/:blogid/comment')
def getcomments(blogid):
    comments = select('select * from comments where blog_id=? order by created_at desc', blogid)
    return translate_time(comments)

@api
@post('/api/:blogid/comment')
def postcomments(blogid):
    user = ctx.request.user
    content = ctx.request.input().newcomment
    if user and content.strip():
        comment = Comment(blog_id=blogid, user_id=user.id, user_name=user.name, user_image=user.image, content=content)
        comment.insert()
        return translate_time(comment)
    raise APIError('not user or blank content')


@view('blog.html')
@get('/blog/:blogid')
def blog(blogid):
    blog = select_one('select * from blogs where id=?',blogid)
    return {'blog': blog}


@api
@post('/test')
def test_():
    i = ctx.request.input()
    value = i.inputname
    print '接收到的值：',value
    blogs = Blog.find_all()
    for blog in blogs:
        blog.created_at = f2time(blog.created_at)
    return translate_time(blogs)


@view('test.html')
@get('/test')
def test():
    return {}


class Paginator(object):
    def __init__(self, page, object_, count): # 传入页码，被分页的list，每页条数
        self.page = page
        self.object_ = object_
        self.count = count
        self.pagenums = self.pagenums()
        self.hasprevious = self.page > 1
        self.hasnext = self.page < self.pagenums
        self.object_list = self.object_list()

    def pagenums(self):
        return len(self.object_)/self.count + (1 if len(self.object_)%self.count else 0)

    def object_list(self):
        if self.page == self.pagenums:
            return self.object_[(self.page-1)*self.count:]
        return self.object_[(self.page-1)*self.count:self.page*self.count]


@view('index.html')
@get('/')
def index():
    return dict()


@view('users.html')
@get('/admin/users')
def get_users():
    return dict()


@api
@get('/api/users')
def api_get_users():
    page = ctx.request.query_string.get('page')
    count = ctx.request.query_string.get('count')
    if page:
        users = User.find_all()
        p = Paginator(page=int(page), object_=users, count=int(count or 10))
        return dict(users=[ {'name':user.name,'email':user.email,'admin':user.admin,'created_at':user.created_at}\
                            for user in translate_time(p.object_list)],
                    pagenums=p.pagenums)
    return dict()


@api
@get('/api/getblog')
def getblog():
    page = ctx.request.query_string.get('page')    # 此处修改了框架的query_string:返回{'a'='1','b'='balbal'}
    count = ctx.request.query_string.get('count')
    if page:
        blogs = Blog.find_all()
        p = Paginator(int(page), blogs, count=int(count or 10))
        return dict(blogs=translate_time(p.object_list),
                    hasnext=p.hasnext,
                    hasprevious=p.hasprevious,
                    pagenums=p.pagenums)
    return dict()


@api
@get('/api/blogs')
def api_get_blogs():
    blogs = Blog.find_all()
    return dict(blogs=translate_time(blogs))

_RE_MD5 = re.compile(r'^[0-9a-z]{32}$')
_RE_EMAIL = re.compile(r'^[0-9A-Za-z\.\-\_]+\@[a-z0-9A-Z\-\_]+[\.0-9A-Za-z\-\_]{1,4}$')

_COOKIE_NAME = 'awesession'
_COOKIE_KEY = configs.session.secret


# cookie: id-expires-md5(id-password-KEY)
def make_signed_cookie(id, password, max_age):
    expires = str(int(time.time()) + (max_age or 86400))  # 一天+现在时间=过期的时间点
    L = [id, expires, hashlib.md5('%s-%s-%s-%s' % (id, password, expires, _COOKIE_KEY)).hexdigest()]
    return '-'.join(L)


@api
@post('/api/users')
def register_user():
    i = ctx.request.input(name='', email='', password='')
    name = i.name.strip()
    email = i.email.strip()
    password = i.password
    if not name:
        raise APIError('name')
    if not email or not _RE_EMAIL.match(email):
        raise APIError('email')
    if not password or not _RE_MD5.match(password):
        raise APIError('password')
    file = i.avatar
    if file:
        #image = file.filename.encode('utf-8')
        dirname =  os.path.join(os.path.dirname(os.path.abspath(__file__)),'static', 'avatar')
        m = hashlib.md5()
        m.update(email)
        with open(dirname + '\\' + m.hexdigest() + '.jpg', 'wb') as f:
            f.write(file.file.read())
        user = User(name=name, email=email, password=password, image=m.hexdigest())
    else:
        user = User(name=name, email=email, password=password)
    user.insert()
    cookie = make_signed_cookie(user.id, user.password, None)
    ctx.response.set_cookie(_COOKIE_NAME, cookie)
    return user


@view('register.html')
@get('/register')
def register():
    return dict()


@view('login.html')
@get('/login')
def log_in():
    return dict()


@view('login.html')
@post('/login')
def login():
    i = ctx.request.input()
    name = i.name.strip()
    password = i.password
    if not name:
        return {'error': u'请填写邮箱或用户名'}
    if _RE_EMAIL.match(name):
        user = select_one('select * from users where email=?', name)
    else:
        user = select_one('select * from users where name=?', name)
    if user:
        if hashlib.md5(password).hexdigest() != user.password:
            return {'error': u'密码错误'}
        max_age = 3600 * 7 * 24
        cookie = make_signed_cookie(user.id, user.password, max_age)
        ctx.response.set_cookie(_COOKIE_NAME, cookie.encode('utf-8'), max_age=max_age)
        raise HttpError.seeother('/')
    return {'error': u'此用户名或邮箱没有注册'}


@interceptor('/')   # 拦截，检验cookie，将是否user或admin挂在request上
def identify_user(next):
    user = None
    cookie = ctx.request.cookies.get(_COOKIE_NAME)
    if cookie:
        user = parse_cookie(cookie)
    ctx.request.user = user
    if user:
        ctx.request.manager = True if user.admin else None
    return next()


def parse_cookie(cookie):
    try:
        L = cookie.split('-')
        id_, expires, md5 = L
        if int(expires) > time.time():
            user = User.get(id_)
            if md5 == hashlib.md5('%s-%s-%s-%s' % (id_, user.password, expires, _COOKIE_KEY)).hexdigest():
                return user
    except Exception as e:
        return None


@get('/logout')
def logout():
    if ctx.request.user:
        # ctx.response.delete_cookie(_COOKIE_NAME)  # 失效
        ctx.response.set_cookie(_COOKIE_NAME, '')
    raise HttpError.seeother('/login')


@view('create_blog.html')
@get('/create_blog')    # 如果get请求里带有blogid，模板渲染blog
def get_create_blog():
    if not ctx.request.user:
        raise HttpError.seeother('/login')
    if not ctx.request.manager:
        raise HttpError.seeother('/')
    blogid = ctx.request.query_string.get('blogid')
    if blogid:
        return {'blog': select_one('select * from blogs where id=?', blogid)}
    return dict()


@api
@post('/api/create_blog')   # 根据有无blogid，选择新建或者update
def create_blog():
    if not ctx.request.user:
        raise HttpError.seeother('/login')
    if not ctx.request.manager:
        raise APIError('not admin')
    i = ctx.request.input(name='', summary='', content='', blogid='')
    name = i.name
    summary = i.summary
    content = i.content
    if not name :
        raise APIError('name cant be none')
    if not summary:
        raise APIError('summary cant be none')
    if  not content:
        raise APIError('content cant be none')
    if i.blogid:
        #blog = select_one('select * from blogs where id=?', i.blogid)
        #blog = Blog(user_id=i.blogid, name=name, summary=summary, content=content)
        #update('update users set name=? summary=? content=? where id=?', name, summary, content, i.blogid)
        blog = select_one('select * from blogs where id=?', i.blogid)
        blog_to_update = Blog(id=blog.id, name=name, summary=summary, content=content)
        blog_to_update.update()
        return translate_time(select_one('select * from blogs where id=?', i.blogid))
    blog = Blog(name=name, summary=summary, content=content,user_id=ctx.request.user.id, user_name=ctx.request.user.name )
    blog.insert()
    return translate_time(blog)


@view('test1.html')
@get('/test')
def get_testpage():
    return dict()


@api
@post('/test')
def post_testpage():
    blogs = Blog.find_all()
    return translate_time(blogs)