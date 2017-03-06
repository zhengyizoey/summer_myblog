# coding=utf-8
import types, os, re, cgi, sys, time, datetime, functools, mimetypes, threading, logging, traceback, urllib
from db import Dict
from python_utils import converters as utils
try:
    from cStringIO import cStringIO
except ImportError:
    from StringIO import StringIO

'''
实现接口：
1、url，处理函数（func)的映射，func return dict ,经过view渲染成html数据
2、url拦截（权限判断）
3、报错
4、线程下的request，response
5、使用wsgiserver来运行服务器
'''
ctx = threading.local()
_RE_RESPONSE_STATUS = re.compile(r'~\d\d\d(\[\w\]+)?$')
_HEADER_X_POWERED_BY = ('X-Powered-By', 'transwrap/1.0')
_TIMEDELTA_ZERO = datetime.timedelta(0)
_RE_TZ = re.compile('^([\+\-])([0-9]{1,2})\:([0-9]{1,2})$')
_RESPONSE_STATUS = {
# Informational
    100: 'Continue',
    101: 'Switching Protocols',
    102: 'Processing',

    # Successful
    200: 'OK',
    201: 'Created',
    202: 'Accepted',
    203: 'Non-Authoritative Information',
    204: 'No Content',
    205: 'Reset Content',
    206: 'Partial Content',
    207: 'Multi Status',
    226: 'IM Used',

    # Redirection
    300: 'Multiple Choices',
    301: 'Moved Permanently',
    302: 'Found',
    303: 'See Other',
    304: 'Not Modified',
    305: 'Use Proxy',
    307: 'Temporary Redirect',

    # Client Error
    400: 'Bad Request',
    401: 'Unauthorized',
    402: 'Payment Required',
    403: 'Forbidden',
    404: 'Not Found',
    405: 'Method Not Allowed',
    406: 'Not Acceptable',
    407: 'Proxy Authentication Required',
    408: 'Request Timeout',
    409: 'Conflict',
    410: 'Gone',
    411: 'Length Required',
    412: 'Precondition Failed',
    413: 'Request Entity Too Large',
    414: 'Request URI Too Long',
    415: 'Unsupported Media Type',
    416: 'Requested Range Not Satisfiable',
    417: 'Expectation Failed',
    418: "I'm a teapot",
    422: 'Unprocessable Entity',
    423: 'Locked',
    424: 'Failed Dependency',
    426: 'Upgrade Required',

    # Server Error
    500: 'Internal Server Error',
    501: 'Not Implemented',
    502: 'Bad Gateway',
    503: 'Service Unavailable',
    504: 'Gateway Timeout',
    505: 'HTTP Version Not Supported',
    507: 'Insufficient Storage',
    510: 'Not Extended',
}
_RESPONSE_HEADERS = (
    'Accept-Ranges',
    'Age',
    'Allow',
    'Cache-Control',
    'Connection',
    'Content-Encoding',
    'Content-Language',
    'Content-Length',
    'Content-Location',
    'Content-MD5',
    'Content-Disposition',
    'Content-Range',
    'Content-Type',
    'Date',
    'ETag',
    'Expires',
    'Last-Modified',
    'Link',
    'Location',
    'P3P',
    'Pragma',
    'Proxy-Authenticate',
    'Refresh',
    'Retry-After',
    'Server',
    'Set-Cookie',
    'Strict-Transport-Security',
    'Trailer',
    'Transfer-Encoding',
    'Vary',
    'Via',
    'Warning',
    'WWW-Authenticate',
    'X-Frame-Options',
    'X-XSS-Protection',
    'X-Content-Type-Options',
    'X-Forwarded-Proto',
    'X-Powered-By',
    'X-UA-Compatible',)

# UTC('+00:00')
class UTC(datetime.tzinfo):
    def __init__(self, utc):
        utc = str(utc.strip().upper())
        mt = _RE_TZ.match(utc)
        if mt:
            minus = mt.group(1) == '-'
            h = int(mt.group(2))
            m = int(mt.group(3))
            if minus:
                h, m = (-h), (-h)
            self._utcoffset = datetime.timedelta(hours=h, minutes=m)
            self._tzname = 'UTC%s' % utc
        else:
            raise ValueError('bad utc time zone')
    # 表示与标准时区的偏移量
    def utcoffset(self, date_time):
        return self._utcoffset
    # 夏令时
    def dst(self, date_time):
        return _TIMEDELTA_ZERO
    # 所在时区的名字
    def tzname(self, date_time):
        return self._tzname
    def __str__(self):
        return 'UTC timezone info object (%s)' % self._tzname
    __repr__ = __str__


UTC_0 = UTC('+00:00')

# 以下3个类，将状态吗，和状态的说明组装
class _HttpError(Exception):
    # init an httperror with responsed code 404
    def __init__(self, code):
        super(_HttpError,self).__init__()
        self.status = '%d %s' % (code, _RESPONSE_STATUS[code])
        self._headers = None
    # 添加header进_headers，如果没有self._headers,则添加powered by transwrap
    def header(self, name, value):
        if not self._headers:
            self._headers = [_HEADER_X_POWERED_BY]
        self._headers.append((name, value))
    # 读取_headers
    @property
    def headers(self):
        if hasattr(self, '_headers'):
            return self._headers
        return []
    def __str__(self):
        return self.status
    __repr__ = __str__

# e = _RedirectError(302,'http://www.app.com/login')
class _RedirectError(_HttpError):
    def __init__(self, code, location):
        super(_RedirectError, self).__init__(code)
        self.location = location
    def __str__(self):
        return '%s,%s'%(self.status, self.location)
    __repr__ = __str__

class HttpError(object):
    @staticmethod
    def badrequest():
        return _HttpError(400)
    @staticmethod
    def unauthorized():
        return _HttpError(401)
    @staticmethod
    def forbidden():
        return _HttpError(403)
    @staticmethod
    def not_found():
        return _HttpError(404)
    @staticmethod
    def conflict():
        return _HttpError(409)
    @staticmethod
    def internalerror():
        return _HttpError(500)
    @staticmethod
    def redirect(location):
        return _RedirectError(301, location)  # permanent redirect
    @staticmethod
    def found(locaton):                         # e=HttpError.found('http://www.pi.com')
        return _RedirectError(302, locaton)   # temporary redirect
    @staticmethod
    def seeother(location):                    # e=HttpError.seeother('http://www.pi.com/seeother?r=123')
        return _RedirectError(303, location)  # temporary redirect

_RESPONSE_HEADER_DICT = dict(zip(map(lambda x: x.upper(), _RESPONSE_HEADERS), _RESPONSE_HEADERS))

class Request(object):
    # 将wsgi的environ保存到self._environ
    def __init__(self, environ):
        self._environ = environ


    # 处理 cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
    # r = Request({'REQUEST_METHOD':'POST', 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ')})
    # r.get('a') r.get('c')
    # f = r.get('file') f.filename f.file.read()
    def _parse_input(self):
        def _convert(item):
            if isinstance(item,list):
                return [utils.to_unicode(i.value) for i in item]
            if item.filename:
                return MultipartFile(item)
            return utils.to_unicode(item.value)
        fs = cgi.FieldStorage(fp=self._environ['wsgi.input'], environ=self._environ, keep_blank_values=True)
        inputs = dict()
        for key in fs:
            inputs[key] = _convert(fs[key])
        return inputs

    # 返回上面那个函数的inputs
    def _get_raw_input(self):
        if not hasattr(self, '_raw_input'):
            self._raw_input = self._parse_input()
        return self._raw_input

    def __getitem__(self, item):
        r = self._get_raw_input()[item]
        if isinstance(r, list):
            return r[0]
        return r

    # inputs里面的c: 'wsgi.input':StringIO('a=1&b=M%20M&c=ABC&c=XYZ'
    def get(self, key, default=None):
        r = self._get_raw_input().get(key, default)
        if isinstance(r, list):
            return r[0]
        return r

    def gets(self, key):
        r = self._get_raw_input()[key]
        if isinstance(r, list):
            return r[:]
        return r

    # 将**kwargs里的，放入inputs里。。
    # i = r.input(x=123)
    # i.a  i.b  i.x
    def input(self, **kwargs):
        copy = Dict(**kwargs)   # 这个Dict是已经实现d.a调用的dict
        raw = self._get_raw_input()
        for k, v in raw.iteritems():
            copy[k] = v[0] if isinstance(v, list) else v
        return copy

    # r = Request({'REQUEST_METHOD':'POST','wsgi,input':StringIO('<xml><raw/>')})
    def get_body(self):
        fp = self._environ['wsgi.input']
        return fp.read()

    @property
    def remote_addr(self):
        return self._environ.get('REMOTE_ADDR', '0.0.0.0')

    @property
    def document_root(self):
        return self._environ.get('DOCUMENT_ROOT', '')

    @property
    def query_string(self):
        return self._environ.get('QUERY_STRING', '')

    @property
    def environ(self):
        return self._environ

    @property
    def request_method(self):
        return self._environ['REQUEST_METHOD']

    @property
    def path_info(self):
        return urllib.unquote(self._environ.get('PATH_INFO', ''))  #  r = Request({'PATH_INFO':'/test/a%20b.html'})
        # )

    @property
    def host(self):
        return self._environ.get('HTTP_HOST', '')   # r = Request({'HTTP_HOST':'localhost:8080'})

    # 从environ里提取出 HTTP_ 开头的header
    # 将‘HTTP_ACCEPT_ENCODING' => 'ACCEPT-ENCODING'，将这些放进self._headers 并返回
    def _get_headers(self):
        if not hasattr(self, '_headers'):
            hdrs = {}
            for k, v in self._environ.iteritems():
                if k.startswith('HTTP_'):
                    hdrs[k[5:].replace('_', '-').upper()] = v.decode('utf-8')
            self._headers = hdrs
        return self._headers

    @property
    def headers(self):
        return dict(**self._get_headers())

    # 获取指定的header，r.header('User-Agent')
    def header(self, header, default=None):
        return self._get_headers().get(header.upper(), default)

    def _get_cookies(self):
        if not hasattr(self, '_cookies'):
            cookies = {}
            cookie_str = self._environ.get('HTTP_COOKIE')
            if cookie_str:
                for c in cookie_str.split(';'):  # "  'bdn'='hljkgh';'hjl'='jldf' "
                    pos = c.find('=')
                    if pos > 0:
                        cookies[c[:pos].strip()] = utils.unquote(c[pos+1:])
            self._cookies = cookies
        return self._cookies

    @property
    def cookies(self):
        return Dict(**self._get_cookies())

    def cookie(self, name, default=None):
        return self._get_cookies().get(name, default)


class Response(object):
    def __init__(self):
        self._status = '200 ok'
        self._headers = {'CONTENT-TYPE': 'text/html;charset=utf-8'}

    # 删除指定header，r.unset_header('CONTENT-TYPE')
    def unset_header(self, name):
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:   # 如果不是headers那个标准字典里的
            key = name
        if key in self._headers:
            del self._headers[key]

    # r.set_header('CONTENT-TYPE','image/png')
    def set_header(self, name, value):
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        self._headers[key] = utils.to_str(value)

    def header(self, name):
        key = name.upper()
        if key not in _RESPONSE_HEADER_DICT:
            key = name
        return self._headers.get(key)

    # 返回所有header，包括set_cookie也在头部 [( , ),( , )]
    @property
    def headers(self):
        L = [(_RESPONSE_HEADER_DICT.get(k, k), v) for k, v in self._headers.iteritems()]
        if hasattr(self, '_cookies'):
            for v in self._cookies.iteritems():
                L.append(('Set-Cookie', v))
        L.append(_HEADER_X_POWERED_BY)
        return L

    @property
    def content_type(self):
        return self.header('CONTENT-TYPE')

    @content_type.setter
    def content_type(self, value):
        if value:
            self.set_header('CONTENT-TYPE', value)
        else:
            self.unset_header('CONTENT-TYPE')

    @property
    def content_length(self):
        return self.header('CONTENT-LENGTH')

    @content_length.setter
    def content_length(self, value):
        self.set_header('CONTENT-LENGTH', str(value))

    def delete_cookie(self, name):
        self.set_cookie(name, '__deleted__', expires=0)

     #{'company':'company=abc%2Cinc;Max-Age=3600;Path=/;HttpOnly'}
     # http_only:client-side script cannot access cookies with Httponly flag
    def set_cookie(self, name, value, max_age=None, expires=None, path='/', domain=None, secure=False, http_only=True):
        if not hasattr(self, '_cookies'):
            self._cookies = {}
        L = ['%s=%s'%(utils.quote(name), utils.quote(value))]
        if expires is not None:
            if isinstance(expires, (float, int, long)):
                L.append('Expires=%s'%datetime.datetime.fromtimestamp(expires, UTC_0).
                         strftime('%a,%d-%b-%Y %H:%M:%S GMT'))
            if isinstance(expires, (datetime.date, datetime.datetime)):
                L.append('Expires=%s'%expires.astimezone(UTC_0).strftime('%a,%d-%b-%Y %H:%M:%S GMT'))
        elif isinstance(max_age, (int, long)):
            L.append('Max-Age=%d'%max_age)
        L.append('Path=%s'%path)
        if domain:
            L.append('Domain=%s'%domain)
        if secure:
            L.append('Secure')
        if http_only:
            L.append('HttpOnly')
        self._cookies[name] = ';'.join(L)

    def unset_cookie(self, name):
        if hasattr(self, '_cookies'):
            if name in self._cookies:
                del self._cookies[name]

    @property
    def status_code(self):
        return int(self._status[:3])  # r.status_code = 500  _status='500 internal error'

    @property
    def status(self):
        return self._status

    # r.status = 404   或者 '404 err '  或者 u'304 denied' 其他的不行
    @status.setter
    def status(self, value):
        if isinstance(value, (int, long)):
            if 100 <= value <= 999:
                st = _RESPONSE_STATUS.get(value, '')
                if st:
                    self._status = '%d%s'%(value, st)  # 如果value是标准status里的400,value=400 st=not found
                else:
                    self._status = str(value)
            else:
                raise ValueError('bad response code:%d'%value)
        elif isinstance(value, basestring):
            if isinstance(value, unicode):
                value = value.encode('utf-8')
            if _RE_RESPONSE_STATUS.match(value):
                self._status = value
            else:
                raise ValueError('bad response code:%s'%value)
        else:
            raise TypeError('bad type of response code')

# 捕获变量的re
_re_route = re.compile(r'(:[a-zA-Z_]\W*)')  # ':ax' :,字母下划线开头，后面是字母

def get(path):
    '''
    @get('/:id')
    def index(id):
        pass
    '''
    def _decorator(func):
        func.__web_route__ =  path
        func.__web_method__ = 'GET'
        return func
    return _decorator

def post(path):
    def _decorator(func):
        func.__web_route__ = path
        func.__web_method__ = 'POST'
        return func
    return _decorator

# 将路径转换成正则，path=>re，并捕获其中的参数（:变量）
# _build_regex('/path/to/:file')  =>   '~ \\/path \\/to \\/( ?P<file> [~\\/]+ )$
def _build_regex(path):
    re_list = ['^']
    var_list = []
    is_var = False
    for v in _re_route.split(path):     # _re_route 匹配(:字母下划线开头的变量名）:file
        if is_var:
            var_name = v[1:]
            var_list.append(var_name)
            re_list.append(r'(?P<%s>[^\/]+)'%var_name)
        else:
            s = ''
            for ch in v:
                if '0' <= ch <= '9':
                    s += ch
                elif 'A' <= ch <= 'Z':
                    s += ch
                elif 'a' <= ch <= 'z':
                    s += ch
                else:
                    s = s + '\\' + ch     # 每个字母，如果不是上述，就要进行转译成‘\\/'吧
            re_list.append(s)
        is_var = not is_var   # 如果有下一组：v[1]就是那个 :file
    re_list.append('$')
    return ''.join(re_list)


# 读取静态文件的一个生成器
def _static_file_generator(fpath, block_size=8192):
    with open(fpath, 'rb') as f:
        block = f.read(block_size)
        while block:
            yield block
            block = f.read(block_size)

# 动态路由对象，处理get捕获的url 和 func  call:执行func函数
class Route(object):
    def __init__(self, func):
        self.path = func.__web_route__
        self.method = func.__web_method__
        self.is_static = _re_route.search(self.path) is None    # path里面含有变量，没有的话，就是True
        if not self.is_static:
            self.route = re.compile(_build_regex(self.path))    # 有变量的话直接转为正则表达式
        self.func = func

    def match(self, url):
        m = self.route.match(url)
        if m:
            return m.groups()
        return None

    def __call__(self, *args):
        return self.func(*args)

    def __str__(self):
        if self.is_static:
            return 'route(static,%s,path=%s)'%(self.method, self.path)
        return 'route(dynamic,%s,path=%s)'%(self.method, self.path)

    __repr__ = __str__


# 静态路由，和Route相对应   call:返回访问文件的block
class StaticFileRoute(object):
    def __init__(self):
        self.method = 'GET'
        self.is_static = False
        self.route = re.compile('^/stactic/(.+)$')

    def match(self, url):
        if url.startswith('/static/'):
            return (url[1:],)
        return None

    def __call__(self, *args):
        fpath = os.path.join(ctx.application.document_root, args[0])
        if not os.path.isfile(fpath):
            raise HttpError.not_found()
        ftext = os.path.splitext(fpath)[1]    # 'prop.mp3'
        ctx.response.content_type = mimetypes.types_map.get(ftext.lower(), 'application/octet-stream')
        return _static_file_generator(fpath)


# 处理request wsgi.input 里的文件：f = ctx.request['file'] f.filename #test.png  f.file.read()
class MultipartFile(object):
    def __init__(self, storage):
        self.filename = utils.to_unicode(storage.filename)
        self.file = storage.file


# 以下为视图功能，涉及模板引擎和view装饰器的实现

# t = Template('hello.html',title='hello',copyriget='@2010')
# t.model['title']
class Template(object):
    def __init__(self, template_name, **kwargs):
        self.template_name = template_name
        self.model = dict(**kwargs)


class TemplateEngine(object):
    def __call__(self, path, model):
        return '<!--override this method to render template--->'


# template_path = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),'test')
# engine = Jinja2TemplateEngine(template_path)
# engine.add_filter('datetime', lamda dt: dt.strftime(’%Y-%m....))
# engine('test.html', dict(name='zhengyi', post_at=time.time())
# => <html>....</html>
class Jinja2TemplateEngine(TemplateEngine):
    def __init__(self, template_dir, **kwargs):
        from jinja2 import Environment, FileSystemLoader
        if 'autoescape' not in kwargs:
            kwargs['autoescape'] = True
        self._env = Environment(loader=FileSystemLoader(template_dir))

    def add_filter(self, name, fn_filter):
        self._env.filters[name] = fn_filter

    def __call__(self, path, model):
        return self._env.get_template(path).render(**model).encode('utf-8')

def _debug():
    pass

# 处理异常，显示一个异常页面
def _default_error_handler(e, start_response, is_debug):
    if isinstance(e, HttpError):
        logging.info('httperror:%s'%e.status)
        headers = e.headers[:]
        headers.append(('Content-Type', 'Text/html'))
        start_response(e.status, headers)
    logging.exception('Exception:')
    start_response('500 internal server error ',[('Content-Type', 'Text/html'), _HEADER_X_POWERED_BY])
    if is_debug:
        return _debug()
    return ('<html><body><h1>500 internal server error</h1><h3>%s</h3></body></html>'%str(e))

# 装饰器通过Template类 将 path 和 func的dict 关联到一个Template对象上
def view(path):
    def _decorator(func):
        @functools.wraps(func)
        def _wrapper(*args, **kwargs):
            r = func(*args, **kwargs)
            if isinstance(r, dict):
                logging.info('return Template')
                return Template(path, **r)
            raise ValueError('except return a dict when using @view() decorator')
        return _wrapper
    return _decorator

# 以下实现URL拦截器

_RE_INTERCEPTOR_STARTS_WITH = re.compile(r'^([^\*\?]+)\*?$')  # ([*?]+)*?
_RE_INTERCEPTOR_ENDS_WITH = re.compile(r'^\*([^\*\?]+)$')       # *([*?]+)


# 传入需要匹配的url，返回一个函数，该函数接收一个字符串，检测该字符串是否符合pattern
def _build_pattern_fn(pattern):
    m = _RE_INTERCEPTOR_STARTS_WITH.match(pattern)
    if m:
        return lambda p: p.startswith(m.group(1))
    m = _RE_INTERCEPTOR_ENDS_WITH.match(pattern)
    if m:
        return lambda p:p.endswith(m.group(1))
    raise ValueError('Invalid pattern definition in interceptor')


# @interceptor('/admin/')
# def check_admin_url(next):
#       return next() if user.isadmin() else raise seeother('/signin'/)
def interceptor(pattern='/'):
    def _decorator(func):
        func.__interceptor__ = _build_pattern_fn(pattern)   # func.__interceptor__(ctx.request.path_info) 定义的和传进来的
        return func
    return _decorator


# 拦截器接受一个next函数，这样，拦截器可以决定调用next（）继续处理请求还是直接返回
def _build_interceptor_fn(func, next):
    def _wrapper():
        if func.__interceptor__(ctx.request.path_info):
            return func(next)
        else:
            return next()
    return _wrapper


def _build_interceptor_chain(last_fn, *interceptors):
    L = list(interceptors)
    L.reverse()
    fn = last_fn
    for f in L:
        fn = _build_interceptor_fn(f, fn)
    return fn


# m = _load_module('xml')  m.__name__  => 'xml'
def _load_module(module_name):
    last_dot = module_name.refind('.')
    if last_dot == (-1):
        return __import__(module_name, globals=globals(), locals=locals())
    from_module = module_name[:last_dot]
    import_module = module_name[last_dot+1:]
    m = __import__(name=from_module,    # m.__name__ == imported_module.__name__
                   globals=globals(), locals=locals(), fromlist=[import_module])
    return getattr(m, import_module)


class WSGIApplication(object):
    def __init__(self, document_root=None, **kwargs):
        self._running = False
        self._document_root = document_root
        self._interceptors = []
        self._template_engine = None
        self._get_static = {}
        self._post_static = {}
        self._get_dynamic = []
        self._post_dynamic = []

    def _check_not_running(self):
        if self._running:
            raise RuntimeError('cannot modify WSGIApplication when running')

    @property
    def template_engine(self):
        return self._template_engine

    @template_engine.setter
    def template_engine(self, engine):
        self._check_not_running()
        self._template_engine = engine

     # 将urls文件加进来，取出里面的fn,传递给add_url
    def add_module(self, mod):
        self._check_not_running()
        m = mod if type(mod) == types.ModuleType else _load_module(mod)
        logging.info('add modele :%s'%m.__name__)
        for name in dir(m):
            fn = getattr(m, name)
            if callable(fn) and hasattr(fn, '__web_route__') and hasattr(fn, '__web_method__'):
                self.add_url(fn)

     # 将route=Route(fn) ,根据属性static，get,分发进self._get_static
    def add_url(self, fn):
        self._check_not_running()
        route = Route(fn)
        if route.is_static:
            if route.method == 'GET':
                self._get_static[route.path] = route   # route.path = self.path = func.__web_route__
            if route.method == 'POST':
                self._post_static[route.path] = route
        else:
            if route.method == 'GET':
                self._get_dynamic.append(route)
            if route.method == 'POST':
                self._post_dynamic.append(route)
        logging.info('add route:%s'%str(route))

     # 将拦截器func添加进self._interceptors
    def add_interceptor(self, func):
        self._check_not_running()
        self._interceptors.append(func)
        logging.info('add interceptor:%s'%str(func))

    # 启动Python自带的wsgi server
    def run(self, port=9000, host='127.0.0.1'):
        from wsgiref.simple_server import make_server
        logging.info('application (%s) will start at %s:%s...'%(self._document_root, host, port))
        server = make_server(host, port, self.get_wsgi_application(debug=True))
        server.serve_forever()

    def get_wsgi_application(self, debug=False):
        self._check_not_running()
        if debug:
            self._get_dynamic.append(StaticFileRoute())   #TODO:wht dynamic add staticroute???
        self._running = True

        _application = Dict(document_root=self._document_root)  # _application={'document_root':_document_root}

        # 根据请求的path,method,从字典里找出相应的处理函数，执行fn()
        def fn_route():
            request_method = ctx.request.request_method
            path_info = ctx.request.path_info    # 这个事请求里面method和info,从相应字典里取出相应的处理函数
            if request_method == 'GET':
                fn = self._get_static.get(path_info, None)
                if fn:
                    return fn()
                for fn in self._get_dynamic:
                    args = fn.match(path_info)   # TODO 大写加粗，这就是那个提取url里参数的那个！
                    if args:
                        return fn(*args)
                raise HttpError.not_found()
            if request_method == 'POST':
                fn = self._post_static.get(path_info, None)
                if fn:
                    return fn
                for fn in self._post_dynamic:
                    args = fn.match(path_info)   # 从列表里找到符合url的fn,并取出参数，传递给它
                    if args:
                        return fn(*args)
                raise HttpError.not_found()
            raise HttpError.badrequest()

        # 执行顺序：fi1_before,fi2_before,fn,fi2_after,fi1_after
        fn_exec = _build_interceptor_chain(fn_route, *self._interceptors)

        def wsgi(env, start_response):
            ctx.application = _application   # application 里面有document_root属性
            ctx.request = Request(env)
            response = ctx.response = Response()
            try:
                r = fn_exec()
                if isinstance(r, Template):
                    r = self._template_engine(r.template_name, r.model)
                if isinstance(r, unicode):
                    r = r.encode('utf-8')
                if r is None:
                    r = []
                start_response(response.status, response.headers)
                return r
            except _RedirectError, e:
                response.set_header('Location', e.location)
                start_response(e.status, response.headers)
                return []
            except _HttpError, e:
                start_response(e.status, response.headers)
                return ['<html><body><h1>', e.status, '</h1></body></html>']
            except Exception, e:
                logging.exception(e)
                if not debug:   # 生产模式下，只返回错误码
                    start_response('500 internal server error', [])
                    return ['<html><body><h1>500 internal server error</h1></body></html>']
                exc_type, exc_value, exc_traceback = sys.exc_info()     # 调试模式下返回详细信息到页面
                fp = StringIO()
                traceback.print_exception(exc_type, exc_value, exc_traceback, file=fp)
                stacks = fp.getvalue()
                fp.close()
                start_response('500 internal server error', [])
                return [' <html><body><h1>500 internal server error</h1>',
                        stacks.replace('<', '&lt').replace('>', '&gt'),'</body></html>']
            finally:
                del ctx.application
                del ctx.request
                del ctx.response
        return wsgi

if __name__ == '__main__':
    sys.path.append('.')
    import doctest
    doctest.testmod()



















