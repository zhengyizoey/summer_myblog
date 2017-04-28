# coding=utf-8
import re, hashlib, time, datetime, os
from models import User, Blog, Comment, Category,engine, session
from transwrap.web import get, post, view, ctx, HttpError, interceptor
from api import api, APIError
from config import configs
from utils import parse_cookie, make_signed_cookie, translate_time, Paginator

_COOKIE_NAME = configs.cookies.cookieawesome


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
        session.query(Blog).filter(Blog.id == blogid).delete()
        session.commit()
        return blog.as_dict()
    raise APIError('not admin')


@api
@get('/api/:blogid/comment')
def getcomments(blogid):
    comments = session.query(Comment).filter(Comment.blog == blogid).all()
    return translate_time([comment.as_dict() for comment in comments])


@api
@post('/api/:blogid/comment')
def postcomments(blogid):
    user = ctx.request.user
    content = ctx.request.input().newcomment
    if user and content.strip():
        comment = Comment(blog=blogid, user=user.id, content=content)
        session.add(comment)
        session.commit()
        return translate_time(comment.as_dict())
    raise APIError('not user or blank content')


@view('blog.html')
@get('/blog/:blogid')
def blog(blogid):
    blog = session.query(Blog).filter(Blog.id == blogid).first()
    return {'blog': blog}


@view('index.html')
@get('/')
def index():
    return {}


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
        users = session.query(User).all()
        p = Paginator(page=int(page), object_=users, count=int(count or 10))
        return dict(users=translate_time([user.as_dict() for user in  p.object_list]),
                    pagenums=p.pagenums)
    return dict()


@api
@get('/api/getblog')
def getblog():
    page = ctx.request.query_string.get('page')    # 此处修改了框架的query_string:返回{'a'='1','b'='balbal'}
    count = ctx.request.query_string.get('count')
    cat = ctx.request.query_string.get('cat')
    if page:
        if cat == 'all' or cat is None:
            blogs = session.query(Blog).order_by(Blog.created_at.desc()).all()
        else:
            blogs = session.query(Blog).filter(Blog.category == cat).order_by(Blog.created_at.desc()).all()
        p = Paginator(int(page), blogs, count=int(count or 6))
        categories = session.query(Category).all()
        catobject = session.query(Category).filter(Category.id == cat).first()
        return dict(blogs=translate_time([blog.as_dict() for blog in p.object_list]),
                    hasnext=p.hasnext,
                    hasprevious=p.hasprevious,
                    pagenums=p.pagenums,
                    currentcat=catobject.id if catobject else None,
                    categories=[cat.as_dict() for cat in categories])
    return dict()


@api
@get('/api/blogs')
def api_get_blogs():
    blogs = session.query(Blog).all()
    return dict(blogs=translate_time(blogs))

_RE_MD5 = re.compile(r'^[0-9a-z]{32}$')
_RE_EMAIL = re.compile(r'^[0-9A-Za-z\.\-\_]+\@[a-z0-9A-Z\-\_]+[\.0-9A-Za-z\-\_]{1,4}$')


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
        dirname =  os.path.join(os.path.dirname(os.path.abspath(__file__)), 'static', 'avatar')
        m = hashlib.md5()
        m.update(email)
        with open(dirname + '\\' + m.hexdigest() + '.jpg', 'wb') as f:
            f.write(file.file.read())
        user = User(name=name, email=email, password=password, image=m.hexdigest())
    else:
        user = User(name=name, email=email, password=password)
    session.add(user)
    session.commit()
    cookie = make_signed_cookie(user.id, user.password, None)
    ctx.response.set_cookie(_COOKIE_NAME, cookie.encode('utf-8'))  # 恩，框架只对body进行编码，头部转码
    return user.as_dict()


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
        user = session.query(User).filter(User.email == name).first()
    else:
        user = session.query(User).filter(User.name == name).first()
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
    catgories = session.query(Category).all()
    if blogid:
        blog = session.query(Blog).filter(Blog.id == blogid).first()
        return {'blog': blog, 'categories': catgories}
    defaultcat = session.query(Category).first()
    return {'currentcat': defaultcat, 'categories': catgories}


@api
@post('/api/create_blog')   # 根据有无blogid，选择新建或者update
def create_blog():
    if not ctx.request.user:
        raise HttpError.seeother('/login')
    if not ctx.request.manager:
        raise APIError('not admin')
    i = ctx.request.input(name='', summary='', content='', blogid='', currentcat='')
    name = i.name
    summary = i.summary
    content = i.content
    currentcat = i.currentcat
    if not name:
        raise APIError('name cant be none')
    if not summary:
        raise APIError('summary cant be none')
    if not content:
        raise APIError('content cant be none')
    if i.blogid:
        # blog = select_one('select * from blogs where id=?', i.blogid)
        # blog_to_update = Blog(id=blog.id, name=name, summary=summary, content=content)
        # blog_to_update.update()
        session.query(Blog).filter(Blog.id == i.blogid).\
            update({'name': name, 'summary': summary, 'content': content, 'category':currentcat})
        session.commit()
        # return translate_time(select_one('select * from blogs where id=?', i.blogid))
        return translate_time(session.query(Blog).filter(Blog.id == i.blogid).first())
    # blog = Blog(name=name, summary=summary, content=content,user_id=ctx.request.user.id, user_name=ctx.request.user.name )
    # blog.insert()
    blog = Blog(name=name, summary=summary, content=content, user=ctx.request.user.id, category=currentcat)
    session.add(blog)
    session.commit()
    return blog.as_dict()
